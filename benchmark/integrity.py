"""Experimental integrity checks.

These are the checks that make a number trustworthy. They answer three
questions that a pass rate on its own cannot:

* Is every task well-formed, solvable, and actually failing before work starts?
* Did any agent reach the tests it was being measured against?
* Has the record been edited since it was written?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .adapters import NoopAdapter, OracleAdapter
from .runner import run_attempt
from .scoring import Status
from .storage import ResultsStore
from .tasks import Task, TaskSpecError, load_tasks


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class CheckReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, ok=ok, detail=detail))

    def render(self) -> str:
        lines = [
            f"[{'PASS' if check.ok else 'FAIL'}] {check.name}"
            + (f"\n         {check.detail}" if check.detail else "")
            for check in self.checks
        ]
        failures = sum(1 for check in self.checks if not check.ok)
        lines.append("")
        lines.append(
            f"{len(self.checks) - failures}/{len(self.checks)} checks passed"
            + ("" if self.ok else f" -- {failures} FAILED")
        )
        return "\n".join(lines)


def check_task_definitions(tasks_dir: Path | None = None) -> CheckReport:
    """Static validation: specs parse, fixtures and reference solutions exist."""
    report = CheckReport()
    try:
        tasks = load_tasks(tasks_dir)
    except TaskSpecError as exc:
        report.add("task specs parse", False, str(exc))
        return report

    report.add("task specs parse", True, f"{len(tasks)} task(s) loaded")
    report.add("task registry is non-empty", bool(tasks), "" if tasks else "no tasks found")

    for task in tasks:
        report.add(
            f"{task.id}: has reference solution",
            task.has_reference_solution,
            "" if task.has_reference_solution else f"missing {task.solution_dir}/",
        )
        report.add(
            f"{task.id}: declares protected paths",
            bool(task.protected_paths),
            "" if task.protected_paths else "protected_paths must not be empty",
        )
    return report


def check_task_polarity(task: Task, *, sandbox_root: Path | None = None) -> list[CheckResult]:
    """Dynamic validation of one task using the two control adapters.

    The noop adapter must fail the task (otherwise the task measures nothing)
    and the oracle must pass it (otherwise the task is unsolvable or its
    verification is broken).
    """
    results: list[CheckResult] = []

    noop = run_attempt(task, NoopAdapter(), sandbox_root=sandbox_root)
    results.append(
        CheckResult(
            name=f"{task.id}: fails before any work (noop control)",
            ok=noop.status is Status.FAILED,
            detail="" if noop.status is Status.FAILED else f"noop produced status={noop.status}",
        )
    )

    oracle = run_attempt(task, OracleAdapter(), sandbox_root=sandbox_root)
    detail = ""
    if oracle.status is not Status.PASSED:
        stderr = oracle.verification.stderr if oracle.verification else ""
        detail = f"oracle produced status={oracle.status}: {oracle.score.reason}\n{stderr[-1500:]}"
    results.append(
        CheckResult(
            name=f"{task.id}: solvable and verifiable (oracle control)",
            ok=oracle.status is Status.PASSED,
            detail=detail,
        )
    )
    return results


def selfcheck(tasks_dir: Path | None = None, *, sandbox_root: Path | None = None) -> CheckReport:
    """Full harness self-validation across every registered task."""
    report = check_task_definitions(tasks_dir)
    if not report.ok:
        return report
    for task in load_tasks(tasks_dir):
        report.checks.extend(check_task_polarity(task, sandbox_root=sandbox_root))
    return report


def check_recorded_results(store: ResultsStore) -> CheckReport:
    """Audit the stored record for signs of editing or incomparable data."""
    report = CheckReport()

    contradictions = store.query(
        "SELECT COUNT(*) AS n FROM attempts WHERE (passed = 1) != (status = 'passed') OR (passed = 1 AND tampered = 1)"
    )[0]["n"]
    report.add(
        "no contradictory result rows",
        contradictions == 0,
        "" if contradictions == 0 else f"{contradictions} row(s) claim a pass they did not earn",
    )

    orphans = store.query(
        "SELECT COUNT(*) AS n FROM attempts a LEFT JOIN runs r ON r.id = a.run_id WHERE r.id IS NULL"
    )[0]["n"]
    report.add(
        "every attempt belongs to a run",
        orphans == 0,
        "" if orphans == 0 else f"{orphans} orphaned attempt row(s)",
    )

    drift = store.fixture_drift()
    report.add(
        "task fixtures stable across runs",
        not drift,
        ""
        if not drift
        else "task definitions changed between runs; results either side are not comparable: "
        + ", ".join(f"{row['task_id']} ({row['distinct_fingerprints']} versions)" for row in drift),
    )

    dirty = store.query(
        "SELECT COUNT(*) AS n FROM runs WHERE git_dirty = 1 AND status = 'completed'"
    )[0]["n"]
    # A dirty run is disclosed, not rejected: local iteration is legitimate,
    # silently publishing it as reproducible is not.
    report.add(
        "recorded runs are reproducible (clean checkout)",
        True,
        "" if dirty == 0 else f"note: {dirty} run(s) were made from an uncommitted working tree",
    )

    # Only real measurements are audited here: a control legitimately changes
    # nothing, and synthetic rows are disclosed by their own check below.
    inert = store.query(
        """
        SELECT r.run_uid, r.agent, a.task_id, a.attempt_index
        FROM attempts a JOIN runs r ON r.id = a.run_id
        WHERE a.workspace_hash_before = a.workspace_hash_after
          AND a.status != 'harness_error'
          AND r.run_kind = 'measurement'
        ORDER BY a.created_at DESC
        """
    )
    # An agent that changed nothing almost always failed to start (auth, quota,
    # a crash swallowed by a zero exit code). Scoring that as a capability
    # failure would be a fabricated measurement, so it is surfaced loudly.
    report.add(
        "every measured attempt actually changed the workspace",
        not inert,
        ""
        if not inert
        else "attempts recorded with no file changes -- these are not capability measurements:\n         "
        + "\n         ".join(
            f"{row['agent']} / {row['task_id']} #{row['attempt_index']} ({row['run_uid'][:8]})"
            for row in inert
        ),
    )

    samples = store.query(
        "SELECT COUNT(*) AS n FROM attempts a JOIN runs r ON r.id = a.run_id "
        "WHERE r.run_kind = 'development_sample'"
    )[0]["n"]
    # Synthetic rows are allowed to exist -- the analytics stack needs shape to
    # be built against -- but their presence is always announced.
    report.add(
        "synthetic development rows are disclosed",
        True,
        ""
        if samples == 0
        else f"note: {samples} synthetic attempt(s) present. They are excluded from "
        "'measurement' analyses and must never be quoted as evidence.",
    )

    tampered = store.tampered_attempts()
    report.add(
        "no attempt modified protected test paths",
        not tampered,
        ""
        if not tampered
        else "\n         ".join(
            f"{row['adapter']} / {row['task_id']} #{row['attempt_index']} ({row['run_uid'][:8]})"
            for row in tampered
        ),
    )
    return report
