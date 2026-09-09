"""Command-line interface: ``python3 -m benchmark <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .adapters import CONTROL_ADAPTERS, available_adapters, get_adapter
from .config import RunConfig, db_path
from .integrity import check_recorded_results, selfcheck
from .report import leaderboard, render_table, run_report, run_report_json
from .runner import AttemptResult, execute_run
from .scoring import Status
from .storage import ResultsStore
from .tasks import TaskSpecError, load_tasks, select_tasks

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def _print_attempt(result: AttemptResult) -> None:
    marker = {
        Status.PASSED: "PASS",
        Status.FAILED: "FAIL",
        Status.TIMEOUT: "TIME",
        Status.TAMPERED: "TAMPER",
        Status.AGENT_ERROR: "AGENT!",
        Status.HARNESS_ERROR: "HARNESS!",
    }[result.status]
    print(
        f"  [{marker:>8}] {result.task_id} #{result.attempt_index} "
        f"({result.total_duration_ms / 1000:.1f}s) {result.score.reason}",
        flush=True,
    )


def cmd_list(args: argparse.Namespace) -> int:
    tasks = load_tasks()
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": task.id,
                        "title": task.title,
                        "category": task.category,
                        "difficulty": task.difficulty,
                        "tags": list(task.tags),
                        "acceptance_criteria": list(task.acceptance_criteria),
                        "expected_files": list(task.expected_files),
                        "has_hidden_tests": task.has_hidden_tests,
                        "protected_paths": list(task.protected_paths),
                        "fingerprint": task.spec_fingerprint(),
                    }
                    for task in tasks
                ],
                indent=2,
            )
        )
        return EXIT_OK
    if not tasks:
        print("no tasks registered")
        return EXIT_OK
    print(
        render_table(
            ["id", "difficulty", "category", "hidden", "title"],
            [
                [
                    task.id,
                    task.difficulty,
                    task.category,
                    "yes" if task.has_hidden_tests else "no",
                    task.title,
                ]
                for task in tasks
            ],
        )
    )
    print(f"\n{len(tasks)} task(s)")
    return EXIT_OK


def cmd_adapters(_: argparse.Namespace) -> int:
    rows = []
    for name in available_adapters():
        adapter = get_adapter(name)
        role = "control" if name in CONTROL_ADAPTERS else "agent under test"
        rows.append([name, role, adapter.version()])
    print(render_table(["adapter", "role", "version"], rows))
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    config = RunConfig(
        adapter=args.adapter,
        task_ids=tuple(args.task),
        attempts=args.attempts,
        keep_sandboxes=args.keep_sandboxes,
        notes=args.notes,
        label=args.label,
        agent=args.agent,
        model=args.model,
        run_kind="control" if args.adapter in CONTROL_ADAPTERS else "measurement",
    )
    try:
        tasks = select_tasks(config.task_ids)
    except TaskSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.category:
        tasks = [task for task in tasks if task.category in set(args.category)]
    if args.difficulty:
        tasks = [task for task in tasks if task.difficulty in set(args.difficulty)]
    if not tasks:
        print("error: no tasks match the given filters", file=sys.stderr)
        return EXIT_USAGE

    print(
        f"running {len(tasks)} task(s) x {config.attempts} attempt(s) "
        f"with adapter '{config.adapter}'"
    )
    with ResultsStore(args.db) as store:
        result = execute_run(config, store, tasks=tasks, on_attempt=_print_attempt)
        print()
        print(run_report(store, result.run_uid))

    rate = result.pass_rate
    print(f"\nrun uid: {result.run_uid}")
    # Exit status reports whether the *harness* worked, not whether the agent
    # scored well. A low score is a finding, not a command failure.
    harness_errors = [a for a in result.attempts if a.status is Status.HARNESS_ERROR]
    if harness_errors:
        print(f"error: {len(harness_errors)} harness error(s)", file=sys.stderr)
        return EXIT_FAILURE
    if rate is not None:
        print(f"pass rate: {rate * 100:.1f}%")
    return EXIT_OK


def cmd_selfcheck(args: argparse.Namespace) -> int:
    report = selfcheck()
    print(report.render())
    return EXIT_OK if report.ok else EXIT_FAILURE


def cmd_verify_integrity(args: argparse.Namespace) -> int:
    definitions = selfcheck() if args.deep else None
    path = args.db or db_path()
    ok = True

    if definitions is not None:
        print(definitions.render())
        print()
        ok = definitions.ok

    if not Path(path).exists():
        print(f"no results database at {path}; nothing recorded to audit")
        return EXIT_OK if ok else EXIT_FAILURE

    with ResultsStore(Path(path)) as store:
        report = check_recorded_results(store)
    print(report.render())
    return EXIT_OK if (ok and report.ok) else EXIT_FAILURE


def cmd_report(args: argparse.Namespace) -> int:
    with ResultsStore(args.db) as store:
        if args.run:
            print(run_report_json(store, args.run) if args.json else run_report(store, args.run))
            return EXIT_OK
        if args.leaderboard:
            print(leaderboard(store))
            return EXIT_OK
        runs = store.latest_runs(args.limit)
        if not runs:
            print("no runs recorded yet")
            return EXIT_OK
        print(
            render_table(
                ["run", "adapter", "started", "attempts", "passed", "tampered", "pass rate"],
                [
                    [
                        str(row["run_uid"])[:8],
                        str(row["adapter"]),
                        str(row["started_at"]),
                        str(row["attempts"]),
                        str(row["passed"] or 0),
                        str(row["tampered"] or 0),
                        "n/a" if row["pass_rate"] is None else f"{row['pass_rate'] * 100:.1f}%",
                    ]
                    for row in runs
                ],
            )
        )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="AgentDev Lab: a reproducible benchmark harness for AI coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"agentdev-lab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list registered tasks")
    p_list.add_argument("--json", action="store_true", help="emit JSON")
    p_list.set_defaults(func=cmd_list)

    p_adapters = sub.add_parser("adapters", help="list available adapters and their versions")
    p_adapters.set_defaults(func=cmd_adapters)

    p_run = sub.add_parser("run", help="run tasks with an adapter and record the results")
    p_run.add_argument("--adapter", required=True, choices=available_adapters())
    p_run.add_argument("--task", action="append", default=[], help="task id (repeatable; default: all)")
    p_run.add_argument("--attempts", type=int, default=1, help="attempts per task (default: 1)")
    p_run.add_argument("--keep-sandboxes", action="store_true", help="do not delete sandboxes")
    p_run.add_argument("--agent", default="", help="agent product name (default: adapter name)")
    p_run.add_argument("--model", default="", help="model identifier under test")
    p_run.add_argument("--category", action="append", default=[], help="filter tasks by category")
    p_run.add_argument("--difficulty", action="append", default=[], help="filter tasks by difficulty")
    p_run.add_argument("--label", default="", help="short label for this run")
    p_run.add_argument("--notes", default="", help="free-text notes stored with the run")
    p_run.add_argument("--db", type=Path, default=None, help="results database path")
    p_run.set_defaults(func=cmd_run)

    p_self = sub.add_parser(
        "selfcheck", help="validate every task with the noop and oracle controls"
    )
    p_self.set_defaults(func=cmd_selfcheck)

    p_verify = sub.add_parser("verify-integrity", help="audit the recorded results")
    p_verify.add_argument("--db", type=Path, default=None, help="results database path")
    p_verify.add_argument("--deep", action="store_true", help="also re-run the task selfcheck")
    p_verify.set_defaults(func=cmd_verify_integrity)

    p_report = sub.add_parser("report", help="report on recorded runs")
    p_report.add_argument("--run", help="run uid to report on")
    p_report.add_argument("--leaderboard", action="store_true", help="aggregate by adapter")
    p_report.add_argument("--limit", type=int, default=20)
    p_report.add_argument("--json", action="store_true", help="emit JSON (with --run)")
    p_report.add_argument("--db", type=Path, default=None, help="results database path")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except (TaskSpecError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
