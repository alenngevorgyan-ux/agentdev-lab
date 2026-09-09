"""Container isolation via Docker.

The strongest boundary the lab supports where a daemon is available: the agent
runs in a container whose only view of the host is a bind mount of the attempt
workspace. The benchmark checkout, the results database, other attempts and the
host home directory are not merely unreadable -- they are absent from the mount
namespace entirely.

**Validation status on the machine that wrote this file:** the Docker CLI was
present but no daemon was reachable, so this backend has been exercised only
through its command construction, not against a live daemon. ``probe()``
reports it unavailable in that situation and the harness refuses to claim
isolation. See docs/isolation.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from ..execution import CommandResult, build_env, run_command
from .base import (
    NETWORK_ALLOWED,
    NETWORK_DENIED,
    AgentSession,
    IsolationBackend,
    IsolationReport,
    IsolationUnavailable,
    SessionSpec,
)

#: Mount point for the workspace inside the container.
CONTAINER_WORKSPACE = "/workspace"
#: A small, pinned image. Pinned by digest-friendly tag so a run records what
#: it actually used rather than whatever ``latest`` happened to be.
DEFAULT_IMAGE = "python:3.12-slim"
PROBE_TIMEOUT_SEC = 20


class DockerSession(AgentSession):
    """A container that lives for the duration of one attempt."""

    def __init__(self, spec: SessionSpec, report: IsolationReport, image: str, binary: str) -> None:
        super().__init__(spec.workspace, report)
        self._spec = spec
        self._image = image
        self._binary = binary

    def _docker_command(self, command: Sequence[str], extra_env: Mapping[str, str] | None):
        args = [
            self._binary,
            "run",
            "--rm",
            "--interactive",
            # No host identity, no host network, no extra kernel powers.
            "--network",
            "bridge" if self._spec.network else "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "512",
            "--workdir",
            CONTAINER_WORKSPACE,
            # The one and only host path the container can see.
            "--volume",
            f"{Path(self.workspace).resolve()}:{CONTAINER_WORKSPACE}:rw",
            "--env",
            f"HOME={CONTAINER_WORKSPACE}",
            "--env",
            "AGENTDEV_ISOLATION=docker",
        ]
        for key in list(self._spec.secrets) + list(extra_env or {}):
            # Values are passed through the environment of `docker run` itself
            # rather than on the command line, so they never reach a process
            # listing or a stored command string.
            args += ["--env", key]
        args.append(self._image)
        args += list(command)
        return args

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_sec: int,
        stdin_text: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        env = build_env(dict(self._spec.secrets) | dict(extra_env or {}))
        return run_command(
            self._docker_command(command, extra_env),
            cwd=self.workspace,
            timeout_sec=timeout_sec,
            env=env,
            stdin_text=stdin_text,
        )


class DockerBackend(IsolationBackend):
    name = "docker"

    def __init__(self, image: str = DEFAULT_IMAGE, binary: str = "docker") -> None:
        self.image = image
        self.binary = binary

    def _daemon_version(self) -> str | None:
        """Server version, or None when no daemon answers."""
        if shutil.which(self.binary) is None:
            return None
        try:
            result = subprocess.run(
                [self.binary, "version", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_SEC,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        server = payload.get("Server") or {}
        return server.get("Version")

    def probe(self) -> IsolationReport:
        if shutil.which(self.binary) is None:
            return self._unavailable(f"{self.binary!r} is not on PATH")
        version = self._daemon_version()
        if version is None:
            return self._unavailable(
                "the Docker CLI is present but no daemon answered; container "
                "isolation cannot be applied"
            )
        return IsolationReport(
            backend=self.name,
            version=f"docker/{version}",
            active=True,
            publishable=True,
            network_policy=NETWORK_DENIED,
            detail=(
                f"container from {self.image}; only the attempt workspace is bind-mounted, "
                "all capabilities dropped, no new privileges"
            ),
        )

    def _unavailable(self, reason: str) -> IsolationReport:
        return IsolationReport(
            backend=self.name,
            version="unknown",
            active=False,
            publishable=False,
            network_policy="unknown",
            detail="",
            unavailable_reason=reason,
        )

    def session(self, spec: SessionSpec) -> AgentSession:
        report = self.probe()
        if not report.active:
            raise IsolationUnavailable(report.unavailable_reason)
        live = IsolationReport(
            backend=report.backend,
            version=report.version,
            active=True,
            publishable=True,
            network_policy=NETWORK_ALLOWED if spec.network else NETWORK_DENIED,
            detail=report.detail,
        )
        return DockerSession(spec, live, self.image, self.binary)
