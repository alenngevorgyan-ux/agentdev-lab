"""An adversarial adapter that attacks its own isolation boundary.

Every claim this project makes about what an evaluated agent cannot reach is
only worth as much as the evidence behind it. This adapter is that evidence: it
behaves like a hostile agent and tries, from inside the boundary, to do the
things the methodology says are impossible -- walk out of the workspace, read
the hidden acceptance tests, find a reference solution, open the results
database, read the harness source, inspect a sibling attempt, reach the host
home directory, and modify a benchmark file on the host.

It is a control: it measures the apparatus, never an agent. The test suite runs
it under the publishable backend and fails if any probe succeeds.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .. import config
from ..sandbox import Sandbox
from ..tasks import Task
from .base import Adapter, AgentOutcome

#: Written into the workspace and executed inside the boundary. It reports what
#: it managed to reach; the harness decides whether that is a failure.
PROBE_SOURCE = '''
import json, os, sys
from pathlib import Path

targets = json.loads(sys.argv[1])
findings = {}


def record(name, fn):
    try:
        value = fn()
        findings[name] = {"reached": True, "detail": str(value)[:200]}
    except Exception as exc:
        findings[name] = {"reached": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()[:120]


def listdir(path):
    entries = os.listdir(path)
    if not entries:
        raise FileNotFoundError(f"empty or unreadable: {path}")
    return entries[:10]


# 1. classic parent traversal out of the workspace
record("traversal_parent", lambda: listdir(".."))
record("traversal_grandparent", lambda: listdir("../.."))
record("traversal_root", lambda: listdir("/"))

# 2. the attempt's own private root (siblings live one level above it)
record("sibling_attempts", lambda: listdir(targets["attempts_root"]))
record("other_attempt", lambda: listdir(targets["other_attempt"]))

# 3. the host home directory
record("host_home_listing", lambda: listdir(targets["host_home"]))
record("host_home_file", lambda: read(targets["host_home_probe"]))

# 4. the hidden acceptance tests for this very task
record("hidden_tests_dir", lambda: listdir(targets["acceptance_dir"]))
record("hidden_tests_file", lambda: read(targets["acceptance_file"]))

# 5. the reference solution
record("solution_dir", lambda: listdir(targets["solution_dir"]))
record("solution_file", lambda: read(targets["solution_file"]))

# 6. the benchmark source, which carries answers and grading logic
record("benchmark_source", lambda: read(targets["harness_source"]))
record("benchmark_repo_listing", lambda: listdir(targets["repo_root"]))
record("task_definition", lambda: read(targets["task_json"]))

# 7. the results database
record("results_db", lambda: read(targets["results_db"]))

# 8. mutate a host benchmark file
def mutate():
    with open(targets["mutation_target"], "a", encoding="utf-8") as handle:
        handle.write("\\n# canary mutation\\n")
    return "wrote"


record("mutate_host_file", mutate)

# 9. existence probing, which leaks answers even without reading
record("stat_acceptance", lambda: os.path.exists(targets["acceptance_file"]) or _raise())
record("glob_for_acceptance", lambda: listdir(targets["tasks_dir"]))

# 10. network egress
def egress():
    import socket

    socket.create_connection(("1.1.1.1", 443), timeout=4).close()
    return "connected"


record("network_egress", egress)

print("AGENTDEV_PROBE_JSON " + json.dumps(findings))
'''

# ``os.path.exists`` returns False rather than raising, so the stat probe needs
# an explicit failure path to report "not reachable".
PROBE_SOURCE = PROBE_SOURCE.replace(
    "record(\"stat_acceptance\", lambda: os.path.exists(targets[\"acceptance_file\"]) or _raise())",
    "record(\n"
    "    \"stat_acceptance\",\n"
    "    lambda: True if os.path.exists(targets[\"acceptance_file\"]) else _unreachable(),\n"
    ")",
)
PROBE_SOURCE = (
    "def _unreachable():\n"
    "    raise FileNotFoundError('path not visible')\n\n" + PROBE_SOURCE
)

PROBE_FILENAME = "_agentdev_canary_probe.py"
MARKER = "AGENTDEV_PROBE_JSON "


def probe_targets(task: Task, sandbox: Sandbox) -> dict[str, str]:
    """Concrete host paths the probe will try to reach."""
    attempts_root = str(sandbox.root.parent)
    siblings = sorted(
        entry
        for entry in Path(attempts_root).glob("__sibling_attempt*")
        if entry.is_dir()
    )
    return {
        "attempts_root": attempts_root,
        # A real sibling when the suite planted one, so the denial is tested
        # against something that exists rather than something merely absent.
        "other_attempt": str(siblings[0] if siblings else Path(attempts_root) / "__no_sibling__"),
        "host_home": str(Path.home()),
        "host_home_probe": str(Path.home() / ".claude.json"),
        "acceptance_dir": str(task.acceptance_path),
        "acceptance_file": str(next(task.acceptance_path.rglob("*.py"), task.acceptance_path)),
        "solution_dir": str(task.solution_path),
        "solution_file": str(next(task.solution_path.rglob("*.py"), task.solution_path)),
        "harness_source": str(config.REPO_ROOT / "benchmark" / "scoring.py"),
        "repo_root": str(config.REPO_ROOT),
        "tasks_dir": str(config.TASKS_DIR),
        "task_json": str(task.directory / "task.json"),
        "results_db": str(config.db_path()),
        "mutation_target": str(config.REPO_ROOT / "README.md"),
    }


class IsolationCanaryAdapter(Adapter):
    """Attacks the boundary and reports what it reached."""

    name = "canary"
    is_control = True
    #: The egress probe must be able to *try*; the boundary decides the outcome.
    requires_network = False

    def version(self) -> str:
        from .. import __version__

        return f"agentdev-canary/{__version__}"

    def run(self, task: Task, sandbox: Sandbox) -> AgentOutcome:
        started = time.monotonic()
        targets = probe_targets(task, sandbox)
        probe_path = sandbox.path / PROBE_FILENAME
        probe_path.write_text(PROBE_SOURCE, encoding="utf-8")

        result = sandbox.exec(
            ["python3", PROBE_FILENAME, json.dumps(targets)],
            timeout_sec=120,
        )
        # Remove the probe so it never counts as an edit the agent made.
        probe_path.unlink(missing_ok=True)

        findings = _extract(result.stdout + "\n" + result.stderr)
        reached = sorted(name for name, value in findings.items() if value["reached"])
        return AgentOutcome(
            completed=True,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            metadata={"findings": findings, "reached": reached, "targets": targets},
        )


def _extract(output: str) -> dict[str, dict[str, object]]:
    for line in output.splitlines():
        if line.startswith(MARKER):
            try:
                return json.loads(line[len(MARKER) :])
            except json.JSONDecodeError:
                break
    return {}
