"""Per-attempt workspaces, and the boundary the agent runs inside.

Each attempt gets a *private root* containing nothing but its own workspace,
scratch and home directories. The workspace is a fresh copy of the task
fixture; the hidden acceptance tests and the reference solution stay behind in
the task directory and are applied by the host-side evaluator after the agent
has exited.

The directory layout alone is not the boundary -- a changed working directory
never is. Commands reach the workspace through an :class:`AgentSession` from
``benchmark.isolation``, which confines them. ``Sandbox.exec`` refuses to run
anything when no session has been attached, so there is no path by which an
agent turn quietly executes on the bare host.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from typing import Mapping, Sequence

from .config import sandbox_root
from .execution import CommandResult
from .hashing import hash_paths, hash_tree
from .isolation import AgentSession
from .tasks import Task

#: Name of the workspace directory inside an attempt's private root.
WORKSPACE_DIR = "workspace"


class SandboxNotIsolated(RuntimeError):
    """Raised when something tries to execute without a boundary attached."""


@dataclass
class Sandbox:
    """A live workspace for one attempt, plus the boundary around it."""

    task: Task
    path: Path
    keep: bool = False
    #: The private per-attempt root. Its only children are the workspace and
    #: the scratch/home directories, so a sibling attempt is not reachable
    #: even by path traversal.
    private_root: Path | None = None
    #: Attached by the runner for the duration of a turn.
    session: AgentSession | None = None

    @property
    def root(self) -> Path:
        return self.private_root or self.path

    def exec(
        self,
        command: Sequence[str],
        *,
        timeout_sec: int,
        stdin_text: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Run a command inside this attempt's isolation boundary.

        There is deliberately no fallback to an unconfined subprocess: an
        attempt with no session is a harness bug, not a reason to measure
        something weaker and call it the same thing.
        """
        if self.session is None:
            raise SandboxNotIsolated(
                "no isolation session is attached to this sandbox; refusing to "
                "execute an agent turn outside a boundary"
            )
        return self.session.run(
            command, timeout_sec=timeout_sec, stdin_text=stdin_text, extra_env=extra_env
        )

    def snapshot_protected(self) -> str:
        """Digest of the task's protected paths as they currently stand."""
        return hash_paths(self.path, self.task.protected_paths)

    def snapshot_tree(self) -> str:
        return hash_tree(self.path)

    def apply_overlay(self, overlay: Path) -> list[str]:
        """Copy ``overlay`` over the sandbox, returning the relative paths written."""
        if not overlay.is_dir():
            raise FileNotFoundError(f"overlay directory not found: {overlay}")
        written: list[str] = []
        for source in sorted(overlay.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(overlay)
            destination = self.path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            written.append(relative.as_posix())
        return written

    def cleanup(self) -> None:
        if self.keep:
            return
        target = self.root
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.cleanup()


def create_sandbox(task: Task, *, keep: bool = False, root: Path | None = None) -> Sandbox:
    """Materialise a private root holding a fresh copy of ``task``'s workspace."""
    base = root or sandbox_root()
    base.mkdir(parents=True, exist_ok=True)
    # Resolved because the isolation backends match canonical paths; on macOS
    # the temporary directory reaches the sandbox through a symlink.
    private_root = Path(os.path.realpath(tempfile.mkdtemp(prefix=f"{task.id}__", dir=str(base))))
    workspace = private_root / WORKSPACE_DIR
    shutil.copytree(
        task.workspace_path,
        workspace,
        symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    for scratch in ("tmp", "home"):
        (private_root / scratch).mkdir(parents=True, exist_ok=True)
    return Sandbox(task=task, path=workspace, keep=keep, private_root=private_root)
