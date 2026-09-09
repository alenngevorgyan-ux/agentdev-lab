"""The agent adapter interface.

An adapter is handed a sandbox and a task, and is expected to modify the
sandbox in place. It never decides whether it succeeded -- scoring is the
harness's job, computed from the task's own verification command.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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

    @abstractmethod
    def version(self) -> str:
        """Identify the exact agent build being measured."""

    @abstractmethod
    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        """Attempt ``task`` by editing ``sandbox.path`` in place."""

    def describe(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version()}
