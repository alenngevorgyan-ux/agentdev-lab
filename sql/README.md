# SQL

The analytics store is SQLite: zero dependencies, one file, and readable by any
tool a reviewer already has.

## Layout

| Path | Contents |
| --- | --- |
| `schema.sql` | Tables, constraints, append-only triggers, reporting views. |
| `queries/` | Curated analyses, numbered and documented (`benchmark sql` lists them). |

## Model

Four grains, from coarse to fine:

| Table | One row is | Why it exists |
| --- | --- | --- |
| `runs` | one `benchmark run` invocation | provenance: agent, model, commit, dirty flag, platform, run kind |
| `attempts` | one (task, attempt) | the unit of measurement |
| `attempt_tests` | one test outcome inside an attempt | partial credit and regression analysis, which an exit code cannot express |
| `attempt_logs` | captured output | evidence, kept out of the analytical path |

Reference tables: `tasks` (category, difficulty, hidden-test flag),
`failure_categories` (the taxonomy, so analyses can join definitions rather
than hardcode strings), and `analysis_scope`.

Views: `v_attempt_detail` (the join every analysis builds on, excluding harness
errors), `v_run_summary`, `v_task_pass_rate`.

## `analysis_scope` — what a number was allowed to count

Analyses do not hardcode a filter. They read `analysis_scope`, a table holding
the run kinds currently included:

```sql
SELECT * FROM analysis_scope;          -- measurement (the default)
```

Change it with `python3 -m benchmark sql <query> --scope sample|control|all`,
or directly. Because the setting lives in the database, a later reader can see
exactly what any given analysis was permitted to count — synthetic development
rows cannot silently enter a result, and the CLI and dashboard both announce it
when they do.

## Running the queries

```bash
python3 -m benchmark sql                     # list all 24 with descriptions
python3 -m benchmark sql 09                  # run one by number
python3 -m benchmark sql 09 --show           # print the SQL instead
python3 -m benchmark sql 09 --json           # machine-readable rows
sqlite3 results/agentdev.sqlite3 < sql/queries/09_hardest_tasks.sql
```

## The queries

| # | Query | Technique |
| --- | --- | --- |
| 01 | Headline metrics | CTE, aggregates, CASE, NULLIF |
| 02 | Agent comparison | GROUP BY, ratios, conditional aggregation |
| 03 | Success by category | GROUP BY, share-of-total window |
| 04 | Success by difficulty | GROUP BY, CASE ordering |
| 05 | First-pass success | ROW_NUMBER window, CTE |
| 06 | Eventual vs first-pass | two CTEs, JOIN between them |
| 07 | Failure taxonomy | JOIN to reference table, window share |
| 08 | Failure mix by category | CASE pivot |
| 09 | Hardest tasks | DENSE_RANK window, HAVING |
| 10 | Median completion time | PERCENT_RANK window, ordered statistics |
| 11 | Latency distribution | CASE bucketing, window share |
| 12 | Regression analysis | conditional aggregation, HAVING |
| 13 | Cost per successful task | NULLIF guard, RANK window |
| 14 | Human intervention rate | conditional aggregation |
| 15 | Effort vs outcome | CASE bucketing, comparative aggregates |
| 16 | Attempt variance | CTE, HAVING, min/max over repeats |
| 17 | Partial credit | filtered aggregates |
| 18 | Hidden vs visible tests | JOIN to `attempt_tests` |
| 19 | Flaky tests | JOIN, GROUP BY, HAVING |
| 20 | Run over time | LAG window |
| 21 | Task catalogue | LEFT JOIN so unmeasured tasks still appear |
| 22 | Category coverage | window share-of-total |
| 23 | Integrity audit | UNION ALL across checks, subqueries |
| 24 | Run explorer | ROW_NUMBER window, JOIN |
| 25 | Isolation provenance | GROUP BY, CASE, conditional aggregation |

Every query is executed by the test suite against seeded data, so a broken
query fails the build rather than silently returning nothing.
