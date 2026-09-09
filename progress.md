# Progress log

Append-only project log. Every session adds a dated entry before it ends:
what was built, what the authoritative commands actually reported, what is
unfinished, and the next concrete step.

---

## Implementation plan

A 72-hour research engineering project, sequenced so that every milestone is
independently defensible.

| # | Milestone | Definition of done | Status |
| --- | --- | --- | --- |
| M0 | Repository foundation | README, CLAUDE.md, ARCHITECTURE.md, progress.md, tests.json, docs/, sql/, benchmark/, tests/ in place. | **done** |
| M1 | Task model + sandboxing | Strict task specs, content-addressed fixtures, isolated per-attempt sandboxes, bounded subprocess execution. | **done** |
| M2 | Scoring + tamper detection | Mechanical scoring; protected-path digests before and after the agent's turn; tampering can never be a pass. | **done** |
| M3 | Append-only results store | SQLite schema with constraints and triggers; full provenance on every run; reporting views. | **done** |
| M4 | Controls + selfcheck | `noop` and `oracle` adapters; `selfcheck` asserts both polarities for every task. | **done** |
| M5 | Seed task suite | Three deterministic Python tasks (easy/medium/hard) that self-check clean. | **done** |
| M6 | Real agent adapter | `claude-code` adapter driving the CLI headlessly in a sandbox; end-to-end validated against the live binary. | **in progress** |
| M7 | Baseline measurement | A multi-attempt run of `claude-code` over the full suite from a clean checkout, with integrity audit. | not started |
| M8 | Task suite expansion | Grow to 10-15 tasks across bugfix / feature / refactor / performance, including multi-file fixtures. | not started |
| M9 | Analysis | Per-task and per-category breakdowns, variance across attempts, failure taxonomy. | not started |
| M10 | Write-up | Methodology and findings, with every number traceable to a `run_uid`. | not started |

Sequencing rationale: the apparatus is built and validated *before* any agent
is measured, so the first real number arrives on a harness that has already
demonstrated it can detect its own failure modes.

---

## 2026-09-09 — Session 1: foundation and working harness

### Built

- Repository foundation: `README.md`, `CLAUDE.md`, `ARCHITECTURE.md`,
  `tests.json`, `.gitignore`, `docs/`, `sql/`, `benchmark/`, `tests/`.
- Harness core (M1-M4): `tasks.py` (strict spec validation), `hashing.py`
  (canonical digests), `sandbox.py`, `execution.py` (timeouts, minimal env,
  bounded capture), `scoring.py`, `storage.py`, `runner.py`, `integrity.py`,
  `report.py`, `cli.py`.
- Results schema `sql/schema.sql`: constraints making a tampered pass
  unrepresentable, triggers making attempts append-only, two reporting views,
  four standalone analysis queries.
- Adapters: `noop` and `oracle` controls, plus `claude-code` driving the real
  CLI headlessly.
- Seed tasks (M5), all deterministic and standard-library only:
  `py-001-interval-merge` (easy, bugfix), `py-002-config-merge` (medium,
  feature), `py-003-token-bucket` (hard, feature).
- Test suite: 122 tests, including adversarial adapters that delete tests and
  that replace them with `@unittest.skip` — both are recorded as `tampered`.

### Design decisions

- **Standard library only, `unittest` not `pytest`.** A sandbox that needs an
  installed package is not reproducible.
- **Tamper detection outranks verification.** Once protected paths change, the
  verification command is not even run.
- **Append-only results, enforced by triggers.** The guarantee holds against
  direct `sqlite3` access, not just against the harness API.
- **Harness errors excluded from pass-rate denominators**, agent errors
  included. Our bugs are not the agent's failures; the agent's are.

### Authoritative commands — actual output

```
$ python3 -m unittest discover -s tests -t . -q
Ran 122 tests in 40.489s
OK

$ python3 -m benchmark selfcheck
14/14 checks passed

$ python3 -m benchmark verify-integrity
5/5 checks passed
```

### Control runs (harness validation, not agent results)

| Adapter | run_uid | Attempts | Passed | Tampered | Pass rate |
| --- | --- | --- | --- | --- | --- |
| `noop` | `5e402411c0c441ef` | 3 | 0 | 0 | 0.0% |
| `oracle` | `5133d015f5b14803` | 3 | 3 | 0 | 100.0% |

Both controls behaved exactly as required: every task fails with no work done
and passes with the reference solution, so the scale is bounded at both ends.
Both runs were made from an uncommitted working tree and are recorded with
`git_dirty = 1`; they validate the harness and are not reproducible results.

**No agent has been measured yet.** There is deliberately no `claude-code`
number in this entry.

### Unfinished

- M6: the `claude-code` adapter reports the live CLI version
  (`claude-code/2.1.266`) but has not yet completed an end-to-end attempt.
- M7: no baseline measurement exists.
- Task suite is 3 tasks; single-file Python only.

### Next step

Commit this milestone (all three authoritative suites are green), then run
`python3 -m benchmark run --adapter claude-code --task py-001-interval-merge`
from the clean checkout to validate M6 end to end before attempting a baseline.
