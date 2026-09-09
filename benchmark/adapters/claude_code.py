"""Adapter for the Claude Code CLI running headlessly inside a sandbox.

The CLI is invoked with ``--print`` so it runs to completion without a TTY, and
is given the sandbox as its working directory. Nothing outside the sandbox is
reachable, and the task prompt is passed on stdin so no shell quoting can alter
it.
"""

from __future__ import annotations

import os
import shutil

from ..execution import build_env, run_command
from ..sandbox import Sandbox
from ..tasks import Task
from .base import Adapter, AgentOutcome

DEFAULT_BINARY = "claude"
DEFAULT_TIMEOUT_SEC = 900

PROMPT_TEMPLATE = """\
You are working inside an isolated benchmark workspace. Your working directory
already contains the project.

Task: {title}

{prompt}

Rules:
- Modify only the source files needed to complete the task.
- Do not edit, delete, weaken, or skip any test file. The following paths are
  protected and any change to them invalidates the attempt: {protected}
- Do not add third-party dependencies; the standard library only.
- When you are done, stop. Do not ask questions.
"""


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"

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

    def build_prompt(self, task: Task) -> str:
        return PROMPT_TEMPLATE.format(
            title=task.title,
            prompt=task.prompt.strip(),
            protected=", ".join(task.protected_paths),
        )

    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        if not self.available():
            return AgentOutcome(
                completed=False,
                duration_ms=0,
                error=f"claude binary not found on PATH: {self.binary!r}",
            )

        command = [self.binary, "--print", "--permission-mode", "bypassPermissions"]
        if self.model:
            command += ["--model", self.model]

        env = build_env()
        # Anthropic credentials are the one secret the agent legitimately needs.
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            if key in os.environ:
                env[key] = os.environ[key]

        result = run_command(
            command,
            cwd=sandbox.path,
            timeout_sec=self.timeout_sec,
            env=env,
            stdin_text=self.build_prompt(task),
        )
        return AgentOutcome(
            completed=not result.timed_out,
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            error="agent timed out" if result.timed_out else "",
            metadata={"model": self.model or "default", "timeout_sec": self.timeout_sec},
        )
