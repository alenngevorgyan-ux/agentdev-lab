"""Turning one attempt into one recorded outcome.

Scoring is deliberately mechanical. The only evidence admitted is the outcome
of the task's own acceptance suite, the tamper digests taken around the agent's
turn, and the baseline comparison that identifies regressions. There is no
partial credit toward a pass, no model-judged grading, and no path by which an
adapter can report its own success.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .adapters.base import AgentOutcome
from .execution import CommandResult
from .testparse import SuiteResult


class Status(StrEnum):
    """Terminal state of a single attempt."""

    PASSED = "passed"
    FAILED = "failed"
    #: The acceptance suite exceeded the task's timeout.
    TIMEOUT = "timeout"
    #: A protected path changed during the agent's turn. Never counted as a pass.
    TAMPERED = "tampered"
    #: The agent itself could not run to completion (crash, timeout, misconfig).
    AGENT_ERROR = "agent_error"
    #: The harness failed (missing fixture, IO error). Excluded from rates.
    HARNESS_ERROR = "harness_error"


#: Statuses that count toward the denominator of a pass rate. A harness failure
#: is our bug, not a result, so it is excluded rather than counted as a failure.
SCORED_STATUSES = frozenset(
    {Status.PASSED, Status.FAILED, Status.TIMEOUT, Status.TAMPERED, Status.AGENT_ERROR}
)


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
    suite: SuiteResult | None,
    regressions: int,
    protected_before: str,
    protected_after: str,
) -> Score:
    """Decide the outcome of one attempt.

    Precedence is fixed and each step is absolute:

    1. tampering  -- editing the tests is never a pass, whatever they then said
    2. agent error -- an agent that never ran was never measured
    3. timeout
    4. regression -- breaking working behaviour is not success, even if the
       acceptance command happened to exit 0
    5. the acceptance suite's exit code
    """
    if protected_before != protected_after:
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
            reason="acceptance evaluation did not run",
        )

    if verification.timed_out:
        return Score(
            status=Status.TIMEOUT,
            passed=False,
            tampered=False,
            reason="acceptance suite timed out",
        )

    if regressions > 0:
        return Score(
            status=Status.FAILED,
            passed=False,
            tampered=False,
            reason=f"introduced {regressions} regression(s) in previously passing tests",
        )

    if suite is not None and suite.collection_error:
        return Score(
            status=Status.FAILED,
            passed=False,
            tampered=False,
            reason="acceptance suite could not be collected (import or syntax error)",
        )

    if verification.exit_code == 0:
        return Score(
            status=Status.PASSED, passed=True, tampered=False, reason="acceptance suite passed"
        )

    detail = f"{suite.passed}/{suite.total} tests passed" if suite and suite.total else "suite failed"
    return Score(
        status=Status.FAILED,
        passed=False,
        tampered=False,
        reason=f"acceptance suite exited {verification.exit_code}: {detail}",
    )
