# Experimental integrity

The rules that make a number here worth quoting. Each one names the failure it
prevents and the mechanism that enforces it — a rule enforced only by good
intentions is not enforced.

## 1. No fabricated data

**Failure it prevents:** a plausible number that was never measured.

Every number in a report is read back out of the results database. There is no
code path that computes a rate from anything else, and `report.py` has no
access to a live run. Numbers appearing in documentation must either come from
a named `run_uid` or be visibly marked as illustrative.

If a measurement does not exist, the honest output is "not measured yet" plus
the command that would measure it.

## 2. No weakening tests

**Failure it prevents:** an agent (or an engineer) making the bar lower instead
of clearing it.

Each task declares `protected_paths`. Their digest is taken immediately before
and immediately after the agent's turn. Any difference yields `tampered`:

- verification is not run — a green suite proves nothing once it has been edited;
- `Score` refuses to construct a passing tampered result;
- `CHECK (NOT (passed = 1 AND tampered = 1))` refuses to store one;
- `v_run_summary` counts it as a non-pass;
- `verify-integrity` surfaces it as a finding.

Both realistic cheats are covered by tests: deleting the test file, and
replacing it with a `@unittest.skip` that "passes". Both are recorded as
`tampered`.

The same rule binds contributors. Never relax the harness's own suite, an
integrity check, a schema constraint, or a command in `tests.json` to obtain a
green result.

## 3. Both controls, always

**Failure it prevents:** measuring a task that was already passing, or one that
nothing could pass.

`selfcheck` asserts, for every task, that `noop` **fails** it and `oracle`
**passes** it. It is an authoritative test command, so a broken task cannot
reach a milestone commit.

## 4. Provenance on every row

**Failure it prevents:** comparing numbers produced by different apparatus.

Every run records the harness version, protocol version, git commit, dirty
flag, Python version, platform, adapter name and adapter version. Every attempt
records a fingerprint of the task spec *and* fixture as they were at run time.

- Bump `HARNESS_PROTOCOL_VERSION` when a change alters measured outcomes.
- `git_dirty = 1` marks a run made from uncommitted code. Such runs are kept
  and disclosed, never presented as reproducible.
- `verify-integrity` reports fixture drift rather than averaging across it.

## 5. Append-only record

**Failure it prevents:** quietly correcting a result after seeing it.

`attempts` and `attempt_logs` cannot be updated or deleted; `runs` cannot be
deleted and their provenance cannot be rewritten. All four are enforced by
SQLite triggers, so the guarantee holds even against `sqlite3` on the command
line. A run may only be closed out.

If a result is wrong, the remedy is a new run.

## 6. Honest denominators

**Failure it prevents:** charging our bugs to the agent, or hiding them.

`harness_error` marks a failure of the lab itself and is excluded from pass
rates while remaining visible in reports. Agent crashes and timeouts are
`agent_error` and **are** counted — an agent that cannot finish has not solved
the task.

## 6b. The answers are structurally unreachable

**Failure it prevents:** an agent reading the tests, the reference solution or
the grading logic it is being measured against.

Prompt instructions are not a boundary. The agent turn runs inside a
kernel-enforced policy whose only writable path is its own workspace; the task
directory, the harness checkout, the results database, sibling attempts and the
host home directory cannot be read, written or even stat-ed. An adversarial
canary adapter attacks that boundary on every test run and must reach nothing.

Where no backend can enforce a boundary, the harness refuses to run. Running
anyway requires `--isolation none` by name and records every affected run as
NON-PUBLISHABLE. Full detail: [isolation.md](isolation.md).

## 6c. Grading cannot be hijacked

**Failure it prevents:** a forged test run.

An agent that plants a file named after a standard-library module the evaluator
imports can make the "suite" print a pass and exit zero without touching a
protected path. Evaluation therefore runs with the working directory off the
import path, and any added stdlib-shadowing file in the workspace root is
recorded as tampering.

## 6d. Credentials never enter the record

**Failure it prevents:** publishing a secret through evidence.

Captured output is redacted where it is captured, so the database, exports, the
dashboard and the session log all inherit it. `verify-integrity` re-checks
stored evidence for credential-shaped values, and a test asserts no tracked file
contains one.

## 7. An agent that never ran was never measured

**Failure it prevents:** recording an infrastructure failure as a capability
failure.

An agent CLI can fail to start and still exit 0 — printing "Not logged in",
"Invalid API key", or a quota message. Scored naively, every task becomes a
task the agent attempted and failed, and the resulting pass rate is fiction.

Two mechanisms guard this:

- Adapters preflight (binary present, credentials reachable) and scan output
  for non-start signatures, returning `agent_error` instead of a failed task.
- `verify-integrity` flags any non-control attempt whose workspace digest is
  unchanged, retroactively catching rows recorded before an adapter learned to
  detect its own failure mode. Because results are append-only, such a row
  cannot be quietly removed — it is disclosed instead.

## 8. Controls are not competitors

`noop` and `oracle` bound the scale. They never appear in a claim about agent
capability, and the leaderboard says so in print.

## Auditing

```bash
python3 -m benchmark verify-integrity          # audit the recorded results
python3 -m benchmark verify-integrity --deep   # also re-validate every task
```

Standalone queries live in `sql/queries/`: `tamper_report.sql`,
`fixture_drift.sql`, `no_change_attempts.sql`, `task_pass_rate.sql`,
`run_summary.sql`.
