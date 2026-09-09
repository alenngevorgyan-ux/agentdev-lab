"""Live counts of what the repository actually contains.

Documentation that hardcodes "212 tests" goes stale the moment a test is added,
and a reviewer who spots one stale number reasonably doubts the rest. These
counts are computed from the repository, printed by ``benchmark stats``, and
asserted against the documentation by ``tests/test_docs.py``.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path

from . import HARNESS_PROTOCOL_VERSION, __version__
from .adapters import CONTROL_ADAPTERS, available_adapters
from .config import REPO_ROOT
from .queries import load_queries
from .tasks import load_tasks


@dataclass(frozen=True)
class Stats:
    harness_version: str
    protocol_version: int
    tasks: int
    categories: int
    tasks_with_hidden_tests: int
    sql_queries: int
    tests: int
    agent_adapters: tuple[str, ...]
    control_adapters: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "harness_version": self.harness_version,
            "protocol_version": self.protocol_version,
            "tasks": self.tasks,
            "categories": self.categories,
            "tasks_with_hidden_tests": self.tasks_with_hidden_tests,
            "sql_queries": self.sql_queries,
            "tests": self.tests,
            "agent_adapters": list(self.agent_adapters),
            "control_adapters": list(self.control_adapters),
        }


def count_tests(tests_dir: Path | None = None) -> int:
    """Number of test cases the authoritative suite would run."""
    root = tests_dir or REPO_ROOT / "tests"
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(root), top_level_dir=str(REPO_ROOT)
    )
    return suite.countTestCases()


def gather(tests_dir: Path | None = None) -> Stats:
    tasks = load_tasks()
    return Stats(
        harness_version=__version__,
        protocol_version=HARNESS_PROTOCOL_VERSION,
        tasks=len(tasks),
        categories=len({task.category for task in tasks}),
        tasks_with_hidden_tests=sum(1 for task in tasks if task.has_hidden_tests),
        sql_queries=len(load_queries()),
        tests=count_tests(tests_dir),
        agent_adapters=tuple(n for n in available_adapters() if n not in CONTROL_ADAPTERS),
        control_adapters=tuple(sorted(CONTROL_ADAPTERS)),
    )
