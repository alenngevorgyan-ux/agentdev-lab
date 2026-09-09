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
from .failures import TAXONOMY


class ProtocolMismatch(RuntimeError):
    """Raised when a results database was written by a different protocol."""


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
        self._assert_protocol_compatible()
        self.connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('protocol_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(HARNESS_PROTOCOL_VERSION),),
        )
        # The taxonomy lives in the database so analyses can join definitions.
        self.connection.executemany(
            "INSERT INTO failure_categories(category, description) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET description = excluded.description",
            [(str(category), description) for category, description in TAXONOMY.items()],
        )
        # Seed the default only for a brand-new database. Re-inserting on every
        # open would silently widen a scope someone deliberately narrowed, which
        # could fold synthetic rows back into a real measurement.
        if not self.connection.execute("SELECT 1 FROM analysis_scope LIMIT 1").fetchone():
            self.connection.execute("INSERT INTO analysis_scope(run_kind) VALUES ('measurement')")
        self.connection.commit()

    def _assert_protocol_compatible(self) -> None:
        """Refuse a database written by a different measurement protocol.

        ``CREATE TABLE IF NOT EXISTS`` silently leaves an older database
        without the newer columns, which would surface much later as a
        confusing SQL error -- or worse, as a run recorded with provenance
        missing. Failing here keeps incompatible records apart.
        """
        tables = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if tables is None:
            return  # a fresh database
        row = self.connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'protocol_version'"
        ).fetchone()
        if row is None:
            return
        stored = int(row[0])
        if stored != HARNESS_PROTOCOL_VERSION:
            raise ProtocolMismatch(
                f"{self.path} was written under protocol version {stored}, but this "
                f"harness records protocol version {HARNESS_PROTOCOL_VERSION}. Results "
                "from different protocols are not comparable; point AGENTDEV_DB at a "
                "new file rather than mixing them."
            )

    def analysis_scope(self) -> list[str]:
        return [row["run_kind"] for row in self.query("SELECT run_kind FROM analysis_scope ORDER BY 1")]

    def set_analysis_scope(self, run_kinds: Sequence[str]) -> None:
        """Choose which run kinds the curated analyses include.

        Widening the scope to include synthetic or control rows is a deliberate,
        recorded act -- the setting lives in the database, so a later reader can
        see what any given analysis was allowed to count.
        """
        if not run_kinds:
            raise ValueError("analysis scope must include at least one run kind")
        self.connection.execute("DELETE FROM analysis_scope")
        self.connection.executemany(
            "INSERT INTO analysis_scope(run_kind) VALUES (?)", [(kind,) for kind in run_kinds]
        )
        self.connection.commit()

    def register_tasks(self, tasks: Sequence[Any]) -> None:
        """Snapshot task metadata so SQL can group by category and difficulty."""
        self.connection.executemany(
            """
            INSERT INTO tasks (task_id, title, category, difficulty, language,
                               timeout_sec, expected_files, has_hidden_tests, tags, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                difficulty = excluded.difficulty,
                language = excluded.language,
                timeout_sec = excluded.timeout_sec,
                expected_files = excluded.expected_files,
                has_hidden_tests = excluded.has_hidden_tests,
                tags = excluded.tags
            """,
            [
                (
                    task.id,
                    task.title,
                    task.category,
                    task.difficulty,
                    task.language,
                    task.verify.timeout_sec,
                    len(task.expected_files),
                    1 if task.has_hidden_tests else 0,
                    ",".join(task.tags),
                    utc_now(),
                )
                for task in tasks
            ],
        )
        self.connection.commit()

    # -- writing ------------------------------------------------------------

    def start_run(
        self,
        *,
        adapter: str,
        adapter_version: str,
        attempts_per_task: int,
        agent: str = "",
        model: str = "unspecified",
        model_resolved: str | None = None,
        agent_flags: str = "",
        agent_timeout_sec: int | None = None,
        isolation_backend: str = "unknown",
        isolation_version: str = "unknown",
        isolation_active: bool = False,
        publishable: bool = False,
        network_policy: str = "unknown",
        experiment_name: str = "",
        experiment_hash: str = "",
        run_kind: str = "measurement",
        label: str = "",
        notes: str = "",
    ) -> tuple[int, str]:
        """Open a run row and return ``(run_id, run_uid)``."""
        commit, dirty = git_provenance()
        run_uid = uuid.uuid4().hex
        cursor = self.connection.execute(
            """
            INSERT INTO runs (
                run_uid, started_at, status, run_kind, adapter, agent, model,
                model_resolved, agent_flags, agent_timeout_sec,
                isolation_backend, isolation_version, isolation_active, publishable,
                network_policy,
                adapter_version, harness_version, protocol_version, attempts_per_task,
                git_commit, git_dirty, python_version, platform,
                experiment_name, experiment_hash, label, notes
            ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_uid,
                utc_now(),
                run_kind,
                adapter,
                agent or adapter,
                model,
                model_resolved,
                agent_flags,
                agent_timeout_sec,
                isolation_backend,
                isolation_version,
                1 if isolation_active else 0,
                1 if publishable else 0,
                network_policy,
                adapter_version,
                __version__,
                HARNESS_PROTOCOL_VERSION,
                attempts_per_task,
                commit,
                1 if dirty else 0,
                sys.version.split()[0],
                platform.platform(),
                experiment_name,
                experiment_hash,
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
            "failure_category",
            "classification_source",
            "reason",
            "tests_total",
            "tests_passed",
            "baseline_passed",
            "regressions",
            "files_changed",
            "lines_added",
            "lines_deleted",
            "expected_files_touched",
            "fixture_hash",
            "isolation_active",
            "network_policy",
            "started_at",
            "finished_at",
            "tool_calls",
            "num_turns",
            "cost_usd",
            "human_interventions",
            "verify_exit_code",
            "verify_duration_ms",
            "agent_duration_ms",
            "total_duration_ms",
            "protected_hash_before",
            "protected_hash_after",
            "workspace_hash_before",
            "workspace_hash_after",
            "notes",
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

    def record_tests(
        self, attempt_id: int, rows: Sequence[tuple[str, str, int, int]]
    ) -> None:
        """Store per-test outcomes: (test_id, outcome, baseline_satisfied, is_hidden)."""
        if not rows:
            return
        self.connection.executemany(
            "INSERT INTO attempt_tests (attempt_id, test_id, outcome, baseline_satisfied, is_hidden) "
            "VALUES (?, ?, ?, ?, ?)",
            [(attempt_id, *row) for row in rows],
        )
        self.connection.commit()

    def record_resolved_model(self, run_id: int, model: str) -> None:
        """Record the model the agent actually reported, if it reported one.

        Written once, only from agent telemetry. It is never inferred: a run
        whose agent reports nothing keeps NULL here, and a write-up must then
        say "model as requested, not confirmed by the agent".
        """
        if not model:
            return
        self.connection.execute(
            "UPDATE runs SET model_resolved = ? WHERE id = ? AND model_resolved IS NULL",
            (model, run_id),
        )
        self.connection.commit()

    def relabel_failure(self, attempt_id: int, category: str, note: str = "") -> None:
        """Apply a human failure label, which is tracked separately from the classifier."""
        self.connection.execute(
            "UPDATE attempts SET failure_category = ?, classification_source = 'human', "
            "notes = ? WHERE id = ?",
            (category, note, attempt_id),
        )
        self.connection.commit()

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
