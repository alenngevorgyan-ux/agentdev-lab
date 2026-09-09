"""Turning one attempt into one recorded outcome.

Scoring is deliberately mechanical. The only evidence admitted is the exit code
of the task's own verification command plus the tamper digests taken around the
agent's turn. There is no partial credit, no model-judged grading, and no path
by which an adapter can report its own success.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .adapters.base import AgentOutcome
from .execution import CommandResult


class Status(StrEnum):
    """Terminal state of a single attempt."""

    PASSED = "passed"
    FAILED = "failed"
    #: The verification command exceeded the task's timeout.
    TIMEOUT = "timeout"
    #: A protected path changed during the agent's turn. Never counted as a pass.
    TAMPERED = "tampered"
    #: The agent itself could not run to completion (crash, timeout, misconfig).
    AGENT_ERROR = "agent_error"
    #: The harness failed (missing fixture, IO error). Excluded from rates.
    HARNESS_ERROR = "harness_error"


#: Statuses that count toward the denominator of a pass rate. A harness failure
#: is our bug, not a result, so it is excluded rather than counted as a failure.
SCORED_STATUSES = frozenset({Status.PASSED, Status.FAILED, Status.TIMEOUT, Status.TAMPERED, Status.AGENT_ERROR})


@dataclass(frozen=True)
class Score:
    status: Status
    passed: bool
    tampered: bool
    reason: str

    def __post_init__(self) -> None:
        if self.passed and self.status is not Status.PASSED:
            raise ValueError("passed=True is only valid for Status.PASSED")


def score_attempt(
    *,
    agent: AgentOutcome,
    verification: CommandResult | None,
    protected_before: str,
    protected_after: str,
) -> Score:
    """Decide the outcome of one attempt.

    Tamper detection is evaluated first and is absolute: an attempt that
    modified a protected test path is never a pass, no matter what the
    verification command then reported.
    """
    tampered = protected_before != protected_after
    if tampered:
        return Score(
            status=Status.TAMPERED,
            passed=False,
            tampered=True,
            reason="protected paths were modified during the agent's turn",
        )

    if not agent.completed:
        return Score(
            status=Status.AGENT_ERROR,
            passed=False,
            tampered=False,
            reason=agent.error or "agent did not complete",
        )

    if verification is None:
        return Score(
            status=Status.HARNESS_ERROR,
            passed=False,
            tampered=False,
            reason="verification did not run",
        )

    if verification.timed_out:
        return Score(
            status=Status.TIMEOUT,
            passed=False,
            tampered=False,
            reason="verification command timed out",
        )

    if verification.exit_code == 0:
        return Score(status=Status.PASSED, passed=True, tampered=False, reason="verification succeeded")

    return Score(
        status=Status.FAILED,
        passed=False,
        tampered=False,
        reason=f"verification exited {verification.exit_code}",
    )
