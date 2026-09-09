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
| M6 | Real agent adapter | `claude-code` adapter driving the CLI headlessly in a sandbox; end-to-end validated against the live binary. | **blocked** — harness side done and validated; blocked on credentials (see Session 2). |
| M7 | Baseline measurement | A multi-attempt run of `claude-code` over the full suite from a clean checkout, with integrity audit. | not started |
| M8 | Task suite expansion | Grow to 10-15 tasks across bugfix / feature / refactor / performance, including multi-file fixtures. | in progress — 4 of 10-15 |
| M9 | Analysis | Per-task and per-category breakdowns, variance across attempts, failure taxonomy. | not started |
| M10 | Write-up | Methodology and findings, with every number traceable to a `run_uid`. | not started |

Sequencing rationale: the apparatus is built and validated *before* any agent
is measured, so the first real number arrives on a harness that has already
demonstrated it can detect its own failure modes.

---

## Implementation plan v2 — full research instrument

Session 3 expands the harness from a working measurement apparatus into the
complete instrument: hidden acceptance tests, per-test metrics, regression
detection, a failure taxonomy, a 15-25 task suite, SQL analytics, a dashboard,
and export.

| # | Milestone | Definition of done | Status |
| --- | --- | --- | --- |
| N1 | Metrics model v2 | Per-test results, regressions, diff stats, tool calls, cost, failure category, agent/model split, run kinds. Protocol version 2. | **done** |
| N2 | Hidden acceptance tests | `acceptance/` overlay applied only after the agent's turn; the agent never sees the tests it is graded on. | **done** |
| N3 | Baseline + regression detection | Pristine baseline evaluated per attempt; a test that passed before and fails after is a recorded regression. | **done** |
| N4 | Failure taxonomy | 12-category taxonomy with an evidence-based classifier, honestly labelled as heuristic. | **done** |
| N5 | Task suite 15-25 | Realistic multi-file tasks across all twelve capability categories. | **done** |
| N6 | SQL analytics | 20+ documented queries: GROUP BY, JOIN, CTE, CASE, window functions, ranking, comparative analysis. | **done** |
| N7 | Export | JSON and CSV export of runs, attempts, per-test results. | **done** |
| N8 | Dashboard | Zero-dependency local dashboard: headline metrics, agent comparison, category/difficulty breakdowns, latency distribution, failure taxonomy, run explorer. | **done** |
| N9 | Sample development data | Synthetic runs, unmistakably labelled, so the analytics stack is reviewable before real agent runs exist. | **done** |
| N10 | Setup + final pass | One init command, clean-install check, full suite, every query verified, honest limitations. | **done** |

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

---

## 2026-09-09 — Session 2: first real agent attempt, and the defect it exposed

### What happened

Ran the `claude-code` adapter end to end for the first time
(`run_uid 33b1263267344688`, task `py-001-interval-merge`). It reported a
`failed` attempt in 11.2 seconds. The stored agent log gave the real story:

```
Not logged in · Please run /login
```

The CLI could not authenticate as a subprocess, printed that, **and exited 0**.
The harness therefore recorded a normal failed attempt — that is, an
infrastructure failure recorded as a capability failure. Left alone, this is
exactly the kind of fabricated number this project exists to prevent, and at
scale it would have produced a confident "claude-code scores 0%".

Root cause: this machine's CLI is authenticated by its host session, not by a
credentials file or environment variable a child process can reuse. The
sandbox's deliberately minimal environment is not at fault; no reachable
credential exists to pass.

### Fixes

- `ClaudeCodeAdapter.preflight()` — refuses to measure when the binary is
  missing or no credential is reachable, returning `agent_error` before the
  attempt rather than a failed task afterwards.
- `NOT_READY_SIGNATURES` — output scan for "not logged in", "invalid api key",
  "credit balance", "rate limit" and similar, which turn a zero exit code into
  `agent_error`.
- New integrity check: **"every measured attempt actually changed the
  workspace"**. Any non-control attempt whose workspace digest is unchanged is
  flagged as not-a-measurement. Also available as
  `sql/queries/no_change_attempts.sql`.
- Nine new adapter tests plus two integrity tests covering both directions
  (an inert agent attempt is flagged; the noop control legitimately is not).

### Disclosure

Run `33b1263267344688` remains in the local results database and **must not be
read as a measurement of Claude Code**. It cannot be deleted — attempts are
append-only by design — so the audit discloses it instead:

```
$ python3 -m benchmark verify-integrity
[FAIL] every measured attempt actually changed the workspace
         attempts recorded with no file changes -- these are not capability measurements:
         claude-code / py-001-interval-merge #1 (33b12632)
5/6 checks passed -- 1 FAILED
```

This is the append-only rule working as intended: a bad number gets corrected
in public, not erased. A fresh checkout has no results database and audits
clean.

### Also built

- `py-004-extract-validation` (M8): a multi-file refactor task. Two modules
  carry drifted copies of the same validation logic; the agent must extract a
  shared module while preserving public behaviour, including fixing the drift.
  Self-checks clean in both directions.

### Authoritative commands — actual output

```
$ python3 -m unittest discover -s tests -t . -q
Ran 133 tests in 47.839s
OK

$ python3 -m benchmark selfcheck
18/18 checks passed

$ python3 -m benchmark verify-integrity
5/6 checks passed -- 1 FAILED   (the disclosed row above; clean on a fresh checkout)
```

### Unfinished

- M6/M7: **no valid measurement of any agent exists yet.** Unblocking requires
  `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` in the environment running
  the harness.
- M8: 4 tasks of a target 10-15; still single-language (Python).

### Next step

Export a credential, then:

```bash
python3 -m benchmark run --adapter claude-code --task py-001-interval-merge
```

Confirm the attempt actually changes the workspace before spending a full
multi-attempt baseline run (M7).

---

## 2026-09-09 — Session 3: from harness to research instrument

### Built

**Metrics model v2** (protocol version 2). Hidden acceptance tests as an
`acceptance/` overlay applied only after the agent's turn. A per-task baseline
evaluation of the pristine fixture, making regressions provable rather than
asserted. Per-test outcomes parsed from verbose `unittest` output into
`attempt_tests`. Diff statistics against the fixture. A twelve-category failure
taxonomy with an evidence-based classifier that returns `unclassified` rather
than guessing, and stores whether a label came from the machine or a human.

**Task suite: 4 -> 18**, covering all twelve capability categories. Fourteen
grade against hidden tests. Highlights: `py-008` is graded by **mutation
testing** (the agent's test suite must catch six deliberately broken
implementations); `py-011` adds cache TTL over a suite with 23 already-passing
tests, so regressions are detectable; `py-013` hides a data-loss bug in a
sixteen-stage pipeline; `py-014` enforces a layering rule on the import graph.

**Analytics.** 24 documented SQL analyses; an `analysis_scope` table so what a
number was allowed to count is itself stored; a zero-dependency dashboard;
JSON/CSV export carrying provenance and caveats; clearly-labelled synthetic
development data; `setup.sh`.

### Defects the instrument caught in itself

Three, all found by the controls or the new tests rather than by inspection:

1. `py-007`'s prompt specified `multiplier ** (n - 1)` while its tests required
   `(n - 2)`. A task whose prompt contradicts its tests measures prompt
   inconsistency, not capability. Prompt corrected.
2. `py-012`'s API-respect test forbade the substring `_tokens` anywhere, and so
   failed a correct solution for naming its own attribute. Replaced with an AST
   check for private access *on the bus object*.
3. Reopening the results database re-seeded the default analysis scope, silently
   widening a scope someone had deliberately narrowed — which could have folded
   synthetic rows back into a real measurement. Now seeded only for a new
   database.
4. **The per-test parser silently under-counted suites.** `unittest -v` prints a
   documented test across two lines (name, then "description ... ok"), and a
   test that writes to stderr has its outcome pushed below its header. Both were
   dropped, so `py-008` recorded "3/3" for a ten-test suite — a fabricated
   metric, even though the pass/fail itself was right. The parser now stitches
   split records; an incomplete parse falls back to the runner's own count as
   the denominator (never inflating the pass fraction), annotates the attempt,
   and is surfaced by a new integrity check. That check is what found the
   remaining eight affected attempts.

   Also fixed the `py-008` fixture, which leaked a `/dev/null` handle and emitted
   a ResourceWarning into the graded output stream.

### Authoritative commands — actual output

```
$ python3 -m unittest discover -s tests -t . -q
Ran 221 tests in 161.575s
OK

$ python3 -m benchmark selfcheck
74/74 checks passed

$ python3 -m benchmark verify-integrity
8/8 checks passed
```

Clean-install check: a fresh `git clone` into an empty directory, then
`./setup.sh --sample`, reproduces all of the above, executes all 24 queries with
non-empty results, renders the dashboard and writes a CSV export.

### Control runs over the full suite (harness validation, not agent results)

| Adapter | run_uid | Tasks | Passed | Pass rate |
| --- | --- | --- | --- | --- |
| `noop` | `5f3aeecea000462b` | 18 | 0 | 0.0% |
| `oracle` | `c4f0441acd1a4811` | 18 | 18 | 100.0% |

The local results database was regenerated after the parser fix: the change
altered a task fixture and the per-test counts, so the earlier rows described a
different apparatus. It held only controls and synthetic samples — no
measurement has ever been deleted, and none exists to delete.

Both bounds hold across all eighteen tasks: nothing passes without work, and
everything passes with the reference solution.

### Still true, and stated plainly

**No agent has been measured.** The leaderboard contains two controls and two
synthetic sample agents, and every surface that shows them says so. Unblocking
M7 needs `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` in the environment
running the harness.

### Next step

With a credential exported:

```bash
python3 -m benchmark run --adapter claude-code --agent claude-code \
    --model claude-opus-5 --task py-001-interval-merge
```

Confirm the attempt actually changes the workspace and that `verify-integrity`
stays clean, then run the full suite at `--attempts 5` for a baseline (M7).

---

## Implementation plan v3 — surviving hostile review

Session 4 addresses the objections a senior infrastructure reviewer would raise
before looking at any number.

| # | Milestone | Definition of done | Status |
| --- | --- | --- | --- |
| H1 | Real isolation | The agent turn runs inside a backend-enforced boundary; no silent fallback to a working directory. | **done** |
| H2 | Adversarial proof | A hostile adapter attacks the boundary from inside; every probe denied, asserted by the suite. | **done** |
| H3 | Run provenance | Isolation backend/version/active, publishable, network policy, model requested vs resolved, agent flags, fixture hash, timestamps. | **done** |
| H4 | Secret hygiene | Redaction at the capture choke point; audit of stored evidence; tracked-file scan. | **done** |
| H5 | Codex adapter | Built from the installed CLI's real flags, with parity tests against Claude Code. | **done** (no end-to-end run) |
| H6 | Frozen comparison protocol | Pre-registered, hashed manifest; publication gate. | **done** (not yet run) |
| H7 | Hostile methodology review | Every leakage, contamination and bias vector reviewed; real problems fixed, the rest disclosed. | **done** |
| H8 | Documentation consistency | Volatile counts removed; docs asserted against the repository by a test. | **done** |
| H9 | Review package | README trust/limits sections, interviewer brief, isolation and threat-model documents. | **done** |

---

## 2026-09-09 — Session 4: making the methodology survive hostile review

The objection this session answers: **a temporary working directory is not an
isolation boundary, so "the agent could not see the hidden tests" was a claim,
not a fact.** It is now a fact, and the rest of the session removed the other
objections a reviewer would raise before looking at any number.

### Isolation (H1, H2)

`benchmark/isolation/` defines a backend contract with three implementations.
**Seatbelt** (macOS, kernel-enforced, deny-by-default) is active and used for
every measurement in this repository. **Docker** is implemented but reports
itself unavailable without a daemon, which was the case here. **`none`** exists
only so that "we could not isolate" is a recorded fact; it is never selected
automatically and marks runs NON-PUBLISHABLE.

`Sandbox.exec` raises when no boundary is attached, so there is no code path by
which an agent turn runs on the bare host. Each attempt gets a private root
containing only its own workspace, scratch and home.

The evidence is an adversarial adapter (`benchmark/adapters/canary.py`) that
attacks its own boundary with nineteen probes. All nineteen are denied:

```
denied  traversal_parent, traversal_grandparent, traversal_root
denied  host_home_listing, host_home_file
denied  hidden_tests_dir, hidden_tests_file, stat_acceptance
denied  solution_dir, solution_file
denied  benchmark_source, benchmark_repo_listing, task_definition
denied  results_db
denied  sibling_attempts, other_attempt      (against a real sibling directory)
denied  glob_for_acceptance
denied  mutate_host_file                     (tracked file byte-identical after)
denied  network_egress
reached: []
```

### Three real defects found by attacking the project

1. **A complete grading bypass.** `python -m unittest` prepends the working
   directory to `sys.path`. An agent that writes `unittest.py` into its
   workspace has the runner import *that* file, which prints a convincing
   `Ran 12 ... OK` summary and exits zero -- touching no protected path, so
   tamper detection was blind. Demonstrated, then closed twice: evaluation runs
   with `PYTHONSAFEPATH=1`, and any added file shadowing a standard-library name
   is recorded as tampering.
2. **A denial of service in the measurement path,** introduced by this
   session's own redaction work. Unbounded regex quantifiers made redacting a
   10 KB log take 8.93s and a full-size capture hang for minutes. Since captured
   output is attacker-influenced, an agent could stall the harness grading it.
   Every quantifier is now bounded: the same 10 KB takes 0.038s.
3. **A scope that widened itself:** reopening the results database re-seeded the
   default analysis scope, which could have folded synthetic sample rows back
   into a real measurement.

A fourth, smaller finding: the test suite was not safe to run concurrently --
several runs shared one sandbox root, which is what made it appear to hang. The
canary's sibling directory is now named per process.

### Provenance (H3)

Protocol version 3. Runs now record the isolation backend, its version, whether
a boundary was actually enforced, whether the result is publishable, the network
policy, the agent flags, the agent timeout, the requested model **and** the
resolved model as separate columns, and the frozen experiment hash. Attempts
record the fixture hash they were handed, the boundary they ran under and
start/finish timestamps. A model name is never inferred: unreported stays NULL.
A database written under a different protocol is refused with a clear message
rather than silently reused.

### Secret hygiene (H4)

Redaction happens once, where subprocess output enters the harness, so the
database, exports, dashboard and this log all inherit it. `verify-integrity`
re-checks stored evidence for credential-shaped values, and a test scans every
tracked file. `bypassPermissions` and Codex's
`--dangerously-bypass-approvals-and-sandbox` are now defensible: they are
reachable only inside a boundary.

### Codex adapter and parity (H5)

Built from the installed CLI's actual `--help` output (`codex-cli 0.153.4`), not
from guesses. One shared prompt builder means every agent receives byte-identical
instructions; parity tests assert that, plus identical fixtures and equal
timeouts. A live test confirms the installed CLI accepts every flag, with a
companion test proving that check is not vacuous.

**No end-to-end Codex run has been performed**, and none is claimed. The CLI
authenticates through a ChatGPT session in `CODEX_HOME`, inside the host home
directory, which the boundary denies by design.

### Frozen comparison protocol (H6)

`docs/comparison-protocol.md` fixes, in advance: identical task versions and
fixture hashes, equal timeouts, attempts per task, retry policy, treatment of
infrastructure errors, rate limits and timeouts, model identity rules,
interleaved and seed-permuted ordering, and the analysis plan. Thresholds that
could otherwise be relaxed after seeing a result are numbers in the document: a
comparison is void above 5% rate-limited attempts or 10% timeouts.

`experiments/claude-vs-codex-v1.json` is pre-registered and frozen; its hash is
`2da56d6fb6ed9966...`, it pins every task fingerprint, and it plans 180 attempts.
`benchmark experiment verify` implements the publication gate and currently
reports, correctly, that the experiment has not been run.

### Acceptance gate -- actual output

```
$ python3 -m unittest discover -s tests -t . -q
Ran 386 tests in 59.377s
OK

$ python3 -m benchmark selfcheck --deterministic
92/92 checks passed

$ python3 -m benchmark verify-integrity
10/10 checks passed

$ python3 -m unittest tests.test_isolation -q
OK          (41 isolation tests; every canary probe denied)

$ every SQL analysis
25 analyses executed, 0 failed

$ credential scan over tracked files
269 tracked files scanned; credential-shaped content in: none
```

Control runs over the full suite: `noop` 0/18, `oracle` 18/18, both
recorded with `isolation_active = 1`.

### Still true

**No agent has been measured.** Both agent adapters refuse to run without a
credential in the environment, because the boundary denies the home directories
where their CLIs keep their logins. That refusal is the correct behaviour: a
recorded "could not run" is worth more than a fabricated zero.

**The tasks and the harness still share an author.** No mechanism here fixes
that, and it is now stated in the README, the comparison protocol, the threat
model and the interviewer brief.

### Next step

Export `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`, then run one task per agent to
confirm each attempt actually changes the workspace and that `verify-integrity`
stays clean. Only then run the frozen experiment:

```bash
python3 -m benchmark run --adapter claude-code --attempts 5 \
    --experiment experiments/claude-vs-codex-v1.json
python3 -m benchmark run --adapter codex --attempts 5 \
    --experiment experiments/claude-vs-codex-v1.json
python3 -m benchmark experiment verify experiments/claude-vs-codex-v1.json
```

### Verification record

Session 4's work is commit `05fb439efe3c64d0ac8afe028448e9a7f8f582b0`
("Make the isolation claim structural, and the methodology frozen"), pushed to
`origin/main`. Every command below was executed against that commit; the output
is quoted verbatim, not summarised from memory.

| Gate | Command | Result |
| --- | --- | --- |
| Unit + integration | `python3 -m unittest discover -s tests -t . -q` | `Ran 386 tests in 59.377s` / `OK` |
| Task self-check | `python3 -m benchmark selfcheck --deterministic` | `92/92 checks passed` |
| Recorded-results audit | `python3 -m benchmark verify-integrity` | `10/10 checks passed` |
| Adversarial isolation | `python3 -m unittest tests.test_isolation -q` | `Ran 41 tests` / `OK`; canary reached `[]` |
| SQL analyses | all files in `sql/queries/` | `25 analyses executed, 0 failed` |
| Credential scan | every tracked file | `269 tracked files scanned; credential-shaped content in: none` |
| Controls | `noop` / `oracle` over all 18 tasks | `0.0%` / `100.0%`, both `isolation_active = 1` |
| Publication gate | `benchmark experiment verify` | `0/1 -- the experiment has not been run` (correct) |

Clean-clone verification: a fresh `git clone` of that commit into an empty
directory, then `./setup.sh --sample`, reproduced `Ran 386 tests ... OK`,
`92/92`, `10/10` and `41 isolation tests OK`; executed all 25 analyses with
non-empty results; rendered the dashboard with its synthetic-data banner; and
wrote a CSV export. No generated artefact is tracked.

The publication gate failing is the honest state, not a defect: no agent has
been measured, so there is nothing under the frozen manifest to publish.
