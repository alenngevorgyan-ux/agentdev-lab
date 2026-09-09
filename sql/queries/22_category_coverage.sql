-- 22 | Suite balance: how the benchmark itself is distributed.
-- Demonstrates: GROUP BY, window share-of-total, CASE.
-- A benchmark skewed toward one category measures that category, not agents.
SELECT
    category,
    COUNT(*)                                                  AS tasks,
    SUM(CASE WHEN difficulty = 'easy'   THEN 1 ELSE 0 END)    AS easy,
    SUM(CASE WHEN difficulty = 'medium' THEN 1 ELSE 0 END)    AS medium,
    SUM(CASE WHEN difficulty = 'hard'   THEN 1 ELSE 0 END)    AS hard,
    SUM(has_hidden_tests)                                     AS with_hidden_tests,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)        AS share_of_suite_pct
FROM tasks
GROUP BY category
ORDER BY tasks DESC, category;
