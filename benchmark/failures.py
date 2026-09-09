"""Failure taxonomy for coding agents, and an evidence-based classifier.

The taxonomy names *how* an attempt failed, which a pass rate cannot express.
"Claude Code fails 40% of refactoring tasks" is a number; "of those failures,
two thirds are under-editing and one third is hallucinated APIs" is a finding.

The classifier is a **heuristic**. It reads only recorded evidence (test
outcomes, diff statistics, captured output) and is deliberately conservative:
when the evidence does not clearly indicate a category it returns
``UNCLASSIFIED`` rather than guessing. Every stored classification records
whether it came from this classifier or from a human, so a hand-labelled study
is never silently mixed with machine labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureCategory(StrEnum):
    """Why an attempt did not succeed."""

    NONE = "none"                             # the attempt passed
    MISUNDERSTOOD_REQUIREMENT = "misunderstood_requirement"
    INCOMPLETE_IMPLEMENTATION = "incomplete_implementation"
    WRONG_LOCATION = "wrong_location"
    REGRESSION = "regression"
    HALLUCINATED_API = "hallucinated_api"
    DEPENDENCY_REASONING = "dependency_reasoning"
    CONTEXT_LOSS = "context_loss"
    TEST_GAMING = "test_gaming"
    OVER_EDITING = "over_editing"
    UNDER_EDITING = "under_editing"
    TIMEOUT = "timeout"
    ENVIRONMENT_FAILURE = "environment_failure"
    UNCLASSIFIED = "unclassified"


#: Human-readable definitions, mirrored into the ``failure_categories`` table
#: so SQL analyses can join against them.
TAXONOMY: dict[FailureCategory, str] = {
    FailureCategory.NONE: "The attempt passed; no failure to classify.",
    FailureCategory.MISUNDERSTOOD_REQUIREMENT: (
        "The agent produced working code that solves a different problem than the one stated."
    ),
    FailureCategory.INCOMPLETE_IMPLEMENTATION: (
        "The agent implemented part of the requirement; some acceptance tests still fail."
    ),
    FailureCategory.WRONG_LOCATION: (
        "The agent edited files unrelated to the requirement and left the relevant ones untouched."
    ),
    FailureCategory.REGRESSION: (
        "The agent broke behaviour that worked before its turn."
    ),
    FailureCategory.HALLUCINATED_API: (
        "The agent called a function, module, or attribute that does not exist."
    ),
    FailureCategory.DEPENDENCY_REASONING: (
        "The agent failed to trace how a change propagates across modules or call sites."
    ),
    FailureCategory.CONTEXT_LOSS: (
        "The agent lost track of earlier constraints or of its own prior edits mid-task."
    ),
    FailureCategory.TEST_GAMING: (
        "The agent edited, skipped, or weakened the tests instead of satisfying them."
    ),
    FailureCategory.OVER_EDITING: (
        "The agent rewrote far more of the repository than the task required."
    ),
    FailureCategory.UNDER_EDITING: (
        "The agent changed little or nothing, leaving the task essentially untouched."
    ),
    FailureCategory.TIMEOUT: "The agent or its verification exceeded the time budget.",
    FailureCategory.ENVIRONMENT_FAILURE: (
        "The agent or harness could not run: missing credentials, tooling, or a crash."
    ),
    FailureCategory.UNCLASSIFIED: (
        "Evidence was insufficient for a confident automatic label; needs human review."
    ),
}

#: A diff this large relative to the task's expectation reads as over-editing.
OVER_EDIT_FILE_MULTIPLIER = 3
OVER_EDIT_MIN_FILES = 4
#: Fewer changed lines than this reads as the agent barely engaging.
UNDER_EDIT_LINE_THRESHOLD = 3

#: Substrings in captured output that identify a specific mechanical failure.
_HALLUCINATION_MARKERS = (
    "modulenotfounderror",
    "importerror",
    "has no attribute",
    "is not defined",
    "no module named",
)
_ENVIRONMENT_MARKERS = (
    "command not found",
    "permission denied",
    "not logged in",
    "invalid api key",
    "connection refused",
)


@dataclass(frozen=True)
class FailureEvidence:
    """Everything the classifier is allowed to look at."""

    status: str
    tests_total: int
    tests_passed: int
    regressions: int
    files_changed: int
    lines_changed: int
    expected_files_touched: int
    expected_files_declared: int
    output: str = ""

    @property
    def all_passed(self) -> bool:
        return self.tests_total > 0 and self.tests_passed == self.tests_total


def classify(evidence: FailureEvidence) -> FailureCategory:
    """Label a failure from recorded evidence, or return ``UNCLASSIFIED``.

    Ordered from the most mechanically certain signal to the least. Anything
    that cannot be established from evidence -- notably distinguishing a
    misunderstood requirement from an incomplete one -- is left to a human.
    """
    status = evidence.status
    if status == "passed":
        return FailureCategory.NONE
    if status == "tampered":
        return FailureCategory.TEST_GAMING
    if status == "timeout":
        return FailureCategory.TIMEOUT
    if status in ("agent_error", "harness_error"):
        return FailureCategory.ENVIRONMENT_FAILURE

    lowered = evidence.output.lower()
    if any(marker in lowered for marker in _ENVIRONMENT_MARKERS):
        return FailureCategory.ENVIRONMENT_FAILURE

    # A regression is a distinct product harm: something that worked no longer
    # does. It outranks "some tests fail", which is true of every failure.
    if evidence.regressions > 0:
        return FailureCategory.REGRESSION

    if any(marker in lowered for marker in _HALLUCINATION_MARKERS):
        return FailureCategory.HALLUCINATED_API

    if evidence.lines_changed <= UNDER_EDIT_LINE_THRESHOLD:
        return FailureCategory.UNDER_EDITING

    if (
        evidence.expected_files_declared > 0
        and evidence.expected_files_touched == 0
        and evidence.files_changed > 0
    ):
        return FailureCategory.WRONG_LOCATION

    if evidence.expected_files_declared > 0 and evidence.files_changed >= max(
        OVER_EDIT_MIN_FILES, evidence.expected_files_declared * OVER_EDIT_FILE_MULTIPLIER
    ):
        return FailureCategory.OVER_EDITING

    if evidence.tests_total > 0 and 0 < evidence.tests_passed < evidence.tests_total:
        return FailureCategory.INCOMPLETE_IMPLEMENTATION

    # Distinguishing "solved the wrong problem" from "solved nothing" needs
    # judgement the evidence does not carry.
    return FailureCategory.UNCLASSIFIED
