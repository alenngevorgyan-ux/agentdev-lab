"""Diff statistics between the pristine fixture and a post-attempt workspace.

Files changed and lines added/deleted are the cheapest honest proxies for how
much of the repository an agent disturbed. They separate an agent that made a
two-line fix from one that rewrote the module, which a pass/fail cannot.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from .hashing import hash_file, iter_files

#: Files larger than this are counted as changed but not line-diffed.
MAX_DIFF_BYTES = 1024 * 1024


@dataclass(frozen=True)
class DiffStats:
    files_changed: int = 0
    files_added: int = 0
    files_deleted: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    changed_paths: tuple[str, ...] = field(default_factory=tuple)

    @property
    def lines_changed(self) -> int:
        return self.lines_added + self.lines_deleted

    @property
    def is_empty(self) -> bool:
        return self.files_changed == 0

    def touched(self, relative_paths: tuple[str, ...]) -> int:
        """How many of ``relative_paths`` this diff actually touched."""
        changed = set(self.changed_paths)
        return sum(1 for path in relative_paths if path in changed)


def _read_lines(path: Path) -> list[str] | None:
    if path.stat().st_size > MAX_DIFF_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def _line_delta(before: Path | None, after: Path | None) -> tuple[int, int]:
    old = _read_lines(before) if before is not None else []
    new = _read_lines(after) if after is not None else []
    if old is None or new is None:
        # Binary or oversized: the change is real but not line-countable.
        return 0, 0
    added = deleted = 0
    for line in difflib.unified_diff(old, new, n=0, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            deleted += 1
    return added, deleted


def compute_diff(before_root: Path, after_root: Path) -> DiffStats:
    """Compare two trees and summarise what changed."""
    before = {path.relative_to(before_root).as_posix(): path for path in iter_files(before_root)}
    after = {path.relative_to(after_root).as_posix(): path for path in iter_files(after_root)}

    changed: list[str] = []
    added_files = deleted_files = 0
    lines_added = lines_deleted = 0

    for relative in sorted(set(before) | set(after)):
        old_path, new_path = before.get(relative), after.get(relative)
        if old_path is not None and new_path is not None:
            if hash_file(old_path) == hash_file(new_path):
                continue
        elif new_path is not None:
            added_files += 1
        else:
            deleted_files += 1

        changed.append(relative)
        delta_added, delta_deleted = _line_delta(old_path, new_path)
        lines_added += delta_added
        lines_deleted += delta_deleted

    return DiffStats(
        files_changed=len(changed),
        files_added=added_files,
        files_deleted=deleted_files,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        changed_paths=tuple(changed),
    )
