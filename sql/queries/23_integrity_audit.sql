-- 23 | Integrity audit: rows that must be inspected before quoting anything.
-- Demonstrates: UNION ALL across heterogeneous checks, CASE, subqueries.
SELECT 'tampered attempts' AS finding,
       COUNT(*)            AS rows_affected,
       CASE WHEN COUNT(*) = 0 THEN 'clean' ELSE 'investigate' END AS verdict
FROM attempts WHERE tampered = 1
UNION ALL
SELECT 'attempts that changed nothing (non-control)',
       COUNT(*),
       CASE WHEN COUNT(*) = 0 THEN 'clean' ELSE 'investigate' END
FROM attempts a JOIN runs r ON r.id = a.run_id
WHERE a.workspace_hash_before = a.workspace_hash_after
  AND a.status != 'harness_error'
  AND r.run_kind IN (SELECT run_kind FROM analysis_scope)
UNION ALL
SELECT 'runs from a dirty working tree',
       COUNT(*),
       CASE WHEN COUNT(*) = 0 THEN 'clean' ELSE 'disclose' END
FROM runs WHERE git_dirty = 1 AND run_kind IN (SELECT run_kind FROM analysis_scope)
UNION ALL
SELECT 'tasks whose fixture changed between runs',
       COUNT(*),
       CASE WHEN COUNT(*) = 0 THEN 'clean' ELSE 'not comparable' END
FROM (SELECT task_id FROM attempts GROUP BY task_id HAVING COUNT(DISTINCT task_fingerprint) > 1)
UNION ALL
SELECT 'harness errors (excluded from rates)',
       COUNT(*),
       CASE WHEN COUNT(*) = 0 THEN 'clean' ELSE 'our bug' END
FROM attempts WHERE status = 'harness_error'
UNION ALL
SELECT 'development sample rows present',
       COUNT(*),
       CASE WHEN COUNT(*) = 0 THEN 'none' ELSE 'never quote these' END
FROM attempts a JOIN runs r ON r.id = a.run_id WHERE r.run_kind = 'development_sample';
