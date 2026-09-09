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
