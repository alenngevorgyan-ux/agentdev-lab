"""The agent adapter interface.

An adapter is handed a sandbox and a task, and is expected to modify the
sandbox in place. It never decides whether it succeeded -- scoring is the
harness's job, computed from the task's own verification command.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..sandbox import Sandbox
from ..tasks import Task


@dataclass
class AgentOutcome:
    """What an adapter reports back about its own attempt."""

    #: False when the agent itself failed to run (crash, timeout, bad config).
    #: A failing *task* is not an error -- that is simply a failed attempt.
    completed: bool
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Adapter(ABC):
    """Base class for every agent under test."""

    #: Stable identifier used on the command line and in stored results.
    name: str = "base"

    #: True for the harness's own controls (noop, oracle). Controls act on the
    #: workspace directly from the host: they are part of the apparatus, not
    #: agents under test, and the record never claims they were isolated.
    is_control: bool = False

    #: Whether the agent turn needs the network. Recorded as the run's network
    #: policy, and granted by the isolation boundary only when true.
    requires_network: bool = False

    def toolchain_paths(self) -> tuple[Path, ...]:
        """Host paths the boundary must expose read-only for the agent to start.

        Keep this as small as the agent genuinely needs: every entry is a hole
        in the boundary that has to be justified.
        """
        return ()

    def describe_flags(self) -> tuple[str, ...]:
        """The flags this adapter passes to the agent, for the record.

        Never include a secret: flags are stored and exported verbatim.
        """
        return ()

    def credentials(self) -> dict[str, str]:
        """Secrets to expose inside the boundary, at minimum scope.

        Values are read from the host environment at call time and are never
        stored, logged, or written into the results database.
        """
        return {}

    @abstractmethod
    def version(self) -> str:
        """Identify the exact agent build being measured."""

    @abstractmethod
    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        """Attempt ``task`` by editing ``sandbox.path`` in place."""

    def describe(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version()}
