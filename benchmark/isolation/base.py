"""The isolation boundary an evaluated agent runs inside.

A changed working directory is not a security boundary. Everything the
benchmark must keep away from the agent -- hidden acceptance tests, reference
solutions, the results database, other attempts, the harness source, the host
home directory -- has to be *structurally* unreachable, not merely absent from
the prompt.

This module defines the contract. Each backend either enforces that boundary or
reports honestly that it cannot, in which case the run is marked
NON-PUBLISHABLE rather than silently degraded.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Mapping, Sequence

from ..execution import CommandResult

#: What an agent turn is permitted to reach on the network.
NETWORK_DENIED = "denied"
NETWORK_ALLOWED = "allowed"
#: No boundary exists, so the process has whatever the host user has.
NETWORK_UNRESTRICTED_HOST = "unrestricted-host"


@dataclass(frozen=True)
class IsolationReport:
    """Whether a backend can enforce a boundary here, and on what terms."""

    backend: str
    version: str
    #: True only when a kernel- or container-level boundary is actually applied.
    active: bool
    #: Whether measurements taken under this backend may be published as
    #: isolated results. False forces the NON-PUBLISHABLE marking.
    publishable: bool
    network_policy: str
    detail: str = ""
    unavailable_reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "version": self.version,
            "active": self.active,
            "publishable": self.publishable,
            "network_policy": self.network_policy,
            "detail": self.detail,
            "unavailable_reason": self.unavailable_reason,
        }


class IsolationUnavailable(RuntimeError):
    """Raised when a requested backend cannot enforce a boundary here."""


class AgentSession(ABC):
    """A live boundary around one attempt's workspace.

    Commands run through a session execute *inside* the boundary with the
    workspace as their working directory. There is deliberately no method that
    runs something outside it.
    """

    def __init__(self, workspace: Path, report: IsolationReport) -> None:
        self.workspace = workspace
        self.report = report

    @abstractmethod
    def run(
        self,
        command: Sequence[str],
        *,
        timeout_sec: int,
        stdin_text: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Execute ``command`` inside the boundary."""

    def close(self) -> None:
        """Release any resources the boundary holds."""

    def __enter__(self) -> "AgentSession":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


@dataclass
class SessionSpec:
    """What a session must provide for one turn."""

    workspace: Path
    #: Network access for this turn. Evaluation always runs with it denied.
    network: bool = False
    #: Credentials to expose inside the boundary. Minimum scope: only the
    #: variables the agent genuinely needs, and never for evaluation.
    secrets: Mapping[str, str] = field(default_factory=dict)
    #: Read-only host paths the toolchain needs (interpreter, agent binary).
    toolchain_paths: tuple[Path, ...] = ()


class IsolationBackend(ABC):
    """A mechanism that can confine a process to one workspace."""

    name: str = "base"

    @abstractmethod
    def probe(self) -> IsolationReport:
        """Report whether this backend can enforce a boundary on this machine."""

    @abstractmethod
    def session(self, spec: SessionSpec) -> AgentSession:
        """Open a boundary around ``spec.workspace``."""

    def available(self) -> bool:
        return self.probe().active
