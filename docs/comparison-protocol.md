# Comparison protocol

The frozen rules for any Claude Code vs Codex (or any agent vs agent)
comparison run in this lab.

Its purpose is narrow and specific: **to make it impossible to quietly change
the methodology after seeing which agent wins.** Every decision that could be
tuned in hindsight is fixed here, in writing, before the first measurement, and
captured in a machine-readable manifest whose hash is recorded with the run.

Status: **no comparison has been run.** This document is the pre-registration,
not a report.

---

## 1. Pre-registration

Before any comparison run:

1. Write the experiment manifest (`experiments/*.json`, schema below).
2. Commit it. The commit must precede the first measurement.
3. `python3 -m benchmark experiment freeze <manifest>` records its SHA-256 and
   the task fingerprints it pins.
4. Run. Every attempt stores the manifest hash it ran under.

A manifest edited after results exist produces a different hash, and the
analysis refuses to pool attempts recorded under different hashes. Changing the
method is allowed; changing it *invisibly* is not.

## 2. What must be identical across agents

| Dimension | Rule |
| --- | --- |
| Task set | The same task ids, pinned by `task_fingerprint` (spec + fixture + hidden tests). Any fingerprint mismatch invalidates the comparison. |
| Initial fixture | Byte-identical. Each attempt records `fixture_hash`; a comparison asserts they match per task. |
| Instructions | One shared prompt builder (`benchmark/adapters/prompt.py`). Adapters may differ in *delivery*, never in wording. Asserted by `tests/test_adapter_parity.py`. |
| Acceptance suite | The same hidden tests, applied by the host after the agent exits. |
| Timeout | The same agent budget for every agent (`agent_timeout_sec`), and the task's own `verify.timeout_sec` for evaluation. |
| Isolation | The same backend, with `isolation_active = 1` for every attempt. |
| Network | Allowed during the agent turn (both agents need their API), denied during evaluation. |
| Attempts per task | The same `attempts_per_task` for every agent. |
| Harness | The same `protocol_version` and git commit, with `git_dirty = 0`. |

## 3. Sample size and ordering

- **Attempts per task: 5** for a headline comparison; 1 is an anecdote and is
  reported as such if used. Agents are non-deterministic; the denominator is
  always reported alongside the rate.
- **Ordering is interleaved by task, and the agent order within each task is
  permuted by a seed recorded in the manifest.** Running all of agent A and then
  all of agent B confounds the comparison with anything that drifted in between:
  API load, a model rollout, a machine under different pressure.
- The seed is fixed in the manifest before the run, so the ordering cannot be
  reshuffled after seeing a result.

## 4. Retry policy

There is exactly one retry rule, and it never depends on the outcome:

- **A task attempt is never retried because it failed.** `attempts_per_task` is
  fixed in advance; every attempt is recorded and counted.
- An attempt may be **re-executed only** when the harness itself failed
  (`harness_error`), and the re-execution is recorded as a new attempt with the
  original left in place. Nothing is deleted; attempts are append-only.
- "Best of N" is not a metric this lab reports. First-pass success and eventual
  success are both reported, from the same attempts.

## 5. Infrastructure errors, rate limits and timeouts

These are distinguished because conflating them is how a benchmark accidentally
measures an API instead of an agent.

| Situation | Status | Counted in the pass rate? |
| --- | --- | --- |
| Harness bug, IO failure, missing fixture | `harness_error` | **No.** Excluded from the denominator, reported separately. |
| Agent could not start: no credential, binary missing, CLI printed a login or quota message | `agent_error` | **No** for a capability claim. Such attempts are quarantined: an agent that never ran was never measured. |
| Agent started and ran out of its time budget | `timeout` | **Yes.** An agent that cannot finish in budget has not solved the task. |
| Rate limited *mid-attempt* | `agent_error` with the CLI's message | **No**, and the whole comparison is suspect: see below. |
| Agent finished, tests failed | `failed` | Yes. |
| Agent edited a protected test path | `tampered` | Yes, as a non-pass, and reported separately as a behavioural finding. |

**Rate-limit rule.** If more than 5% of one agent's attempts end in
`agent_error` from rate limiting, the comparison is **void** and must be re-run.
A throttled agent is being measured on its account's quota, not its capability.
The threshold is fixed here so it cannot be relaxed after seeing whose run got
throttled.

**Timeout budget must be equal and generous.** The budget is chosen before the
run from the oracle control's runtime, not tuned per agent. If either agent's
timeout rate exceeds 10%, the budget was too tight: raise it and re-run *both*
agents, never one.

## 6. Model identity

- `model` records what the operator **requested**. `model_resolved` records what
  the agent **reported**, or `NULL`.
- **A model name is never inferred.** If the CLI does not report one, the field
  stays null and the write-up says "model as requested, not confirmed by the
  agent".
- A comparison must state both agents' CLI versions (`adapter_version`) and
  requested models. Two runs whose CLI versions differ are two experiments.
- Provider-side model rollouts are invisible to us. The manifest records the
  wall-clock window of the run so a later reader can correlate.

## 7. Analysis rules, fixed before results are seen

These are the *only* analyses a comparison reports. Adding one after seeing the
data is a new pre-registration, labelled exploratory.

1. **Primary metric:** overall pass rate per agent, with attempts as the
   denominator, over the full frozen task set.
2. **Secondary:** first-pass success; regression rate; tamper count; median and
   p90 attempt duration; cost per success where both agents report cost.
3. **Breakdowns:** by capability category and by difficulty — reported for both
   agents or for neither.
4. **Every task stays in.** A task may not be dropped from a comparison after
   its outcome is known, for any reason. If a task is discovered to be broken,
   the *whole comparison* is re-run without it and that is disclosed.
5. **No significance claim without a stated test.** With 18 tasks × 5 attempts,
   this lab reports differences descriptively with denominators. Any inferential
   claim must name the test, the unit of analysis (task, not attempt — attempts
   within a task are not independent) and the assumption it rests on.
6. **Uncertainty is reported.** A difference smaller than the spread across
   attempts of the same task is described as "not distinguishable at this sample
   size", not as a win.

## 8. Cherry-picking prevention

- Attempts are append-only at the database level; a bad run cannot be deleted,
  only superseded and disclosed.
- Every attempt records the manifest hash, so the analysis can prove no attempt
  was quietly excluded.
- `benchmark experiment verify` reports any attempt in the window that is *not*
  in the reported set. A comparison whose reported N is smaller than the
  recorded N must explain the gap.
- Task fingerprints are recorded per attempt; editing a task mid-experiment is
  visible as fingerprint drift and voids pooling.

## 9. Task-author bias — the limitation this protocol cannot fix

The tasks were written by the same author who built the harness, with Claude
Code available during authoring. That is a real bias risk and no procedure here
removes it. Mitigations actually in place:

- Every task is validated by two controls: `noop` must fail it, `oracle` must
  pass it. That catches unsolvable and already-passing tasks, not favouritism.
- Tasks are derived from ordinary engineering situations (rounding, pagination,
  layering, retries) rather than from any agent's observed behaviour.
- Hidden acceptance tests are written against the task's written specification,
  and the specification is fixed before the tests.

What would actually fix it: tasks contributed by people who did not build the
harness, and a held-out set neither agent's authors have seen. Neither exists
here. **Any comparison produced by this lab must state this limitation in the
same breath as its headline number.**

## 10. Publication gate

A comparison may be published only if all of the following hold. They are
checked by `benchmark experiment verify`:

- [ ] every attempt has `isolation_active = 1` and `publishable = 1`
- [ ] `git_dirty = 0` for every run
- [ ] one `protocol_version` across all attempts
- [ ] one `task_fingerprint` per task across all attempts
- [ ] one manifest hash across all attempts
- [ ] `attempts_per_task` equal across agents
- [ ] rate-limit `agent_error` share below 5% for every agent
- [ ] timeout share below 10% for every agent
- [ ] `verify-integrity` clean
- [ ] no `development_sample` row inside the analysis scope

Failing any box does not mean the data is worthless — it means the honest
report is "measured under these conditions, not publishable as a clean
comparison", with the failing box named.
