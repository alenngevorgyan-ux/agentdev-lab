"""Content hashing used for fixture pinning and tamper detection.

Every hash in the lab is a SHA-256 over a canonical serialisation, so the same
tree always produces the same digest across machines and Python versions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

#: Directories never included in a tree digest -- they are build residue, not content.
IGNORED_DIR_NAMES = frozenset({"__pycache__", ".git", ".pytest_cache", ".mypy_cache"})
IGNORED_FILE_SUFFIXES = (".pyc", ".pyo")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_json(obj: Any) -> str:
    """Digest of a JSON-serialisable object with key order made canonical."""
    return hash_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every content-bearing file under ``root``, in deterministic order."""
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.name.endswith(IGNORED_FILE_SUFFIXES):
            continue
        yield path


def hash_tree(root: Path) -> str:
    """Digest of a whole directory tree: relative paths and contents both matter."""
    entries = [
        f"{path.relative_to(root).as_posix()}:{hash_file(path)}" for path in iter_files(root)
    ]
    return hash_text("\n".join(entries))


def hash_paths(root: Path, relative_paths: Iterable[str]) -> str:
    """Digest of a specific subset of ``root``.

    Missing paths are recorded explicitly rather than skipped -- deleting a
    protected test file must change the digest just as loudly as editing it.
    """
    entries: list[str] = []
    for rel in sorted(set(relative_paths)):
        target = root / rel
        if not target.exists():
            entries.append(f"{rel}:<missing>")
        elif target.is_dir():
            entries.append(f"{rel}/:{hash_tree(target)}")
        else:
            entries.append(f"{rel}:{hash_file(target)}")
    return hash_text("\n".join(entries))
