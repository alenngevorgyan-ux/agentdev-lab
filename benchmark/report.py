"""Human-readable and machine-readable reporting over stored results.

Reports read only what was recorded. There is no code path here that computes
a number from anything other than rows already in the database.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .scoring import Status
from .storage import ResultsStore


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """A dependency-free fixed-width table."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    line = "  ".join("-" * width for width in widths)
    out = ["  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)), line]
    out += ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows]
    return "\n".join(out)


def run_report(store: ResultsStore, run_uid: str) -> str:
    summary = store.run_summary(run_uid)
    if summary is None:
        return f"no such run: {run_uid}"

    attempts = store.attempts_for_run(run_uid)
    header = [
        f"run        {summary['run_uid']}",
        f"adapter    {summary['adapter']} ({summary['adapter_version']})",
        f"started    {summary['started_at']}",
        f"finished   {summary['finished_at'] or '-'} [{summary['status']}]",
        f"attempts   {summary['attempts']} scored={summary['scored_attempts']} "
        f"passed={summary['passed']} tampered={summary['tampered']} "
        f"harness_errors={summary['harness_errors']}",
        f"pass rate  {_fmt_rate(summary['pass_rate'])}",
        "",
    ]
    rows = [
        [
            str(row["task_id"]),
            str(row["attempt_index"]),
            str(row["status"]),
            "-" if row["verify_exit_code"] is None else str(row["verify_exit_code"]),
            f"{(row['total_duration_ms'] or 0) / 1000:.1f}s",
            (row["reason"] or "")[:60],
        ]
        for row in attempts
    ]
    table = render_table(["task", "#", "status", "exit", "time", "reason"], rows)
    return "\n".join(header) + table


def leaderboard(store: ResultsStore) -> str:
    rows = store.query(
        """
        SELECT r.adapter,
               COUNT(*)                                          AS attempts,
               SUM(a.passed)                                     AS passed,
               SUM(a.tampered)                                    AS tampered,
               ROUND(CAST(SUM(a.passed) AS REAL) / COUNT(*), 4)  AS pass_rate,
               ROUND(AVG(a.total_duration_ms) / 1000.0, 2)       AS avg_seconds
        FROM attempts a
        JOIN runs r ON r.id = a.run_id
        WHERE a.status != 'harness_error'
        GROUP BY r.adapter
        ORDER BY pass_rate DESC, r.adapter
        """
    )
    if not rows:
        return "no results recorded yet"
    table = render_table(
        ["adapter", "attempts", "passed", "tampered", "pass rate", "avg time"],
        [
            [
                str(row["adapter"]),
                str(row["attempts"]),
                str(row["passed"]),
                str(row["tampered"]),
                _fmt_rate(row["pass_rate"]),
                f"{row['avg_seconds']}s",
            ]
            for row in rows
        ],
    )
    note = (
        "\n\nnote: 'noop' and 'oracle' are harness controls, not agents under test. "
        "They bound the scale; they do not compete on it."
    )
    return table + note


def run_report_json(store: ResultsStore, run_uid: str) -> str:
    summary = store.run_summary(run_uid)
    payload = {
        "run": dict(summary) if summary else None,
        "attempts": _rows_to_dicts(store.attempts_for_run(run_uid)),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def status_counts(rows: Iterable[sqlite3.Row]) -> dict[str, int]:
    counts = {str(status): 0 for status in Status}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    return counts
