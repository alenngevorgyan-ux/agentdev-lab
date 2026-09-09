"""Tests for the analytics stack: SQL, sample data, export and dashboard."""

import csv
import json
import sqlite3
import unittest

from benchmark.dashboard import SCOPES, build_page
from benchmark.export import build_export, export_csv, export_json
from benchmark.queries import find_query, load_queries, run_query
from benchmark.sampledata import SAMPLE_AGENTS, seed_sample_data
from benchmark.storage import ResultsStore
from tests.helpers import TempDirTestCase


class SeededStoreTestCase(TempDirTestCase):
    """A store populated with synthetic data, so analyses have shape to run on."""

    attempts_per_task = 2

    def setUp(self):
        super().setUp()
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)
        self.run_uids = seed_sample_data(
            self.store, attempts_per_task=self.attempts_per_task, seed=7
        )
        self.store.set_analysis_scope(["development_sample"])


class SampleDataTest(SeededStoreTestCase):
    def test_one_run_per_sample_agent(self):
        self.assertEqual(len(self.run_uids), len(SAMPLE_AGENTS))

    def test_rows_are_marked_synthetic(self):
        kinds = {row["run_kind"] for row in self.store.query("SELECT run_kind FROM runs")}
        self.assertEqual(kinds, {"development_sample"})

    def test_sample_agents_are_named_unmistakably(self):
        names = {row["agent"] for row in self.store.query("SELECT agent FROM runs")}
        self.assertTrue(all(name.startswith("sample-") for name in names), names)

    def test_generation_is_deterministic(self):
        other = ResultsStore(self.tmp / "second.sqlite3")
        self.addCleanup(other.close)
        seed_sample_data(other, attempts_per_task=self.attempts_per_task, seed=7)

        def signature(store):
            return [
                (row["task_id"], row["status"], row["tests_passed"])
                for row in store.query(
                    "SELECT task_id, status, tests_passed FROM attempts ORDER BY id"
                )
            ]

        self.assertEqual(signature(self.store), signature(other))

    def test_per_test_rows_are_written(self):
        count = self.store.query("SELECT COUNT(*) AS n FROM attempt_tests")[0]["n"]
        self.assertGreater(count, 0)

    def test_sample_data_is_excluded_from_measurement_scope(self):
        self.store.set_analysis_scope(["measurement"])
        rows = run_query(self.store, find_query("02_agent_comparison"))
        self.assertEqual(rows, [])


class QuerySuiteTest(SeededStoreTestCase):
    def test_every_query_is_discovered(self):
        self.assertGreaterEqual(len(load_queries()), 20)

    def test_every_query_has_a_description(self):
        for query in load_queries():
            with self.subTest(query=query.name):
                self.assertNotEqual(query.title, query.name)

    def test_every_query_executes(self):
        """A broken analysis must fail the build, not silently return nothing."""
        for query in load_queries():
            with self.subTest(query=query.name):
                try:
                    run_query(self.store, query)
                except sqlite3.Error as exc:
                    self.fail(f"{query.name} failed: {exc}")

    def test_every_query_returns_rows_for_seeded_data(self):
        empty = [q.name for q in load_queries() if not run_query(self.store, q)]
        self.assertEqual(empty, [], f"queries returning nothing on seeded data: {empty}")

    def test_analysis_queries_respect_the_scope_table(self):
        """No analysis may hardcode which run kinds it counts."""
        scoped = [q for q in load_queries() if "run_kind IN (SELECT run_kind FROM analysis_scope)" in q.sql]
        self.assertGreaterEqual(len(scoped), 15)
        for query in load_queries():
            with self.subTest(query=query.name):
                self.assertNotIn("run_kind = 'measurement'", query.sql)

    def test_queries_demonstrate_the_required_techniques(self):
        corpus = "\n".join(query.sql.upper() for query in load_queries())
        for technique in ("GROUP BY", "JOIN", "WITH ", "CASE", "OVER (", "RANK()", "LAG(", "HAVING"):
            with self.subTest(technique=technique):
                self.assertIn(technique, corpus)

    def test_find_query_accepts_a_number(self):
        self.assertEqual(find_query("09").name, "09_hardest_tasks")

    def test_unknown_query_raises(self):
        with self.assertRaises(KeyError):
            find_query("does-not-exist")


class ScopeTest(SeededStoreTestCase):
    def test_default_scope_is_measurement_only(self):
        fresh = ResultsStore(self.tmp / "fresh.sqlite3")
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.analysis_scope(), ["measurement"])

    def test_scope_is_persisted(self):
        path = self.tmp / "scoped.sqlite3"
        first = ResultsStore(path)
        first.set_analysis_scope(["development_sample", "control"])
        first.close()
        second = ResultsStore(path)
        self.addCleanup(second.close)
        self.assertEqual(second.analysis_scope(), ["control", "development_sample"])

    def test_empty_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.set_analysis_scope([])

    def test_invalid_run_kind_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.set_analysis_scope(["made-up"])


class ExportTest(SeededStoreTestCase):
    def test_json_export_round_trips(self):
        path = export_json(self.store, self.tmp / "export.json")
        payload = json.loads(path.read_text())
        self.assertGreater(len(payload["attempts"]), 0)
        self.assertGreater(len(payload["attempt_tests"]), 0)

    def test_export_carries_provenance_and_caveats(self):
        payload = build_export(self.store)
        self.assertIn("harness_version", payload)
        self.assertIn("analysis_scope", payload)
        self.assertTrue(any("synthetic" in line for line in payload["caveats"]))

    def test_csv_export_writes_every_table(self):
        written = export_csv(self.store, self.tmp / "csv")
        names = {path.name for path in written}
        self.assertLessEqual({"runs.csv", "attempts.csv", "attempt_tests.csv"}, names)
        self.assertIn("README.txt", names)

    def test_csv_rows_are_readable(self):
        export_csv(self.store, self.tmp / "csv")
        with (self.tmp / "csv" / "attempts.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreater(len(rows), 0)
        self.assertIn("failure_category", rows[0])

    def test_csv_readme_warns_about_synthetic_rows(self):
        export_csv(self.store, self.tmp / "csv")
        self.assertIn("synthetic", (self.tmp / "csv" / "README.txt").read_text())


class DashboardTest(SeededStoreTestCase):
    def test_page_renders(self):
        page = build_page(self.store)
        self.assertIn("<!doctype html>", page)
        self.assertIn("AgentDev Lab", page)

    def test_synthetic_scope_shows_a_banner(self):
        self.assertIn("Synthetic development data is included", build_page(self.store))

    def test_measurement_scope_shows_no_banner(self):
        self.store.set_analysis_scope(["measurement"])
        self.assertNotIn("Synthetic development data is included", build_page(self.store))

    def test_every_section_is_present(self):
        page = build_page(self.store)
        for heading in (
            "Headline metrics",
            "Agent comparison",
            "Success by capability category",
            "Success by difficulty",
            "Latency distribution",
            "Failure taxonomy",
            "Human interventions",
            "Integrity audit",
            "Run explorer",
        ):
            with self.subTest(section=heading):
                self.assertIn(heading, page)

    def test_scope_names_match_the_cli(self):
        self.assertEqual(set(SCOPES), {"measurement", "sample", "control", "all"})

    def test_empty_database_still_renders(self):
        empty = ResultsStore(self.tmp / "empty.sqlite3")
        self.addCleanup(empty.close)
        page = build_page(empty)
        self.assertIn("Nothing recorded for this scope yet", page)

    def test_values_are_escaped(self):
        """Task ids and agent names reach the page as text, never as markup."""
        page = build_page(self.store)
        self.assertNotIn("<script>", page.lower().split("</head>", 1)[-1])


if __name__ == "__main__":
    unittest.main()
