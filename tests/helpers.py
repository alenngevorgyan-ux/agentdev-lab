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

VERIFY_COMMAND = ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]

HIDDEN_TEST = """\
import unittest

from src.thing import answer


class Hidden(unittest.TestCase):
    def test_answer_is_an_int(self):
        self.assertIsInstance(answer(), int)
"""


def write_task(
    root: Path,
    task_id: str = "demo-task",
    *,
    source: str = BROKEN_SOURCE,
    solution: str | None = FIXED_SOURCE,
    protected_paths: list[str] | None = None,
    hidden_test: str | None = None,
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

    if hidden_test is not None:
        (directory / "acceptance" / "tests").mkdir(parents=True)
        (directory / "acceptance" / "tests" / "test_hidden.py").write_text(hidden_test)

    spec = {
        "id": task_id,
        "title": "Demo task",
        "language": "python",
        "category": "bugfix_local",
        "difficulty": "easy",
        "prompt": "Make answer() return 42.",
        "acceptance_criteria": ["answer() returns 42."],
        "expected_files": ["src/thing.py"],
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
        # The baseline cache is content-addressed, so a mutated fixture yields a
        # different key rather than a stale hit -- clearing it per test would
        # only make the suite slower. Tests that need a cold cache clear it
        # explicitly.

    @property
    def tmp(self) -> Path:
        return self._tmp

    def make_task(self, **kwargs) -> Task:
        directory = write_task(self.tmp / "tasks", **kwargs)
        return load_task(directory)
