-- 16 | Non-determinism: tasks an agent sometimes passes and sometimes fails.
-- Demonstrates: CTE, HAVING, aggregates over repeated attempts.
-- A task in this list means a single-attempt measurement of it is an anecdote.
WITH per_task AS (
    SELECT
        agent,
        task_id,
        category,
        COUNT(*)          AS attempts,
        SUM(passed)       AS passes,
        MIN(passed)       AS worst,
        MAX(passed)       AS best
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
    GROUP BY agent, task_id, category
    HAVING COUNT(*) > 1
)
SELECT
    agent,
    task_id,
    category,
    attempts,
    passes,
    ROUND(100.0 * passes / attempts, 1)                          AS pass_rate_pct,
    CASE WHEN best > worst THEN 'inconsistent' ELSE 'stable' END AS consistency
FROM per_task
ORDER BY consistency DESC, pass_rate_pct, task_id;
