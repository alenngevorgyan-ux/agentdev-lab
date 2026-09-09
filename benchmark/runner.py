"""Run orchestration: baseline -> agent -> hidden tests -> evaluate -> record.

The agent turn and the evaluation both execute inside an isolation boundary
(``benchmark.isolation``). The agent gets network access only if its adapter
declares it needs it; evaluation never does, because a task whose result
depends on the network is not deterministic. Hidden acceptance tests are
applied by the host *between* those two boundaries, so they are absent from the
filesystem the agent saw.

The order of operations is the experiment's protocol and is deliberately rigid:

1.  Materialise a fresh sandbox from the pinned fixture.
2.  Evaluate a *pristine* copy to learn which tests passed before any work.
3.  Digest the protected paths before the agent touches anything.
4.  Give the agent its turn. It never sees the hidden acceptance tests.
5.  Digest the protected paths again; compute the diff against the fixture.
6.  Overlay the hidden tests and evaluate.
7.  Compare against the baseline to identify regressions.
8.  Score mechanically, classify the failure, append an immutable record.

Nothing between steps 4 and 8 consults the agent's opinion of its own work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .adapters import get_adapter
from .adapters.base import Adapter, AgentOutcome
from .config import RunConfig
from .diffstats import DiffStats, compute_diff
from .execution import CommandResult
from .failures import FailureCategory, FailureEvidence, classify
from .isolation import (
    NETWORK_ALLOWED,
    IsolationBackend,
    IsolationReport,
    IsolationUnavailable,
    SessionSpec,
    select_backend,
)
from .sandbox import Sandbox, create_sandbox
from .scoring import Score, Status, score_attempt
from .storage import ResultsStore, utc_now
from .tasks import Task, select_tasks
from .testparse import SuiteResult, parse_unittest_output

#: Recorded in place of a digest when the sandbox never reached a hashable state.
UNAVAILABLE = "<unavailable>"

#: Baseline evaluations keyed by task fingerprint. The fingerprint covers the
#: spec, the fixture and the hidden tests, so two tasks sharing a key are
#: byte-identical experiments; tasks are required to be deterministic, so their
#: baseline cannot differ between two evaluations within one process.
_BASELINE_CACHE: dict[str, tuple[SuiteResult, str]] = {}


def clear_baseline_cache() -> None:
    """Drop cached baselines. Used by tests that mutate fixtures in place."""
    _BASELINE_CACHE.clear()


@dataclass
class AttemptResult:
    """In-memory view of one recorded attempt."""

    task_id: str
    attempt_index: int
    score: Score
    agent: AgentOutcome
    verification: CommandResult | None
    total_duration_ms: int
    suite: SuiteResult | None = None
    baseline: SuiteResult | None = None
    regressions: tuple[str, ...] = field(default_factory=tuple)
    diff: DiffStats = field(default_factory=DiffStats)
    failure_category: FailureCategory = FailureCategory.UNCLASSIFIED
    protected_hash_before: str = UNAVAILABLE
    protected_hash_after: str = UNAVAILABLE
    workspace_hash_before: str = UNAVAILABLE
    workspace_hash_after: str = UNAVAILABLE
    baseline_output: str = ""
    isolation: IsolationReport | None = None
    #: Digest of the exact tree handed to the agent, before any hidden test.
    fixture_hash: str = ""
    started_at: str = ""
    finished_at: str = ""
    sandbox_path: Path | None = None

    @property
    def status(self) -> Status:
        return self.score.status

    @property
    def tests_total(self) -> int:
        return self.suite.effective_total if self.suite else 0

    @property
    def parse_note(self) -> str:
        """A note when per-test parsing was incomplete, so metrics stay honest."""
        if self.suite is None or self.suite.parse_is_complete:
            return ""
        return (
            f"incomplete per-test parse: {self.suite.total} of "
            f"{self.suite.reported_total} outcomes recovered; per-test rows and "
            "regression detection are partial for this attempt"
        )

    @property
    def tests_passed(self) -> int:
        return self.suite.passed if self.suite else 0


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


def evaluate(
    path: Path, task: Task, backend: IsolationBackend
) -> tuple[CommandResult, SuiteResult]:
    """Run a task's acceptance command in ``path`` and parse per-test outcomes.

    Evaluation runs inside the boundary with the network denied: the verdict
    must depend on the workspace and nothing else. It is also the host's
    verdict, never the agent's -- the agent has already exited by this point.
    """
    with backend.session(SessionSpec(workspace=path, network=False)) as session:
        result = session.run(task.verify.command, timeout_sec=task.verify.timeout_sec)
    # unittest writes its per-test lines to stderr; other runners use stdout.
    suite = parse_unittest_output(result.stdout + "\n" + result.stderr)
    return result, suite


def _prepare_evaluation(sandbox: Sandbox, task: Task) -> list[str]:
    """Overlay the hidden acceptance tests, returning the paths written."""
    if not task.has_hidden_tests:
        return []
    return sandbox.apply_overlay(task.acceptance_path)


def measure_baseline(
    task: Task,
    *,
    sandbox_root: Path | None = None,
    use_cache: bool = True,
    backend: IsolationBackend | None = None,
) -> tuple[SuiteResult, str]:
    """Evaluate the untouched fixture to learn which tests passed beforehand.

    Without this, "the agent broke something" is unprovable: a test failing
    after the attempt might simply have been failing all along.
    """
    key = task.spec_fingerprint()
    if use_cache and key in _BASELINE_CACHE:
        return _BASELINE_CACHE[key]

    resolved = backend or select_backend()
    with create_sandbox(task, root=sandbox_root) as pristine:
        _prepare_evaluation(pristine, task)
        result, suite = evaluate(pristine.path, task, resolved)
    baseline = (suite, result.stdout + "\n" + result.stderr)
    if use_cache:
        _BASELINE_CACHE[key] = baseline
    return baseline


def run_attempt(
    task: Task,
    adapter: Adapter,
    *,
    attempt_index: int = 1,
    keep_sandbox: bool = False,
    sandbox_root: Path | None = None,
    baseline: SuiteResult | None = None,
    baseline_output: str = "",
    backend: IsolationBackend | None = None,
) -> AttemptResult:
    """Execute a single attempt end to end. Never raises for agent failures."""
    started = time.monotonic()
    started_at = utc_now()
    sandbox = None
    resolved = backend or select_backend()
    isolation = resolved.probe()
    try:
        if baseline is None:
            baseline, baseline_output = measure_baseline(
                task, sandbox_root=sandbox_root, backend=resolved
            )

        sandbox = create_sandbox(task, keep=keep_sandbox, root=sandbox_root)
        protected_before = sandbox.snapshot_protected()
        workspace_before = sandbox.snapshot_tree()

        # The agent's turn happens inside the boundary. Controls act host-side
        # -- they are part of the apparatus -- and the record says so rather
        # than claiming an isolation property they never exercised.
        spec = SessionSpec(
            workspace=sandbox.path,
            network=adapter.requires_network,
            secrets=adapter.credentials(),
            toolchain_paths=adapter.toolchain_paths(),
        )
        try:
            with resolved.session(spec) as session:
                sandbox.session = session
                isolation = session.report
                try:
                    agent = adapter.run(task, sandbox)
                except Exception as exc:  # an adapter crash is an agent error
                    agent = AgentOutcome(
                        completed=False, duration_ms=0, error=f"{type(exc).__name__}: {exc}"
                    )
        finally:
            sandbox.session = None

        protected_after = sandbox.snapshot_protected()
        workspace_after = sandbox.snapshot_tree()
        # Measured before the hidden tests land, so the overlay is never
        # mistaken for the agent's own edits.
        diff = compute_diff(task.workspace_path, sandbox.path)

        verification: CommandResult | None = None
        suite: SuiteResult | None = None
        regressions: tuple[str, ...] = ()
        # A tampered or broken attempt yields no measurement worth taking.
        if agent.completed and protected_before == protected_after:
            # Hidden tests land only now, after the agent has exited.
            _prepare_evaluation(sandbox, task)
            verification, suite = evaluate(sandbox.path, task, resolved)
            regressions = tuple(sorted(baseline.satisfied_ids() - suite.satisfied_ids()))

        score = score_attempt(
            agent=agent,
            verification=verification,
            suite=suite,
            regressions=len(regressions),
            protected_before=protected_before,
            protected_after=protected_after,
        )
        result = AttemptResult(
            task_id=task.id,
            attempt_index=attempt_index,
            score=score,
            agent=agent,
            verification=verification,
            total_duration_ms=int((time.monotonic() - started) * 1000),
            suite=suite,
            baseline=baseline,
            regressions=regressions,
            diff=diff,
            protected_hash_before=protected_before,
            protected_hash_after=protected_after,
            workspace_hash_before=workspace_before,
            workspace_hash_after=workspace_after,
            baseline_output=baseline_output,
            isolation=isolation,
            fixture_hash=workspace_before,
            started_at=started_at,
            finished_at=utc_now(),
            sandbox_path=sandbox.path if keep_sandbox else None,
        )
        result.failure_category = classify(_evidence(task, result))
        return result
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
            failure_category=FailureCategory.ENVIRONMENT_FAILURE,
            isolation=isolation,
            started_at=started_at,
            finished_at=utc_now(),
        )
    finally:
        if sandbox is not None:
            sandbox.cleanup()


def _evidence(task: Task, result: AttemptResult) -> FailureEvidence:
    output = "\n".join(
        part
        for part in (
            result.agent.stdout,
            result.agent.stderr,
            result.verification.stdout if result.verification else "",
            result.verification.stderr if result.verification else "",
        )
        if part
    )
    return FailureEvidence(
        status=str(result.status),
        tests_total=result.tests_total,
        tests_passed=result.tests_passed,
        regressions=len(result.regressions),
        files_changed=result.diff.files_changed,
        lines_changed=result.diff.lines_changed,
        expected_files_touched=result.diff.touched(task.expected_files),
        expected_files_declared=len(task.expected_files),
        output=output,
    )


def _persist(store: ResultsStore, run_id: int, task: Task, result: AttemptResult) -> None:
    isolation = result.isolation
    baseline_ids = result.baseline.satisfied_ids() if result.baseline else frozenset()
    hidden_ids = _hidden_test_ids(task)

    attempt_id = store.record_attempt(
        run_id=run_id,
        task_id=task.id,
        task_fingerprint=task.spec_fingerprint(),
        attempt_index=result.attempt_index,
        status=str(result.status),
        passed=1 if result.score.passed else 0,
        tampered=1 if result.score.tampered else 0,
        failure_category=str(result.failure_category),
        classification_source="auto",
        reason=result.score.reason,
        tests_total=result.tests_total,
        tests_passed=result.tests_passed,
        baseline_passed=len(baseline_ids),
        regressions=len(result.regressions),
        files_changed=result.diff.files_changed,
        lines_added=result.diff.lines_added,
        lines_deleted=result.diff.lines_deleted,
        expected_files_touched=result.diff.touched(task.expected_files),
        fixture_hash=result.fixture_hash,
        isolation_active=1 if (isolation and isolation.active) else 0,
        network_policy=isolation.network_policy if isolation else "unknown",
        started_at=result.started_at,
        finished_at=result.finished_at,
        tool_calls=result.agent.metadata.get("tool_calls"),
        num_turns=result.agent.metadata.get("num_turns"),
        cost_usd=result.agent.metadata.get("cost_usd"),
        human_interventions=int(result.agent.metadata.get("human_interventions", 0)),
        verify_exit_code=result.verification.exit_code if result.verification else None,
        verify_duration_ms=result.verification.duration_ms if result.verification else None,
        agent_duration_ms=result.agent.duration_ms,
        total_duration_ms=result.total_duration_ms,
        protected_hash_before=result.protected_hash_before,
        protected_hash_after=result.protected_hash_after,
        workspace_hash_before=result.workspace_hash_before,
        workspace_hash_after=result.workspace_hash_after,
        notes=result.parse_note,
    )

    if result.suite is not None:
        store.record_tests(
            attempt_id,
            [
                (
                    test.test_id,
                    str(test.outcome),
                    1 if test.test_id in baseline_ids else 0,
                    1 if any(test.test_id.startswith(prefix) for prefix in hidden_ids) else 0,
                )
                for test in result.suite.tests
            ],
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


def _hidden_test_ids(task: Task) -> tuple[str, ...]:
    """Dotted module prefixes contributed by the hidden acceptance overlay."""
    if not task.has_hidden_tests:
        return ()
    prefixes = []
    for path in task.acceptance_path.rglob("*.py"):
        relative = path.relative_to(task.acceptance_path).with_suffix("")
        prefixes.append(".".join(relative.parts))
    return tuple(prefixes)


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

    backend = select_backend(config.isolation)
    isolation = backend.probe()
    # A control never enters the boundary, so it is never marked publishable as
    # an isolated agent measurement, however strong the backend happens to be.
    publishable = bool(isolation.publishable and not adapter.is_control)

    store.register_tasks(selected)
    run_id, run_uid = store.start_run(
        adapter=adapter.name,
        agent=config.agent or adapter.name,
        model=config.model or "unspecified",
        model_resolved=None,
        agent_flags=" ".join(adapter.describe_flags()),
        agent_timeout_sec=getattr(adapter, "timeout_sec", None),
        isolation_backend=isolation.backend,
        isolation_version=isolation.version,
        isolation_active=isolation.active,
        publishable=publishable,
        network_policy=(
            NETWORK_ALLOWED if adapter.requires_network else isolation.network_policy
        ),
        adapter_version=adapter.version(),
        attempts_per_task=config.attempts,
        run_kind=config.run_kind,
        label=config.label,
        notes=config.notes,
    )

    results: list[AttemptResult] = []
    aborted = False
    try:
        for task in selected:
            # Measured once per task per run: the fixture is identical for every
            # attempt, so re-measuring it would only add noise and cost.
            baseline, baseline_output = measure_baseline(task, backend=backend)
            for index in range(1, config.attempts + 1):
                result = run_attempt(
                    task,
                    adapter,
                    attempt_index=index,
                    keep_sandbox=config.keep_sandboxes,
                    baseline=baseline,
                    baseline_output=baseline_output,
                    backend=backend,
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
