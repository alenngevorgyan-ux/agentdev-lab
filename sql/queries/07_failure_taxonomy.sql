-- 07 | Failure taxonomy: how attempts fail, not just how often.
-- Demonstrates: JOIN to a reference table, GROUP BY, share-of-total window.
SELECT
    d.agent,
    d.failure_category,
    fc.description,
    COUNT(*)                                                            AS failures,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY d.agent), 1)
                                                                        AS share_of_failures_pct,
    SUM(CASE WHEN d.classification_source = 'human' THEN 1 ELSE 0 END)   AS human_labelled
FROM v_attempt_detail d
JOIN failure_categories fc ON fc.category = d.failure_category
WHERE d.run_kind IN (SELECT run_kind FROM analysis_scope) AND d.passed = 0
GROUP BY d.agent, d.failure_category, fc.description
ORDER BY d.agent, failures DESC;
