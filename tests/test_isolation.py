"""Isolation: what the boundary must structurally prevent.

These tests are the evidence behind the project's central claim. If they pass,
the hidden acceptance tests, reference solutions, results database, harness
source, sibling attempts and host home directory were not merely absent from
the prompt -- an evaluated agent could not reach them.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from benchmark import config
from benchmark.adapters import CONTROL_ADAPTERS, IsolationCanaryAdapter, get_adapter
from benchmark.isolation import (
    NETWORK_DENIED,
    DockerBackend,
    IsolationUnavailable,
    NoIsolation,
    SessionSpec,
    available_backends,
    get_backend,
    probe_all,
    select_backend,
)
from benchmark.isolation.seatbelt import build_profile
from benchmark.runner import clear_baseline_cache, run_attempt
from benchmark.sandbox import SandboxNotIsolated, create_sandbox
from benchmark.tasks import load_registry
from tests.helpers import TempDirTestCase


def publishable_backend():
    """The strongest backend that can actually enforce a boundary here."""
    for report in probe_all():
        if report.active and report.publishable:
            return get_backend(report.backend)
    return None


class BackendSelectionTest(unittest.TestCase):
    def test_auto_never_selects_no_isolation(self):
        """Falling back to cwd-only 'isolation' silently is the failure mode."""
        try:
            backend = select_backend("auto")
        except IsolationUnavailable:
            return  # refusing outright is the other acceptable answer
        self.assertNotEqual(backend.name, NoIsolation.name)
        self.assertTrue(backend.probe().active)

    def test_no_isolation_must_be_requested_by_name(self):
        backend = select_backend("none")
        self.assertEqual(backend.name, "none")

    def test_no_isolation_is_never_publishable(self):
        report = NoIsolation().probe()
        self.assertFalse(report.active)
        self.assertFalse(report.publishable)
        self.assertIn("NON-PUBLISHABLE", report.detail)

    def test_unavailable_backend_raises_rather_than_degrading(self):
        backend = DockerBackend(binary="definitely-not-docker-xyz")
        self.assertFalse(backend.probe().active)
        with self.assertRaises(IsolationUnavailable):
            backend.session(SessionSpec(workspace=Path.cwd()))

    def test_docker_probe_is_honest_without_a_daemon(self):
        report = DockerBackend().probe()
        if not report.active:
            self.assertFalse(report.publishable)
            self.assertTrue(report.unavailable_reason)

    def test_every_backend_reports_a_network_policy(self):
        for report in probe_all():
            with self.subTest(backend=report.backend):
                self.assertTrue(report.network_policy)

    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(KeyError):
            get_backend("nonsense")

    def test_auto_is_offered_on_the_command_line(self):
        self.assertIn("auto", available_backends())


class SeatbeltProfileTest(unittest.TestCase):
    """The generated policy must be deny-by-default and minimal."""

    def setUp(self):
        self.profile = build_profile(writable=[Path("/private/tmp/ws")], allow_network=False)

    def test_denies_by_default(self):
        self.assertIn("(deny default)", self.profile)

    def test_network_is_denied_unless_requested(self):
        self.assertNotIn("(allow network*)", self.profile)
        self.assertIn("(allow network*)", build_profile(writable=[Path("/private/tmp/ws")], allow_network=True))

    def test_writable_set_is_limited_to_the_given_paths(self):
        write_block = self.profile.split("(allow file-read* file-write*")[1]
        self.assertIn("/private/tmp/ws", write_block)
        for forbidden in (str(Path.home()), str(config.REPO_ROOT)):
            self.assertNotIn(forbidden, write_block)

    def test_home_and_repo_are_not_readable(self):
        self.assertNotIn(str(config.REPO_ROOT), self.profile)
        self.assertNotIn(str(Path.home()) + '"', self.profile)

    def test_metadata_allowance_is_scoped_to_the_system_tree(self):
        """stat is granted for the interpreter's own startup, nothing wider."""
        self.assertIn('(allow file-read-metadata (literal "/") (subpath "/usr"))', self.profile)


class SandboxBoundaryTest(TempDirTestCase):
    def test_exec_without_a_session_is_refused(self):
        """No silent fallback to an unconfined subprocess."""
        task = self.make_task()
        with create_sandbox(task, root=self.tmp / "sb") as sandbox:
            with self.assertRaises(SandboxNotIsolated):
                sandbox.exec(["python3", "-c", "pass"], timeout_sec=10)

    def test_private_root_contains_only_the_attempt(self):
        task = self.make_task()
        with create_sandbox(task, root=self.tmp / "sb") as sandbox:
            children = sorted(path.name for path in sandbox.root.iterdir())
            self.assertEqual(children, ["home", "tmp", "workspace"])

    def test_sibling_attempts_have_separate_private_roots(self):
        task = self.make_task()
        with create_sandbox(task, root=self.tmp / "sb") as first:
            with create_sandbox(task, root=self.tmp / "sb") as second:
                self.assertNotEqual(first.root, second.root)

    def test_hidden_tests_are_absent_from_the_workspace(self):
        """The overlay is applied by the evaluator, after the agent has exited."""
        from tests.helpers import HIDDEN_TEST

        task = self.make_task(task_id="hidden-demo", hidden_test=HIDDEN_TEST)
        with create_sandbox(task, root=self.tmp / "sb") as sandbox:
            present = [p.name for p in sandbox.path.rglob("*.py")]
            self.assertNotIn("test_hidden.py", present)

    def test_solution_is_absent_from_the_workspace(self):
        task = self.make_task()
        with create_sandbox(task, root=self.tmp / "sb") as sandbox:
            self.assertFalse((sandbox.path / "solution").exists())
            contents = {p.read_text() for p in sandbox.path.rglob("*.py") if p.is_file()}
            self.assertNotIn("def answer():\n    return 42\n", contents)


@unittest.skipIf(publishable_backend() is None, "no publishable isolation backend on this machine")
class AdversarialCanaryTest(unittest.TestCase):
    """A hostile agent attacks the boundary; every probe must fail."""

    @classmethod
    def setUpClass(cls):
        clear_baseline_cache()
        cls.backend = publishable_backend()
        cls.task = load_registry()["py-005-report-filter-crash"]
        cls.readme = config.REPO_ROOT / "README.md"
        cls.readme_before = cls.readme.read_bytes()
        # A real sibling attempt, so "cannot see another attempt" is tested
        # against something that genuinely exists.
        root = config.sandbox_root()
        root.mkdir(parents=True, exist_ok=True)
        # Named per process: the suite shares one sandbox root, and a fixed name
        # would collide between concurrent runs.
        cls.sibling = root / f"__sibling_attempt_{os.getpid()}__"
        (cls.sibling / "workspace").mkdir(parents=True, exist_ok=True)
        (cls.sibling / "workspace" / "leak.txt").write_text("SIBLING-ATTEMPT-CANARY\n")

        cls.result = run_attempt(
            cls.task, IsolationCanaryAdapter(), backend=cls.backend
        )
        cls.findings = cls.result.agent.metadata.get("findings", {})

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls.sibling, ignore_errors=True)

    def _assert_denied(self, probe):
        self.assertIn(probe, self.findings, f"probe {probe} did not run")
        finding = self.findings[probe]
        self.assertFalse(
            finding["reached"],
            f"ISOLATION BREACH: {probe} reached {finding['detail']}",
        )

    def test_the_probe_actually_ran(self):
        self.assertTrue(self.findings, "the canary produced no findings")
        self.assertTrue(self.result.isolation.active)

    def test_parent_traversal_is_denied(self):
        self._assert_denied("traversal_parent")

    def test_grandparent_traversal_is_denied(self):
        self._assert_denied("traversal_grandparent")

    def test_filesystem_root_is_denied(self):
        self._assert_denied("traversal_root")

    def test_host_home_listing_is_denied(self):
        self._assert_denied("host_home_listing")

    def test_host_home_file_is_denied(self):
        self._assert_denied("host_home_file")

    def test_hidden_acceptance_tests_are_denied(self):
        self._assert_denied("hidden_tests_dir")
        self._assert_denied("hidden_tests_file")

    def test_existence_of_hidden_tests_cannot_even_be_probed(self):
        self._assert_denied("stat_acceptance")

    def test_reference_solution_is_denied(self):
        self._assert_denied("solution_dir")
        self._assert_denied("solution_file")

    def test_benchmark_source_is_denied(self):
        self._assert_denied("benchmark_source")
        self._assert_denied("benchmark_repo_listing")

    def test_task_definition_is_denied(self):
        self._assert_denied("task_definition")

    def test_results_database_is_denied(self):
        self._assert_denied("results_db")

    def test_sibling_attempt_is_denied(self):
        self._assert_denied("sibling_attempts")
        self._assert_denied("other_attempt")

    def test_task_registry_cannot_be_searched(self):
        self._assert_denied("glob_for_acceptance")

    def test_host_file_mutation_is_denied(self):
        self._assert_denied("mutate_host_file")

    def test_host_file_is_byte_identical_afterwards(self):
        self.assertEqual(self.readme.read_bytes(), self.readme_before)

    def test_network_egress_is_denied_when_not_requested(self):
        self._assert_denied("network_egress")

    def test_nothing_at_all_was_reached(self):
        reached = self.result.agent.metadata.get("reached", [])
        self.assertEqual(reached, [], f"ISOLATION BREACH: {reached}")


@unittest.skipIf(publishable_backend() is None, "no publishable isolation backend on this machine")
class EvaluationIsolationTest(unittest.TestCase):
    def test_evaluation_runs_with_the_network_denied(self):
        """A verdict that can depend on the network is not deterministic."""
        backend = publishable_backend()
        with backend.session(SessionSpec(workspace=Path(os.getcwd()), network=False)) as session:
            self.assertEqual(session.report.network_policy, NETWORK_DENIED)

    def test_attempts_record_the_boundary_they_ran_under(self):
        clear_baseline_cache()
        task = load_registry()["py-001-interval-merge"]
        result = run_attempt(task, get_adapter("noop"), backend=publishable_backend())
        self.assertIsNotNone(result.isolation)
        self.assertTrue(result.isolation.active)


class ToolchainExposureTest(unittest.TestCase):
    """Read-only holes for the toolchain must not become answer leaks."""

    def test_claude_toolchain_path_excludes_the_repo_and_home_root(self):
        adapter = get_adapter("claude-code")
        for path in adapter.toolchain_paths():
            with self.subTest(path=path):
                self.assertNotEqual(path, Path.home())
                self.assertFalse(str(path).startswith(str(config.REPO_ROOT)))

    def test_controls_declare_themselves_as_controls(self):
        for name in CONTROL_ADAPTERS:
            with self.subTest(adapter=name):
                self.assertTrue(get_adapter(name).is_control)

    def test_only_the_agent_under_test_requests_network(self):
        self.assertTrue(get_adapter("claude-code").requires_network)
        for name in CONTROL_ADAPTERS:
            with self.subTest(adapter=name):
                self.assertFalse(get_adapter(name).requires_network)


if __name__ == "__main__":
    unittest.main()
