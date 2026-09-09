"""Parsing per-test outcomes out of a verbose ``unittest`` run.

A single exit code answers "did everything pass". Research needs more: which
tests passed, how many, and -- by comparing against a baseline -- which
previously-passing tests an agent broke. That requires per-test granularity,
so evaluation runs ``unittest -v`` and parses its output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class TestOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    EXPECTED_FAILURE = "expected_failure"
    UNEXPECTED_SUCCESS = "unexpected_success"


#: Outcomes that count as the test being satisfied.
SATISFIED = frozenset({TestOutcome.PASSED, TestOutcome.EXPECTED_FAILURE})

# unittest -v writes e.g.
#   test_merge (tests.test_x.MergeTest.test_merge) ... ok
#   test_merge (tests.test_x.MergeTest.test_merge) ... FAIL
#   test_merge (tests.test_x.MergeTest) ... skipped 'reason'
_LINE = re.compile(
    r"^(?P<name>[\w.]+ \([\w.]+\)(?: \([^)]*\))?)"
    r"(?: \.\.\. |\s*\.\.\.\s*)"
    r"(?P<outcome>ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)\s*$"
)

_OUTCOMES = {
    "ok": TestOutcome.PASSED,
    "FAIL": TestOutcome.FAILED,
    "ERROR": TestOutcome.ERROR,
    "expected failure": TestOutcome.EXPECTED_FAILURE,
    "unexpected success": TestOutcome.UNEXPECTED_SUCCESS,
}

_SUMMARY = re.compile(r"^Ran (?P<count>\d+) tests? in ", re.MULTILINE)


@dataclass(frozen=True)
class TestResult:
    test_id: str
    outcome: TestOutcome

    @property
    def satisfied(self) -> bool:
        return self.outcome in SATISFIED


@dataclass(frozen=True)
class SuiteResult:
    """Per-test outcomes for one evaluation."""

    tests: tuple[TestResult, ...]
    #: Count reported by unittest itself, used to detect a truncated parse.
    reported_total: int | None = None
    #: True when the suite could not even be collected (an import error, say).
    collection_error: bool = False

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def passed(self) -> int:
        return sum(1 for test in self.tests if test.satisfied)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_fraction(self) -> float:
        return (self.passed / self.total) if self.total else 0.0

    @property
    def parse_is_complete(self) -> bool:
        """Whether every test unittest claims to have run was also parsed."""
        return self.reported_total is None or self.reported_total == self.total

    def satisfied_ids(self) -> frozenset[str]:
        return frozenset(test.test_id for test in self.tests if test.satisfied)


def _normalise(raw_name: str) -> str:
    """Reduce a unittest header to a stable dotted test id.

    Python versions differ in how they render the header; the parenthesised
    dotted path is the stable part, so it is preferred when present.
    """
    if "(" in raw_name and ")" in raw_name:
        inner = raw_name[raw_name.index("(") + 1 : raw_name.rindex(")")].strip()
        method = raw_name.split(" ", 1)[0]
        # Older format omits the method from the dotted path; append it.
        return inner if inner.endswith(f".{method}") else f"{inner}.{method}"
    return raw_name.strip()


def parse_unittest_output(text: str) -> SuiteResult:
    """Parse ``python -m unittest -v`` output into per-test outcomes."""
    results: list[TestResult] = []
    for line in text.splitlines():
        match = _LINE.match(line.strip())
        if match is None:
            continue
        raw_outcome = match.group("outcome")
        outcome = (
            TestOutcome.SKIPPED
            if raw_outcome.startswith("skipped")
            else _OUTCOMES.get(raw_outcome)
        )
        if outcome is None:
            continue
        results.append(TestResult(test_id=_normalise(match.group("name")), outcome=outcome))

    summary = _SUMMARY.search(text)
    reported = int(summary.group("count")) if summary else None
    # No tests and no summary means the suite never ran -- typically an import
    # error in the code under test. That is a real, reportable outcome.
    collection_error = not results and reported in (None, 0)
    return SuiteResult(
        tests=tuple(results), reported_total=reported, collection_error=collection_error
    )
