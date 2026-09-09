-- 19 | Tests that disagree with themselves across attempts of the same task.
-- Demonstrates: JOIN, GROUP BY, HAVING, aggregates over a child table.
-- A flaky test manufactures fake capability differences; this finds them.
SELECT
    d.task_id,
    t.test_id,
    COUNT(*)                                                                  AS observations,
    SUM(CASE WHEN t.outcome = 'passed' THEN 1 ELSE 0 END)                     AS passed,
    SUM(CASE WHEN t.outcome IN ('failed', 'error') THEN 1 ELSE 0 END)         AS failed,
    ROUND(100.0 * SUM(CASE WHEN t.outcome = 'passed' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                              AS pass_pct
FROM attempt_tests t
JOIN v_attempt_detail d ON d.attempt_id = t.attempt_id
JOIN attempts a         ON a.id = t.attempt_id
WHERE d.run_kind IN (SELECT run_kind FROM analysis_scope)
GROUP BY d.task_id, t.test_id
HAVING SUM(CASE WHEN t.outcome = 'passed' THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN t.outcome IN ('failed', 'error') THEN 1 ELSE 0 END) > 0
ORDER BY pass_pct, d.task_id;
