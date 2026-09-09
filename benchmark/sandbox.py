"""Isolated per-attempt workspaces.

Each attempt gets a fresh copy of the task fixture. The agent may write
anywhere inside it; nothing it does can reach the task definition, another
attempt, or the results database.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from .config import sandbox_root
from .hashing import hash_paths, hash_tree
from .tasks import Task


@dataclass
class Sandbox:
    """A live sandbox directory for one attempt."""

    task: Task
    path: Path
    keep: bool = False

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
        if not self.keep and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)

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
    """Materialise a fresh copy of ``task``'s workspace."""
    base = root or sandbox_root()
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=f"{task.id}__", dir=str(base)))
    # copytree needs the destination absent; mkdtemp already created it.
    shutil.rmtree(path)
    shutil.copytree(
        task.workspace_path,
        path,
        symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    return Sandbox(task=task, path=path, keep=keep)
