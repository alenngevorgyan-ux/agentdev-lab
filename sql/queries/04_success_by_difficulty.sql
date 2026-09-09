-- 04 | Success rate by difficulty, with the expected monotonic decline made visible.
-- Demonstrates: GROUP BY, CASE ordering, comparative aggregate.
SELECT
    difficulty,
    agent,
    COUNT(*)                                     AS attempts,
    SUM(passed)                                  AS passed,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)     AS pass_rate_pct,
    ROUND(AVG(tests_pass_fraction) * 100, 1)     AS mean_tests_passed_pct
FROM v_attempt_detail
WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
GROUP BY difficulty, agent
ORDER BY
    CASE difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 WHEN 'hard' THEN 3 ELSE 4 END,
    agent;
