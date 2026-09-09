-- 12 | Regressions: attempts that broke behaviour which previously worked.
-- Demonstrates: GROUP BY, conditional aggregation, JOIN through the view.
-- A regression is the failure mode a reviewer fears most, so it is counted
-- separately from "did not finish the job".
SELECT
    agent,
    category,
    COUNT(*)                                                          AS attempts,
    SUM(CASE WHEN regressions > 0 THEN 1 ELSE 0 END)                  AS attempts_with_regressions,
    ROUND(100.0 * SUM(CASE WHEN regressions > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                      AS regression_rate_pct,
    SUM(regressions)                                                  AS tests_broken,
    MAX(regressions)                                                  AS worst_single_attempt
FROM v_attempt_detail
WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
GROUP BY agent, category
HAVING SUM(regressions) > 0
ORDER BY regression_rate_pct DESC;
