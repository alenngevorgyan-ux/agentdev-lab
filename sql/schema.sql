-- AgentDev Lab results schema (protocol version 2).
--
-- Design rule: the results database is an append-only laboratory notebook.
-- Attempts are immutable once written and deletion is blocked at the database
-- level. If a result is wrong, the remedy is a new run, never an edit.
--
-- Grain:
--   runs          one `benchmark run` invocation  (agent x model x task set)
--   attempts      one (task, attempt) inside a run  -- the unit of measurement
--   attempt_tests one test outcome inside an attempt -- enables regression and
--                 partial-credit analysis that a single exit code cannot express
--   attempt_logs  captured stdout/stderr, kept separate so analytics stay cheap

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Reference data ------------------------------------------------------------

-- The failure taxonomy, kept in the database so analyses can JOIN definitions
-- instead of hardcoding strings.
CREATE TABLE IF NOT EXISTS failure_categories (
    category    TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

-- Which run kinds the curated analyses currently include. Analysis queries
-- read this table rather than hardcoding a filter, so the scope of every
-- reported number is itself stored, inspectable and auditable -- including
-- from the sqlite3 command line. It defaults to real measurements only.
CREATE TABLE IF NOT EXISTS analysis_scope (
    run_kind TEXT PRIMARY KEY
             CHECK (run_kind IN ('measurement', 'control', 'development_sample'))
);

-- Snapshot of task metadata, refreshed on every run. Lets SQL group by
-- category and difficulty without reading the task files.
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,
    difficulty      TEXT NOT NULL,
    language        TEXT NOT NULL,
    timeout_sec     INTEGER NOT NULL,
    expected_files  INTEGER NOT NULL DEFAULT 0,
    has_hidden_tests INTEGER NOT NULL DEFAULT 0 CHECK (has_hidden_tests IN (0, 1)),
    tags            TEXT NOT NULL DEFAULT '',
    first_seen_at   TEXT NOT NULL
);

-- Measurements --------------------------------------------------------------

CREATE TABLE IF NOT EXISTS runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uid           TEXT    NOT NULL UNIQUE,
    started_at        TEXT    NOT NULL,          -- ISO-8601 UTC
    finished_at       TEXT,
    status            TEXT    NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running', 'completed', 'aborted')),
    -- run_kind separates real measurements from harness controls and from
    -- clearly-labelled synthetic development data. Analyses filter on it so
    -- sample rows can never be mistaken for evidence.
    run_kind          TEXT    NOT NULL DEFAULT 'measurement'
                              CHECK (run_kind IN ('measurement', 'control', 'development_sample')),
    adapter           TEXT    NOT NULL,
    agent             TEXT    NOT NULL,          -- product name, e.g. 'claude-code'
    model             TEXT    NOT NULL DEFAULT 'unspecified',
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

CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(run_kind);

CREATE TABLE IF NOT EXISTS attempts (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                 INTEGER NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    task_id                TEXT    NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
    task_fingerprint       TEXT    NOT NULL,     -- spec + fixture digest at run time
    attempt_index          INTEGER NOT NULL CHECK (attempt_index >= 1),
    status                 TEXT    NOT NULL CHECK (status IN (
                                        'passed', 'failed', 'timeout',
                                        'tampered', 'agent_error', 'harness_error')),
    passed                 INTEGER NOT NULL CHECK (passed IN (0, 1)),
    tampered               INTEGER NOT NULL CHECK (tampered IN (0, 1)),
    failure_category       TEXT    NOT NULL DEFAULT 'unclassified'
                                   REFERENCES failure_categories(category),
    -- 'auto' labels come from the heuristic classifier, 'human' from review.
    -- Kept apart so a hand-labelled study is never diluted by machine guesses.
    classification_source  TEXT    NOT NULL DEFAULT 'auto'
                                   CHECK (classification_source IN ('auto', 'human')),
    reason                 TEXT    NOT NULL DEFAULT '',

    -- test outcomes
    tests_total            INTEGER NOT NULL DEFAULT 0,
    tests_passed           INTEGER NOT NULL DEFAULT 0,
    baseline_passed        INTEGER NOT NULL DEFAULT 0,
    regressions            INTEGER NOT NULL DEFAULT 0 CHECK (regressions >= 0),

    -- effort and footprint
    files_changed          INTEGER NOT NULL DEFAULT 0,
    lines_added            INTEGER NOT NULL DEFAULT 0,
    lines_deleted          INTEGER NOT NULL DEFAULT 0,
    expected_files_touched INTEGER NOT NULL DEFAULT 0,

    -- agent-reported telemetry; NULL means the agent does not report it
    tool_calls             INTEGER,
    num_turns              INTEGER,
    cost_usd               REAL,
    human_interventions    INTEGER NOT NULL DEFAULT 0 CHECK (human_interventions >= 0),

    -- timing
    verify_exit_code       INTEGER,
    verify_duration_ms     INTEGER,
    agent_duration_ms      INTEGER NOT NULL DEFAULT 0,
    total_duration_ms      INTEGER NOT NULL DEFAULT 0,

    -- integrity
    protected_hash_before  TEXT    NOT NULL,
    protected_hash_after   TEXT    NOT NULL,
    workspace_hash_before  TEXT    NOT NULL,
    workspace_hash_after   TEXT    NOT NULL,

    notes                  TEXT    NOT NULL DEFAULT '',
    created_at             TEXT    NOT NULL,

    UNIQUE (run_id, task_id, attempt_index),
    -- A pass and a tamper are mutually exclusive by construction, not convention.
    CHECK (NOT (passed = 1 AND tampered = 1)),
    CHECK ((passed = 1) = (status = 'passed')),
    CHECK (tests_passed <= tests_total),
    -- A pass with a regression would be a contradiction in terms.
    CHECK (NOT (passed = 1 AND regressions > 0))
);

CREATE INDEX IF NOT EXISTS idx_attempts_run     ON attempts(run_id);
CREATE INDEX IF NOT EXISTS idx_attempts_task    ON attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_attempts_failure ON attempts(failure_category);

CREATE TABLE IF NOT EXISTS attempt_tests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id   INTEGER NOT NULL REFERENCES attempts(id) ON DELETE RESTRICT,
    test_id      TEXT    NOT NULL,
    outcome      TEXT    NOT NULL CHECK (outcome IN (
                            'passed', 'failed', 'error', 'skipped',
                            'expected_failure', 'unexpected_success')),
    -- Whether this test was satisfied before the agent's turn. A test that was
    -- satisfied at baseline and is not now is precisely a regression.
    baseline_satisfied INTEGER NOT NULL CHECK (baseline_satisfied IN (0, 1)),
    is_hidden    INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
    UNIQUE (attempt_id, test_id)
);

CREATE INDEX IF NOT EXISTS idx_attempt_tests_attempt ON attempt_tests(attempt_id);

CREATE TABLE IF NOT EXISTS attempt_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE RESTRICT,
    stream     TEXT    NOT NULL CHECK (stream IN (
                            'agent_stdout', 'agent_stderr',
                            'verify_stdout', 'verify_stderr',
                            'baseline_stdout', 'baseline_stderr')),
    content    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_attempt ON attempt_logs(attempt_id);

-- ---------------------------------------------------------------------------
-- Append-only enforcement
-- ---------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS attempts_no_delete
BEFORE DELETE ON attempts
BEGIN
    SELECT RAISE(ABORT, 'attempts are append-only: deleting recorded results is not permitted');
END;

-- Measured facts are frozen. The only mutable fields are the human review
-- columns, because relabelling a failure after inspection is legitimate
-- research; changing what was measured is not.
CREATE TRIGGER IF NOT EXISTS attempts_measurements_immutable
BEFORE UPDATE ON attempts
WHEN OLD.run_id           IS NOT NEW.run_id
  OR OLD.task_id          IS NOT NEW.task_id
  OR OLD.task_fingerprint IS NOT NEW.task_fingerprint
  OR OLD.attempt_index    IS NOT NEW.attempt_index
  OR OLD.status           IS NOT NEW.status
  OR OLD.passed           IS NOT NEW.passed
  OR OLD.tampered         IS NOT NEW.tampered
  OR OLD.tests_total      IS NOT NEW.tests_total
  OR OLD.tests_passed     IS NOT NEW.tests_passed
  OR OLD.baseline_passed  IS NOT NEW.baseline_passed
  OR OLD.regressions      IS NOT NEW.regressions
  OR OLD.files_changed    IS NOT NEW.files_changed
  OR OLD.lines_added      IS NOT NEW.lines_added
  OR OLD.lines_deleted    IS NOT NEW.lines_deleted
  OR OLD.cost_usd         IS NOT NEW.cost_usd
  OR OLD.total_duration_ms IS NOT NEW.total_duration_ms
  OR OLD.protected_hash_before IS NOT NEW.protected_hash_before
  OR OLD.protected_hash_after  IS NOT NEW.protected_hash_after
  OR OLD.workspace_hash_before IS NOT NEW.workspace_hash_before
  OR OLD.workspace_hash_after  IS NOT NEW.workspace_hash_after
BEGIN
    SELECT RAISE(ABORT,
        'measured fields are immutable; only failure_category, classification_source and notes may be revised');
END;

-- A human relabel must say so, so machine and human labels stay separable.
CREATE TRIGGER IF NOT EXISTS attempts_relabel_must_be_attributed
BEFORE UPDATE OF failure_category ON attempts
WHEN NEW.classification_source != 'human'
BEGIN
    SELECT RAISE(ABORT, 'revising failure_category requires classification_source = ''human''');
END;

CREATE TRIGGER IF NOT EXISTS attempt_tests_no_delete
BEFORE DELETE ON attempt_tests
BEGIN
    SELECT RAISE(ABORT, 'per-test results are append-only');
END;

CREATE TRIGGER IF NOT EXISTS attempt_tests_no_update
BEFORE UPDATE ON attempt_tests
BEGIN
    SELECT RAISE(ABORT, 'per-test results are immutable');
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

CREATE TRIGGER IF NOT EXISTS runs_provenance_immutable
BEFORE UPDATE ON runs
WHEN OLD.run_uid          IS NOT NEW.run_uid
  OR OLD.started_at       IS NOT NEW.started_at
  OR OLD.run_kind         IS NOT NEW.run_kind
  OR OLD.adapter          IS NOT NEW.adapter
  OR OLD.agent            IS NOT NEW.agent
  OR OLD.model            IS NOT NEW.model
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

-- Attempts joined to their run and task, with derived per-attempt measures.
-- Every analysis query builds on this rather than re-deriving the joins.
CREATE VIEW IF NOT EXISTS v_attempt_detail AS
SELECT
    a.id                AS attempt_id,
    r.run_uid,
    r.run_kind,
    r.agent,
    r.model,
    r.adapter,
    r.git_commit,
    a.task_id,
    t.category,
    t.difficulty,
    t.title             AS task_title,
    a.attempt_index,
    a.status,
    a.passed,
    a.tampered,
    a.regressions,
    a.failure_category,
    a.classification_source,
    a.tests_total,
    a.tests_passed,
    CASE WHEN a.tests_total > 0
         THEN ROUND(CAST(a.tests_passed AS REAL) / a.tests_total, 4)
    END                 AS tests_pass_fraction,
    a.files_changed,
    a.lines_added,
    a.lines_deleted,
    a.lines_added + a.lines_deleted AS lines_changed,
    a.expected_files_touched,
    a.tool_calls,
    a.num_turns,
    a.cost_usd,
    a.human_interventions,
    a.agent_duration_ms,
    a.total_duration_ms,
    ROUND(a.total_duration_ms / 1000.0, 2) AS total_seconds,
    a.created_at
FROM attempts a
JOIN runs  r ON r.id = a.run_id
JOIN tasks t ON t.task_id = a.task_id
WHERE a.status != 'harness_error';   -- our own bugs are not measurements

CREATE VIEW IF NOT EXISTS v_run_summary AS
SELECT
    r.id                                                   AS run_id,
    r.run_uid,
    r.run_kind,
    r.agent,
    r.model,
    r.adapter,
    r.adapter_version,
    r.started_at,
    r.finished_at,
    r.status,
    COUNT(a.id)                                            AS attempts,
    SUM(a.passed)                                          AS passed,
    SUM(a.tampered)                                        AS tampered,
    SUM(a.regressions > 0)                                 AS attempts_with_regressions,
    SUM(a.status = 'harness_error')                        AS harness_errors,
    SUM(CASE WHEN a.status != 'harness_error' THEN 1 ELSE 0 END) AS scored_attempts,
    ROUND(
        CAST(SUM(a.passed) AS REAL)
        / NULLIF(SUM(CASE WHEN a.status != 'harness_error' THEN 1 ELSE 0 END), 0), 4
    )                                                      AS pass_rate,
    SUM(a.human_interventions)                             AS human_interventions,
    ROUND(SUM(COALESCE(a.cost_usd, 0)), 4)                 AS total_cost_usd,
    SUM(a.total_duration_ms)                               AS total_duration_ms
FROM runs r
LEFT JOIN attempts a ON a.run_id = r.id
GROUP BY r.id;

CREATE VIEW IF NOT EXISTS v_task_pass_rate AS
SELECT
    d.task_id,
    d.category,
    d.difficulty,
    d.agent,
    d.model,
    COUNT(*)                                          AS attempts,
    SUM(d.passed)                                     AS passed,
    ROUND(CAST(SUM(d.passed) AS REAL) / COUNT(*), 4)  AS pass_rate,
    ROUND(AVG(d.tests_pass_fraction), 4)              AS avg_tests_pass_fraction,
    ROUND(AVG(d.total_seconds), 2)                    AS avg_seconds
FROM v_attempt_detail d
WHERE d.run_kind != 'control'
GROUP BY d.task_id, d.agent, d.model;
