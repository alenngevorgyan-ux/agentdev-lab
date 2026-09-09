"""Documentation must agree with the repository.

A reviewer who finds one stale number reasonably doubts every other number, so
the counts that appear in prose are asserted against the live repository, and
volatile ones are not allowed to be hardcoded at all.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from benchmark.config import REPO_ROOT
from benchmark.queries import load_queries
from benchmark.stats import gather

DOCS = sorted((REPO_ROOT / "docs").glob("*.md"))
TOP_LEVEL = [REPO_ROOT / name for name in ("README.md", "ARCHITECTURE.md", "CLAUDE.md")]
ALL_MARKDOWN = [*TOP_LEVEL, *DOCS, REPO_ROOT / "sql" / "README.md", REPO_ROOT / "progress.md"]

#: progress.md is an append-only log: it records what was true at the time, so
#: historical counts in it are correct and must not be rewritten.
HISTORICAL = {REPO_ROOT / "progress.md"}


class RequiredDocumentTest(unittest.TestCase):
    def test_every_referenced_document_exists(self):
        for path in (
            "README.md", "ARCHITECTURE.md", "CLAUDE.md", "progress.md", "tests.json",
            "setup.sh", "sql/README.md",
            "docs/task-format.md", "docs/adapters.md", "docs/integrity.md",
            "docs/methodology.md", "docs/metrics.md", "docs/failure-taxonomy.md",
            "docs/dashboard.md", "docs/isolation.md", "docs/threat-model.md",
            "docs/comparison-protocol.md", "docs/interviewer-brief.md",
        ):
            with self.subTest(document=path):
                self.assertTrue((REPO_ROOT / path).is_file(), f"missing {path}")

    def test_internal_links_resolve(self):
        broken = []
        for document in ALL_MARKDOWN:
            if not document.is_file():
                continue
            for target in re.findall(r"\]\(([^)#][^)]*)\)", document.read_text(encoding="utf-8")):
                if target.startswith(("http", "mailto:")):
                    continue
                if not (document.parent / target.split("#")[0]).exists():
                    broken.append(f"{document.name} -> {target}")
        self.assertEqual(broken, [])


class CountConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.stats = gather()

    def test_task_count_claims_are_correct(self):
        pattern = re.compile(r"(\d+)\s+(?:benchmark\s+)?tasks\b")
        wrong = []
        for document in ALL_MARKDOWN:
            if not document.is_file() or document in HISTORICAL:
                continue
            for count in pattern.findall(document.read_text(encoding="utf-8")):
                if int(count) != self.stats.tasks:
                    wrong.append(f"{document.name}: claims {count} tasks")
        self.assertEqual(wrong, [], f"actual: {self.stats.tasks}")

    def test_category_count_claims_are_correct(self):
        pattern = re.compile(r"(\d+)\s+(?:capability\s+)?categories\b")
        wrong = []
        for document in ALL_MARKDOWN:
            if not document.is_file() or document in HISTORICAL:
                continue
            for count in pattern.findall(document.read_text(encoding="utf-8")):
                if int(count) != self.stats.categories:
                    wrong.append(f"{document.name}: claims {count} categories")
        self.assertEqual(wrong, [], f"actual: {self.stats.categories}")

    def test_sql_analysis_count_claims_are_correct(self):
        pattern = re.compile(r"(\d+)\s+(?:documented\s+|curated\s+)?(?:SQL\s+)?analyses\b")
        wrong = []
        for document in ALL_MARKDOWN:
            if not document.is_file() or document in HISTORICAL:
                continue
            for count in pattern.findall(document.read_text(encoding="utf-8")):
                if int(count) != self.stats.sql_queries:
                    wrong.append(f"{document.name}: claims {count} analyses")
        self.assertEqual(wrong, [], f"actual: {self.stats.sql_queries}")

    def test_no_document_hardcodes_a_test_count(self):
        """The suite grows constantly; a number here would be stale by tomorrow."""
        pattern = re.compile(r"\b\d+\s+tests\b")
        offenders = []
        for document in ALL_MARKDOWN:
            if not document.is_file() or document in HISTORICAL:
                continue
            if pattern.search(document.read_text(encoding="utf-8")):
                offenders.append(document.name)
        self.assertEqual(
            offenders, [], "use `python3 -m benchmark stats` instead of a hardcoded count"
        )

    def test_query_files_match_the_documented_index(self):
        index = (REPO_ROOT / "sql" / "README.md").read_text(encoding="utf-8")
        for query in load_queries():
            with self.subTest(query=query.name):
                self.assertIn(query.name.split("_", 1)[0], index)


class TestsJsonTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((REPO_ROOT / "tests.json").read_text(encoding="utf-8"))

    def test_every_authoritative_suite_is_runnable(self):
        for suite in self.manifest["suites"]:
            with self.subTest(suite=suite["id"]):
                self.assertTrue(suite["command"])
                self.assertGreater(suite["timeout_sec"], 0)

    def test_the_gate_names_only_declared_suites(self):
        declared = {suite["id"] for suite in self.manifest["suites"]}
        self.assertLessEqual(set(self.manifest["gate"]["required_suites"]), declared)

    def test_readme_documents_the_authoritative_commands(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for suite in self.manifest["suites"]:
            if not suite.get("authoritative"):
                continue
            head = " ".join(suite["command"][:4])
            with self.subTest(suite=suite["id"]):
                self.assertIn(head, readme, f"README does not show: {head}")

    def test_no_suite_was_narrowed_with_failfast(self):
        """Narrowing an authoritative command hides later failures."""
        for suite in self.manifest["suites"]:
            with self.subTest(suite=suite["id"]):
                self.assertNotIn("--failfast", suite["command"])
                self.assertNotIn("-f", suite["command"])


class HonestyTest(unittest.TestCase):
    """The documentation must not claim results that do not exist."""

    def test_no_document_reports_an_agent_pass_rate(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        brief = (REPO_ROOT / "docs" / "interviewer-brief.md").read_text(encoding="utf-8")
        for document, name in ((readme, "README.md"), (brief, "interviewer-brief.md")):
            with self.subTest(document=name):
                self.assertNotRegex(
                    document,
                    r"claude[- ]code\s+(?:scored|achieved|passed)\s+\d",
                    "a result is claimed that has not been measured",
                )

    def test_readme_states_that_no_agent_has_been_measured(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("No agent has been measured", readme)

    def test_readme_has_the_trust_and_limits_sections(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Why this benchmark is trustworthy", readme)
        self.assertIn("What this benchmark does NOT prove", readme)

    def test_task_author_bias_is_disclosed(self):
        """The limitation no mechanism here fixes must be stated, not buried."""
        for path in ("README.md", "docs/comparison-protocol.md", "docs/threat-model.md",
                     "docs/interviewer-brief.md"):
            with self.subTest(document=path):
                text = (REPO_ROOT / path).read_text(encoding="utf-8").lower()
                self.assertIn("author", text)

    def test_codex_adapter_is_not_claimed_to_be_validated(self):
        adapters = (REPO_ROOT / "docs" / "adapters.md").read_text(encoding="utf-8").lower()
        self.assertIn("codex", adapters)
        self.assertTrue(
            "not" in adapters and ("end-to-end" in adapters or "unvalidated" in adapters),
            "the Codex adapter's validation status must be stated",
        )


if __name__ == "__main__":
    unittest.main()
