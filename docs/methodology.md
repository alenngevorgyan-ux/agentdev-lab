# Methodology

How to run a measurement whose result means something.

## Definitions

| Term | Meaning |
| --- | --- |
| **Attempt** | One (task, agent) pair executed once. The unit of measurement. |
| **Run** | One invocation of `benchmark run`: a set of tasks × attempts under one adapter. |
| **Pass rate** | passing attempts ÷ scored attempts, where scored excludes `harness_error`. |
| **Status** | `passed`, `failed`, `timeout`, `tampered`, `agent_error`, `harness_error`. |

## Before measuring

```bash
git status --porcelain          # a clean tree, or the run is marked dirty
python3 -m unittest discover -s tests -t . -v
python3 -m benchmark selfcheck
```

`selfcheck` establishes the two bounds of the scale on the current apparatus:
every task fails with no work and passes with the reference solution.

## Measuring

```bash
python3 -m benchmark run --adapter claude-code --attempts 5 --label "baseline"
```

**On sample size.** Agents are non-deterministic. A single attempt per task is
an anecdote. Use `--attempts 5` or more for any number you intend to quote, and
report the number of attempts alongside the rate — a rate without its
denominator is not a result.

**On comparisons.** Two adapters are comparable only when the git commit, the
protocol version, and every task fingerprint match. `verify-integrity` reports
fixture drift; treat it as a blocker, not a warning.

## Reading results

```bash
python3 -m benchmark report                      # recent runs
python3 -m benchmark report --run <uid>          # per-attempt detail
python3 -m benchmark report --run <uid> --json   # machine-readable
python3 -m benchmark report --leaderboard        # aggregate by adapter
python3 -m benchmark verify-integrity            # audit before quoting anything
```

Read the statuses, not only the rate. They separate three very different
stories that a single percentage hides:

- **`failed`** — the agent produced code; the code was wrong. The interesting case.
- **`timeout`** — the agent's own edits made verification hang, or the task's
  budget is too tight. Check which before drawing a conclusion.
- **`agent_error`** — the agent never finished. An infrastructure and capability
  story mixed together; investigate before counting it as a capability signal.
- **`tampered`** — the agent went after the tests. Always worth reporting
  separately; it is a behavioural finding, not a scoring detail.

## Reporting

State, every time: adapter and adapter version, git commit, attempts per task,
number of tasks, the pass rate with its denominator, and the tamper count.
Numbers without that context are not reproducible claims.

Never publish a run made from a dirty working tree as a reproducible result.
Never drop a task from a comparison after seeing its outcome — that is
selection on the dependent variable, and it is the most common way an honest
benchmark becomes a dishonest one.
