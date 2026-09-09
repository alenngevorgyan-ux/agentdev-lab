# Architecture

This document explains what AgentDev Lab is made of and, more importantly, why
each piece is shaped the way it is. Most of the design exists to remove ways an
evaluation can quietly lie.

## 1. The measurement

One **attempt** is one (task, agent) pair executed once. Its protocol is fixed:

```
create sandbox from pinned fixture
  evaluate a pristine copy          -> baseline: which tests passed before any work
  digest protected paths            -> before
  agent's turn                      -> AgentOutcome (ran / did not run)
  digest protected paths            -> after;  diff vs the fixture
  if before == after and agent ran:
      overlay the hidden acceptance tests
      run the task's evaluation command, parse per-test outcomes
      regressions = baseline satisfied - now satisfied
  score(tamper, agent, timeout, regressions, exit code)
  classify the failure from recorded evidence
  append immutable row + per-test rows + captured logs
destroy sandbox
```

Four properties follow directly from that ordering.

**The agent cannot grade itself.** `AgentOutcome` carries `completed`, which
answers "did the process run to completion" — not "did it succeed". Success is
computed in `scoring.py` from the verification exit code alone.

**Weakening the tests cannot help.** The digest of the protected paths is taken
before and after the agent's turn. Any difference — an edited assertion, a
`@skip`, a deleted file — yields `tampered`. Verification is not even run,
because there is nothing left worth measuring. `tampered` can never be a pass:
the invariant is enforced in the `Score` dataclass, again in a `CHECK`
constraint, and again in the reporting views.

**Hidden tests cannot be fitted to.** The acceptance overlay lands only after the
agent's turn, so the assertions an attempt is graded on were never present in the
workspace it read. Fourteen of the eighteen tasks use one.

**Breaking working code is provable.** Without the baseline in step 2, "the agent
broke something" is unfalsifiable: a failing test might have been failing all
along. With it, a regression is a set difference, and it demotes the attempt even
when the acceptance command exits 0.

**Results are comparable or visibly not.** Every attempt stores a fingerprint
of the task spec *and* its fixture tree at run time. Editing a task changes the
fingerprint, and `verify-integrity` reports the drift instead of averaging
across two different experiments.

## 2. Modules

| Module | Responsibility | Why it is separate |
| --- | --- | --- |
| `tasks.py` | Load and strictly validate task specs. | A typo in `protected_paths` must fail loudly, not silently disable tamper detection. Unknown keys are rejected. |
| `hashing.py` | Canonical SHA-256 over files, trees, JSON. | One definition of "did this change", used by fingerprints and tamper detection alike. Ignores `__pycache__` so build residue never reads as an edit. |
| `sandbox.py` | Per-attempt isolated workspace. | Attempts must not see each other, and nothing an agent does may reach the task definition or the database. |
| `execution.py` | Subprocess with timeout, minimal env, bounded capture. | A stray `PYTHONPATH` or an unbounded log must not be able to change or drown a measurement. |
| `scoring.py` | The only place an outcome is decided. | One function, mechanical rules, no partial credit, no model-judged grading. |
| `storage.py` | Append-only SQLite persistence. | Results are a laboratory notebook. There is deliberately no update or delete path for an attempt. |
| `runner.py` | The protocol above. | Keeps ordering in one readable place; an adapter crash becomes an agent error, never a silent skip. |
| `integrity.py` | Self-validation and record auditing. | The checks that turn a number into evidence. |
| `testparse.py` | Per-test outcomes from verbose `unittest` output. | An exit code cannot express partial credit or identify which test regressed. |
| `diffstats.py` | Files and lines changed against the fixture. | Separates a two-line fix from a rewrite, which pass/fail hides. |
| `failures.py` | The taxonomy and its evidence-based classifier. | Turns "it failed" into an actionable finding, while refusing to guess. |
| `queries.py` | Discovery and execution of the curated SQL. | The `.sql` files are what run; there is no query builder that could differ from them. |
| `export.py` | JSON and CSV export with provenance. | Analysis should not require this repository. |
| `dashboard.py` | A local page rendered from the curated queries. | The dashboard performs no arithmetic of its own. |
| `sampledata.py` | Clearly-labelled synthetic rows. | Lets the analytics be built and reviewed before real runs exist, without ever passing as evidence. |
| `report.py` | Rendering over stored rows only. | Reports can restate the record; they can never compute a new one. |
| `adapters/` | Agents under test and controls. | The only place that knows how to drive a specific agent. |

## 3. Why the controls exist

A benchmark can be broken in two directions, and each has a control:

- **`noop`** changes nothing. If a task passes with no work done, the task was
  already green and measures nothing.
- **`oracle`** applies the task's reference solution. If a task fails with a
  known-correct solution, the task is unsolvable or its verification is broken.

`python3 -m benchmark selfcheck` asserts both polarities for every task, and is
an authoritative test command. Controls are labelled as controls in every
report so a `100%` oracle row is never mistaken for an agent result.

## 4. Storage model

`sql/schema.sql` defines three tables (`runs`, `attempts`, `attempt_logs`) and
two reporting views. The constraints carry real weight:

- `CHECK (NOT (passed = 1 AND tampered = 1))` — a cheat is never a pass.
- `CHECK ((passed = 1) = (status = 'passed'))` — the boolean and the status can
  never disagree.
- `UNIQUE (run_id, task_id, attempt_index)` — no accidental double-counting.
- Triggers block `UPDATE` and `DELETE` on `attempts`, `DELETE` on `runs` and
  `attempt_logs`, and any rewrite of a run's provenance. A run may only be
  *closed out*.

Harness errors (our bugs: an IO failure, a missing fixture) are recorded as
`harness_error` and **excluded from the denominator** of a pass rate. Counting
our own failure as the agent's failure would be as dishonest as the reverse.

## 4a. Scope, stored in the database

Analyses do not hardcode which rows they may count. They read `analysis_scope`, a
one-column table listing the run kinds currently in scope, defaulting to real
measurements only. Widening it to include controls or synthetic rows is a
deliberate act that is itself persisted, so a later reader can see exactly what
any number was permitted to count — and both the CLI and the dashboard announce
it in words when synthetic rows are included.

The alternative, a `WHERE run_kind = 'measurement'` in each file, would have been
invisible to anyone running the queries through `sqlite3` and impossible to widen
without editing 24 files.

## 5. Deliberate constraints

**Standard library only.** A benchmark whose environment drifts is not
reproducible. Tasks use `unittest`, not `pytest`, for the same reason: a
sandbox needs nothing installed. Adding a dependency requires recording the
decision here.

**Injected clocks over real time in tasks.** Tasks are deterministic by
construction (see `py-003-token-bucket`); a flaky task produces noise that
looks like a capability difference.

**Bounded everything.** Every subprocess has a timeout, every capture has a
size cap, every sandbox is destroyed. An agent that hangs produces a recorded
`agent_error`, not a stalled run.

## 6. Known limitations

Stated plainly, because a benchmark that hides its limits is marketing:

- Tasks are currently single-file Python problems with small fixtures. They do
  not measure multi-repo navigation, build systems, or long-horizon work.
- Verification is exit-code based. It measures "tests pass", not code quality,
  performance, or maintainability.
- Tamper detection covers declared `protected_paths`. An agent could still make
  a task pass in a degenerate way *within* the source it is allowed to edit;
  task authors are responsible for tests that pin behaviour, not shape.
- Sandboxes are filesystem-isolated, not OS-sandboxed. The harness is intended
  for agents you already trust to run locally.
- Sample sizes are whatever `--attempts` was set to. Non-determinism in an
  agent is real; a single attempt is an anecdote, not a rate.
