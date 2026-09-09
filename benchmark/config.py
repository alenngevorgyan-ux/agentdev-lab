"""Filesystem layout and run-wide configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
TASKS_DIR = BENCHMARK_DIR / "tasks"
SQL_DIR = REPO_ROOT / "sql"
SCHEMA_PATH = SQL_DIR / "schema.sql"
QUERIES_DIR = SQL_DIR / "queries"

DEFAULT_RESULTS_DIR = REPO_ROOT / "results"
DEFAULT_DB_PATH = DEFAULT_RESULTS_DIR / "agentdev.sqlite3"

#: Hard ceiling applied to any single subprocess, regardless of task settings.
MAX_TIMEOUT_SEC = 3600

VALID_RUN_KINDS = frozenset({"measurement", "control", "development_sample"})

#: Captured stream output is truncated at this size before being stored.
MAX_CAPTURED_BYTES = 256 * 1024


def db_path() -> Path:
    """Resolve the results database path (``AGENTDEV_DB`` overrides the default)."""
    override = os.environ.get("AGENTDEV_DB")
    return Path(override).expanduser().resolve() if override else DEFAULT_DB_PATH


def sandbox_root() -> Path:
    """Root directory under which per-attempt sandboxes are created."""
    override = os.environ.get("AGENTDEV_SANDBOX_ROOT")
    return Path(override).expanduser().resolve() if override else REPO_ROOT / ".sandboxes"


@dataclass(frozen=True)
class RunConfig:
    """Everything that parameterises one benchmark run."""

    adapter: str
    task_ids: tuple[str, ...]
    attempts: int = 1
    keep_sandboxes: bool = False
    notes: str = ""
    label: str = ""
    #: Product name of the agent under test; defaults to the adapter name.
    agent: str = ""
    #: Model identifier, recorded so results are attributable to a build.
    model: str = ""
    #: 'measurement' for real data, 'control' for harness controls,
    #: 'development_sample' for synthetic rows that must never be quoted.
    run_kind: str = "measurement"

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be >= 1")
        if self.run_kind not in VALID_RUN_KINDS:
            raise ValueError(f"run_kind must be one of {sorted(VALID_RUN_KINDS)}")
