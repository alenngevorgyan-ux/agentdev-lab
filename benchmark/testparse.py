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
#
# Two things split a test across lines, and missing either silently under-counts
# the suite:
#   * a docstring -- unittest prints the name, then "<description> ... ok" below;
#   * anything the test itself writes, which lands between header and outcome.
# Headers and outcomes are therefore matched separately and stitched together.
_OUTCOME_ALTERNATIVES = r"ok|FAIL|ERROR|skipped.*|expected failure|unexpected success"
_NAME = r"(?P<name>[\w.]+ \([\w.]+\)(?: \([^)]*\))?)"

_LINE = re.compile(rf"^{_NAME}(?: \.\.\. |\s*\.\.\.\s*)(?P<outcome>{_OUTCOME_ALTERNATIVES})\s*$")
_HEADER_ONLY = re.compile(rf"^{_NAME}\s*\.\.\.\s*(?P<trailing>.*)$")
_NAME_ONLY = re.compile(rf"^{_NAME}\s*$")
_BARE_OUTCOME = re.compile(rf"^(?P<outcome>{_OUTCOME_ALTERNATIVES})\s*$")
#: A docstring line: "<short description> ... ok".
_DESCRIBED_OUTCOME = re.compile(rf"^.*\.\.\.\s*(?P<outcome>{_OUTCOME_ALTERNATIVES})\s*$")

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

    @property
    def effective_total(self) -> int:
        """The denominator to report.

        When the parse missed outcomes, the runner's own count is the honest
        denominator: reporting only what we could parse would silently shrink
        the suite and inflate the pass fraction.
        """
        return max(self.total, self.reported_total or 0)

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


def _to_outcome(raw: str) -> TestOutcome | None:
    return TestOutcome.SKIPPED if raw.startswith("skipped") else _OUTCOMES.get(raw)


def parse_unittest_output(text: str) -> SuiteResult:
    """Parse ``python -m unittest -v`` output into per-test outcomes."""
    results: list[TestResult] = []
    pending: str | None = None

    for line in text.splitlines():
        stripped = line.strip()

        match = _LINE.match(stripped)
        if match is not None:
            outcome = _to_outcome(match.group("outcome"))
            if outcome is not None:
                results.append(TestResult(_normalise(match.group("name")), outcome))
                pending = None
            continue

        header = _HEADER_ONLY.match(stripped)
        if header is not None:
            # The outcome will arrive after whatever the test itself printed.
            pending = _normalise(header.group("name"))
            continue

        name_only = _NAME_ONLY.match(stripped)
        if name_only is not None:
            # A documented test: its description and outcome are on the next line.
            pending = _normalise(name_only.group("name"))
            continue

        if pending is not None:
            # Only consulted while a header is open, so an arbitrary line ending
            # in "... ok" elsewhere in the output cannot invent a result.
            match = _BARE_OUTCOME.match(stripped) or _DESCRIBED_OUTCOME.match(stripped)
            if match is not None:
                outcome = _to_outcome(match.group("outcome"))
                if outcome is not None:
                    results.append(TestResult(pending, outcome))
                    pending = None

    summary = _SUMMARY.search(text)
    reported = int(summary.group("count")) if summary else None
    # No tests and no summary means the suite never ran -- typically an import
    # error in the code under test. That is a real, reportable outcome.
    collection_error = not results and reported in (None, 0)
    return SuiteResult(
        tests=tuple(results), reported_total=reported, collection_error=collection_error
    )
