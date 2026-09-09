-- 09 | Task leaderboard: which tasks defeat agents most often.
-- Demonstrates: window ranking (DENSE_RANK), GROUP BY, HAVING.
WITH task_stats AS (
    SELECT
        task_id,
        category,
        difficulty,
        COUNT(*)                                  AS attempts,
        SUM(passed)                               AS passed,
        1.0 * SUM(passed) / COUNT(*)              AS pass_rate,
        AVG(tests_pass_fraction)                  AS mean_tests_fraction
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
    GROUP BY task_id, category, difficulty
    HAVING COUNT(*) >= 1
)
SELECT
    DENSE_RANK() OVER (ORDER BY pass_rate ASC, mean_tests_fraction ASC) AS hardness_rank,
    task_id,
    category,
    difficulty,
    attempts,
    passed,
    ROUND(100.0 * pass_rate, 1)            AS pass_rate_pct,
    ROUND(100.0 * mean_tests_fraction, 1)  AS mean_tests_passed_pct
FROM task_stats
ORDER BY hardness_rank, task_id;
