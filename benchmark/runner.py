"""Run orchestration: sandbox -> agent -> verify -> score -> record.

The order of operations is the experiment's protocol and is deliberately rigid:

1. Materialise a fresh sandbox from the pinned fixture.
2. Digest the protected paths *before* the agent touches anything.
3. Give the agent its turn.
4. Digest the protected paths again.
5. Run the task's verification command.
6. Score mechanically and append the result.

Nothing between steps 3 and 6 consults the agent's opinion of its own work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .adapters import get_adapter
from .adapters.base import Adapter, AgentOutcome
from .config import RunConfig
from .execution import CommandResult, run_command
from .sandbox import create_sandbox
from .scoring import Score, Status, score_attempt
from .storage import ResultsStore
from .tasks import Task, select_tasks

#: Recorded in place of a digest when the sandbox never reached a hashable state.
UNAVAILABLE = "<unavailable>"


@dataclass
class AttemptResult:
    """In-memory view of one recorded attempt."""

    task_id: str
    attempt_index: int
    score: Score
    agent: AgentOutcome
    verification: CommandResult | None
    total_duration_ms: int
    protected_hash_before: str = UNAVAILABLE
    protected_hash_after: str = UNAVAILABLE
    workspace_hash_before: str = UNAVAILABLE
    workspace_hash_after: str = UNAVAILABLE
    sandbox_path: Path | None = None

    @property
    def status(self) -> Status:
        return self.score.status


@dataclass
class RunResult:
    run_id: int
    run_uid: str
    adapter: str
    attempts: list[AttemptResult]

    @property
    def scored(self) -> list[AttemptResult]:
        return [a for a in self.attempts if a.status is not Status.HARNESS_ERROR]

    @property
    def passed(self) -> int:
        return sum(1 for a in self.attempts if a.score.passed)

    @property
    def pass_rate(self) -> float | None:
        scored = self.scored
        return (self.passed / len(scored)) if scored else None


ProgressHook = Callable[[AttemptResult], None]


def run_attempt(
    task: Task,
    adapter: Adapter,
    *,
    attempt_index: int = 1,
    keep_sandbox: bool = False,
    sandbox_root: Path | None = None,
) -> AttemptResult:
    """Execute a single attempt end to end. Never raises for agent failures."""
    started = time.monotonic()
    sandbox = None
    try:
        sandbox = create_sandbox(task, keep=keep_sandbox, root=sandbox_root)
        protected_before = sandbox.snapshot_protected()
        workspace_before = sandbox.snapshot_tree()

        try:
            agent = adapter.run(task, sandbox)
        except Exception as exc:  # an adapter crash is an agent error, not a harness error
            agent = AgentOutcome(
                completed=False, duration_ms=0, error=f"{type(exc).__name__}: {exc}"
            )

        protected_after = sandbox.snapshot_protected()
        workspace_after = sandbox.snapshot_tree()

        verification: CommandResult | None = None
        # Skip verification when the turn is already void: a tampered workspace
        # or a broken agent yields no measurement worth taking.
        if agent.completed and protected_before == protected_after:
            verification = run_command(
                task.verify.command, cwd=sandbox.path, timeout_sec=task.verify.timeout_sec
            )

        score = score_attempt(
            agent=agent,
            verification=verification,
            protected_before=protected_before,
            protected_after=protected_after,
        )
        return AttemptResult(
            task_id=task.id,
            attempt_index=attempt_index,
            score=score,
            agent=agent,
            verification=verification,
            total_duration_ms=int((time.monotonic() - started) * 1000),
            protected_hash_before=protected_before,
            protected_hash_after=protected_after,
            workspace_hash_before=workspace_before,
            workspace_hash_after=workspace_after,
            sandbox_path=sandbox.path if keep_sandbox else None,
        )
    except Exception as exc:  # sandbox/IO failure: our bug, excluded from rates
        return AttemptResult(
            task_id=task.id,
            attempt_index=attempt_index,
            score=Score(
                status=Status.HARNESS_ERROR,
                passed=False,
                tampered=False,
                reason=f"{type(exc).__name__}: {exc}",
            ),
            agent=AgentOutcome(completed=False, duration_ms=0, error=str(exc)),
            verification=None,
            total_duration_ms=int((time.monotonic() - started) * 1000),
        )
    finally:
        if sandbox is not None:
            sandbox.cleanup()


def _persist(
    store: ResultsStore,
    run_id: int,
    task: Task,
    result: AttemptResult,
) -> None:
    attempt_id = store.record_attempt(
        run_id=run_id,
        task_id=task.id,
        task_fingerprint=task.spec_fingerprint(),
        attempt_index=result.attempt_index,
        status=str(result.status),
        passed=1 if result.score.passed else 0,
        tampered=1 if result.score.tampered else 0,
        reason=result.score.reason,
        verify_exit_code=result.verification.exit_code if result.verification else None,
        verify_duration_ms=result.verification.duration_ms if result.verification else None,
        agent_duration_ms=result.agent.duration_ms,
        total_duration_ms=result.total_duration_ms,
        protected_hash_before=result.protected_hash_before,
        protected_hash_after=result.protected_hash_after,
        workspace_hash_before=result.workspace_hash_before,
        workspace_hash_after=result.workspace_hash_after,
    )
    store.record_logs(
        attempt_id,
        {
            "agent_stdout": result.agent.stdout,
            "agent_stderr": result.agent.stderr,
            "verify_stdout": result.verification.stdout if result.verification else "",
            "verify_stderr": result.verification.stderr if result.verification else "",
        },
    )


def execute_run(
    config: RunConfig,
    store: ResultsStore,
    *,
    tasks: Iterable[Task] | None = None,
    on_attempt: ProgressHook | None = None,
) -> RunResult:
    """Run every selected task ``config.attempts`` times and record the results."""
    adapter = get_adapter(config.adapter)
    selected = list(tasks) if tasks is not None else select_tasks(config.task_ids)
    if not selected:
        raise ValueError("no tasks selected")

    run_id, run_uid = store.start_run(
        adapter=adapter.name,
        adapter_version=adapter.version(),
        attempts_per_task=config.attempts,
        label=config.label,
        notes=config.notes,
    )

    results: list[AttemptResult] = []
    aborted = False
    try:
        for task in selected:
            for index in range(1, config.attempts + 1):
                result = run_attempt(
                    task, adapter, attempt_index=index, keep_sandbox=config.keep_sandboxes
                )
                _persist(store, run_id, task, result)
                results.append(result)
                if on_attempt is not None:
                    on_attempt(result)
    except KeyboardInterrupt:
        aborted = True
        raise
    finally:
        store.finish_run(run_id, status="aborted" if aborted else "completed")

    return RunResult(run_id=run_id, run_uid=run_uid, adapter=adapter.name, attempts=results)
