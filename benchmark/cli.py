"""Command-line interface: ``python3 -m benchmark <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .adapters import CONTROL_ADAPTERS, available_adapters, get_adapter
from .config import RunConfig, db_path
from .dashboard import build_page, serve
from .export import export_csv, export_json
from .experiment import check_drift, freeze, list_experiments, load_experiment, write_experiment
from .integrity import check_recorded_results, selfcheck, verify_experiment
from .isolation import IsolationUnavailable, available_backends, probe_all
from .queries import find_query, load_queries, run_query
from .report import leaderboard, render_table, run_report, run_report_json
from .sampledata import SAMPLE_LABEL, seed_sample_data
from .stats import gather
from .isolation import select_backend
from .runner import AttemptResult, execute_run
from .scoring import Status
from .storage import ResultsStore
from .tasks import TaskSpecError, load_tasks, select_tasks

#: Named analysis scopes. 'measurement' is the default and the only one whose
#: numbers may be quoted as evidence.
SCOPES = {
    "measurement": ["measurement"],
    "sample": ["development_sample"],
    "control": ["control"],
    "all": ["measurement", "control", "development_sample"],
}

#: Printed whenever a run cannot be published as an isolated measurement.
NON_PUBLISHABLE_BANNER = (
    "NON-PUBLISHABLE: no enforced isolation boundary. The agent runs with host "
    "privileges, so no claim may be made that hidden tests, reference solutions "
    "or the results database were unreachable."
)

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
        experiment=args.experiment,
        run_kind="control" if args.adapter in CONTROL_ADAPTERS else "measurement",
        isolation=args.isolation,
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

    try:
        backend = select_backend(config.isolation)
    except IsolationUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    isolation = backend.probe()

    print(
        f"running {len(tasks)} task(s) x {config.attempts} attempt(s) "
        f"with adapter '{config.adapter}'"
    )
    print(
        f"isolation: {isolation.backend} ({isolation.version}) "
        f"active={isolation.active} network={'allowed' if get_adapter(config.adapter).requires_network else isolation.network_policy}"
    )
    if not isolation.publishable:
        print(f"\n!! {NON_PUBLISHABLE_BANNER}\n")
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


def cmd_experiment(args: argparse.Namespace) -> int:
    if args.action == "list":
        manifests = list_experiments()
        if not manifests:
            print("no experiment manifests in experiments/")
            return EXIT_OK
        rows = []
        for path in manifests:
            experiment = load_experiment(path)
            rows.append(
                [
                    experiment.name,
                    str(len(experiment.task_ids)),
                    str(experiment.attempts_per_task),
                    ", ".join(agent["adapter"] for agent in experiment.agents),
                    experiment.manifest_hash()[:12],
                ]
            )
        print(render_table(["name", "tasks", "attempts", "agents", "hash"], rows))
        return EXIT_OK

    if not args.manifest:
        print("error: a manifest path is required", file=sys.stderr)
        return EXIT_USAGE
    path = Path(args.manifest)

    if args.action == "freeze":
        frozen = freeze(load_experiment(path))
        write_experiment(frozen, path)
        print(f"pinned {len(frozen.task_fingerprints)} task fingerprint(s)")
        print(f"manifest hash: {frozen.manifest_hash()}")
        print("\nCommit this file before the first measurement: an edit afterwards")
        print("changes the hash, and attempts under different hashes are never pooled.")
        return EXIT_OK

    experiment = load_experiment(path)
    if args.action == "show":
        print(f"name       {experiment.name}")
        print(f"hash       {experiment.manifest_hash()}")
        print(f"agents     {', '.join(a['adapter'] + '/' + a['model'] for a in experiment.agents)}")
        print(f"tasks      {len(experiment.task_ids)}")
        print(f"attempts   {experiment.attempts_per_task} per task per agent")
        print(f"timeout    {experiment.agent_timeout_sec}s")
        print(f"isolation  {experiment.isolation}")
        print(f"network    {experiment.network_policy}")
        print(f"ordering   interleaved, permuted with seed {experiment.ordering_seed}")
        print(f"planned    {len(experiment.attempt_order())} attempts")
        print("\nanalysis plan (fixed before results are seen):")
        for line in experiment.analysis_plan:
            print(f"  - {line}")
        drift = check_drift(experiment)
        print(f"\nfixture drift: {', '.join(drift) if drift else 'none'}")
        return EXIT_OK

    with ResultsStore(args.db) as store:
        report = verify_experiment(store, experiment)
    print(report.render())
    return EXIT_OK if report.ok else EXIT_FAILURE


def cmd_stats(args: argparse.Namespace) -> int:
    stats = gather()
    if args.json:
        print(json.dumps(stats.as_dict(), indent=2))
        return EXIT_OK
    print(
        render_table(
            ["item", "count"],
            [
                ["harness version", stats.harness_version],
                ["protocol version", str(stats.protocol_version)],
                ["benchmark tasks", str(stats.tasks)],
                ["capability categories", str(stats.categories)],
                ["tasks with hidden tests", str(stats.tasks_with_hidden_tests)],
                ["SQL analyses", str(stats.sql_queries)],
                ["tests in the suite", str(stats.tests)],
                ["agent adapters", ", ".join(stats.agent_adapters)],
                ["control adapters", ", ".join(stats.control_adapters)],
            ],
        )
    )
    return EXIT_OK


def cmd_isolation(_: argparse.Namespace) -> int:
    rows = [
        [
            report.backend,
            "yes" if report.active else "no",
            "yes" if report.publishable else "no",
            report.version,
            report.network_policy,
            (report.unavailable_reason or report.detail)[:64],
        ]
        for report in probe_all()
    ]
    print(render_table(["backend", "active", "publishable", "version", "network", "detail"], rows))
    print(
        "\n'auto' selects the strongest active backend and refuses to run when none is "
        "available.\nRuns made without an enforced boundary are recorded as NON-PUBLISHABLE."
    )
    return EXIT_OK


def cmd_selfcheck(args: argparse.Namespace) -> int:
    report = selfcheck(check_determinism=args.deterministic)
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


def _render_rows(rows: list) -> str:
    if not rows:
        return "(no rows)"
    headers = list(rows[0].keys())
    body = [["" if row[h] is None else str(row[h]) for h in headers] for row in rows]
    return render_table(headers, body)


def cmd_sql(args: argparse.Namespace) -> int:
    queries = load_queries()
    if not args.query:
        print(render_table(["query", "description"], [[q.name, q.title] for q in queries]))
        print(f"\n{len(queries)} queries. Run one with: python3 -m benchmark sql <name-or-number>")
        return EXIT_OK

    try:
        query = find_query(args.query)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.show:
        print(query.sql)
        return EXIT_OK

    with ResultsStore(args.db) as store:
        if args.scope:
            store.set_analysis_scope(SCOPES[args.scope])
        scope = store.analysis_scope()
        rows = run_query(store, query)
        if args.json:
            print(json.dumps([dict(row) for row in rows], indent=2, default=str))
        else:
            print(f"-- {query.name}: {query.title}")
            print(f"-- analysis scope: {', '.join(scope)}")
            if "development_sample" in scope:
                print("-- !! SYNTHETIC ROWS ARE INCLUDED: these numbers are not evidence.")
            print()
            print(_render_rows(rows))
    return EXIT_OK


def cmd_seed_sample(args: argparse.Namespace) -> int:
    with ResultsStore(args.db) as store:
        run_uids = seed_sample_data(store, attempts_per_task=args.attempts, seed=args.seed)
    print(f"seeded {len(run_uids)} synthetic run(s): {', '.join(uid[:8] for uid in run_uids)}")
    print(f"\n!! {SAMPLE_LABEL}")
    print("   These rows are invented. They are excluded from every 'measurement'")
    print("   query and are reported by `benchmark verify-integrity`.")
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    with ResultsStore(args.db) as store:
        if args.format == "json":
            written = [export_json(store, args.out)]
        else:
            written = export_csv(store, args.out)
    for path in written:
        print(path)
    return EXIT_OK


def cmd_dashboard(args: argparse.Namespace) -> int:
    if args.scope:
        with ResultsStore(args.db) as store:
            store.set_analysis_scope(SCOPES[args.scope])
    if args.render:
        with ResultsStore(args.db) as store:
            Path(args.render).write_text(build_page(store), encoding="utf-8")
        print(f"wrote {args.render}")
        return EXIT_OK
    serve(port=args.port, db=args.db)
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
    p_run.add_argument(
        "--isolation",
        default="auto",
        choices=available_backends(),
        help="isolation backend ('auto' refuses if none can enforce a boundary; "
        "'none' records the run as NON-PUBLISHABLE)",
    )
    p_run.add_argument("--agent", default="", help="agent product name (default: adapter name)")
    p_run.add_argument("--model", default="", help="model identifier under test")
    p_run.add_argument("--category", action="append", default=[], help="filter tasks by category")
    p_run.add_argument("--difficulty", action="append", default=[], help="filter tasks by difficulty")
    p_run.add_argument(
        "--experiment", default="", help="frozen manifest this run executes under"
    )
    p_run.add_argument("--label", default="", help="short label for this run")
    p_run.add_argument("--notes", default="", help="free-text notes stored with the run")
    p_run.add_argument("--db", type=Path, default=None, help="results database path")
    p_run.set_defaults(func=cmd_run)

    p_exp = sub.add_parser("experiment", help="frozen comparison manifests")
    p_exp.add_argument(
        "action", choices=("list", "show", "freeze", "verify"),
        help="list manifests, show one, pin its task fingerprints, or check the publication gate",
    )
    p_exp.add_argument("manifest", nargs="?", help="path to a manifest JSON file")
    p_exp.add_argument("--db", type=Path, default=None, help="results database path")
    p_exp.set_defaults(func=cmd_experiment)

    p_stats = sub.add_parser("stats", help="live counts of what the repository contains")
    p_stats.add_argument("--json", action="store_true")
    p_stats.set_defaults(func=cmd_stats)

    p_iso = sub.add_parser("isolation", help="report which isolation backends work here")
    p_iso.set_defaults(func=cmd_isolation)

    p_self = sub.add_parser(
        "selfcheck", help="validate every task with the noop and oracle controls"
    )
    p_self.add_argument(
        "--deterministic",
        action="store_true",
        help="also evaluate each pristine fixture twice and require the same verdict",
    )
    p_self.set_defaults(func=cmd_selfcheck)

    p_verify = sub.add_parser("verify-integrity", help="audit the recorded results")
    p_verify.add_argument("--db", type=Path, default=None, help="results database path")
    p_verify.add_argument("--deep", action="store_true", help="also re-run the task selfcheck")
    p_verify.set_defaults(func=cmd_verify_integrity)

    p_export = sub.add_parser("export", help="export the full record as JSON or CSV")
    p_export.add_argument("--format", choices=("json", "csv"), default="json")
    p_export.add_argument("--out", type=Path, required=True, help="output file (json) or directory (csv)")
    p_export.add_argument("--db", type=Path, default=None, help="results database path")
    p_export.set_defaults(func=cmd_export)

    p_dash = sub.add_parser("dashboard", help="serve the local analytics dashboard")
    p_dash.add_argument("--port", type=int, default=8765)
    p_dash.add_argument("--scope", choices=sorted(SCOPES), help="analysis scope to apply first")
    p_dash.add_argument("--render", type=Path, help="write the page to a file instead of serving")
    p_dash.add_argument("--db", type=Path, default=None, help="results database path")
    p_dash.set_defaults(func=cmd_dashboard)

    p_seed = sub.add_parser(
        "seed-sample",
        help="populate the database with clearly-labelled synthetic development data",
    )
    p_seed.add_argument("--attempts", type=int, default=3, help="synthetic attempts per task")
    p_seed.add_argument("--seed", type=int, default=20260909, help="random seed")
    p_seed.add_argument("--db", type=Path, default=None, help="results database path")
    p_seed.set_defaults(func=cmd_seed_sample)

    p_sql = sub.add_parser("sql", help="list or run the curated SQL analyses")
    p_sql.add_argument("query", nargs="?", help="query name or number (omit to list them)")
    p_sql.add_argument("--show", action="store_true", help="print the SQL instead of running it")
    p_sql.add_argument("--json", action="store_true", help="emit JSON rows")
    p_sql.add_argument(
        "--scope",
        choices=sorted(SCOPES),
        help="which run kinds the analyses count (stored in the database)",
    )
    p_sql.add_argument("--db", type=Path, default=None, help="results database path")
    p_sql.set_defaults(func=cmd_sql)

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
