-- 14 | Human intervention: how often a run needed a person.
-- Demonstrates: GROUP BY, conditional aggregation, CASE.
-- Reserved for supervised runs; unattended harness runs record zero, which is
-- itself the honest value rather than a missing one.
SELECT
    agent,
    run_kind,
    COUNT(*)                                                                  AS attempts,
    SUM(human_interventions)                                                  AS interventions,
    SUM(CASE WHEN human_interventions > 0 THEN 1 ELSE 0 END)                  AS attempts_needing_help,
    ROUND(100.0 * SUM(CASE WHEN human_interventions > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                              AS intervention_rate_pct,
    ROUND(1.0 * SUM(human_interventions) / COUNT(*), 2)                       AS interventions_per_attempt
FROM v_attempt_detail
GROUP BY agent, run_kind
ORDER BY intervention_rate_pct DESC;
