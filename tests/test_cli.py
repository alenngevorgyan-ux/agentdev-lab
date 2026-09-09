import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from benchmark.cli import main
from benchmark.report import leaderboard, render_table, run_report
from benchmark.storage import ResultsStore
from tests.helpers import TempDirTestCase
from tests.test_storage import attempt_fields


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTest(TempDirTestCase):
    def test_list_tasks(self):
        code, out, _ = run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn("py-001-interval-merge", out)

    def test_list_json_is_parseable(self):
        code, out, _ = run_cli(["list", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(all("fingerprint" in entry for entry in payload))

    def test_adapters_are_listed_with_roles(self):
        code, out, _ = run_cli(["adapters"])
        self.assertEqual(code, 0)
        self.assertIn("control", out)
        self.assertIn("agent under test", out)

    def test_unknown_adapter_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as ctx:
            run_cli(["run", "--adapter", "gpt-imaginary"])
        self.assertEqual(ctx.exception.code, 2)

    def test_unknown_task_is_a_usage_error(self):
        code, _, err = run_cli(
            ["run", "--adapter", "noop", "--task", "no-such-task", "--db", str(self.tmp / "db.sqlite3")]
        )
        self.assertEqual(code, 2)
        self.assertIn("unknown task", err)

    def test_run_then_report_round_trip(self):
        db = str(self.tmp / "db.sqlite3")
        code, out, _ = run_cli(
            ["run", "--adapter", "oracle", "--task", "py-001-interval-merge", "--db", db]
        )
        self.assertEqual(code, 0)
        self.assertIn("PASS", out)
        run_uid = out.split("run uid:")[1].split()[0]

        code, report_out, _ = run_cli(["report", "--run", run_uid, "--db", db])
        self.assertEqual(code, 0)
        self.assertIn("py-001-interval-merge", report_out)

        code, json_out, _ = run_cli(["report", "--run", run_uid, "--json", "--db", db])
        self.assertEqual(code, 0)
        payload = json.loads(json_out)
        self.assertEqual(payload["run"]["passed"], 1)

    def test_report_without_results(self):
        code, out, _ = run_cli(["report", "--db", str(self.tmp / "empty.sqlite3")])
        self.assertEqual(code, 0)
        self.assertIn("no runs recorded", out)

    def test_verify_integrity_on_missing_db(self):
        code, out, _ = run_cli(["verify-integrity", "--db", str(self.tmp / "nothing.sqlite3")])
        self.assertEqual(code, 0)
        self.assertIn("nothing recorded", out)

    def test_verify_integrity_fails_on_tampered_record(self):
        db = self.tmp / "db.sqlite3"
        store = ResultsStore(db)
        run_id, _ = store.start_run(adapter="noop", adapter_version="v1", attempts_per_task=1)
        store.record_attempt(
            **attempt_fields(run_id=run_id, status="tampered", passed=0, tampered=1)
        )
        store.close()
        code, out, _ = run_cli(["verify-integrity", "--db", str(db)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)


class ReportRenderingTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.store = ResultsStore(self.tmp / "db.sqlite3")
        self.addCleanup(self.store.close)

    def test_render_table_aligns_columns(self):
        text = render_table(["a", "bbbb"], [["xxxxx", "y"]])
        self.assertEqual(len(text.splitlines()), 3)

    def test_unknown_run_is_reported(self):
        self.assertIn("no such run", run_report(self.store, "does-not-exist"))

    def test_empty_leaderboard(self):
        self.assertIn("no results", leaderboard(self.store))

    def test_leaderboard_flags_controls(self):
        run_id, _ = self.store.start_run(
            adapter="oracle", adapter_version="v1", attempts_per_task=1
        )
        self.store.record_attempt(**attempt_fields(run_id=run_id))
        self.assertIn("harness controls", leaderboard(self.store))


if __name__ == "__main__":
    unittest.main()
