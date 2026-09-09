-- 02 | Head-to-head comparison of every agent/model measured.
-- Demonstrates: GROUP BY, CASE, aggregate ratios, ranking by a derived metric.
-- Controls are excluded: they bound the scale rather than compete on it.
SELECT
    agent,
    model,
    COUNT(*)                                                     AS attempts,
    SUM(passed)                                                  AS passed,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)                     AS pass_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN regressions > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                 AS regression_rate_pct,
    ROUND(100.0 * SUM(tampered) / COUNT(*), 1)                   AS tamper_rate_pct,
    ROUND(AVG(tests_pass_fraction) * 100, 1)                     AS mean_tests_passed_pct,
    ROUND(AVG(total_seconds), 1)                                 AS mean_seconds,
    ROUND(AVG(lines_changed), 1)                                 AS mean_lines_changed,
    ROUND(AVG(COALESCE(cost_usd, 0)), 4)                         AS mean_cost_usd
FROM v_attempt_detail
WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
GROUP BY agent, model
ORDER BY pass_rate_pct DESC, mean_seconds ASC;
