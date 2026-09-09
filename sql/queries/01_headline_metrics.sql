-- 01 | Headline metrics for the whole database, split by run kind.
-- Demonstrates: CTE, aggregates, CASE, NULLIF guard.
-- run_kind is always reported so control and sample rows can never be
-- silently folded into a claim about an agent.
WITH scored AS (
    SELECT * FROM v_attempt_detail
)
SELECT
    run_kind,
    COUNT(DISTINCT run_uid)                                   AS runs,
    COUNT(DISTINCT task_id)                                   AS tasks_touched,
    COUNT(*)                                                  AS attempts,
    SUM(passed)                                               AS passed,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)                  AS pass_rate_pct,
    SUM(CASE WHEN regressions > 0 THEN 1 ELSE 0 END)          AS attempts_with_regressions,
    SUM(tampered)                                             AS tampered,
    SUM(human_interventions)                                  AS human_interventions,
    ROUND(AVG(total_seconds), 1)                              AS mean_seconds,
    ROUND(SUM(COALESCE(cost_usd, 0)), 4)                      AS total_cost_usd,
    ROUND(
        SUM(COALESCE(cost_usd, 0)) / NULLIF(SUM(passed), 0), 4
    )                                                         AS cost_per_success_usd
FROM scored
GROUP BY run_kind
ORDER BY run_kind;
