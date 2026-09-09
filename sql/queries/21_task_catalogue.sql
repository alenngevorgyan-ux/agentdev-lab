-- 21 | The task catalogue and how much evidence exists per task.
-- Demonstrates: LEFT JOIN (tasks with no attempts must still appear), GROUP BY.
SELECT
    t.task_id,
    t.category,
    t.difficulty,
    CASE t.has_hidden_tests WHEN 1 THEN 'yes' ELSE 'no' END      AS hidden_tests,
    t.timeout_sec,
    COUNT(a.id)                                                  AS recorded_attempts,
    COALESCE(SUM(a.passed), 0)                                   AS passes,
    CASE
        WHEN COUNT(a.id) = 0 THEN 'never measured'
        WHEN COUNT(a.id) < 3 THEN 'thin evidence'
        ELSE 'measured'
    END                                                          AS evidence
FROM tasks t
LEFT JOIN attempts a ON a.task_id = t.task_id AND a.status != 'harness_error'
GROUP BY t.task_id
ORDER BY t.category, t.task_id;
