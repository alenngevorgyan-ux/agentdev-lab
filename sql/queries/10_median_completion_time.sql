-- 10 | Median and quartile completion time per agent.
-- Demonstrates: NTILE/PERCENT_RANK window functions, CTE, ordered statistics.
-- The mean is misleading here: a single timeout drags it far from typical.
WITH ranked AS (
    SELECT
        agent,
        total_seconds,
        PERCENT_RANK() OVER (PARTITION BY agent ORDER BY total_seconds) AS pct_rank
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
)
SELECT
    agent,
    COUNT(*)                                                           AS attempts,
    ROUND(MIN(total_seconds), 1)                                       AS fastest_seconds,
    ROUND(MIN(CASE WHEN pct_rank >= 0.25 THEN total_seconds END), 1)   AS p25_seconds,
    ROUND(MIN(CASE WHEN pct_rank >= 0.50 THEN total_seconds END), 1)   AS median_seconds,
    ROUND(MIN(CASE WHEN pct_rank >= 0.90 THEN total_seconds END), 1)   AS p90_seconds,
    ROUND(MAX(total_seconds), 1)                                       AS slowest_seconds,
    ROUND(AVG(total_seconds), 1)                                       AS mean_seconds
FROM ranked
GROUP BY agent
ORDER BY median_seconds;
