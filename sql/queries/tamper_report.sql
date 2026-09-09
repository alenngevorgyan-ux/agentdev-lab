-- Every attempt in which protected paths were modified. Should normally be empty;
-- a non-empty result is a finding about the agent, not a bug in the harness.
SELECT r.run_uid, r.adapter, a.task_id, a.attempt_index, a.created_at, a.reason
FROM attempts a
JOIN runs r ON r.id = a.run_id
WHERE a.tampered = 1
ORDER BY a.created_at DESC;
