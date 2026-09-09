"""macOS Seatbelt isolation (``sandbox-exec``).

Seatbelt applies a kernel-enforced policy to a process and everything it
spawns. The policy here is deny-by-default: the only writable paths are the
attempt's own workspace and its private scratch directory, and the only
readable paths beyond those are the system and toolchain directories the
interpreter and agent binary need in order to start.

That makes the properties the benchmark needs structural rather than
advisory. The hidden acceptance tests, the reference solutions, the results
database, the harness source, other attempts and the host home directory are
not merely absent from the workspace -- an ``open()`` on them fails with
EPERM inside the boundary, which the adversarial suite proves.

Apple has deprecated ``sandbox-exec`` but it remains functional; the backend
records the OS build so a future behaviour change is visible in the record.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Mapping, Sequence

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

#: Resolved at import time: the binary has moved between macOS releases, so it
#: is located rather than assumed.
SANDBOX_EXEC = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"

#: Read-only roots every process needs in order to start at all. Deliberately
#: coarse for system directories and deliberately absent for anything under
#: the user's home, /tmp, or the benchmark checkout.
SYSTEM_READ_ROOTS: tuple[str, ...] = (
    "/usr/lib",
    "/usr/share",
    "/usr/bin",
    "/usr/libexec",
    # /usr/local is a firmlink on modern macOS and is NOT covered by /usr.
    "/usr/local",
    "/bin",
    "/sbin",
    "/System",
    "/Library",
    "/opt",
    "/private/var/select",
    "/private/var/db/dyld",
)

DEVICE_LITERALS: tuple[str, ...] = (
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/dtracehelper",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/stderr",
)


def _escape(path: Path | str) -> str:
    """Quote a path for a Seatbelt profile literal."""
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def _resolve(path: Path | str) -> Path:
    """Canonical path. Seatbelt matches resolved paths, not symlinks."""
    return Path(os.path.realpath(str(path)))


def build_profile(
    *,
    writable: Iterable[Path],
    readable: Iterable[Path] = (),
    allow_network: bool = False,
) -> str:
    """Render a deny-by-default Seatbelt profile.

    Nothing is granted that is not listed here, including the ability to stat a
    path -- so a probe cannot even learn whether a file exists outside the
    boundary.
    """
    lines = [
        "(version 1)",
        ";; AgentDev Lab isolation profile -- deny by default.",
        "(deny default)",
        "(allow process-exec process-fork signal)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow ipc-posix-shm)",
        '(allow file-ioctl (literal "/dev/null") (literal "/dev/tty"))',
        # The interpreter resolves its own path at startup, which needs stat on
        # the root and on the system tree. Metadata is *not* granted anywhere
        # else: the home directory, /tmp and the benchmark checkout cannot even
        # be probed for existence, let alone read.
        '(allow file-read-metadata (literal "/") (subpath "/usr"))',
    ]

    read_paths = list(SYSTEM_READ_ROOTS) + [str(_resolve(p)) for p in readable]
    lines.append("(allow file-read*")
    lines += [f'  (subpath "{_escape(path)}")' for path in read_paths]
    lines += [f'  (literal "{_escape(device)}")' for device in DEVICE_LITERALS]
    lines.append(")")

    lines.append("(allow file-read* file-write*")
    lines += [f'  (subpath "{_escape(_resolve(path))}")' for path in writable]
    lines += [f'  (literal "{_escape(device)}")' for device in DEVICE_LITERALS]
    lines.append(")")

    if allow_network:
        lines.append(";; Network permitted: the agent under test must reach its API.")
        lines.append("(allow network*)")
        # Name resolution needs the resolver configuration and its socket.
        lines.append('(allow file-read* (subpath "/private/etc") (subpath "/private/var/run"))')
    else:
        lines.append(";; Network denied: evaluation must not depend on the outside world.")

    return "\n".join(lines) + "\n"


class SeatbeltSession(AgentSession):
    """A workspace confined by a kernel-enforced Seatbelt profile."""

    def __init__(
        self,
        spec: SessionSpec,
        report: IsolationReport,
        private_root: Path,
        profile_path: Path,
        owns_root: bool,
    ) -> None:
        super().__init__(spec.workspace, report)
        self._spec = spec
        self._private_root = private_root
        self._profile_path = profile_path
        self._owns_root = owns_root

    def _env(self, extra: Mapping[str, str] | None) -> dict[str, str]:
        env = build_env()
        # The host home directory is unreachable inside the boundary, so point
        # HOME at an empty private directory rather than leaving it dangling.
        env["HOME"] = str(self._private_root / "home")
        env["TMPDIR"] = str(self._private_root / "tmp")
        env["AGENTDEV_ISOLATION"] = self.report.backend
        env.update(self._spec.secrets)
        env.update(extra or {})
        return env

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_sec: int,
        stdin_text: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        wrapped = [SANDBOX_EXEC, "-f", str(self._profile_path), *command]
        return run_command(
            wrapped,
            cwd=self.workspace,
            timeout_sec=timeout_sec,
            env=self._env(extra_env),
            stdin_text=stdin_text,
        )

    def close(self) -> None:
        # The profile lives outside the boundary so the confined process can
        # neither read nor rewrite the policy that governs it.
        self._profile_path.unlink(missing_ok=True)
        if self._owns_root:
            shutil.rmtree(self._private_root, ignore_errors=True)


class SeatbeltBackend(IsolationBackend):
    name = "seatbelt"

    def __init__(self, control_dir: Path | None = None) -> None:
        self._control_dir = control_dir

    def probe(self) -> IsolationReport:
        if platform.system() != "Darwin":
            return self._unavailable("Seatbelt exists only on macOS")
        if not Path(SANDBOX_EXEC).exists():
            return self._unavailable("sandbox-exec was not found on this system")
        return IsolationReport(
            backend=self.name,
            version=f"darwin/{platform.release()}",
            active=True,
            publishable=True,
            network_policy=NETWORK_DENIED,
            detail=(
                "kernel-enforced deny-by-default policy; only the attempt workspace "
                "and its private scratch directory are writable"
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

        workspace = _resolve(spec.workspace)
        # The private root is the workspace's parent when the runner already
        # laid one out; otherwise one is created and owned by this session.
        private_root = workspace.parent
        owns_root = False
        if private_root == workspace:  # defensive: workspace at filesystem root
            private_root = Path(tempfile.mkdtemp(prefix="agentdev-priv-"))
            owns_root = True

        for name in ("tmp", "home"):
            (private_root / name).mkdir(parents=True, exist_ok=True)

        control_dir = self._control_dir or Path(tempfile.gettempdir()) / "agentdev-control"
        control_dir.mkdir(parents=True, exist_ok=True)
        handle, profile_name = tempfile.mkstemp(suffix=".sb", dir=str(control_dir))
        os.close(handle)
        profile_path = Path(profile_name)
        profile_path.write_text(
            build_profile(
                writable=[workspace, private_root / "tmp", private_root / "home"],
                readable=[_resolve(sys.executable).parent.parent, *spec.toolchain_paths],
                allow_network=spec.network,
            ),
            encoding="utf-8",
        )

        actual_report = IsolationReport(
            backend=report.backend,
            version=report.version,
            active=True,
            publishable=True,
            network_policy=NETWORK_ALLOWED if spec.network else NETWORK_DENIED,
            detail=report.detail,
        )
        return SeatbeltSession(spec, actual_report, private_root, profile_path, owns_root)


def seatbelt_supported() -> bool:
    return platform.system() == "Darwin" and Path(SANDBOX_EXEC).exists()
