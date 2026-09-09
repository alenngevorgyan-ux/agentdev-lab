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
from .experiment import check_drift
from .redaction import contains_secret
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


def check_task_determinism(task: Task, *, sandbox_root: Path | None = None) -> CheckResult:
    """Evaluate a pristine fixture twice and require the same verdict.

    The baseline is cached per task fingerprint, which is sound only if a task
    is deterministic. A task that answers differently on two identical runs
    would produce phantom regressions, so it is caught here rather than
    silently becoming noise that looks like a capability difference.
    """
    from .runner import measure_baseline

    first, _ = measure_baseline(task, sandbox_root=sandbox_root, use_cache=False)
    second, _ = measure_baseline(task, sandbox_root=sandbox_root, use_cache=False)
    same = first.satisfied_ids() == second.satisfied_ids() and first.total == second.total
    return CheckResult(
        name=f"{task.id}: evaluates deterministically",
        ok=same,
        detail=""
        if same
        else (
            f"two evaluations of the untouched fixture disagreed: "
            f"{first.passed}/{first.total} then {second.passed}/{second.total}"
        ),
    )


def selfcheck(
    tasks_dir: Path | None = None,
    *,
    sandbox_root: Path | None = None,
    check_determinism: bool = False,
) -> CheckReport:
    """Full harness self-validation across every registered task."""
    report = check_task_definitions(tasks_dir)
    if not report.ok:
        return report
    for task in load_tasks(tasks_dir):
        report.checks.extend(check_task_polarity(task, sandbox_root=sandbox_root))
        if check_determinism:
            report.checks.append(check_task_determinism(task, sandbox_root=sandbox_root))
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

    partial = store.query(
        "SELECT COUNT(*) AS n FROM attempts WHERE notes LIKE 'incomplete per-test parse%'"
    )[0]["n"]
    # A partially parsed suite still has a valid pass/fail, but its per-test
    # metrics understate the truth -- so it is surfaced rather than averaged in.
    report.add(
        "per-test results were fully parsed",
        partial == 0,
        ""
        if partial == 0
        else f"{partial} attempt(s) have partial per-test data; their regression counts "
        "and pass fractions are lower bounds, not measurements",
    )

    unisolated = store.query(
        """
        SELECT r.agent, COUNT(*) AS n
        FROM attempts a JOIN runs r ON r.id = a.run_id
        WHERE r.run_kind = 'measurement' AND a.isolation_active = 0
          AND a.status != 'harness_error'
        GROUP BY r.agent
        """
    )
    # An unisolated measurement cannot support any claim about what the agent
    # could or could not reach, which is the claim this project exists to make.
    report.add(
        "every measurement ran inside an enforced boundary",
        not unisolated,
        ""
        if not unisolated
        else "NON-PUBLISHABLE attempts recorded without isolation: "
        + ", ".join(f"{row['agent']} ({row['n']})" for row in unisolated),
    )

    # Captured output is redacted at the point of capture; this is the check
    # that the choke point actually held for everything already stored.
    leaked = [
        f"attempt {row['attempt_id']} / {row['stream']}"
        for row in store.query("SELECT attempt_id, stream, content FROM attempt_logs")
        if contains_secret(row["content"])
    ]
    leaked += [
        f"run {row['run_uid'][:8]} notes"
        for row in store.query("SELECT run_uid, notes, label FROM runs")
        if contains_secret(row["notes"]) or contains_secret(row["label"])
    ]
    report.add(
        "no credential-shaped value is stored",
        not leaked,
        ""
        if not leaked
        else "credential-shaped values found in stored evidence: " + ", ".join(leaked[:10]),
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


def verify_experiment(store: ResultsStore, experiment) -> CheckReport:
    """The publication gate from docs/comparison-protocol.md.

    Every box is checked against the stored record rather than asserted in
    prose. Failing a box does not make the data worthless -- it makes the honest
    report "measured under these conditions, not publishable as a clean
    comparison", with the failing box named.
    """
    report = CheckReport()
    manifest_hash = experiment.manifest_hash()
    rows = store.query(
        """
        SELECT a.*, r.agent, r.git_dirty, r.protocol_version, r.isolation_active,
               r.publishable, r.run_kind, r.attempts_per_task
        FROM attempts a JOIN runs r ON r.id = a.run_id
        WHERE r.experiment_hash = ?
        """,
        (manifest_hash,),
    )

    report.add(
        "attempts exist for this manifest",
        bool(rows),
        ""
        if rows
        else f"no attempt recorded under manifest hash {manifest_hash[:12]}; "
        "the experiment has not been run",
    )
    if not rows:
        return report

    drift = check_drift(experiment)
    report.add(
        "task fixtures match the frozen manifest",
        not drift,
        "" if not drift else f"fixtures drifted since freezing: {drift}",
    )

    unisolated = [r for r in rows if not r["isolation_active"]]
    report.add(
        "every attempt ran inside an enforced boundary",
        not unisolated,
        "" if not unisolated else f"{len(unisolated)} attempt(s) ran without isolation",
    )

    unpublishable = [r for r in rows if not r["publishable"]]
    report.add(
        "every attempt is publishable",
        not unpublishable,
        "" if not unpublishable else f"{len(unpublishable)} attempt(s) are NON-PUBLISHABLE",
    )

    dirty = [r for r in rows if r["git_dirty"]]
    report.add(
        "every run came from a clean checkout",
        not dirty,
        "" if not dirty else f"{len(dirty)} attempt(s) ran from an uncommitted working tree",
    )

    protocols = {r["protocol_version"] for r in rows}
    report.add(
        "one protocol version across the experiment",
        len(protocols) == 1,
        "" if len(protocols) == 1 else f"attempts span protocol versions {sorted(protocols)}",
    )

    per_task_fingerprints: dict[str, set[str]] = {}
    for row in rows:
        per_task_fingerprints.setdefault(row["task_id"], set()).add(row["task_fingerprint"])
    inconsistent = [task for task, seen in per_task_fingerprints.items() if len(seen) > 1]
    report.add(
        "one fixture per task across the experiment",
        not inconsistent,
        "" if not inconsistent else f"tasks measured against more than one fixture: {inconsistent}",
    )

    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        counts[(row["agent"], row["task_id"])] = counts.get((row["agent"], row["task_id"]), 0) + 1
    # Running one agent more often than another on the same task is a
    # cherry-picking vector, so any deviation from the manifest is named.
    uneven = sorted(
        f"{agent}/{task}={count}"
        for (agent, task), count in counts.items()
        if count != experiment.attempts_per_task
    )
    report.add(
        "attempts per task match the manifest",
        not uneven,
        "" if not uneven else f"uneven attempt counts: {uneven[:8]}",
    )

    samples = [r for r in rows if r["run_kind"] == "development_sample"]
    report.add(
        "no synthetic row is inside the experiment",
        not samples,
        "" if not samples else f"{len(samples)} synthetic attempt(s) recorded under this manifest",
    )

    for agent in sorted({r["agent"] for r in rows}):
        agent_rows = [r for r in rows if r["agent"] == agent]
        rate_limited = [
            r for r in agent_rows
            if r["status"] == "agent_error" and "rate limit" in (r["reason"] or "").lower()
        ]
        share = len(rate_limited) / len(agent_rows)
        report.add(
            f"{agent}: rate-limit share below 5%",
            share < 0.05,
            ""
            if share < 0.05
            else f"{share:.0%} of attempts were rate limited; the comparison is void "
            "(a throttled agent is measured on its quota, not its capability)",
        )
        timeouts = [r for r in agent_rows if r["status"] == "timeout"]
        timeout_share = len(timeouts) / len(agent_rows)
        report.add(
            f"{agent}: timeout share below 10%",
            timeout_share < 0.10,
            ""
            if timeout_share < 0.10
            else f"{timeout_share:.0%} of attempts timed out; the budget was too tight, "
            "raise it and re-run every agent",
        )

    return report
