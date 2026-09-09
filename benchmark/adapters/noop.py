"""The lower control: an agent that changes nothing.

Its role is to prove that tasks are actually failing before any work is done.
A task the noop adapter passes is a broken task, not an easy one.
"""

from __future__ import annotations

from .. import __version__
from ..sandbox import Sandbox
from ..tasks import Task
from .base import Adapter, AgentOutcome


class NoopAdapter(Adapter):
    name = "noop"
    is_control = True

    def version(self) -> str:
        return f"agentdev-noop/{__version__}"

    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        return AgentOutcome(
            completed=True,
            duration_ms=0,
            stdout="noop adapter made no changes",
            exit_code=0,
            metadata={"changed_files": []},
        )
