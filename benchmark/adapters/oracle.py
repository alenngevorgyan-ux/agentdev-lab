"""The upper control: applies the task's reference solution.

Its role is to prove that a task is solvable and that its verification command
recognises a correct solution. A task the oracle fails is a broken task.

The oracle is a harness self-test. Its results describe the harness, never an
agent, and are stored under the ``oracle`` adapter name so they can never be
confused with measurements of a real agent.
"""

from __future__ import annotations

import time

from .. import __version__
from ..sandbox import Sandbox
from ..tasks import Task
from .base import Adapter, AgentOutcome


class OracleAdapter(Adapter):
    name = "oracle"
    is_control = True

    def version(self) -> str:
        return f"agentdev-oracle/{__version__}"

    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        if not task.has_reference_solution:
            return AgentOutcome(
                completed=False,
                duration_ms=0,
                error=f"task {task.id} has no reference solution at {task.solution_dir!r}",
            )
        started = time.monotonic()
        written = sandbox.apply_overlay(task.solution_path)
        duration_ms = int((time.monotonic() - started) * 1000)
        return AgentOutcome(
            completed=True,
            duration_ms=duration_ms,
            stdout="applied reference solution: " + ", ".join(written),
            exit_code=0,
            metadata={"changed_files": written},
        )
