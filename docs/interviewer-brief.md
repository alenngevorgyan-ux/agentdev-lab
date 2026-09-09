# AgentDev Lab — brief

*Two pages. No results are claimed; none have been collected.*

## The problem

Teams are adopting AI coding agents without a defensible way to compare them.
The public benchmarks that exist are easy to fool by accident: the agent reads
the tests it is graded on, or edits them, or the task was already passing, or
the fixture changed between runs, or a bad result quietly disappears.

The product question underneath is not "which agent scores higher" but **"can
we produce a number about agent capability that survives a hostile reviewer?"**
This project is an attempt at the instrument, not at the number.

## Methodology

One **attempt** = one (task, agent) pair, executed once:

1. A private root is created holding only this attempt's workspace, copied from
   a content-hashed fixture.
2. A pristine copy is evaluated first, recording which tests passed **before**
   any work — without this, "the agent broke it" is unfalsifiable.
3. The protected test paths are digested.
4. **The agent runs inside a kernel-enforced isolation boundary.**
5. The protected paths are digested again; the workspace is diffed against the
   fixture.
6. The host applies the **hidden acceptance tests** — which were never on a
   filesystem the agent could see — and evaluates, with the network denied.
7. Regressions = tests satisfied at baseline and no longer satisfied.
8. The outcome is scored mechanically and appended immutably.

18 tasks span 12 capability categories: repository exploration, localized and
multi-file bug fixing, feature work, refactoring, test generation, precise
requirement following, ambiguous requirements, regression avoidance, in-repo API
use, long-context navigation and architectural constraints. One is graded by
**mutation testing** — the agent writes a test suite, and it only counts if it
catches six deliberately broken implementations.

## Architecture

Standard library only, so the environment cannot drift.

```
benchmark/isolation/    the boundary: docker | seatbelt | none, selected explicitly
benchmark/runner.py     the attempt protocol above
benchmark/scoring.py    the one place an outcome is decided
benchmark/storage.py    append-only SQLite, enforced by triggers
benchmark/experiment.py frozen, hashed comparison manifests
sql/                    schema + 25 documented analyses
benchmark/tasks/        task.json + workspace/ + acceptance/ + solution/
```

## The five properties that make a number defensible

1. **Answers are structurally unreachable.** Not "the prompt didn't mention
   them" — an `open()` on the hidden tests, the reference solution, the harness
   source, the results database, a sibling attempt or the host home directory
   fails with EPERM inside the boundary, and `os.path.exists()` returns False. A
   hostile canary adapter attacks that boundary with nineteen probes on every
   test run. Where no boundary can be enforced the harness refuses to run, or
   records the run NON-PUBLISHABLE. It never degrades silently.
2. **The agent never grades itself.** Adapters report whether the process *ran*.
   The verdict is the host's, computed after the agent has exited.
3. **Gaming the grader is caught.** Editing, deleting or skipping a protected
   test is `tampered`, which can never be a pass — enforced in the dataclass, a
   database `CHECK`, and the reporting views.
4. **Regressions are provable**, via the pre-measured baseline, and demote an
   attempt whatever the exit code said.
5. **Methodology is frozen before results.** A hashed manifest pins the task set,
   attempts, timeout, ordering seed and *analysis plan*; every attempt records
   the hash; attempts under different hashes are never pooled; results cannot be
   deleted.

## Bugs the benchmark caught in itself

This is the part I would want to be asked about. Each was found by the
apparatus, not by inspection, and each is now a regression test.

- **A grading bypass.** An agent that plants `unittest.py` in its workspace
  hijacks `python -m unittest`: the forged module prints a convincing
  `Ran 12 … OK` and exits zero. It touches no protected path, so tamper
  detection was blind to it. Closed twice: evaluation now runs with the working
  directory off the import path, and any added file shadowing a standard-library
  name is recorded as tampering.
- **Silent metric fabrication.** The per-test parser dropped tests whose output
  spanned two lines, recording "3/3" for a suite of ten. Pass/fail was right;
  the per-test metrics were lower bounds presented as measurements. The parser
  was fixed, and an incomplete parse now falls back to the runner's own count so
  it can never inflate a pass fraction.
- **An infrastructure failure scored as a capability failure.** Claude Code
  printed "Not logged in" and exited zero; the harness recorded a normal failed
  attempt. At scale that would have produced a confident, fictional 0%. Adapters
  now preflight, and the audit flags any attempt that changed nothing.
- **A scope that widened itself.** Reopening the database re-seeded the default
  analysis scope, which could have folded synthetic sample rows back into a real
  measurement.
- **Two bad tasks.** The oracle control caught a task whose prompt contradicted
  its own tests, and one that failed a correct solution over a substring match.

## Limitations, stated plainly

- **No agent has been measured.** Every visible number is a control or
  clearly-labelled synthetic data. That is a deliberate refusal to publish a
  number the harness could not yet defend.
- **The tasks and the harness share an author**, who used Claude Code while
  writing them. The controls catch unsolvable and already-passing tasks; they do
  not catch favouritism. Unfixed, and stated wherever a result is reported.
- 18 small Python tasks are not a sample of software engineering. No build
  systems, no multi-repo work, nothing long-horizon.
- Grading is exit-code based. It measures "the tests pass", not whether a
  reviewer would accept the diff.
- Isolation is proven on macOS Seatbelt. The Docker backend is implemented but
  never ran against a live daemon.
- The Codex adapter's flags are verified against the installed CLI and its
  command construction is tested, but it has never completed an end-to-end run.

## The experiment that comes next

Pre-registered in `experiments/claude-vs-codex-v1.json`, frozen and hashed:
Claude Code against Codex, 18 tasks × 5 attempts × 2 agents = 180 attempts,
equal timeouts, identical prompts and fixtures, interleaved and seed-permuted
ordering, analysis plan fixed in advance. It needs API credentials for both
agents, since the boundary denies the home directories where their CLIs keep
their logins.

`python3 -m benchmark experiment verify` checks the publication gate: enforced
isolation on every attempt, a clean checkout, one protocol version, one fixture
per task, equal attempt counts, no synthetic rows, and rate-limit and timeout
shares under their thresholds. Today it reports, correctly, that the experiment
has not been run.
