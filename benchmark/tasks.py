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

#: The capability dimensions the suite is designed to cover. Each names a
#: distinct thing an agent must be able to do on a real codebase.
VALID_CATEGORIES = frozenset(
    {
        "exploration",              # find the right place in an unfamiliar repo
        "bugfix_local",             # a defect contained in one file
        "bugfix_multifile",         # a defect whose fix spans modules
        "feature",                  # build something new to a written spec
        "refactor",                 # restructure without changing behaviour
        "test_generation",          # write the tests, not just the code
        "requirements_following",   # honour every clause of a precise spec
        "ambiguous_requirements",   # act sensibly when the spec underspecifies
        "regression_avoidance",     # change one behaviour, preserve the rest
        "dependency_api",           # use an unfamiliar in-repo API correctly
        "long_context_navigation",  # work across a repo too large to hold at once
        "architectural_constraints",# respect a stated design boundary
    }
)
VALID_DIFFICULTIES = frozenset({"easy", "medium", "hard"})

_REQUIRED_KEYS = frozenset(
    {
        "id",
        "title",
        "language",
        "category",
        "difficulty",
        "prompt",
        "acceptance_criteria",
        "protected_paths",
        "verify",
    }
)
_OPTIONAL_KEYS = frozenset(
    {
        "workspace_dir",
        "solution_dir",
        "acceptance_dir",
        "expected_files",
        "tags",
        "$comment",
    }
)
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
    acceptance_criteria: tuple[str, ...]
    directory: Path
    workspace_dir: str = "workspace"
    solution_dir: str = "solution"
    acceptance_dir: str = "acceptance"
    expected_files: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def workspace_path(self) -> Path:
        return self.directory / self.workspace_dir

    @property
    def solution_path(self) -> Path:
        return self.directory / self.solution_dir

    @property
    def acceptance_path(self) -> Path:
        return self.directory / self.acceptance_dir

    @property
    def has_reference_solution(self) -> bool:
        return self.solution_path.is_dir()

    @property
    def has_hidden_tests(self) -> bool:
        """Whether extra tests are overlaid only at evaluation time.

        Hidden tests are never present in the workspace the agent sees, so an
        agent cannot tune its work to the exact assertions it will be graded on.
        """
        return self.acceptance_path.is_dir()

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
                    "acceptance_criteria": list(self.acceptance_criteria),
                    "expected_files": list(self.expected_files),
                    "verify": self.verify.as_dict(),
                    "tags": list(self.tags),
                },
                "workspace": hash_tree(self.workspace_path),
                "hidden_tests": (
                    hash_tree(self.acceptance_path) if self.has_hidden_tests else ""
                ),
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
    acceptance_dir = raw.get("acceptance_dir", "acceptance")
    for key, value in (
        ("workspace_dir", workspace_dir),
        ("solution_dir", solution_dir),
        ("acceptance_dir", acceptance_dir),
    ):
        _require(isinstance(value, str), f"{task_id}: '{key}' must be a string")

    task = Task(
        id=task_id,
        title=raw["title"],
        language=raw["language"],
        category=raw["category"],
        difficulty=raw["difficulty"],
        prompt=raw["prompt"],
        protected_paths=_parse_str_tuple(raw["protected_paths"], task_id, "protected_paths", allow_empty=False),
        verify=_parse_verify(raw["verify"], task_id),
        acceptance_criteria=_parse_str_tuple(
            raw["acceptance_criteria"], task_id, "acceptance_criteria", allow_empty=False
        ),
        directory=directory,
        workspace_dir=workspace_dir,
        solution_dir=solution_dir,
        acceptance_dir=acceptance_dir,
        expected_files=_parse_str_tuple(
            raw.get("expected_files", []), task_id, "expected_files", allow_empty=True
        ),
        tags=_parse_str_tuple(raw.get("tags", []), task_id, "tags", allow_empty=True),
    )

    _require(task.workspace_path.is_dir(), f"{task_id}: missing workspace directory {workspace_dir!r}")
    for rel in task.protected_paths:
        _require(
            (task.workspace_path / rel).exists(),
            f"{task_id}: protected path {rel!r} does not exist in the workspace",
        )
    # A hidden test that lands on top of a visible one would silently replace
    # the assertions the agent was shown, which is a different experiment.
    if task.has_hidden_tests:
        for hidden in task.acceptance_path.rglob("*"):
            if hidden.is_file():
                relative = hidden.relative_to(task.acceptance_path)
                _require(
                    not (task.workspace_path / relative).exists(),
                    f"{task_id}: hidden test {relative.as_posix()!r} would overwrite a visible file",
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
