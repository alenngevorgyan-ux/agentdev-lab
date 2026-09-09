-- 11 | Latency histogram in fixed buckets.
-- Demonstrates: CASE bucketing, GROUP BY, share-of-total window.
WITH bucketed AS (
    SELECT
        agent,
        CASE
            WHEN total_seconds <  10  THEN 'a: < 10s'
            WHEN total_seconds <  30  THEN 'b: 10-30s'
            WHEN total_seconds <  60  THEN 'c: 30-60s'
            WHEN total_seconds < 180  THEN 'd: 1-3 min'
            WHEN total_seconds < 600  THEN 'e: 3-10 min'
            ELSE                           'f: > 10 min'
        END AS bucket,
        passed
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
)
SELECT
    agent,
    bucket,
    COUNT(*)                                                              AS attempts,
    SUM(passed)                                                           AS passed,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY agent), 1)  AS share_pct
FROM bucketed
GROUP BY agent, bucket
ORDER BY agent, bucket;
