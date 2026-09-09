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
python3 -m benchmark stats  # live counts: tasks, categories, analyses, tests
python3 -m benchmark isolation   # which isolation backends work on this machine
```

Nothing to install. Python 3.11+, standard library only.

| What | Where |
| --- | --- |
| How one attempt is measured | [The measurement](#the-measurement) below, `benchmark/runner.py` |
| The 18 benchmark tasks | `python3 -m benchmark list`, `benchmark/tasks/` |
| Why the numbers are trustworthy | [Why this benchmark is trustworthy](#why-this-benchmark-is-trustworthy), [docs/integrity.md](docs/integrity.md) |
| How the agent is isolated, and the proof | [docs/isolation.md](docs/isolation.md) |
| The hostile review of this project | [docs/threat-model.md](docs/threat-model.md) |
| The frozen agent-vs-agent protocol | [docs/comparison-protocol.md](docs/comparison-protocol.md) |
| A two-page brief | [docs/interviewer-brief.md](docs/interviewer-brief.md) |
| The metrics and how they are derived | [docs/metrics.md](docs/metrics.md) |
| How agents fail, categorised | [docs/failure-taxonomy.md](docs/failure-taxonomy.md) |
| 25 SQL analyses | `python3 -m benchmark sql`, [sql/README.md](sql/README.md) |
| Design decisions and trade-offs | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Running an agent end to end | [docs/methodology.md](docs/methodology.md) |
| Writing a new adapter | [docs/adapters.md](docs/adapters.md) |
| The dashboard | [docs/dashboard.md](docs/dashboard.md) |
| What this cannot do | [Limitations](#limitations) |

---

## The measurement

One **attempt** is one (task, agent) pair executed once, through a fixed protocol:

```
 1. private root holding only this attempt's workspace, from the pinned fixture
 2. evaluate a pristine copy          -> which tests passed BEFORE any work
 3. digest the protected test paths   -> before
 4. THE AGENT'S TURN, inside an enforced isolation boundary
 5. digest the protected paths again  -> after;  diff vs the fixture
 6. overlay the hidden tests (host-side, agent already exited) and evaluate
 7. compare against step 2            -> regressions
 8. score mechanically, classify the failure, append an immutable record
```

## Why this benchmark is trustworthy

Five properties, each enforced by a mechanism rather than by a promise, and each
with a test that fails the build if it stops holding:

**1. The agent cannot reach the answers — structurally, not by instruction.**
The agent turn runs inside a kernel-enforced boundary whose only writable path
is its own workspace. The hidden acceptance tests, the reference solution, the
harness source, the results database, sibling attempts and the host home
directory are not merely absent from the prompt: an `open()` on them fails with
EPERM, and `os.path.exists()` returns False. A hostile canary adapter attacks
that boundary with nineteen probes on every test run; all nineteen are denied.
Where no boundary can be enforced, the harness refuses to run, or records the
run as NON-PUBLISHABLE — it never silently degrades to a working directory.

**2. The agent cannot grade itself.** Adapters report whether the agent *ran*,
never whether it *succeeded*. Success is computed from the acceptance suite's
exit code by the host, after the agent has exited.

**3. Gaming the grader cannot help.** Each task declares protected paths,
digested before and after the agent's turn; any change — an edited assertion, a
`@skip`, a deleted file — is `tampered`, which can never be a pass. Planting a
module that hijacks the interpreter running the tests is caught too: evaluation
runs with the working directory off the import path, and any added file shadowing
a standard-library name is recorded as tampering. Most tasks grade against hidden
tests the agent never sees, so work cannot be fitted to the exact assertions.

**4. Breaking working code is caught.** Every attempt is compared against a
baseline evaluation of the untouched fixture. A test that passed before and fails
after is a recorded regression, and a regression demotes the attempt whatever the
exit code said.

**5. The methodology is frozen before the results.** A comparison runs under a
hashed manifest pinning the task set, attempt count, timeout, ordering seed and
the analysis plan. Every attempt records that hash; attempts under different
hashes are never pooled. Results are append-only at the database level, so a run
cannot be deleted after it is seen — only superseded and disclosed.

See [docs/threat-model.md](docs/threat-model.md) for the full hostile review,
including the two grading bypasses this project found in itself.

## What this benchmark does NOT prove

- **Nothing about Claude Code or Codex yet.** No agent measurement exists. Every
  number visible today is a control or clearly-labelled synthetic sample data.
- **Not that agents are good at software engineering.** Eighteen small Python
  tasks, written by one person, are not a sample of the work. They say nothing
  about build systems, multi-repo changes, or anything lasting longer than one
  agent turn.
- **Not that the tasks are unbiased.** The harness and the tasks share an author.
  The controls catch unsolvable and already-passing tasks; they do not catch
  favouritism. This is unfixed and is stated wherever a number is reported.
- **Not code quality.** Grading is exit-code based: it measures "the tests pass",
  not readability, performance, or whether a reviewer would accept the diff.
- **Not a security sandbox for untrusted agents.** The boundary keeps the
  benchmark's answers away from the agent. The agent turn has network access
  because it must reach its API, and no filesystem policy constrains what it
  sends.

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
python3 -m benchmark sql                       # list the 25 analyses
python3 -m benchmark sql 09                    # run one
python3 -m benchmark dashboard                 # local dashboard on :8765
python3 -m benchmark export --format csv --out out/
python3 -m benchmark verify-integrity          # audit before quoting anything
python3 -m benchmark isolation                 # backends and whether they enforce
python3 -m benchmark experiment show experiments/claude-vs-codex-v1.json
```

Measuring a real agent (credentials must be in the environment: the boundary
denies the host home directory, so a CLI's own login file is unreachable by
design):

```bash
ANTHROPIC_API_KEY=... python3 -m benchmark run \
    --adapter claude-code --model claude-opus-5 --attempts 5 \
    --experiment experiments/claude-vs-codex-v1.json
python3 -m benchmark experiment verify experiments/claude-vs-codex-v1.json
```

---

## Controls

| Adapter | Role | What it proves |
| --- | --- | --- |
| `noop` | control | Changes nothing. A task it passes is a broken task. |
| `oracle` | control | Applies the reference solution. A task it fails is a broken task. |
| `canary` | control | Attacks its own isolation boundary and reports what it reached. Nothing, if the boundary holds. |
| `claude-code` | agent under test | Drives the Claude Code CLI headlessly inside the boundary. |
| `codex` | agent under test | Drives the Codex CLI non-interactively inside the boundary. Flags verified against the installed CLI; **no end-to-end run yet**. |

`selfcheck` asserts both polarities for all 18 tasks and is an authoritative test
command, so a broken task cannot reach a commit. Controls never appear in a claim
about agent capability, and every report says so.

---

## Tests

The authoritative commands live in [`tests.json`](tests.json) and are run verbatim:

```bash
python3 -m unittest discover -s tests -t . -v     # unit + integration
python3 -m benchmark selfcheck --deterministic    # controls validate every task
python3 -m benchmark verify-integrity             # audit of the stored record
python3 -m unittest tests.test_isolation -v       # the boundary must hold
```

Counts are not hardcoded here, because a stale number invites doubt about every
other number. `python3 -m benchmark stats` prints the live ones, and
`tests/test_docs.py` fails the build if this file disagrees with the repository.

The suite is adversarial about its own guarantees. It includes adapters that
delete the tests, that replace them with `@unittest.skip`, and that forge a
passing run by planting a module named after the standard-library one the
runner imports — all three must be recorded as `tampered`. It runs an isolation
canary that attacks the boundary from inside with nineteen probes, and executes
every SQL analysis, so a broken query fails the build.

---

## Status

| Milestone | State |
| --- | --- |
| Harness, sandboxing, scoring, integrity | done |
| 18 tasks across 12 categories | done |
| Metrics, SQL, dashboard, export | done |
| Enforced isolation + adversarial proof | done |
| Codex adapter, prompt/fixture parity | done (adapter unvalidated end-to-end — see below) |
| Frozen comparison protocol + manifest | done (pre-registered, not yet run) |
| **Real agent measurements** | **not collected** — see below |

Both agent adapters refuse to measure without a credential in the environment,
because the isolation boundary denies the host home directory where each CLI
keeps its login. That is deliberate: it is better to record "could not run" than
to publish a meaningless zero. The Codex adapter's flags are verified against the
installed CLI (`codex-cli 0.153.4`) and its command construction is tested, but
**no end-to-end Codex run has been performed**, so no claim is made that it
produces valid measurements.

The full story — including a bad row that is disclosed rather than deleted, and
the two grading bypasses the project found in itself — is in
[progress.md](progress.md) and [docs/threat-model.md](docs/threat-model.md).

---

## Limitations

Stated plainly, because a benchmark that hides its limits is marketing.

- **No real agent has been measured.** Every number visible today is either a
  control or synthetic sample data.
- Tasks are Python and small by design — cheap and deterministic, but they do not
  measure build systems, multi-repo work, or long-horizon projects.
- Verification is exit-code based: it measures "tests pass", not readability,
  performance or maintainability.
- Tamper detection covers declared protected paths plus interpreter shadowing. An
  agent could still satisfy a test degenerately *within* the code it may edit;
  task authors carry that.
- Isolation is verified on macOS via Seatbelt. The Docker backend is implemented
  but was never exercised against a live daemon, and Apple has deprecated
  `sandbox-exec`; the backend records the OS build so a behaviour change shows up.
- The tasks and the harness share an author. No procedure here removes that bias.
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
