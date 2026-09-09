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

1. **Run through `sandbox.exec`.** `sandbox.path` is the working directory and
   the only writable location. There is no unconfined fallback.
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
| `canary` | control | Attacks its own isolation boundary and reports what it reached. Evidence for docs/isolation.md. |
| `claude-code` | agent under test | `claude --print --permission-mode bypassPermissions`, prompt on stdin. |
| `codex` | agent under test | `codex exec --ignore-user-config --ephemeral --skip-git-repo-check --color never --json --dangerously-bypass-approvals-and-sandbox`, prompt on stdin. |

Controls measure the harness, not an agent, and are labelled as such in reports.

### Codex adapter: validation status

The flags above were read from `codex exec --help` for the installed CLI
(`codex-cli 0.153.4`), not assumed, and `tests/test_adapter_parity.py` re-checks
that the installed CLI accepts every one of them — plus a companion test proving
the check is not vacuous, by confirming an unknown flag *is* rejected.

**A live end-to-end Codex run has not been performed.** The installed CLI
authenticates through a ChatGPT session stored in `CODEX_HOME`, which lives in
the host home directory and is therefore unreachable inside the isolation
boundary by design. A real run needs `OPENAI_API_KEY` in the environment. Until
one exists, **no claim is made that this adapter produces valid measurements** —
only that its command construction is correct and its flags are accepted.

The same applies to `claude-code`: its command is validated, but no successful
end-to-end measurement has been recorded either.

### Permission-bypass flags

Both agent adapters disable their CLI's own approval prompts. Codex's help calls
its flag "intended solely for running in environments that are externally
sandboxed" -- which is exactly this one. That is defensible only because
`Sandbox.exec` refuses to run without a boundary, so the flags can never act as
a host-level permission bypass. See docs/isolation.md.

## Adding an adapter

1. Subclass `Adapter` in `benchmark/adapters/`.
2. Register it in `benchmark/adapters/__init__.py`.
3. Add tests. `tests/test_runner.py` shows the pattern, including adversarial
   adapters that delete or skip tests — those must be recorded as `tampered`.
4. Credentials come from the environment via `credentials()`, at minimum scope.
   They are never stored: captured output is redacted where it is captured, and
   `verify-integrity` re-checks stored evidence for credential-shaped values.
5. Declare `requires_network` honestly. It becomes the run's recorded network
   policy, and the boundary grants egress only when it is true.
6. Keep `toolchain_paths()` as small as the agent genuinely needs: every entry
   is a hole in the boundary that has to be justified.
