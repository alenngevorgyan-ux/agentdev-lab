-- 06 | How much retrying buys: first-attempt success against eventual success.
-- Demonstrates: two CTEs, JOIN between them, comparative analysis.
WITH first_attempts AS (
    SELECT agent, task_id, MAX(CASE WHEN attempt_index = 1 THEN passed END) AS first_passed
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
    GROUP BY agent, task_id
),
eventual AS (
    SELECT agent, task_id, MAX(passed) AS ever_passed
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
    GROUP BY agent, task_id
)
SELECT
    f.agent,
    COUNT(*)                                                       AS tasks,
    SUM(f.first_passed)                                            AS passed_first_time,
    SUM(e.ever_passed)                                             AS passed_eventually,
    ROUND(100.0 * SUM(f.first_passed) / COUNT(*), 1)               AS first_pass_pct,
    ROUND(100.0 * SUM(e.ever_passed) / COUNT(*), 1)                AS eventual_pass_pct,
    SUM(e.ever_passed) - SUM(f.first_passed)                       AS tasks_rescued_by_retrying
FROM first_attempts f
JOIN eventual e ON e.agent = f.agent AND e.task_id = f.task_id
GROUP BY f.agent
ORDER BY eventual_pass_pct DESC;
