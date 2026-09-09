# CLAUDE.md — persistent context for AgentDev Lab

This file is the standing brief for every Claude Code session in this
repository, local or cloud. Read it before doing anything else. If something
here conflicts with a habit or a default, this file wins.

---

## 1. Project goal

AgentDev Lab is a **reproducible benchmark and research lab for evaluating AI
coding agents**. It measures one thing honestly:

> Given a real repository and a real task, does an agent produce code that
> passes tests it was never allowed to touch?

This is a 72-hour research engineering project. The deliverable is not a high
score — it is a measurement apparatus whose numbers can be defended. A result
that makes an agent look bad is a finding. A result that makes an agent look
good because the harness was lenient is a defect.

## 2. Architecture in one screen

One attempt runs through a fixed protocol. The order is the experiment; do not
reorder it:

```
1. create a fresh sandbox from the pinned task fixture
2. digest the task's protected paths          -> protected_hash_before
3. give the agent its turn (adapter.run)
4. digest the protected paths again           -> protected_hash_after
5. run the task's own verification command (only if 2 == 4 and the agent finished)
6. score mechanically, append an immutable row
```

Key invariants:

- **The agent never grades itself.** `AgentOutcome.completed` says only whether
  the agent *ran*, never whether it *succeeded*.
- **Tamper detection outranks everything.** `protected_hash_before !=
  protected_hash_after` yields `tampered`, which is never a pass, even if the
  tests then went green.
- **Results are append-only**, enforced by SQLite triggers, not by etiquette.
- **Every result carries provenance**: harness version, protocol version, git
  commit, dirty flag, Python version, platform, and a fingerprint of the task
  spec + fixture at run time.

Full reasoning: `ARCHITECTURE.md`. Integrity rules: `docs/integrity.md`.

## 3. Repository layout

```
benchmark/
  __init__.py        version + HARNESS_PROTOCOL_VERSION (bump when semantics change)
  config.py          paths, env overrides, RunConfig
  hashing.py         canonical SHA-256 over files/trees/JSON
  tasks.py           task spec loading + strict validation
  sandbox.py         per-attempt isolated workspaces
  execution.py       subprocess with timeout, minimal env, bounded capture
  scoring.py         Status enum + the only place an outcome is decided
  storage.py         SQLite persistence (append-only)
  runner.py          the attempt/run protocol above
  integrity.py       selfcheck + recorded-results audit
  report.py          rendering over stored rows only
  cli.py             `python3 -m benchmark ...`
  adapters/          noop (control), oracle (control), claude_code (under test)
  tasks/<task-id>/   task.json + workspace/ + solution/
sql/
  schema.sql         results schema, constraints, append-only triggers, views
  queries/           standalone analysis queries
tests/               the harness's own suite (stdlib unittest)
docs/                task format, adapter contract, integrity, methodology
tests.json           authoritative test commands
progress.md          session log
```

## 4. Setup

No installation, no virtualenv, no dependencies.

```bash
cd /path/to/agentdev-lab
python3 --version          # must be >= 3.11
python3 -m benchmark list
```

Environment overrides (all optional):

| Variable | Effect |
| --- | --- |
| `AGENTDEV_DB` | Results database path (default `results/agentdev.sqlite3`). |
| `AGENTDEV_SANDBOX_ROOT` | Where per-attempt sandboxes are created. |
| `AGENTDEV_CLAUDE_BIN` | Claude Code binary for the `claude-code` adapter. |
| `AGENTDEV_CLAUDE_MODEL` | Model passed to that adapter. |
| `AGENTDEV_AGENT_TIMEOUT_SEC` | Per-attempt agent timeout (default 900). |

## 5. Authoritative test commands

Defined in `tests.json` and run **verbatim**. All three must exit 0 before any
milestone is committed:

```bash
python3 -m unittest discover -s tests -t . -v     # unit + integration
python3 -m benchmark selfcheck                    # controls validate every task
python3 -m benchmark verify-integrity             # audit the recorded results
```

`selfcheck` is the one that matters most: for every task it asserts that the
`noop` control **fails** it and the `oracle` control **passes** it. A task that
breaks either direction measures nothing.

## 6. Experimental integrity rules

These are not style preferences. Violating one invalidates the project.

### 6.1 No fabricated benchmark data — ever

- **Never** write a pass rate, timing, token count, or comparison that did not
  come from an actual recorded run in the results database.
- **Never** insert rows into the results database by hand, and never illustrate
  a report with plausible-looking example numbers.
- **Never** describe a run you did not execute, or a result you did not read
  back out of the database.
- If a number is needed and no run exists, the honest output is "not measured
  yet" plus the command that would measure it.
- If asked to estimate, label it an estimate in the same sentence, and never
  store it.
- Placeholder or illustrative numbers in docs must be visibly fake and marked
  as such. Prefer omitting them.

### 6.2 No weakening tests to obtain better results

- **Never** edit, delete, skip, `xfail`, loosen an assertion in, or shorten a
  timeout in a task's protected paths to make an attempt pass.
- **Never** relax the harness's own test suite to make a change land. If a test
  fails, either the change is wrong or the test encodes a rule that has
  genuinely changed — and in the second case, say so explicitly and change the
  rule deliberately.
- **Never** weaken a check in `benchmark/integrity.py` or a constraint in
  `sql/schema.sql` to get a green run.
- **Never** narrow an authoritative command in `tests.json` (fewer tests, a
  subset path, `--failfast` to hide later failures).
- Deleting a task because agents keep failing it is data suppression. A hard
  task is a finding; record it.

### 6.3 Comparability

- Bump `HARNESS_PROTOCOL_VERSION` when a change alters measured outcomes.
- Editing a task fixture changes its fingerprint and makes results either side
  of the edit non-comparable. Prefer adding a new task id over mutating one
  that has already been measured.
- Runs from a dirty working tree are recorded as `git_dirty = 1`. Never present
  such a run as reproducible.

### 6.4 Controls are not competitors

`noop` and `oracle` measure the harness, not an agent. Never include them in a
claim about agent capability.

## 7. Session discipline

**Before ending a session, update `progress.md`.** Append a dated entry
covering: what was built, what the authoritative commands reported (actual
output, not a summary from memory), what is unfinished, and the next concrete
step. This file is how the next session — which remembers nothing — resumes
without re-deriving the project.

**Commit stable milestones.** A milestone is committable when all three
authoritative suites exit 0. Commit at that point rather than accumulating a
large unreviewable change. Use imperative subjects (`add token-bucket task`,
`enforce append-only attempts`). Never commit `results/`, `.sandboxes/`, or any
generated database.

## 8. Working conventions

- Standard library only. Adding a dependency requires an explicit decision
  recorded in `ARCHITECTURE.md`.
- Type hints on public functions; dataclasses for structured values.
- Comments explain *why*, never *what*. The code says what.
- New harness behaviour ships with a test in the same change.
- New tasks must self-check clean (`noop` fails it, `oracle` passes it) before
  being committed.
