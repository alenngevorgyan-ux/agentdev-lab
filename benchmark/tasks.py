"""Task specifications: loading, strict validation, and the task registry.

A task is a directory under ``benchmark/tasks/``::

    benchmark/tasks/<task-id>/
        task.json      # the specification (schema below)
        workspace/     # the tree the agent is given, verbatim
        solution/      # reference overlay applied by the oracle adapter

The spec is validated strictly: unknown keys are an error. A typo in
``protected_paths`` must fail loudly rather than silently disable tamper
detection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import MAX_TIMEOUT_SEC, TASKS_DIR
from .hashing import hash_json, hash_tree

VALID_CATEGORIES = frozenset({"bugfix", "feature", "refactor", "performance"})
VALID_DIFFICULTIES = frozenset({"easy", "medium", "hard"})

_REQUIRED_KEYS = frozenset(
    {"id", "title", "language", "category", "difficulty", "prompt", "protected_paths", "verify"}
)
_OPTIONAL_KEYS = frozenset({"workspace_dir", "solution_dir", "tags", "$comment"})
_VERIFY_REQUIRED = frozenset({"command", "timeout_sec"})


class TaskSpecError(ValueError):
    """Raised when a task specification is malformed."""


@dataclass(frozen=True)
class VerifySpec:
    """The command that decides whether an attempt passed."""

    command: tuple[str, ...]
    timeout_sec: int

    def as_dict(self) -> dict:
        return {"command": list(self.command), "timeout_sec": self.timeout_sec}


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    language: str
    category: str
    difficulty: str
    prompt: str
    protected_paths: tuple[str, ...]
    verify: VerifySpec
    directory: Path
    workspace_dir: str = "workspace"
    solution_dir: str = "solution"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def workspace_path(self) -> Path:
        return self.directory / self.workspace_dir

    @property
    def solution_path(self) -> Path:
        return self.directory / self.solution_dir

    @property
    def has_reference_solution(self) -> bool:
        return self.solution_path.is_dir()

    def spec_fingerprint(self) -> str:
        """Digest covering both the spec and the fixture tree it ships with.

        Stored with every result so a task edited after the fact can never be
        mistaken for the task that was actually measured.
        """
        return hash_json(
            {
                "spec": {
                    "id": self.id,
                    "title": self.title,
                    "language": self.language,
                    "category": self.category,
                    "difficulty": self.difficulty,
                    "prompt": self.prompt,
                    "protected_paths": list(self.protected_paths),
                    "verify": self.verify.as_dict(),
                    "tags": list(self.tags),
                },
                "workspace": hash_tree(self.workspace_path),
            }
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TaskSpecError(message)


def _parse_verify(raw: object, task_id: str) -> VerifySpec:
    _require(isinstance(raw, dict), f"{task_id}: 'verify' must be an object")
    assert isinstance(raw, dict)  # narrowed by the check above
    unknown = set(raw) - _VERIFY_REQUIRED
    _require(not unknown, f"{task_id}: unknown key(s) in 'verify': {sorted(unknown)}")
    missing = _VERIFY_REQUIRED - set(raw)
    _require(not missing, f"{task_id}: missing key(s) in 'verify': {sorted(missing)}")

    command = raw["command"]
    _require(
        isinstance(command, list) and command and all(isinstance(part, str) for part in command),
        f"{task_id}: 'verify.command' must be a non-empty list of strings",
    )
    timeout = raw["timeout_sec"]
    _require(
        isinstance(timeout, int) and not isinstance(timeout, bool) and 0 < timeout <= MAX_TIMEOUT_SEC,
        f"{task_id}: 'verify.timeout_sec' must be an int in 1..{MAX_TIMEOUT_SEC}",
    )
    return VerifySpec(command=tuple(command), timeout_sec=timeout)


def _parse_str_tuple(raw: object, task_id: str, key: str, *, allow_empty: bool) -> tuple[str, ...]:
    _require(isinstance(raw, list), f"{task_id}: '{key}' must be a list of strings")
    assert isinstance(raw, list)
    _require(
        all(isinstance(item, str) and item.strip() for item in raw),
        f"{task_id}: '{key}' must contain non-empty strings",
    )
    _require(allow_empty or bool(raw), f"{task_id}: '{key}' must not be empty")
    for item in raw:
        _require(
            not Path(item).is_absolute() and ".." not in Path(item).parts,
            f"{task_id}: '{key}' entry {item!r} must be a relative path inside the workspace",
        )
    return tuple(raw)


def load_task(directory: Path) -> Task:
    """Load and validate one task directory."""
    spec_path = directory / "task.json"
    _require(spec_path.is_file(), f"{directory}: missing task.json")
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaskSpecError(f"{spec_path}: invalid JSON: {exc}") from exc
    _require(isinstance(raw, dict), f"{spec_path}: top level must be an object")

    task_id = raw.get("id")
    _require(isinstance(task_id, str) and task_id.strip(), f"{spec_path}: 'id' must be a string")
    assert isinstance(task_id, str)
    _require(
        task_id == directory.name,
        f"{spec_path}: 'id' ({task_id!r}) must match the directory name ({directory.name!r})",
    )

    unknown = set(raw) - _REQUIRED_KEYS - _OPTIONAL_KEYS
    _require(not unknown, f"{task_id}: unknown key(s): {sorted(unknown)}")
    missing = _REQUIRED_KEYS - set(raw)
    _require(not missing, f"{task_id}: missing key(s): {sorted(missing)}")

    for key in ("title", "language", "prompt"):
        _require(
            isinstance(raw[key], str) and raw[key].strip(), f"{task_id}: '{key}' must be a non-empty string"
        )
    _require(
        raw["category"] in VALID_CATEGORIES,
        f"{task_id}: 'category' must be one of {sorted(VALID_CATEGORIES)}",
    )
    _require(
        raw["difficulty"] in VALID_DIFFICULTIES,
        f"{task_id}: 'difficulty' must be one of {sorted(VALID_DIFFICULTIES)}",
    )

    workspace_dir = raw.get("workspace_dir", "workspace")
    solution_dir = raw.get("solution_dir", "solution")
    _require(isinstance(workspace_dir, str), f"{task_id}: 'workspace_dir' must be a string")
    _require(isinstance(solution_dir, str), f"{task_id}: 'solution_dir' must be a string")

    task = Task(
        id=task_id,
        title=raw["title"],
        language=raw["language"],
        category=raw["category"],
        difficulty=raw["difficulty"],
        prompt=raw["prompt"],
        protected_paths=_parse_str_tuple(raw["protected_paths"], task_id, "protected_paths", allow_empty=False),
        verify=_parse_verify(raw["verify"], task_id),
        directory=directory,
        workspace_dir=workspace_dir,
        solution_dir=solution_dir,
        tags=_parse_str_tuple(raw.get("tags", []), task_id, "tags", allow_empty=True),
    )

    _require(task.workspace_path.is_dir(), f"{task_id}: missing workspace directory {workspace_dir!r}")
    for rel in task.protected_paths:
        _require(
            (task.workspace_path / rel).exists(),
            f"{task_id}: protected path {rel!r} does not exist in the workspace",
        )
    return task


def load_tasks(tasks_dir: Path | None = None) -> list[Task]:
    """Load every task under ``tasks_dir``, sorted by id."""
    root = tasks_dir or TASKS_DIR
    if not root.is_dir():
        return []
    tasks = [
        load_task(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and not child.name.startswith((".", "_"))
    ]
    seen: set[str] = set()
    for task in tasks:
        _require(task.id not in seen, f"duplicate task id: {task.id}")
        seen.add(task.id)
    return tasks


def load_registry(tasks_dir: Path | None = None) -> dict[str, Task]:
    return {task.id: task for task in load_tasks(tasks_dir)}


def select_tasks(task_ids: tuple[str, ...], tasks_dir: Path | None = None) -> list[Task]:
    """Resolve requested ids (empty selection means every task)."""
    registry = load_registry(tasks_dir)
    if not task_ids:
        return list(registry.values())
    unknown = [tid for tid in task_ids if tid not in registry]
    if unknown:
        raise TaskSpecError(f"unknown task id(s): {sorted(unknown)}")
    return [registry[tid] for tid in task_ids]
