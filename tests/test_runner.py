import unittest

from benchmark.adapters.base import Adapter, AgentOutcome
from benchmark.adapters.noop import NoopAdapter
from benchmark.adapters.oracle import OracleAdapter
from benchmark.config import RunConfig
from benchmark.runner import UNAVAILABLE, execute_run, run_attempt
from benchmark.scoring import Status
from benchmark.storage import ResultsStore
from tests.helpers import FIXED_SOURCE, TempDirTestCase, write_task


class CheatingAdapter(Adapter):
    """An agent that deletes the tests instead of fixing the code."""

    name = "cheater"

    def version(self):
        return "cheater/1.0"

    def run(self, task, sandbox):
        for path in (sandbox.path / "tests").glob("test_*.py"):
            path.write_text("# tests removed\n")
        return AgentOutcome(completed=True, duration_ms=1)


class SkippingAdapter(Adapter):
    """An agent that skips the tests rather than making them pass."""

    name = "skipper"

    def version(self):
        return "skipper/1.0"

    def run(self, task, sandbox):
        target = sandbox.path / "tests" / "test_thing.py"
        target.write_text(
            "import unittest\n\n\n"
            "class T(unittest.TestCase):\n"
            "    @unittest.skip('flaky')\n"
            "    def test_answer(self):\n"
            "        pass\n"
        )
        return AgentOutcome(completed=True, duration_ms=1)


class CrashingAdapter(Adapter):
    name = "crasher"

    def version(self):
        return "crasher/1.0"

    def run(self, task, sandbox):
        raise RuntimeError("adapter exploded")


class HangingAdapter(Adapter):
    """An agent that reports its own failure honestly."""

    name = "hanger"

    def version(self):
        return "hanger/1.0"

    def run(self, task, sandbox):
        return AgentOutcome(completed=False, duration_ms=5, error="agent timed out")


class RunAttemptTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.task = self.make_task()
        self.root = self.tmp / "sandboxes"

    def attempt(self, adapter, **kwargs):
        return run_attempt(self.task, adapter, sandbox_root=self.root, **kwargs)

    def test_noop_fails_the_task(self):
        result = self.attempt(NoopAdapter())
        self.assertIs(result.status, Status.FAILED)
        self.assertEqual(result.verification.exit_code, 1)

    def test_per_test_outcomes_are_captured(self):
        result = self.attempt(NoopAdapter())
        self.assertGreater(result.tests_total, 0)
        self.assertTrue(result.suite.parse_is_complete)

    def test_diff_stats_reflect_the_edit(self):
        result = self.attempt(OracleAdapter())
        self.assertEqual(result.diff.files_changed, 1)
        self.assertEqual(result.diff.changed_paths, ("src/thing.py",))
        self.assertGreater(result.diff.lines_changed, 0)

    def test_noop_changes_nothing(self):
        self.assertTrue(self.attempt(NoopAdapter()).diff.is_empty)

    def test_hidden_tests_are_invisible_to_the_agent_but_graded(self):
        """The agent must never see the assertions it is graded on."""
        from tests.helpers import HIDDEN_TEST

        task = self.make_task(task_id="hidden-demo", hidden_test=HIDDEN_TEST)
        self.assertFalse((task.workspace_path / "tests" / "test_hidden.py").exists())
        result = run_attempt(task, OracleAdapter(), sandbox_root=self.root)
        self.assertIs(result.status, Status.PASSED)
        self.assertIn(
            "tests.test_hidden.Hidden.test_answer_is_an_int",
            {test.test_id for test in result.suite.tests},
        )

    def test_oracle_passes_the_task(self):
        result = self.attempt(OracleAdapter())
        self.assertIs(result.status, Status.PASSED)
        self.assertTrue(result.score.passed)

    def test_deleting_tests_is_recorded_as_tampering(self):
        result = self.attempt(CheatingAdapter())
        self.assertIs(result.status, Status.TAMPERED)
        self.assertFalse(result.score.passed)

    def test_skipping_tests_is_recorded_as_tampering(self):
        """A green-but-empty suite must not read as success."""
        result = self.attempt(SkippingAdapter())
        self.assertIs(result.status, Status.TAMPERED)

    def test_verification_is_skipped_once_tampering_is_detected(self):
        self.assertIsNone(self.attempt(CheatingAdapter()).verification)

    def test_adapter_crash_is_an_agent_error(self):
        result = self.attempt(CrashingAdapter())
        self.assertIs(result.status, Status.AGENT_ERROR)
        self.assertIn("adapter exploded", result.score.reason)

    def test_self_reported_agent_failure(self):
        self.assertIs(self.attempt(HangingAdapter()).status, Status.AGENT_ERROR)

    def test_hashes_are_recorded(self):
        result = self.attempt(OracleAdapter())
        self.assertEqual(result.protected_hash_before, result.protected_hash_after)
        self.assertNotEqual(result.workspace_hash_before, result.workspace_hash_after)

    def test_sandbox_is_removed_by_default(self):
        self.attempt(OracleAdapter())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_oracle_without_reference_solution_is_an_agent_error(self):
        task = self.make_task(task_id="no-solution", solution=None)
        result = run_attempt(task, OracleAdapter(), sandbox_root=self.root)
        self.assertIs(result.status, Status.AGENT_ERROR)


class ExecuteRunTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.tasks_dir = self.tmp / "tasks"
        write_task(self.tasks_dir, task_id="task-broken")
        write_task(self.tasks_dir, task_id="task-already-fixed", source=FIXED_SOURCE)
        from benchmark.tasks import load_tasks

        self.tasks = load_tasks(self.tasks_dir)
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)

    def run_with(self, adapter_name, attempts=1):
        config = RunConfig(adapter=adapter_name, task_ids=(), attempts=attempts)
        return execute_run(config, self.store, tasks=self.tasks)

    def test_run_records_every_attempt(self):
        result = self.run_with("noop", attempts=2)
        self.assertEqual(len(result.attempts), 4)
        self.assertEqual(len(self.store.attempts_for_run(result.run_uid)), 4)

    def test_pass_rate_reflects_reality(self):
        result = self.run_with("noop")
        # One task is broken, one already passes: exactly half should pass.
        self.assertEqual(result.passed, 1)
        self.assertAlmostEqual(result.pass_rate, 0.5)

    def test_oracle_passes_everything(self):
        result = self.run_with("oracle")
        self.assertEqual(result.pass_rate, 1.0)

    def test_run_is_closed_out(self):
        result = self.run_with("noop")
        summary = self.store.run_summary(result.run_uid)
        self.assertEqual(summary["status"], "completed")
        self.assertIsNotNone(summary["finished_at"])

    def test_fingerprint_is_stored_with_each_attempt(self):
        result = self.run_with("noop")
        fingerprints = {row["task_fingerprint"] for row in self.store.attempts_for_run(result.run_uid)}
        self.assertEqual(len(fingerprints), 2)
        self.assertNotIn("", fingerprints)

    def test_logs_are_persisted(self):
        result = self.run_with("noop")
        rows = self.store.query(
            "SELECT COUNT(*) AS n FROM attempt_logs l JOIN attempts a ON a.id = l.attempt_id "
            "JOIN runs r ON r.id = a.run_id WHERE r.run_uid = ?",
            (result.run_uid,),
        )
        self.assertGreater(rows[0]["n"], 0)

    def test_empty_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            execute_run(RunConfig(adapter="noop", task_ids=()), self.store, tasks=[])

    def test_unavailable_sentinel_is_defined(self):
        self.assertEqual(UNAVAILABLE, "<unavailable>")


if __name__ == "__main__":
    unittest.main()


class InterpreterHijackAdapter(Adapter):
    """An agent that forges a passing test run instead of fixing the code.

    It plants a module named after the standard-library module the evaluation
    command imports, which prints a convincing suite summary and exits zero.
    """

    name = "hijacker"

    def version(self):
        return "hijacker/1.0"

    def run(self, task, sandbox):
        (sandbox.path / "unittest.py").write_text(
            "import sys\n"
            'sys.stderr.write("test_a (tests.t.T.test_a) ... ok\\n")\n'
            'sys.stderr.write("\\nRan 1 test in 0.001s\\n\\nOK\\n")\n'
            "sys.exit(0)\n"
        )
        return AgentOutcome(completed=True, duration_ms=1)


class StdlibShadowAdapter(Adapter):
    """A subtler variant: a package rather than a module."""

    name = "shadower"

    def version(self):
        return "shadower/1.0"

    def run(self, task, sandbox):
        package = sandbox.path / "json"
        package.mkdir(exist_ok=True)
        (package / "__init__.py").write_text("raise SystemExit(0)\n")
        return AgentOutcome(completed=True, duration_ms=1)


class InterpreterHijackTest(TempDirTestCase):
    """Grading must not be hijackable by planting files outside the tests."""

    def setUp(self):
        super().setUp()
        self.task = self.make_task()
        self.root = self.tmp / "sandboxes"

    def test_forged_test_run_is_recorded_as_tampering(self):
        result = run_attempt(self.task, InterpreterHijackAdapter(), sandbox_root=self.root)
        self.assertIs(result.status, Status.TAMPERED)
        self.assertFalse(result.score.passed)
        self.assertIn("shadowing", result.score.reason)

    def test_stdlib_package_shadow_is_detected(self):
        result = run_attempt(self.task, StdlibShadowAdapter(), sandbox_root=self.root)
        self.assertIs(result.status, Status.TAMPERED)

    def test_evaluation_is_skipped_once_a_shadow_is_found(self):
        result = run_attempt(self.task, InterpreterHijackAdapter(), sandbox_root=self.root)
        self.assertIsNone(result.verification)

    def test_a_legitimate_fix_is_not_flagged(self):
        result = run_attempt(self.task, OracleAdapter(), sandbox_root=self.root)
        self.assertIs(result.status, Status.PASSED)

    def test_detector_ignores_files_present_in_the_fixture(self):
        from benchmark.runner import detect_interpreter_shadowing

        workspace = self.tmp / "ws"
        (workspace / "src").mkdir(parents=True)
        (workspace / "json.py").write_text("# shipped by the task author\n")
        self.assertEqual(detect_interpreter_shadowing(workspace, workspace), [])

    def test_detector_reports_an_added_shadow(self):
        from benchmark.runner import detect_interpreter_shadowing

        fixture = self.tmp / "fixture"
        (fixture / "src").mkdir(parents=True)
        workspace = self.tmp / "ws2"
        (workspace / "src").mkdir(parents=True)
        (workspace / "unittest.py").write_text("import sys; sys.exit(0)\n")
        self.assertEqual(detect_interpreter_shadowing(workspace, fixture), ["unittest.py"])

    def test_evaluation_ignores_the_working_directory_on_the_import_path(self):
        """The primary defence: a planted stdlib name is never imported."""
        from benchmark.isolation import select_backend
        from benchmark.runner import evaluate
        from benchmark.sandbox import create_sandbox

        with create_sandbox(self.task, root=self.root) as sandbox:
            (sandbox.path / "unittest.py").write_text(
                'import sys\nsys.stderr.write("Ran 99 tests in 0.0s\\n\\nOK\\n")\nsys.exit(0)\n'
            )
            result, suite = evaluate(sandbox.path, self.task, select_backend())
        self.assertNotEqual(result.exit_code, 0, "the forged module was imported")
        self.assertNotEqual(suite.reported_total, 99)


class BaselineCacheTest(TempDirTestCase):
    """The cache is content-addressed, which is what makes reuse safe."""

    def test_identical_fixtures_share_a_baseline(self):
        from benchmark.runner import clear_baseline_cache, measure_baseline

        clear_baseline_cache()
        first = self.make_task(task_id="twin-a")
        second = self.make_task(task_id="twin-b")
        # Different ids mean different specs, so the fingerprints differ and
        # each is measured on its own -- the key is content, not identity.
        self.assertNotEqual(first.spec_fingerprint(), second.spec_fingerprint())
        baseline_one, _ = measure_baseline(first, sandbox_root=self.tmp / "sb")
        baseline_two, _ = measure_baseline(second, sandbox_root=self.tmp / "sb")
        self.assertEqual(baseline_one.satisfied_ids(), baseline_two.satisfied_ids())

    def test_editing_a_fixture_invalidates_the_cached_baseline(self):
        from benchmark.runner import clear_baseline_cache, measure_baseline

        clear_baseline_cache()
        task = self.make_task(task_id="mutating")
        before, _ = measure_baseline(task, sandbox_root=self.tmp / "sb")
        self.assertEqual(before.passed, 0)

        (task.workspace_path / "src" / "thing.py").write_text("def answer():\n    return 42\n")
        after, _ = measure_baseline(task, sandbox_root=self.tmp / "sb")
        self.assertEqual(after.passed, after.total)
        self.assertNotEqual(before.satisfied_ids(), after.satisfied_ids())

    def test_repeated_measurement_of_one_fixture_is_served_from_cache(self):
        from benchmark.runner import _BASELINE_CACHE, clear_baseline_cache, measure_baseline

        clear_baseline_cache()
        task = self.make_task(task_id="cached")
        measure_baseline(task, sandbox_root=self.tmp / "sb")
        self.assertIn(task.spec_fingerprint(), _BASELINE_CACHE)
        measure_baseline(task, sandbox_root=self.tmp / "sb")
        self.assertEqual(len(_BASELINE_CACHE), 1)
