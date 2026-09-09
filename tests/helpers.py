"""Shared fixtures for the harness test suite."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from benchmark.tasks import Task, load_task

PASSING_TEST = """\
import unittest

from src.thing import answer


class T(unittest.TestCase):
    def test_answer(self):
        self.assertEqual(answer(), 42)
"""

BROKEN_SOURCE = "def answer():\n    return 0\n"
FIXED_SOURCE = "def answer():\n    return 42\n"

VERIFY_COMMAND = ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"]


def write_task(
    root: Path,
    task_id: str = "demo-task",
    *,
    source: str = BROKEN_SOURCE,
    solution: str | None = FIXED_SOURCE,
    protected_paths: list[str] | None = None,
    spec_overrides: dict | None = None,
) -> Path:
    """Create a minimal, self-contained task directory under ``root``."""
    directory = root / task_id
    (directory / "workspace" / "src").mkdir(parents=True)
    (directory / "workspace" / "tests").mkdir(parents=True)
    (directory / "workspace" / "src" / "__init__.py").write_text("")
    (directory / "workspace" / "src" / "thing.py").write_text(source)
    (directory / "workspace" / "tests" / "__init__.py").write_text("")
    (directory / "workspace" / "tests" / "test_thing.py").write_text(PASSING_TEST)

    if solution is not None:
        (directory / "solution" / "src").mkdir(parents=True)
        (directory / "solution" / "src" / "thing.py").write_text(solution)

    spec = {
        "id": task_id,
        "title": "Demo task",
        "language": "python",
        "category": "bugfix",
        "difficulty": "easy",
        "prompt": "Make answer() return 42.",
        "protected_paths": protected_paths if protected_paths is not None else ["tests"],
        "verify": {"command": VERIFY_COMMAND, "timeout_sec": 60},
    }
    spec.update(spec_overrides or {})
    (directory / "task.json").write_text(json.dumps(spec, indent=2))
    return directory


class TempDirTestCase(unittest.TestCase):
    """Base case providing a scratch directory scrubbed after every test."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="agentdev-test-"))
        self.addCleanup(shutil.rmtree, self._tmp, True)

    @property
    def tmp(self) -> Path:
        return self._tmp

    def make_task(self, **kwargs) -> Task:
        directory = write_task(self.tmp / "tasks", **kwargs)
        return load_task(directory)
