-- 15 | Does a bigger diff mean a better outcome?
-- Demonstrates: CASE bucketing, GROUP BY, comparative aggregates.
-- Tests the over-editing hypothesis: sprawling changes usually fail more.
WITH sized AS (
    SELECT
        agent,
        passed,
        files_changed,
        lines_changed,
        CASE
            WHEN lines_changed = 0             THEN 'a: no change'
            WHEN lines_changed <= 10           THEN 'b: 1-10 lines'
            WHEN lines_changed <= 50           THEN 'c: 11-50 lines'
            WHEN lines_changed <= 200          THEN 'd: 51-200 lines'
            ELSE                                    'e: > 200 lines'
        END AS diff_size
    FROM v_attempt_detail
    WHERE run_kind IN (SELECT run_kind FROM analysis_scope)
)
SELECT
    diff_size,
    COUNT(*)                                    AS attempts,
    SUM(passed)                                 AS passed,
    ROUND(100.0 * SUM(passed) / COUNT(*), 1)    AS pass_rate_pct,
    ROUND(AVG(files_changed), 1)                AS mean_files_changed
FROM sized
GROUP BY diff_size
ORDER BY diff_size;
