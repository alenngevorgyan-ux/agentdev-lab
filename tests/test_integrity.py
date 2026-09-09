import unittest

from benchmark.integrity import (
    check_recorded_results,
    check_task_definitions,
    check_task_polarity,
    selfcheck,
)
from benchmark.storage import ResultsStore
from benchmark.tasks import load_task
from tests.helpers import FIXED_SOURCE, TempDirTestCase, write_task
from tests.test_storage import FakeTask, attempt_fields


class TaskDefinitionCheckTest(TempDirTestCase):
    def test_well_formed_registry_passes(self):
        tasks_dir = self.tmp / "tasks"
        write_task(tasks_dir, task_id="task-a")
        self.assertTrue(check_task_definitions(tasks_dir).ok)

    def test_missing_reference_solution_is_reported(self):
        tasks_dir = self.tmp / "tasks"
        write_task(tasks_dir, task_id="task-a", solution=None)
        report = check_task_definitions(tasks_dir)
        self.assertFalse(report.ok)
        self.assertTrue(any("reference solution" in check.name for check in report.checks if not check.ok))

    def test_empty_registry_is_reported(self):
        (self.tmp / "empty").mkdir()
        self.assertFalse(check_task_definitions(self.tmp / "empty").ok)

    def test_malformed_spec_is_reported(self):
        tasks_dir = self.tmp / "tasks"
        directory = write_task(tasks_dir, task_id="task-a")
        (directory / "task.json").write_text("{oops")
        self.assertFalse(check_task_definitions(tasks_dir).ok)


class PolarityCheckTest(TempDirTestCase):
    def test_a_proper_task_passes_both_controls(self):
        task = load_task(write_task(self.tmp / "tasks", task_id="good"))
        results = check_task_polarity(task, sandbox_root=self.tmp / "sb")
        self.assertTrue(all(result.ok for result in results), [r.detail for r in results])

    def test_a_task_that_already_passes_is_rejected(self):
        """A task the noop control passes measures nothing and must fail selfcheck."""
        task = load_task(write_task(self.tmp / "tasks", task_id="trivial", source=FIXED_SOURCE))
        results = check_task_polarity(task, sandbox_root=self.tmp / "sb")
        self.assertFalse(results[0].ok)

    def test_a_task_with_a_wrong_reference_solution_is_rejected(self):
        task = load_task(
            write_task(
                self.tmp / "tasks",
                task_id="bad-oracle",
                solution="def answer():\n    return 41\n",
            )
        )
        results = check_task_polarity(task, sandbox_root=self.tmp / "sb")
        self.assertFalse(results[1].ok)


class RecordedResultsCheckTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)
        self.store.register_tasks([FakeTask()])
        self.run_id, self.run_uid = self.store.start_run(
            adapter="noop", agent="noop", adapter_version="v1", attempts_per_task=1,
            run_kind="control",
        )

    def test_clean_record_passes(self):
        self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        self.store.finish_run(self.run_id)
        self.assertTrue(check_recorded_results(self.store).ok)

    def test_fixture_drift_is_detected(self):
        self.store.record_attempt(**attempt_fields(run_id=self.run_id, task_fingerprint="fp-v1"))
        other_run, _ = self.store.start_run(
            adapter="noop", agent="noop", adapter_version="v1", attempts_per_task=1,
            run_kind="control",
        )
        self.store.record_attempt(**attempt_fields(run_id=other_run, task_fingerprint="fp-v2"))
        report = check_recorded_results(self.store)
        self.assertFalse(report.ok)
        self.assertTrue(any("fixtures stable" in check.name for check in report.checks if not check.ok))

    def test_inert_agent_attempt_is_flagged(self):
        """A non-control attempt that changed nothing is not a capability measurement."""
        run_id, _ = self.store.start_run(
            adapter="claude-code", agent="claude-code", adapter_version="v1", attempts_per_task=1
        )
        self.store.record_attempt(
            **attempt_fields(
                run_id=run_id,
                status="failed",
                passed=0,
                workspace_hash_before="same",
                workspace_hash_after="same",
            )
        )
        report = check_recorded_results(self.store)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("actually changed the workspace" in c.name for c in report.checks if not c.ok)
        )

    def test_inert_control_attempt_is_not_flagged(self):
        """The noop control legitimately changes nothing."""
        self.store.record_attempt(
            **attempt_fields(
                run_id=self.run_id,
                status="failed",
                passed=0,
                workspace_hash_before="same",
                workspace_hash_after="same",
            )
        )
        self.assertTrue(check_recorded_results(self.store).ok)

    def test_tampered_attempts_are_surfaced(self):
        self.store.record_attempt(
            **attempt_fields(run_id=self.run_id, status="tampered", passed=0, tampered=1)
        )
        report = check_recorded_results(self.store)
        self.assertFalse(report.ok)


class ShippedRegistrySelfcheckTest(TempDirTestCase):
    """The registry that ships with the repository must always self-check clean."""

    def test_selfcheck_passes(self):
        report = selfcheck(sandbox_root=self.tmp / "sb")
        self.assertTrue(report.ok, report.render())


if __name__ == "__main__":
    unittest.main()
