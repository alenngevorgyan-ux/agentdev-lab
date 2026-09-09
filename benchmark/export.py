"""Result export in JSON and CSV.

Analysis should not require this repository. Export writes the full record --
runs, attempts and per-test outcomes -- in formats any spreadsheet or notebook
can read, with the analysis scope and integrity caveats travelling alongside
the data rather than being left behind.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import HARNESS_PROTOCOL_VERSION, __version__
from .storage import ResultsStore

TABLES = ("runs", "attempts", "attempt_tests", "tasks", "failure_categories")


def _rows(store: ResultsStore, sql: str) -> list[dict]:
    return [dict(row) for row in store.query(sql)]


def build_export(store: ResultsStore) -> dict:
    """Assemble the whole record, with provenance, as plain data."""
    payload: dict = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness_version": __version__,
        "protocol_version": HARNESS_PROTOCOL_VERSION,
        "analysis_scope": store.analysis_scope(),
        "caveats": [
            "Rows with run_kind 'development_sample' are synthetic and are not evidence.",
            "Rows with run_kind 'control' measure the harness, not an agent.",
            "Attempts with status 'harness_error' are excluded from pass rates.",
            "failure_category values with classification_source 'auto' are heuristic labels.",
        ],
    }
    for table in TABLES:
        payload[table] = _rows(store, f"SELECT * FROM {table}")
    payload["attempt_detail"] = _rows(store, "SELECT * FROM v_attempt_detail")
    return payload


def export_json(store: ResultsStore, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_export(store), indent=2, default=str), encoding="utf-8")
    return path


def export_csv(store: ResultsStore, directory: Path) -> list[Path]:
    """Write one CSV per table, plus the joined attempt detail view."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    sources = {name: f"SELECT * FROM {name}" for name in TABLES}
    sources["attempt_detail"] = "SELECT * FROM v_attempt_detail"

    for name, sql in sources.items():
        rows = _rows(store, sql)
        path = directory / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            if rows:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            else:
                handle.write("")
        written.append(path)

    readme = directory / "README.txt"
    readme.write_text(
        "AgentDev Lab CSV export\n"
        f"harness {__version__}, protocol {HARNESS_PROTOCOL_VERSION}\n"
        f"analysis scope at export time: {', '.join(store.analysis_scope())}\n\n"
        "Caveats:\n"
        "  run_kind 'development_sample' rows are synthetic and are not evidence.\n"
        "  run_kind 'control' rows measure the harness, not an agent.\n"
        "  status 'harness_error' attempts are excluded from pass rates.\n"
        "  failure_category with classification_source 'auto' is a heuristic label.\n",
        encoding="utf-8",
    )
    written.append(readme)
    return written
