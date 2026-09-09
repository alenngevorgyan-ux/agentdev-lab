"""Experiment manifests: the frozen configuration of a comparison.

A comparison is only credible if its rules were fixed before the results were
seen. A manifest states those rules -- task set, attempts, timeout, isolation,
ordering seed, analysis plan -- and is hashed. Every attempt records the hash it
ran under, so an analysis can prove that the configuration did not change
mid-experiment, and a manifest edited after the fact produces a different hash
rather than a quiet revision.

See docs/comparison-protocol.md for what the fields mean and why each exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import REPO_ROOT
from .hashing import hash_json
from .tasks import Task, load_registry

EXPERIMENTS_DIR = REPO_ROOT / "experiments"

REQUIRED_KEYS = frozenset(
    {
        "name",
        "description",
        "agents",
        "task_ids",
        "attempts_per_task",
        "agent_timeout_sec",
        "isolation",
        "network_policy",
        "ordering_seed",
        "analysis_plan",
    }
)
OPTIONAL_KEYS = frozenset({"task_fingerprints", "notes", "$comment", "created_at"})


class ManifestError(ValueError):
    """Raised when a manifest is malformed or has drifted from the task suite."""


@dataclass(frozen=True)
class Experiment:
    """A frozen comparison configuration."""

    name: str
    description: str
    agents: tuple[dict[str, str], ...]
    task_ids: tuple[str, ...]
    attempts_per_task: int
    agent_timeout_sec: int
    isolation: str
    network_policy: str
    ordering_seed: int
    analysis_plan: tuple[str, ...]
    task_fingerprints: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    path: Path | None = None

    def payload(self) -> dict[str, Any]:
        """The canonical content that the hash covers."""
        return {
            "name": self.name,
            "description": self.description,
            "agents": [dict(sorted(agent.items())) for agent in self.agents],
            "task_ids": list(self.task_ids),
            "attempts_per_task": self.attempts_per_task,
            "agent_timeout_sec": self.agent_timeout_sec,
            "isolation": self.isolation,
            "network_policy": self.network_policy,
            "ordering_seed": self.ordering_seed,
            "analysis_plan": list(self.analysis_plan),
            "task_fingerprints": dict(sorted(self.task_fingerprints.items())),
        }

    def manifest_hash(self) -> str:
        """Digest of the frozen configuration. Any edit changes it."""
        return hash_json(self.payload())

    def attempt_order(self) -> list[tuple[str, str, int]]:
        """The (task, agent, attempt) sequence, interleaved and permuted.

        Running one agent to completion before the other confounds the result
        with whatever drifted in between. The permutation is driven by the
        manifest's seed, so the ordering is fixed before the run rather than
        chosen after seeing an outcome.
        """
        import random

        rng = random.Random(self.ordering_seed)
        order: list[tuple[str, str, int]] = []
        names = [agent["adapter"] for agent in self.agents]
        for task_id in self.task_ids:
            for index in range(1, self.attempts_per_task + 1):
                shuffled = list(names)
                rng.shuffle(shuffled)
                order.extend((task_id, name, index) for name in shuffled)
        return order


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def load_experiment(path: Path) -> Experiment:
    """Load and strictly validate a manifest."""
    _require(path.is_file(), f"no such manifest: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path}: invalid JSON: {exc}") from exc
    _require(isinstance(raw, dict), f"{path}: top level must be an object")

    unknown = set(raw) - REQUIRED_KEYS - OPTIONAL_KEYS
    _require(not unknown, f"{path}: unknown key(s): {sorted(unknown)}")
    missing = REQUIRED_KEYS - set(raw)
    _require(not missing, f"{path}: missing key(s): {sorted(missing)}")

    agents = raw["agents"]
    _require(
        isinstance(agents, list) and len(agents) >= 2,
        f"{path}: 'agents' must list at least two agents to compare",
    )
    for agent in agents:
        _require(isinstance(agent, dict), f"{path}: each agent must be an object")
        _require("adapter" in agent, f"{path}: each agent needs an 'adapter'")
        _require("model" in agent, f"{path}: each agent needs a 'model' (use 'unspecified')")

    _require(
        isinstance(raw["attempts_per_task"], int) and raw["attempts_per_task"] >= 1,
        f"{path}: 'attempts_per_task' must be a positive integer",
    )
    _require(
        isinstance(raw["agent_timeout_sec"], int) and raw["agent_timeout_sec"] > 0,
        f"{path}: 'agent_timeout_sec' must be a positive integer",
    )
    _require(bool(raw["task_ids"]), f"{path}: 'task_ids' must not be empty")
    _require(
        raw["isolation"] != "none",
        f"{path}: a comparison may not be run without an enforced isolation boundary",
    )

    return Experiment(
        name=raw["name"],
        description=raw["description"],
        agents=tuple(raw["agents"]),
        task_ids=tuple(raw["task_ids"]),
        attempts_per_task=raw["attempts_per_task"],
        agent_timeout_sec=raw["agent_timeout_sec"],
        isolation=raw["isolation"],
        network_policy=raw["network_policy"],
        ordering_seed=raw["ordering_seed"],
        analysis_plan=tuple(raw["analysis_plan"]),
        task_fingerprints=dict(raw.get("task_fingerprints", {})),
        notes=raw.get("notes", ""),
        path=path,
    )


def freeze(experiment: Experiment, registry: dict[str, Task] | None = None) -> Experiment:
    """Pin the current task fingerprints into the manifest."""
    tasks = registry or load_registry()
    missing = [task_id for task_id in experiment.task_ids if task_id not in tasks]
    _require(not missing, f"unknown task id(s) in manifest: {missing}")
    fingerprints = {task_id: tasks[task_id].spec_fingerprint() for task_id in experiment.task_ids}
    return Experiment(
        **{
            **{
                key: getattr(experiment, key)
                for key in (
                    "name", "description", "agents", "task_ids", "attempts_per_task",
                    "agent_timeout_sec", "isolation", "network_policy", "ordering_seed",
                    "analysis_plan", "notes", "path",
                )
            },
            "task_fingerprints": fingerprints,
        }
    )


def check_drift(experiment: Experiment, registry: dict[str, Task] | None = None) -> list[str]:
    """Task ids whose fixture no longer matches what the manifest pinned."""
    if not experiment.task_fingerprints:
        return []
    tasks = registry or load_registry()
    drifted = []
    for task_id, pinned in experiment.task_fingerprints.items():
        task = tasks.get(task_id)
        if task is None or task.spec_fingerprint() != pinned:
            drifted.append(task_id)
    return drifted


def write_experiment(experiment: Experiment, path: Path) -> Path:
    """Write a manifest with its fingerprints pinned."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = experiment.payload()
    payload["notes"] = experiment.notes
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def list_experiments(directory: Path | None = None) -> list[Path]:
    root = directory or EXPERIMENTS_DIR
    return sorted(root.glob("*.json")) if root.is_dir() else []
