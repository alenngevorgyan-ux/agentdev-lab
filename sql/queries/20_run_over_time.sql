-- 20 | Trend: each run compared with that agent's previous run.
-- Demonstrates: LAG window function, CTE, comparative analysis.
WITH run_rates AS (
    SELECT
        agent,
        model,
        run_uid,
        MIN(created_at)                            AS run_started,
        COUNT(*)                                   AS attempts,
        ROUND(100.0 * SUM(passed) / COUNT(*), 1)   AS pass_rate_pct
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
    GROUP BY agent, model, run_uid
)
SELECT
    agent,
    model,
    SUBSTR(run_uid, 1, 8)                                                  AS run,
    run_started,
    attempts,
    pass_rate_pct,
    LAG(pass_rate_pct) OVER (PARTITION BY agent, model ORDER BY run_started)
                                                                           AS previous_pass_rate_pct,
    ROUND(
        pass_rate_pct
        - LAG(pass_rate_pct) OVER (PARTITION BY agent, model ORDER BY run_started), 1
    )                                                                      AS change_pct_points
FROM run_rates
ORDER BY agent, run_started;
