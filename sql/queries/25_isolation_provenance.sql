-- 25 | Under what boundary was each measurement actually taken?
-- Demonstrates: GROUP BY, CASE, conditional aggregation, JOIN through the view.
-- A pass rate means nothing about what the agent could reach unless a boundary
-- was enforced. This is the query to run before quoting any number.
SELECT
    agent,
    model,
    isolation_backend,
    CASE isolation_active WHEN 1 THEN 'enforced' ELSE 'NONE' END        AS boundary,
    CASE publishable      WHEN 1 THEN 'publishable' ELSE 'NON-PUBLISHABLE' END AS status,
    network_policy,
    CASE WHEN experiment_hash = '' THEN '(ad hoc)' ELSE SUBSTR(experiment_hash, 1, 12) END
                                                                        AS experiment,
    COUNT(*)                                                            AS attempts,
    SUM(passed)                                                         AS passed,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)                            AS pass_rate_pct
FROM v_attempt_detail
GROUP BY agent, model, isolation_backend, isolation_active, publishable,
         network_policy, experiment_hash
ORDER BY publishable DESC, agent;
