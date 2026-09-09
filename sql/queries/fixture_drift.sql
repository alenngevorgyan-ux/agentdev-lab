-- Tasks whose fixture fingerprint differs across runs: the task definition
-- changed, so results either side of the change are not comparable.
SELECT task_id, COUNT(DISTINCT task_fingerprint) AS distinct_fingerprints
FROM attempts
GROUP BY task_id
HAVING distinct_fingerprints > 1
ORDER BY task_id;
