# Threat model and hostile review

This document reviews AgentDev Lab the way a reviewer trying to *reject* it
would: by asking, for every number it produces, "what would have to be true for
this to be wrong, and what stops that?"

Each entry names the attack or bias, what defends against it, and — where the
defence is partial or absent — says so instead of masking it.

---

## A. Leakage: could the agent have seen the answer?

### A1. Hidden acceptance tests

**Attack.** The agent reads the tests it will be graded on and writes code
shaped to them, or copies expected values.

**Defence (structural).** Hidden tests live in `benchmark/tasks/<id>/acceptance/`
and are copied into the workspace by the host *after* the agent process has
exited. During the agent turn they are not in the workspace, and the isolation
boundary denies the task directory entirely — an `open()` on it fails with
EPERM, and `os.path.exists()` returns False.

**Evidence.** `tests/test_isolation.py::AdversarialCanaryTest` runs a hostile
adapter that tries to read the acceptance directory, read a specific acceptance
file, and probe its existence. All three are denied.

### A2. Reference solutions

**Attack.** The agent finds `solution/` and copies it.

**Defence.** Same boundary; the solution never enters the workspace. Only the
`oracle` control applies it, host-side, and the oracle is marked `is_control`,
so its results can never be reported as an agent's.

**Evidence.** Canary probes `solution_dir` and `solution_file`: both denied.

### A3. Prompt leakage

**Attack.** The task prompt inadvertently contains the fix, or a path to it.

**Defence.** One shared prompt builder for all agents; a test asserts no
significant line of any reference solution, and no path to `solution/` or
`acceptance/`, appears in any task's prompt.

**Evidence.** `tests/test_adapter_parity.py::test_prompt_never_reveals_the_solution_or_hidden_tests`.

### A4. Harness source and task definitions

**Attack.** The agent reads `benchmark/scoring.py` to learn the grading rules,
or `task.json` to read the acceptance criteria verbatim.

**Defence.** The whole checkout is outside the boundary. Note that the
acceptance *criteria* are deliberately given to the agent in the prompt — those
are the specification, not the answer. The hidden *assertions* are not.

**Evidence.** Canary probes `benchmark_source`, `benchmark_repo_listing`,
`task_definition`: all denied.

---

## B. Grading integrity: could a pass have been unearned?

### B1. Editing or skipping the tests

**Defence.** Protected paths are digested before and after the agent turn; any
difference yields `tampered`, which cannot be a pass — enforced in the `Score`
dataclass, a `CHECK` constraint, and the reporting views. Verification is not
even run.

**Evidence.** `tests/test_runner.py` includes adapters that delete the test file
and that replace it with `@unittest.skip`. Both are recorded as `tampered`.

### B2. Hijacking the interpreter that runs the tests

**Attack.** The agent never touches a protected path. It writes `unittest.py`
into the workspace root. Because Python prepends the working directory to
`sys.path`, `python -m unittest` imports *that* file, which prints a convincing
`Ran 12 ... OK` and exits zero. The parser sees a full pass.

**This attack worked.** It was found during this review and is now closed twice
over:

1. **Primary:** evaluation runs with `PYTHONSAFEPATH=1`, so the working
   directory is not on the import path. The real `unittest` is loaded before
   the discovery root is inserted, so a planted module is never imported.
2. **Secondary:** any file or package added to the workspace root whose name
   matches a standard-library module is detected and recorded as `tampered`,
   because attempting the hijack is itself a finding.

**Evidence.** `tests/test_runner.py::InterpreterHijackTest` includes an adapter
that forges a passing suite and one that shadows a stdlib package; both are
recorded as tampering, and a third test asserts the forged module is not
imported even with the detector disabled.

### B3. Ambiguous grading

**Defence.** A pass requires the acceptance command to exit zero, with no
regression and no tampering. There is no partial credit toward a pass, no
model-judged grading, and no path by which an adapter reports its own success —
`AgentOutcome.completed` says only whether the process ran.

### B4. Parser under-counting

**Attack (and past bug).** A test whose outcome is split across lines is
dropped, so a suite of ten is recorded as three.

**Defence.** The parser stitches both split forms (docstring headers and
interleaved output). When a parse is still incomplete, the runner's own count
becomes the denominator, so a missed outcome can never inflate a pass fraction,
the attempt is annotated, and `verify-integrity` reports it.

---

## C. Contamination

### C1. Baseline contamination

**Attack.** "The agent broke this" is unfalsifiable if the test was already
failing.

**Defence.** Each task's baseline is measured on a pristine copy of the fixture,
with the hidden tests applied, before any agent runs. A regression is the set
difference between baseline-satisfied and now-satisfied tests.

**Limitation.** The baseline is cached per task fingerprint within a process.
That is sound only because tasks are required to be deterministic. A
non-deterministic task would produce a misleading baseline;
`benchmark selfcheck --deterministic` re-measures each baseline and compares.

### C2. Cross-attempt contamination

**Defence.** Each attempt gets a private root containing only its own
workspace, scratch and home directories. Sibling attempts are outside the
boundary by construction.

**Evidence.** Canary probes a real sibling attempt directory and its parent;
both denied with EPERM.

### C3. Synthetic data mixed with measurements

**Defence.** `run_kind` separates `measurement`, `control` and
`development_sample`. Analyses read the `analysis_scope` table rather than
hardcoding a filter, so the scope of every number is itself stored. The CLI and
dashboard print a banner when synthetic rows are in scope, and
`verify-integrity` always reports their presence.

### C4. Result deletion

**Defence.** SQLite triggers block `DELETE` on runs, attempts, per-test rows and
logs, and block `UPDATE` of any measured field. The only mutable columns are the
human review fields, and a relabel must declare `classification_source =
'human'`.

---

## D. Comparison bias

### D1. Cherry-picking

**Defence.** A frozen experiment manifest pins the task set, attempts, timeout,
isolation, ordering seed and *analysis plan*, and is hashed. Every attempt
records the hash. Editing the manifest changes the hash; attempts under
different hashes are never pooled. `benchmark experiment verify` checks the
publication gate.

### D2. Retry bias

**Defence.** `attempts_per_task` is fixed in advance and every attempt is
recorded. A task is never retried because it failed. Re-execution is permitted
only for `harness_error`, and the original row remains.

### D3. Timeout bias

**Defence.** All agents share one budget (asserted by a parity test). The
protocol voids a comparison whose timeout share exceeds 10% and requires
re-running *both* agents with a larger budget, never one.

### D4. Rate-limit bias

**Defence.** Rate-limited attempts are `agent_error`, excluded from capability
claims. Above a 5% share for any agent the comparison is void. The threshold is
fixed in the protocol so it cannot be relaxed after seeing who was throttled.

### D5. Model-version ambiguity

**Defence.** `model` (requested) and `model_resolved` (reported) are separate
columns. A model name is never inferred; unknown stays NULL.

**Limitation.** Provider-side model rollouts are invisible to the harness. The
manifest records the run's wall-clock window so a reader can correlate.

### D6. Task-author bias — **unfixed**

The tasks and the harness share an author, who used Claude Code while writing
them. No procedure here removes that. The controls catch unsolvable and
already-passing tasks, not favouritism.

What would fix it: tasks contributed by people who did not build the harness,
and a held-out set. Neither exists. **Any comparison this lab produces must
state this in the same breath as its headline number.**

---

## E. Statistical honesty

### E1. Misleading sample sizes

**Defence.** Every rate is reported with its denominator. Query 16 lists tasks
an agent both passes and fails, so non-determinism is visible rather than
averaged away.

### E2. Non-independent units

**Stated limitation.** Attempts within a task are not independent, and the 18
tasks are not a random sample of software engineering — they are eighteen
problems one person wrote. The protocol fixes the task as the unit of analysis
for any inferential claim and forbids a significance claim without a named test.

### E3. Classification overclaiming

**Defence.** The failure classifier is a documented heuristic over recorded
evidence. It returns `unclassified` rather than guessing, and every label
records whether a machine or a human assigned it.

---

## F. Isolation itself

### F1. What the boundary permits, and why

The Seatbelt policy is deny-by-default. Three deliberate holes:

| Hole | Why | Risk |
| --- | --- | --- |
| Read on `/usr`, `/System`, `/Library`, `/usr/local` | the interpreter and CLI must start | contains no benchmark data |
| `file-read-metadata` on `/` and `/usr` | the interpreter resolves its own path at startup | leaks *existence* of guessed system paths only; the home directory, `/tmp` and the checkout cannot even be stat-ed |
| Read on the agent binary's install prefix | the agent must execute | contains CLI builds, no benchmark data and no credentials — the CLI's own config file is *not* exposed, which is why an API key must be supplied explicitly |

### F2. Network

The agent turn needs egress to reach its API, so the boundary permits it and the
run records `network_policy = allowed`. **A network-enabled agent could in
principle exfiltrate or fetch, and no filesystem boundary prevents that.** What
it cannot do is read anything from this machine worth exfiltrating. Evaluation
always runs with egress denied.

### F3. Where isolation is unavailable

Docker is implemented but was unreachable on the authoring machine. On a host
with neither backend, `--isolation auto` refuses to run. `--isolation none` must
be asked for by name and marks every resulting run NON-PUBLISHABLE, both in the
database and in a banner.

### F4. What Seatbelt does not give us

It is a filesystem and network policy, not a virtual machine. It does not bound
CPU or memory, and Apple has deprecated `sandbox-exec` — the backend records the
OS build so a behaviour change is visible. Docker is the stronger backend and is
preferred by `auto` when a daemon is present.
