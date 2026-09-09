"""Adapter for the Claude Code CLI running headlessly inside a sandbox.

The CLI is invoked with ``--print`` so it runs to completion without a TTY, and
is given the sandbox as its working directory. Nothing outside the sandbox is
reachable, and the task prompt is passed on stdin so no shell quoting can alter
it.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from ..execution import run_command
from ..sandbox import Sandbox
from ..tasks import Task
from .base import Adapter, AgentOutcome
from .prompt import build_task_prompt

DEFAULT_BINARY = "claude"
DEFAULT_TIMEOUT_SEC = 900

#: Environment variables that can carry credentials into the sandbox.
CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")

#: Output signatures meaning the CLI never started work. The CLI can exit 0
#: while printing one of these, which would otherwise be scored as the agent
#: attempting the task and failing -- a false capability measurement.
NOT_READY_SIGNATURES = (
    "not logged in",
    "please run /login",
    "invalid api key",
    "authentication_error",
    "credit balance is too low",
    "rate limit",
)



def _reported_model(stdout: str) -> dict[str, str]:
    """The model the CLI named for itself, if it named one.

    Absent rather than guessed: an unreported model stays NULL in the record.
    """
    match = re.search(r'"model"\s*:\s*"([^"]+)"', stdout)
    return {"model_resolved": match.group(1)} if match else {}


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"
    #: The agent reaches the Anthropic API, so the boundary must permit egress.
    #: This is recorded as the run's network policy rather than assumed.
    requires_network = True

    def __init__(
        self,
        binary: str | None = None,
        model: str | None = None,
        timeout_sec: int | None = None,
    ) -> None:
        self.binary = binary or os.environ.get("AGENTDEV_CLAUDE_BIN", DEFAULT_BINARY)
        self.model = model or os.environ.get("AGENTDEV_CLAUDE_MODEL", "")
        self.timeout_sec = timeout_sec or int(
            os.environ.get("AGENTDEV_AGENT_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC)
        )
        self._version_cache: str | None = None

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def preflight(self) -> str:
        """Return why the agent cannot run, or an empty string if it can.

        Checked before the attempt so an unauthenticated or missing CLI is
        recorded as an agent error rather than as a task the agent failed.
        """
        if not self.available():
            return f"claude binary not found on PATH: {self.binary!r}"
        if any(os.environ.get(var) for var in CREDENTIAL_VARS):
            return ""
        if (Path.home() / ".claude" / ".credentials.json").is_file():
            return ""
        return (
            "no Claude Code credentials available to a subprocess: set one of "
            + ", ".join(CREDENTIAL_VARS)
            + " (a host-authenticated parent session does not pass credentials to its children)"
        )

    @staticmethod
    def _not_ready_reason(output: str) -> str:
        lowered = output.lower()
        for signature in NOT_READY_SIGNATURES:
            if signature in lowered:
                return f"agent never started work: CLI reported {signature!r}"
        return ""

    def version(self) -> str:
        """Report the CLI's own version string, never a guess."""
        if self._version_cache is not None:
            return self._version_cache
        if not self.available():
            self._version_cache = "unavailable"
            return self._version_cache
        result = run_command([self.binary, "--version"], cwd=os.getcwd(), timeout_sec=60)
        raw = (result.stdout or result.stderr).strip().splitlines()
        self._version_cache = f"claude-code/{raw[0].strip()}" if raw and result.ok else "claude-code/unknown"
        return self._version_cache

    def describe_flags(self) -> tuple[str, ...]:
        flags = ["--print", "--permission-mode", "bypassPermissions"]
        if self.model:
            flags += ["--model", self.model]
        return tuple(flags)

    def toolchain_paths(self) -> tuple[Path, ...]:
        """The agent binary's install prefix, exposed read-only."""
        located = shutil.which(self.binary)
        if located is None:
            return ()
        real = Path(located).resolve()
        return (real.parent,)

    def credentials(self) -> dict[str, str]:
        """Only the Anthropic credential, and only if the host actually has one."""
        return {key: os.environ[key] for key in CREDENTIAL_VARS if os.environ.get(key)}

    def build_prompt(self, task: Task) -> str:
        """The shared prompt, so agents are compared on the same instructions."""
        return build_task_prompt(task)

    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        blocked = self.preflight()
        if blocked:
            return AgentOutcome(completed=False, duration_ms=0, error=blocked)

        # `bypassPermissions` skips the CLI's own approval prompts. That is
        # only defensible because the process is confined: inside the boundary
        # the agent can reach nothing but its own workspace, so the prompts
        # would be guarding a door that is already locked. The harness refuses
        # to run an agent turn without a boundary attached (Sandbox.exec), so
        # this flag can never act as a host-level permission bypass.
        command = [self.binary, "--print", "--permission-mode", "bypassPermissions"]
        if self.model:
            command += ["--model", self.model]

        result = sandbox.exec(
            command,
            timeout_sec=self.timeout_sec,
            stdin_text=self.build_prompt(task),
        )
        error = "agent timed out" if result.timed_out else self._not_ready_reason(
            result.stdout + "\n" + result.stderr
        )
        return AgentOutcome(
            completed=not error,
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            error=error,
            metadata={
                "model": self.model or "default",
                "timeout_sec": self.timeout_sec,
                **_reported_model(result.stdout),
            },
        )
