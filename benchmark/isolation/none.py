"""The absence of isolation, stated plainly.

This backend exists so that "we could not isolate" is a recorded, visible fact
rather than a silent degradation. Runs made under it are NON-PUBLISHABLE: the
agent process has whatever the host user has, so nothing about hidden tests,
reference solutions or the results database being unreachable can be claimed.

It must never be selected automatically. The operator has to ask for it.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..execution import CommandResult, build_env, run_command
from .base import (
    NETWORK_UNRESTRICTED_HOST,
    AgentSession,
    IsolationBackend,
    IsolationReport,
    SessionSpec,
)

WARNING = (
    "NO ISOLATION: the agent runs as the host user with full filesystem access. "
    "Hidden tests, reference solutions and the results database are absent from "
    "the workspace but are NOT structurally unreachable. Results are NON-PUBLISHABLE."
)


class UnisolatedSession(AgentSession):
    """Runs the command as an ordinary host subprocess."""

    def __init__(self, spec: SessionSpec, report: IsolationReport) -> None:
        super().__init__(spec.workspace, report)
        self._spec = spec

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_sec: int,
        stdin_text: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        env = build_env(dict(self._spec.secrets) | dict(extra_env or {}))
        return run_command(
            command,
            cwd=self.workspace,
            timeout_sec=timeout_sec,
            env=env,
            stdin_text=stdin_text,
        )


class NoIsolation(IsolationBackend):
    name = "none"

    def probe(self) -> IsolationReport:
        return IsolationReport(
            backend=self.name,
            version="n/a",
            active=False,
            publishable=False,
            network_policy=NETWORK_UNRESTRICTED_HOST,
            detail=WARNING,
        )

    def session(self, spec: SessionSpec) -> AgentSession:
        return UnisolatedSession(spec, self.probe())
