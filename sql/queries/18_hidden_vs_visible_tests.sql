-- 18 | Do agents do worse on tests they could not see?
-- Demonstrates: JOIN to the per-test table, conditional aggregation.
-- A large gap suggests fitting to the visible assertions rather than the spec.
SELECT
    d.agent,
    CASE t.is_hidden WHEN 1 THEN 'hidden' ELSE 'visible' END              AS test_visibility,
    COUNT(*)                                                              AS test_results,
    SUM(CASE WHEN t.outcome IN ('passed', 'expected_failure') THEN 1 ELSE 0 END)
                                                                          AS satisfied,
    ROUND(
        100.0 * SUM(CASE WHEN t.outcome IN ('passed', 'expected_failure') THEN 1 ELSE 0 END)
        / COUNT(*), 1
    )                                                                     AS satisfied_pct
FROM attempt_tests t
JOIN v_attempt_detail d ON d.attempt_id = t.attempt_id
WHERE d.run_kind IN (SELECT run_kind FROM analysis_scope)
GROUP BY d.agent, t.is_hidden
ORDER BY d.agent, test_visibility;
