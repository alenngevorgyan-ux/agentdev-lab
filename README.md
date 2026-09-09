# AgentDev Lab

A reproducible benchmark and analytics system for comparing AI coding agents —
Claude Code, Codex and others — on realistic software-engineering tasks.

It answers one question honestly:

> Given a real repository and a real task, does an agent produce code that
> passes tests it was never allowed to see or touch?

**No agent has been measured yet.** The instrument is built, self-validating and
populated with clearly-labelled synthetic data so the analytics can be reviewed.
Real Claude/Codex numbers will be collected later and are deliberately absent —
see [Status](#status).

---

## Five-minute tour

```bash
./setup.sh --dashboard      # verifies everything, seeds sample data, opens the dashboard
```

Nothing to install. Python 3.11+, standard library only.

| What | Where |
| --- | --- |
| How one attempt is measured | [The measurement](#the-measurement) below, `benchmark/runner.py` |
| The 18 benchmark tasks | `python3 -m benchmark list`, `benchmark/tasks/` |
| Why the numbers are trustworthy | [docs/integrity.md](docs/integrity.md) |
| The metrics and how they are derived | [docs/metrics.md](docs/metrics.md) |
| How agents fail, categorised | [docs/failure-taxonomy.md](docs/failure-taxonomy.md) |
| 24 SQL analyses | `python3 -m benchmark sql`, [sql/README.md](sql/README.md) |
| Design decisions and trade-offs | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Running an agent end to end | [docs/methodology.md](docs/methodology.md) |
| Writing a new adapter | [docs/adapters.md](docs/adapters.md) |
| The dashboard | [docs/dashboard.md](docs/dashboard.md) |
| What this cannot do | [Limitations](#limitations) |

---

## The measurement

One **attempt** is one (task, agent) pair executed once, through a fixed protocol:

```
 1. fresh sandbox from the pinned task fixture
 2. evaluate a pristine copy         -> which tests passed BEFORE any work
 3. digest the protected test paths  -> before
 4. the agent's turn                 (it never sees the hidden acceptance tests)
 5. digest the protected paths again -> after;  diff vs the fixture
 6. overlay the hidden tests, evaluate
 7. compare against step 2           -> regressions
 8. score mechanically, classify the failure, append an immutable record
```

Four properties follow, and they are what make the number worth quoting:

**The agent cannot grade itself.** Adapters report whether the agent *ran*, never
whether it *succeeded*. Success is computed from the acceptance suite's exit code.

**Weakening the tests cannot help.** Each task declares protected paths, digested
before and after the agent's turn. Any change — an edited assertion, a `@skip`, a
deleted file — is recorded as `tampered`, and a tampered attempt can never be a
pass. That invariant is enforced in the dataclass, in a `CHECK` constraint, and
in the reporting views.

**Fourteen of the eighteen tasks grade against hidden tests** the agent never
sees, so it cannot fit its work to the exact assertions.

**Breaking working code is caught.** Every attempt is compared against a baseline
evaluation of the untouched fixture. A test that passed before and fails after is
a recorded regression, and a regression demotes the attempt whatever the exit code
said.

---

## The task suite

18 tasks over 12 capability categories, all deterministic, all standard-library:

| Category | Tasks | Example |
| --- | --- | --- |
| exploration | 2 | A crash reported only by symptom, in a nine-module repo |
| bugfix_local | 2 | Off-by-one and boundary errors in pagination |
| bugfix_multifile | 2 | Cent drift across money, pricing and invoicing |
| feature | 3 | A retry policy with injected clock and RNG |
| refactor | 2 | Replace a duplicated dispatch chain with a registry |
| test_generation | 1 | **Graded by mutation testing**: the agent's suite must catch six broken implementations |
| requirements_following | 1 | A version parser against a written specification |
| ambiguous_requirements | 1 | An underspecified ticket, graded only on invariants any defensible reading satisfies |
| regression_avoidance | 1 | Add cache TTL without disturbing 23 passing tests |
| dependency_api | 1 | Use an in-house event bus with non-obvious semantics correctly |
| long_context_navigation | 1 | Data loss traced through a sixteen-stage pipeline |
| architectural_constraints | 1 | Ports and adapters, layering enforced on the import graph |

Each task carries a unique id, a clean starting state, a natural-language
requirement, explicit acceptance criteria, protected tests, category, difficulty,
expected affected files, a timeout, and a deterministic evaluation command.
Format: [docs/task-format.md](docs/task-format.md). **Reference solutions are
never exposed to the agent under test** — they exist only for the oracle control.

---

## Metrics

Stored per attempt: pass/fail, percentage of tests passed, regressions, files
changed, lines added/deleted, expected files touched, tool calls, turns, cost,
human interventions, wall-clock duration, failure category, and per-test outcomes.

Derived in SQL: success rate, first-pass success, eventual-vs-first-pass,
median and p90 completion time, regression rate, human-intervention rate, success
by category and by difficulty, cost per successful task, partial credit,
hidden-vs-visible test performance, and attempt-to-attempt variance.

Full definitions: [docs/metrics.md](docs/metrics.md).

---

## Commands

```bash
python3 -m benchmark list                      # the task catalogue
python3 -m benchmark adapters                  # agents and controls, with versions
python3 -m benchmark selfcheck                 # validate the harness against every task
python3 -m benchmark run --adapter oracle      # upper control: must score 100%
python3 -m benchmark run --adapter noop        # lower control: must score 0%
python3 -m benchmark sql                       # list the 24 analyses
python3 -m benchmark sql 09                    # run one
python3 -m benchmark dashboard                 # local dashboard on :8765
python3 -m benchmark export --format csv --out out/
python3 -m benchmark verify-integrity          # audit before quoting anything
```

Measuring a real agent:

```bash
ANTHROPIC_API_KEY=... python3 -m benchmark run \
    --adapter claude-code --agent claude-code --model claude-opus-5 --attempts 5
```

---

## Controls

| Adapter | Role | What it proves |
| --- | --- | --- |
| `noop` | control | Changes nothing. A task it passes is a broken task. |
| `oracle` | control | Applies the reference solution. A task it fails is a broken task. |
| `claude-code` | agent under test | Drives the Claude Code CLI headlessly inside the sandbox. |

`selfcheck` asserts both polarities for all 18 tasks and is an authoritative test
command, so a broken task cannot reach a commit. Controls never appear in a claim
about agent capability, and every report says so.

---

## Tests

The authoritative commands live in [`tests.json`](tests.json) and are run verbatim:

```bash
python3 -m unittest discover -s tests -t . -v     # 212 tests
python3 -m benchmark selfcheck                    # 74 checks over 18 tasks
python3 -m benchmark verify-integrity             # audit of the stored record
```

The suite includes adversarial adapters that delete tests and that replace them
with `@unittest.skip` — both must be recorded as `tampered` — and executes all 24
SQL analyses, so a broken query fails the build.

---

## Status

| Milestone | State |
| --- | --- |
| Harness, sandboxing, scoring, integrity | done |
| 18 tasks across 12 categories | done |
| Metrics, SQL, dashboard, export | done |
| **Real agent measurements** | **not collected** — see below |

The `claude-code` adapter is implemented and validated, but this machine's CLI is
authenticated by its host session and passes no credential to a subprocess. Rather
than publish a meaningless zero, the adapter now refuses to measure without
credentials, and the audit flags any attempt that changed nothing. The full story,
including a bad row that is disclosed rather than deleted, is in
[progress.md](progress.md).

---

## Limitations

Stated plainly, because a benchmark that hides its limits is marketing.

- **No real agent has been measured.** Every number visible today is either a
  control or synthetic sample data.
- Tasks are Python and small by design — cheap and deterministic, but they do not
  measure build systems, multi-repo work, or long-horizon projects.
- Verification is exit-code based: it measures "tests pass", not readability,
  performance or maintainability.
- Tamper detection covers declared protected paths. An agent could still satisfy
  a test degenerately *within* the code it may edit; task authors carry that.
- The failure classifier is a heuristic over recorded evidence and says
  `unclassified` rather than guessing. Machine and human labels are stored
  separately and never mixed.
- Sandboxes are filesystem-isolated, not OS-sandboxed. Run only agents you
  already trust locally.
- Sample size is whatever `--attempts` was set to. A single attempt is an
  anecdote; query 16 shows which tasks are non-deterministic.
- Cost and tool-call figures depend on the agent reporting them; they are `NULL`,
  not zero, when it does not.

## License

Unreleased research code. All rights reserved.
