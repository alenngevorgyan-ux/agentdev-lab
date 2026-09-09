-- AgentDev Lab results schema.
--
-- Design rule: the results database is an append-only laboratory notebook.
-- Attempts are immutable once written, and deletion is blocked at the database
-- level. If a result is wrong, the correct remedy is a new run, never an edit
-- to an old one.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per `benchmark run` invocation.
CREATE TABLE IF NOT EXISTS runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uid           TEXT    NOT NULL UNIQUE,
    started_at        TEXT    NOT NULL,          -- ISO-8601 UTC
    finished_at       TEXT,
    status            TEXT    NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running', 'completed', 'aborted')),
    adapter           TEXT    NOT NULL,
    adapter_version   TEXT    NOT NULL,
    harness_version   TEXT    NOT NULL,
    protocol_version  INTEGER NOT NULL,
    attempts_per_task INTEGER NOT NULL CHECK (attempts_per_task >= 1),
    git_commit        TEXT    NOT NULL,          -- 'unknown' when not a git checkout
    git_dirty         INTEGER NOT NULL CHECK (git_dirty IN (0, 1)),
    python_version    TEXT    NOT NULL,
    platform          TEXT    NOT NULL,
    label             TEXT    NOT NULL DEFAULT '',
    notes             TEXT    NOT NULL DEFAULT ''
);

-- One row per (task, attempt) inside a run. Immutable.
CREATE TABLE IF NOT EXISTS attempts (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                 INTEGER NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    task_id                TEXT    NOT NULL,
    task_fingerprint       TEXT    NOT NULL,     -- spec + fixture digest at run time
    attempt_index          INTEGER NOT NULL CHECK (attempt_index >= 1),
    status                 TEXT    NOT NULL CHECK (status IN (
                                        'passed', 'failed', 'timeout',
                                        'tampered', 'agent_error', 'harness_error')),
    passed                 INTEGER NOT NULL CHECK (passed IN (0, 1)),
    tampered               INTEGER NOT NULL CHECK (tampered IN (0, 1)),
    reason                 TEXT    NOT NULL DEFAULT '',
    verify_exit_code       INTEGER,
    verify_duration_ms     INTEGER,
    agent_duration_ms      INTEGER NOT NULL DEFAULT 0,
    total_duration_ms      INTEGER NOT NULL DEFAULT 0,
    protected_hash_before  TEXT    NOT NULL,
    protected_hash_after   TEXT    NOT NULL,
    workspace_hash_before  TEXT    NOT NULL,
    workspace_hash_after   TEXT    NOT NULL,
    created_at             TEXT    NOT NULL,
    UNIQUE (run_id, task_id, attempt_index),
    -- A pass and a tamper are mutually exclusive by construction, not by convention.
    CHECK (NOT (passed = 1 AND tampered = 1)),
    CHECK ((passed = 1) = (status = 'passed'))
);

CREATE INDEX IF NOT EXISTS idx_attempts_run  ON attempts(run_id);
CREATE INDEX IF NOT EXISTS idx_attempts_task ON attempts(task_id);

-- Raw captured output, kept separate so result queries stay cheap.
CREATE TABLE IF NOT EXISTS attempt_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE RESTRICT,
    stream     TEXT    NOT NULL CHECK (stream IN (
                            'agent_stdout', 'agent_stderr',
                            'verify_stdout', 'verify_stderr')),
    content    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_attempt ON attempt_logs(attempt_id);

-- ---------------------------------------------------------------------------
-- Append-only enforcement
-- ---------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS attempts_no_update
BEFORE UPDATE ON attempts
BEGIN
    SELECT RAISE(ABORT, 'attempts are immutable: record a new run instead of editing results');
END;

CREATE TRIGGER IF NOT EXISTS attempts_no_delete
BEFORE DELETE ON attempts
BEGIN
    SELECT RAISE(ABORT, 'attempts are append-only: deleting recorded results is not permitted');
END;

CREATE TRIGGER IF NOT EXISTS attempt_logs_no_delete
BEFORE DELETE ON attempt_logs
BEGIN
    SELECT RAISE(ABORT, 'attempt logs are append-only');
END;

CREATE TRIGGER IF NOT EXISTS runs_no_delete
BEFORE DELETE ON runs
BEGIN
    SELECT RAISE(ABORT, 'runs are append-only: deleting recorded runs is not permitted');
END;

-- A run may only ever be closed out. Its provenance is frozen at creation.
CREATE TRIGGER IF NOT EXISTS runs_provenance_immutable
BEFORE UPDATE ON runs
WHEN OLD.run_uid          IS NOT NEW.run_uid
  OR OLD.started_at       IS NOT NEW.started_at
  OR OLD.adapter          IS NOT NEW.adapter
  OR OLD.adapter_version  IS NOT NEW.adapter_version
  OR OLD.harness_version  IS NOT NEW.harness_version
  OR OLD.protocol_version IS NOT NEW.protocol_version
  OR OLD.git_commit       IS NOT NEW.git_commit
  OR OLD.git_dirty        IS NOT NEW.git_dirty
  OR OLD.python_version   IS NOT NEW.python_version
  OR OLD.platform         IS NOT NEW.platform
BEGIN
    SELECT RAISE(ABORT, 'run provenance is immutable; only finished_at/status/notes may change');
END;

-- ---------------------------------------------------------------------------
-- Reporting views
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_run_summary AS
SELECT
    r.id                                                   AS run_id,
    r.run_uid,
    r.adapter,
    r.adapter_version,
    r.started_at,
    r.finished_at,
    r.status,
    COUNT(a.id)                                            AS attempts,
    SUM(a.passed)                                          AS passed,
    SUM(a.tampered)                                        AS tampered,
    SUM(a.status = 'harness_error')                        AS harness_errors,
    SUM(CASE WHEN a.status != 'harness_error' THEN 1 ELSE 0 END) AS scored_attempts,
    ROUND(
        CAST(SUM(a.passed) AS REAL)
        / NULLIF(SUM(CASE WHEN a.status != 'harness_error' THEN 1 ELSE 0 END), 0),
        4
    )                                                      AS pass_rate,
    SUM(a.total_duration_ms)                               AS total_duration_ms
FROM runs r
LEFT JOIN attempts a ON a.run_id = r.id
GROUP BY r.id;

CREATE VIEW IF NOT EXISTS v_task_pass_rate AS
SELECT
    a.task_id,
    r.adapter,
    COUNT(*)                                               AS attempts,
    SUM(a.passed)                                          AS passed,
    ROUND(CAST(SUM(a.passed) AS REAL) / COUNT(*), 4)       AS pass_rate,
    ROUND(AVG(a.total_duration_ms), 1)                     AS avg_duration_ms
FROM attempts a
JOIN runs r ON r.id = a.run_id
WHERE a.status != 'harness_error'
GROUP BY a.task_id, r.adapter;
