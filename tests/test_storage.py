import sqlite3
import unittest

from benchmark.storage import ResultsStore, utc_now
from tests.helpers import TempDirTestCase


def attempt_fields(**overrides):
    fields = {
        "run_id": 1,
        "task_id": "demo-task",
        "task_fingerprint": "fp",
        "attempt_index": 1,
        "status": "passed",
        "passed": 1,
        "tampered": 0,
        "reason": "ok",
        "verify_exit_code": 0,
        "verify_duration_ms": 5,
        "agent_duration_ms": 1,
        "total_duration_ms": 10,
        "protected_hash_before": "a",
        "protected_hash_after": "a",
        "workspace_hash_before": "b",
        "workspace_hash_after": "c",
    }
    fields.update(overrides)
    return fields


class StorageTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)
        self.run_id, self.run_uid = self.store.start_run(
            adapter="noop", adapter_version="v1", attempts_per_task=1
        )

    def test_schema_is_created(self):
        tables = {row["name"] for row in self.store.query("SELECT name FROM sqlite_master")}
        self.assertLessEqual({"runs", "attempts", "attempt_logs", "v_run_summary"}, tables)

    def test_run_records_provenance(self):
        row = self.store.query("SELECT * FROM runs WHERE id = ?", (self.run_id,))[0]
        self.assertTrue(row["python_version"])
        self.assertTrue(row["platform"])
        self.assertIn(row["git_dirty"], (0, 1))
        self.assertEqual(row["status"], "running")

    def test_finish_run_closes_it(self):
        self.store.finish_run(self.run_id)
        row = self.store.query("SELECT * FROM runs WHERE id = ?", (self.run_id,))[0]
        self.assertEqual(row["status"], "completed")
        self.assertIsNotNone(row["finished_at"])

    def test_record_attempt_and_summary(self):
        self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        self.store.finish_run(self.run_id)
        summary = self.store.run_summary(self.run_uid)
        self.assertEqual(summary["attempts"], 1)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["pass_rate"], 1.0)

    def test_missing_field_is_rejected(self):
        fields = attempt_fields(run_id=self.run_id)
        fields.pop("tampered")
        with self.assertRaises(ValueError):
            self.store.record_attempt(**fields)

    def test_unexpected_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.record_attempt(**attempt_fields(run_id=self.run_id, bonus_points=10))

    def test_duplicate_attempt_index_is_rejected(self):
        self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_attempt(**attempt_fields(run_id=self.run_id))

    def test_passed_and_tampered_cannot_coexist(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_attempt(
                **attempt_fields(run_id=self.run_id, passed=1, tampered=1, status="passed")
            )

    def test_passed_flag_must_match_status(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_attempt(**attempt_fields(run_id=self.run_id, status="failed", passed=1))

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_attempt(
                **attempt_fields(run_id=self.run_id, status="great", passed=0)
            )

    def test_logs_are_stored(self):
        attempt_id = self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        self.store.record_logs(attempt_id, {"verify_stdout": "output", "verify_stderr": ""})
        rows = self.store.query("SELECT * FROM attempt_logs WHERE attempt_id = ?", (attempt_id,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stream"], "verify_stdout")


class AppendOnlyTest(TempDirTestCase):
    """Recorded results must be impossible to rewrite in place."""

    def setUp(self):
        super().setUp()
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)
        self.run_id, self.run_uid = self.store.start_run(
            adapter="noop", adapter_version="v1", attempts_per_task=1
        )
        self.attempt_id = self.store.record_attempt(
            **attempt_fields(run_id=self.run_id, status="failed", passed=0)
        )

    def test_attempts_cannot_be_updated(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE attempts SET passed = 1, status = 'passed' WHERE id = ?", (self.attempt_id,)
            )

    def test_attempts_cannot_be_deleted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM attempts WHERE id = ?", (self.attempt_id,))

    def test_runs_cannot_be_deleted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM runs WHERE id = ?", (self.run_id,))

    def test_run_provenance_cannot_be_rewritten(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE runs SET git_dirty = 0, git_commit = 'faked' WHERE id = ?", (self.run_id,)
            )

    def test_run_may_still_be_closed_out(self):
        self.store.finish_run(self.run_id)
        self.assertEqual(
            self.store.query("SELECT status FROM runs WHERE id = ?", (self.run_id,))[0]["status"],
            "completed",
        )

    def test_logs_cannot_be_deleted(self):
        self.store.record_logs(self.attempt_id, {"verify_stdout": "evidence"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "DELETE FROM attempt_logs WHERE attempt_id = ?", (self.attempt_id,)
            )


class TimestampTest(unittest.TestCase):
    def test_utc_now_is_iso_utc(self):
        stamp = utc_now()
        self.assertIn("T", stamp)
        self.assertTrue(stamp.endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
