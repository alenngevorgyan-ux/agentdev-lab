-- 05 | First-pass success: did the agent get it right on attempt 1?
-- Demonstrates: window function (ROW_NUMBER), CTE, conditional aggregation.
-- A pass rate over many attempts flatters an agent that needs several tries;
-- first-pass success is the metric a user actually feels.
WITH ordered AS (
    SELECT
        agent,
        model,
        task_id,
        run_uid,
        passed,
        ROW_NUMBER() OVER (
            PARTITION BY run_uid, task_id ORDER BY attempt_index
        ) AS attempt_rank
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
)
SELECT
    agent,
    model,
    COUNT(*)                                        AS tasks_attempted,
    SUM(passed)                                     AS first_attempt_passes,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)        AS first_pass_success_pct
FROM ordered
WHERE attempt_rank = 1
GROUP BY agent, model
ORDER BY first_pass_success_pct DESC;
