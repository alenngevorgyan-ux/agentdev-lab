-- 03 | Success rate by capability category, per agent.
-- Demonstrates: JOIN (through the view), GROUP BY, share-of-total window function.
-- This is the query that turns one number into a capability profile.
SELECT
    category,
    agent,
    COUNT(*)                                                  AS attempts,
    SUM(passed)                                               AS passed,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)                  AS pass_rate_pct,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY agent), 1
    )                                                         AS share_of_agent_attempts_pct,
    ROUND(AVG(total_seconds), 1)                              AS mean_seconds
FROM v_attempt_detail
WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
GROUP BY category, agent
ORDER BY pass_rate_pct ASC, category;
