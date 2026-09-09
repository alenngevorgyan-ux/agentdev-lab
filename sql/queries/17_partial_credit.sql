-- 17 | Partial credit: how close did failing attempts get?
-- Demonstrates: filtered aggregates, GROUP BY, CASE.
-- Distinguishes "almost there" from "nowhere near", which pass/fail hides.
SELECT
    category,
    COUNT(*)                                                                 AS failed_attempts,
    ROUND(AVG(tests_pass_fraction) * 100, 1)                                 AS mean_tests_passed_pct,
    SUM(CASE WHEN tests_pass_fraction >= 0.9 THEN 1 ELSE 0 END)              AS near_misses,
    SUM(CASE WHEN tests_pass_fraction <= 0.1 THEN 1 ELSE 0 END)              AS barely_started,
    ROUND(100.0 * SUM(CASE WHEN tests_pass_fraction >= 0.9 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                             AS near_miss_pct
FROM v_attempt_detail
WHERE run_kind IN (SELECT run_kind FROM analysis_scope) AND passed = 0 AND tests_total > 0
GROUP BY category
ORDER BY mean_tests_passed_pct DESC;
