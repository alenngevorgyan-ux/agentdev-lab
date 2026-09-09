-- Non-control attempts that failed without changing a single file. Usually a
-- sign that the agent never started work (auth, quota, crash) rather than a
-- genuine capability failure -- such rows must not be read as a measurement.
SELECT r.run_uid, r.adapter, a.task_id, a.attempt_index, a.status, a.created_at
FROM attempts a
JOIN runs r ON r.id = a.run_id
WHERE a.workspace_hash_before = a.workspace_hash_after
  AND a.status != 'harness_error'
  AND r.adapter NOT IN ('noop', 'oracle')
ORDER BY a.created_at DESC;
