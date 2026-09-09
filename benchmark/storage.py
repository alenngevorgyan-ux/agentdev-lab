"""SQLite persistence for benchmark results.

The database is append-only (enforced by triggers in ``sql/schema.sql``). This
module never offers an update or delete path for attempts, because there is no
legitimate reason to rewrite a measurement.
"""

from __future__ import annotations

import platform
import sqlite3
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from . import HARNESS_PROTOCOL_VERSION, __version__
from .config import REPO_ROOT, SCHEMA_PATH, db_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_provenance(repo: Path | None = None) -> tuple[str, bool]:
    """Return ``(commit, dirty)`` for the harness checkout.

    Provenance is recorded honestly: a run made from uncommitted code is marked
    dirty so nobody later mistakes it for a reproducible measurement.
    """
    root = repo or REPO_ROOT
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if commit.returncode != 0:
            return "unknown", True
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return commit.stdout.strip(), bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return "unknown", True


class ResultsStore:
    """Connection wrapper over the results database."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._apply_schema()

    def _apply_schema(self) -> None:
        self.connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('protocol_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(HARNESS_PROTOCOL_VERSION),),
        )
        self.connection.commit()

    # -- writing ------------------------------------------------------------

    def start_run(
        self,
        *,
        adapter: str,
        adapter_version: str,
        attempts_per_task: int,
        label: str = "",
        notes: str = "",
    ) -> tuple[int, str]:
        """Open a run row and return ``(run_id, run_uid)``."""
        commit, dirty = git_provenance()
        run_uid = uuid.uuid4().hex
        cursor = self.connection.execute(
            """
            INSERT INTO runs (
                run_uid, started_at, status, adapter, adapter_version,
                harness_version, protocol_version, attempts_per_task,
                git_commit, git_dirty, python_version, platform, label, notes
            ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_uid,
                utc_now(),
                adapter,
                adapter_version,
                __version__,
                HARNESS_PROTOCOL_VERSION,
                attempts_per_task,
                commit,
                1 if dirty else 0,
                sys.version.split()[0],
                platform.platform(),
                label,
                notes,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid), run_uid

    def finish_run(self, run_id: int, *, status: str = "completed") -> None:
        self.connection.execute(
            "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
            (utc_now(), status, run_id),
        )
        self.connection.commit()

    def record_attempt(self, **fields: Any) -> int:
        """Insert one immutable attempt row; returns its id."""
        columns = (
            "run_id",
            "task_id",
            "task_fingerprint",
            "attempt_index",
            "status",
            "passed",
            "tampered",
            "reason",
            "verify_exit_code",
            "verify_duration_ms",
            "agent_duration_ms",
            "total_duration_ms",
            "protected_hash_before",
            "protected_hash_after",
            "workspace_hash_before",
            "workspace_hash_after",
        )
        missing = [column for column in columns if column not in fields]
        if missing:
            raise ValueError(f"record_attempt missing field(s): {missing}")
        unexpected = set(fields) - set(columns)
        if unexpected:
            raise ValueError(f"record_attempt got unexpected field(s): {sorted(unexpected)}")

        placeholders = ", ".join("?" for _ in columns)
        cursor = self.connection.execute(
            f"INSERT INTO attempts ({', '.join(columns)}, created_at) "
            f"VALUES ({placeholders}, ?)",
            tuple(fields[column] for column in columns) + (utc_now(),),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def record_logs(self, attempt_id: int, streams: dict[str, str]) -> None:
        rows = [
            (attempt_id, stream, content)
            for stream, content in streams.items()
            if content
        ]
        if not rows:
            return
        self.connection.executemany(
            "INSERT INTO attempt_logs (attempt_id, stream, content) VALUES (?, ?, ?)", rows
        )
        self.connection.commit()

    # -- reading ------------------------------------------------------------

    def query(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, params))

    def run_summary(self, run_uid: str) -> sqlite3.Row | None:
        rows = self.query("SELECT * FROM v_run_summary WHERE run_uid = ?", (run_uid,))
        return rows[0] if rows else None

    def latest_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM v_run_summary ORDER BY run_id DESC LIMIT ?", (limit,)
        )

    def attempts_for_run(self, run_uid: str) -> list[sqlite3.Row]:
        return self.query(
            """
            SELECT a.* FROM attempts a
            JOIN runs r ON r.id = a.run_id
            WHERE r.run_uid = ?
            ORDER BY a.task_id, a.attempt_index
            """,
            (run_uid,),
        )

    def fixture_drift(self) -> list[sqlite3.Row]:
        return self.query(
            """
            SELECT task_id, COUNT(DISTINCT task_fingerprint) AS distinct_fingerprints
            FROM attempts GROUP BY task_id HAVING distinct_fingerprints > 1
            ORDER BY task_id
            """
        )

    def tampered_attempts(self) -> list[sqlite3.Row]:
        return self.query(
            """
            SELECT r.run_uid, r.adapter, a.task_id, a.attempt_index, a.created_at, a.reason
            FROM attempts a JOIN runs r ON r.id = a.run_id
            WHERE a.tampered = 1 ORDER BY a.created_at DESC
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ResultsStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@contextmanager
def open_store(path: Path | None = None) -> Iterator[ResultsStore]:
    store = ResultsStore(path)
    try:
        yield store
    finally:
        store.close()
