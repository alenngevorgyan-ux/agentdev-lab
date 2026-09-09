-- 13 | Cost efficiency: dollars per task actually solved.
-- Demonstrates: NULLIF guard, aggregates, ranking window.
-- Cost per attempt rewards giving up early; cost per success does not.
WITH costed AS (
    SELECT agent, model, passed, COALESCE(cost_usd, 0) AS cost_usd, total_seconds
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope) AND cost_usd IS NOT NULL
)
SELECT
    agent,
    model,
    COUNT(*)                                                        AS attempts,
    SUM(passed)                                                     AS successes,
    ROUND(SUM(cost_usd), 4)                                         AS total_cost_usd,
    ROUND(AVG(cost_usd), 4)                                         AS cost_per_attempt_usd,
    ROUND(SUM(cost_usd) / NULLIF(SUM(passed), 0), 4)                AS cost_per_success_usd,
    RANK() OVER (ORDER BY SUM(cost_usd) / NULLIF(SUM(passed), 0))   AS efficiency_rank
FROM costed
GROUP BY agent, model
ORDER BY efficiency_rank;
