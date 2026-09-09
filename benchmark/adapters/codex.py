"""Adapter for the Codex CLI running non-interactively inside the boundary.

**Flags are taken from the installed CLI's own ``--help``, not assumed.** The
set below was checked against ``codex exec --help`` for codex-cli 0.153.4, and
``tests/test_adapter_parity.py`` re-checks acceptance against whatever CLI is
installed rather than trusting this comment.

**Validation status.** Command construction and flag acceptance are tested. A
live end-to-end Codex run has *not* been performed by the harness author: the
installed CLI authenticates through a ChatGPT session stored in ``CODEX_HOME``,
which is deliberately unreachable inside the isolation boundary, so a real run
requires an API key in the environment. Until such a run exists, no claim is
made that this adapter produces valid measurements. See docs/adapters.md.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ..execution import run_command
from ..sandbox import Sandbox
from ..tasks import Task
from .base import Adapter, AgentOutcome
from .prompt import build_task_prompt

DEFAULT_BINARY = "codex"
DEFAULT_TIMEOUT_SEC = 900

#: Environment variables that can carry a Codex credential into the boundary.
#: A ChatGPT login stored in CODEX_HOME is not one of them: that directory sits
#: inside the host home, which the boundary denies by design.
CREDENTIAL_VARS = ("OPENAI_API_KEY", "CODEX_API_KEY")

#: Output signatures meaning the CLI never started work. Codex, like any CLI,
#: can exit zero after printing one of these; scored naively that becomes a
#: task the agent attempted and failed, which is a false capability measurement.
NOT_READY_SIGNATURES = (
    "not logged in",
    "please run `codex login`",
    "codex login",
    "invalid api key",
    "unauthorized",
    "quota",
    "rate limit",
)


class CodexAdapter(Adapter):
    name = "codex"
    #: Reaches the OpenAI API, so the boundary must permit egress.
    requires_network = True

    def __init__(
        self,
        binary: str | None = None,
        model: str | None = None,
        timeout_sec: int | None = None,
    ) -> None:
        self.binary = binary or os.environ.get("AGENTDEV_CODEX_BIN", DEFAULT_BINARY)
        self.model = model or os.environ.get("AGENTDEV_CODEX_MODEL", "")
        self.timeout_sec = timeout_sec or int(
            os.environ.get("AGENTDEV_AGENT_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC)
        )
        self._version_cache: str | None = None

    # -- identity -----------------------------------------------------------

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def version(self) -> str:
        """The CLI's own version string, never a guess."""
        if self._version_cache is not None:
            return self._version_cache
        if not self.available():
            self._version_cache = "unavailable"
            return self._version_cache
        result = run_command([self.binary, "--version"], cwd=os.getcwd(), timeout_sec=60)
        raw = (result.stdout or result.stderr).strip().splitlines()
        self._version_cache = f"codex/{raw[0].strip()}" if raw and result.ok else "codex/unknown"
        return self._version_cache

    # -- isolation contract -------------------------------------------------

    def toolchain_paths(self) -> tuple[Path, ...]:
        located = shutil.which(self.binary)
        return (Path(located).resolve().parent,) if located else ()

    def credentials(self) -> dict[str, str]:
        return {key: os.environ[key] for key in CREDENTIAL_VARS if os.environ.get(key)}

    # -- invocation ---------------------------------------------------------

    def build_command(self) -> list[str]:
        """The exact argv, so tests can assert flag acceptance without a run.

        ``--dangerously-bypass-approvals-and-sandbox`` is what the CLI's own
        help describes as "intended solely for running in environments that are
        externally sandboxed" -- which is precisely this one. It is reachable
        only through ``Sandbox.exec``, which refuses to run without a boundary,
        so it can never act as a host-level bypass.
        """
        command = [
            self.binary,
            "exec",
            # Determinism and parity: no user config, no persisted session, no
            # colour codes in the captured evidence, no git assumptions.
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if self.model:
            command += ["--model", self.model]
        return command

    def describe_flags(self) -> tuple[str, ...]:
        return tuple(self.build_command()[2:])

    def build_prompt(self, task: Task) -> str:
        """The shared prompt, identical to every other agent's."""
        return build_task_prompt(task)

    def preflight(self) -> str:
        """Why the agent cannot run, or an empty string if it can."""
        if not self.available():
            return f"codex binary not found on PATH: {self.binary!r}"
        if any(os.environ.get(var) for var in CREDENTIAL_VARS):
            return ""
        return (
            "no Codex credentials available to a subprocess: set one of "
            + ", ".join(CREDENTIAL_VARS)
            + " (a ChatGPT login stored in CODEX_HOME lives in the host home "
            "directory, which the isolation boundary denies by design)"
        )

    @staticmethod
    def _not_ready_reason(output: str) -> str:
        lowered = output.lower()
        for signature in NOT_READY_SIGNATURES:
            if signature in lowered:
                return f"agent never started work: CLI reported {signature!r}"
        return ""

    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        blocked = self.preflight()
        if blocked:
            return AgentOutcome(completed=False, duration_ms=0, error=blocked)

        result = sandbox.exec(
            self.build_command(),
            timeout_sec=self.timeout_sec,
            # The prompt arrives on stdin, so no shell quoting can alter it and
            # it never appears in a process listing.
            stdin_text=self.build_prompt(task),
        )
        error = "agent timed out" if result.timed_out else self._not_ready_reason(
            result.stdout + "\n" + result.stderr
        )
        telemetry = parse_jsonl_telemetry(result.stdout)
        return AgentOutcome(
            completed=not error,
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            error=error,
            metadata={"model": self.model or "default", "timeout_sec": self.timeout_sec, **telemetry},
        )


def parse_jsonl_telemetry(stdout: str) -> dict[str, object]:
    """Extract tool-call and model information from ``--json`` event output.

    Absent fields stay absent rather than defaulting to zero: an agent that
    reports nothing must not look cheaper than one that reports honestly.
    """
    tool_calls = 0
    resolved_model: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = str(event.get("type") or event.get("event") or "")
        if "tool" in kind or "command" in kind or "exec" in kind:
            tool_calls += 1
        for key in ("model", "model_slug"):
            if isinstance(event.get(key), str) and not resolved_model:
                resolved_model = event[key]
    telemetry: dict[str, object] = {}
    if tool_calls:
        telemetry["tool_calls"] = tool_calls
    if resolved_model:
        telemetry["model_resolved"] = resolved_model
    return telemetry
