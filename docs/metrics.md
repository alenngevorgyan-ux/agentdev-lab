# Metrics

What is stored, what is derived, and what each number does and does not mean.

## Grain

| Level | Table | One row is |
| --- | --- | --- |
| Run | `runs` | one `benchmark run` invocation: an agent, a model, a task set |
| Attempt | `attempts` | one (task, attempt) — **the unit of measurement** |
| Test | `attempt_tests` | one test outcome inside an attempt |

## Recorded per run

Provenance, so two numbers are only ever compared when they describe the same
apparatus: `run_uid`, timestamps, `run_kind`, `agent`, `model`, `adapter`,
`adapter_version`, `harness_version`, `protocol_version`, `attempts_per_task`,
`git_commit`, `git_dirty`, `python_version`, `platform`, `label`, `notes`.

`run_kind` is the load-bearing one:

| Kind | Meaning |
| --- | --- |
| `measurement` | A real agent run. The only kind whose numbers may be quoted. |
| `control` | `noop` or `oracle`. Measures the harness, not an agent. |
| `development_sample` | Synthetic. Invented to exercise the analytics. Never evidence. |

## Recorded per attempt

| Field | Meaning |
| --- | --- |
| `status` | `passed`, `failed`, `timeout`, `tampered`, `agent_error`, `harness_error` |
| `passed`, `tampered` | Booleans, constrained so they can never contradict `status` |
| `tests_total`, `tests_passed` | Per-test outcome counts from the acceptance suite |
| `baseline_passed` | Tests already passing before the agent's turn |
| `regressions` | Tests satisfied at baseline and no longer satisfied |
| `files_changed`, `lines_added`, `lines_deleted` | Diff against the pinned fixture |
| `expected_files_touched` | How many of the task's expected files the agent actually edited |
| `tool_calls`, `num_turns`, `cost_usd` | Agent-reported telemetry; `NULL` when unreported |
| `human_interventions` | Reserved for supervised runs; unattended runs record 0 |
| `agent_duration_ms`, `verify_duration_ms`, `total_duration_ms` | Timing |
| `failure_category`, `classification_source` | Taxonomy label and whether a machine or a human assigned it |
| `task_fingerprint` | Digest of the spec *and* fixture at run time |
| Four hashes | Protected paths and workspace, before and after |

## Derived metrics

| Metric | Definition | Query |
| --- | --- | --- |
| Success rate | passing attempts ÷ scored attempts | 01, 02 |
| First-pass success | passes on `attempt_index = 1` ÷ tasks attempted | 05 |
| Eventual success | tasks passed on any attempt ÷ tasks | 06 |
| Median / p25 / p90 completion time | ordered statistics over `total_seconds` | 10 |
| Regression rate | attempts with `regressions > 0` ÷ attempts | 12 |
| Human-intervention rate | attempts with interventions ÷ attempts | 14 |
| Success by category / difficulty | grouped success rate | 03, 04 |
| Cost per successful task | total cost ÷ passes | 13 |
| Partial credit | mean `tests_passed / tests_total` on failures | 17 |
| Hidden-vs-visible gap | satisfied share, split by test visibility | 18 |
| Attempt variance | tasks with both a pass and a fail | 16 |

## Rules that keep the numbers honest

**Scored attempts exclude `harness_error`.** A failure of the lab is our bug, not
the agent's; counting it either way would be dishonest, so it is excluded from
rates and reported separately. Agent crashes and timeouts *are* counted — an agent
that cannot finish has not solved the task.

**A pass rate without its denominator is not a result.** Always report attempts
per task alongside it. Agents are non-deterministic; query 16 names the tasks
where a single attempt would have been an anecdote.

**Cost is `NULL`, not zero, when unreported.** Averages use `NULLIF` guards so an
agent that reports nothing does not appear free.

**A regression can never coexist with a pass.** Enforced by `CHECK (NOT (passed =
1 AND regressions > 0))`, and by scoring precedence before that.

**Machine labels are not human labels.** `classification_source` separates them,
and the database refuses a relabel that does not declare itself human.
