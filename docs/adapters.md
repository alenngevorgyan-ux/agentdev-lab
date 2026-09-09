# Adapter contract

An adapter drives one agent. It receives a task and a sandbox, edits the
sandbox in place, and reports whether it *ran* — never whether it *succeeded*.

```python
class Adapter(ABC):
    name: str

    def version(self) -> str: ...
    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome: ...
```

## `AgentOutcome`

| Field | Meaning |
| --- | --- |
| `completed` | The agent ran to completion. A *failed task* is not an error; a crashed or timed-out agent is. |
| `duration_ms` | Wall time of the agent's turn. |
| `stdout` / `stderr` | Captured output, stored as evidence. |
| `exit_code` | Process exit code, when there was a process. |
| `error` | Why the agent did not complete. |
| `metadata` | Free-form; recorded in logs, never in scoring. |

There is deliberately no `passed` field. Success is computed by the harness
from the task's verification command.

## Rules

1. **Confine yourself to the sandbox.** `sandbox.path` is the working
   directory. Nothing outside it may be read or written.
2. **Never touch `task.protected_paths`.** An adapter that does is recorded as
   tampering, exactly like an agent that does.
3. **Report honestly.** Return `completed=False` with an `error` when the agent
   crashed, timed out, or was misconfigured. Do not paper over a failure.
4. **Preflight before measuring.** If the agent cannot possibly run — binary
   missing, no credentials, quota exhausted — return `completed=False` *before*
   the attempt. A CLI can print "Not logged in" and still exit 0; scored
   naively that becomes a task the agent tried and failed, which is a
   fabricated capability measurement. `ClaudeCodeAdapter.preflight()` and its
   `NOT_READY_SIGNATURES` scan exist for exactly this.
5. **Report a real version.** `version()` must identify the actual build being
   measured — query the binary rather than hardcoding a string. Results are
   only comparable if this is accurate.
6. **Be bounded.** Every subprocess gets a timeout. An adapter that can hang
   forever can stall a run.
7. **Raising is acceptable.** The runner converts an adapter exception into
   `agent_error`; it never becomes a silent skip or a harness error.

## Built-in adapters

| Name | Role | Behaviour |
| --- | --- | --- |
| `noop` | control | Changes nothing. Establishes that tasks fail before work. |
| `oracle` | control | Applies `solution/`. Establishes that tasks are solvable. |
| `claude-code` | agent under test | Runs `claude --print` headlessly with the sandbox as cwd; the prompt arrives on stdin so no shell quoting can alter it. |

Controls measure the harness, not an agent, and are labelled as such in reports.

## Adding an adapter

1. Subclass `Adapter` in `benchmark/adapters/`.
2. Register it in `benchmark/adapters/__init__.py`.
3. Add tests. `tests/test_runner.py` shows the pattern, including adversarial
   adapters that delete or skip tests — those must be recorded as `tampered`.
4. Credentials come from the environment; never store one in the repository.
