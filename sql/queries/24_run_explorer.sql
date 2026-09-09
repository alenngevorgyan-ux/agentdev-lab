-- 24 | Run explorer: every attempt of one run, newest runs first.
-- Demonstrates: JOIN, window numbering, CASE, ORDER BY on a derived column.
-- Optional filter: add  WHERE run_uid = '<uid>'  to drill into a single run.
SELECT
    SUBSTR(d.run_uid, 1, 8)                                               AS run,
    d.agent,
    d.model,
    d.run_kind,
    d.task_id,
    d.category,
    d.difficulty,
    d.attempt_index,
    d.status,
    d.tests_passed || '/' || d.tests_total                                AS tests,
    d.regressions,
    d.files_changed,
    d.lines_added,
    d.lines_deleted,
    d.failure_category,
    d.total_seconds,
    ROW_NUMBER() OVER (PARTITION BY d.run_uid ORDER BY d.task_id, d.attempt_index)
                                                                          AS row_in_run
FROM v_attempt_detail d
ORDER BY d.created_at DESC, d.task_id, d.attempt_index;
