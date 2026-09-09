-- 08 | Which failure modes dominate which capability category.
-- Demonstrates: CASE-based pivot, GROUP BY, aggregates.
SELECT
    category,
    COUNT(*)                                                                     AS failures,
    SUM(CASE WHEN failure_category = 'incomplete_implementation' THEN 1 ELSE 0 END) AS incomplete,
    SUM(CASE WHEN failure_category = 'regression'               THEN 1 ELSE 0 END) AS regression,
    SUM(CASE WHEN failure_category = 'under_editing'            THEN 1 ELSE 0 END) AS under_editing,
    SUM(CASE WHEN failure_category = 'over_editing'             THEN 1 ELSE 0 END) AS over_editing,
    SUM(CASE WHEN failure_category = 'wrong_location'           THEN 1 ELSE 0 END) AS wrong_location,
    SUM(CASE WHEN failure_category = 'hallucinated_api'         THEN 1 ELSE 0 END) AS hallucinated_api,
    SUM(CASE WHEN failure_category = 'test_gaming'              THEN 1 ELSE 0 END) AS test_gaming,
    SUM(CASE WHEN failure_category = 'timeout'                  THEN 1 ELSE 0 END) AS timeout,
    SUM(CASE WHEN failure_category = 'unclassified'             THEN 1 ELSE 0 END) AS needs_review
FROM v_attempt_detail
WHERE run_kind IN (SELECT run_kind FROM analysis_scope) AND passed = 0
GROUP BY category
ORDER BY failures DESC;
