"""Subprocess execution with timeouts, deterministic env, and bounded capture."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .config import MAX_CAPTURED_BYTES, MAX_TIMEOUT_SEC
from .redaction import redact

#: Environment variables passed through to sandboxed commands. Everything else
#: is dropped so a stray local variable cannot change a measured outcome.
_PASSTHROUGH_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SystemRoot")

TIMEOUT_EXIT_CODE = -1000


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def build_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """A minimal, reproducible environment for sandboxed commands."""
    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ}
    env.update(
        {
            # Keep runs byte-identical: no bytecode residue, no hash randomisation,
            # no interference from the harness's own installation.
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "AGENTDEV_SANDBOX": "1",
        }
    )
    env.pop("PYTHONPATH", None)
    if extra:
        env.update(extra)
    return env


def _capture(raw: bytes) -> str:
    """Bound and sanitise a captured stream.

    Redaction happens here, at the single point where subprocess output enters
    the harness, so nothing downstream -- the database, exports, the dashboard,
    the session log -- can inherit a credential from a chattier code path.
    """
    if len(raw) > MAX_CAPTURED_BYTES:
        head = raw[:MAX_CAPTURED_BYTES]
        omitted = len(raw) - MAX_CAPTURED_BYTES
        text = head.decode("utf-8", "replace") + f"\n...[truncated {omitted} bytes]"
    else:
        text = raw.decode("utf-8", "replace")
    return redact(text)


def resolve_command(command: Sequence[str]) -> tuple[str, ...]:
    """Resolve ``python``/``python3`` to the running interpreter.

    Tasks declare ``python3`` for readability; the harness must nonetheless run
    them under the exact interpreter that is executing the benchmark, or the
    recorded runtime would not describe what actually ran.
    """
    parts = list(command)
    if parts and parts[0] in ("python", "python3"):
        parts[0] = sys.executable
    return tuple(parts)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_sec: int,
    env: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
) -> CommandResult:
    """Run ``command`` in ``cwd``, killing the whole process group on timeout."""
    if timeout_sec <= 0 or timeout_sec > MAX_TIMEOUT_SEC:
        raise ValueError(f"timeout_sec must be in 1..{MAX_TIMEOUT_SEC}, got {timeout_sec}")

    resolved = resolve_command(command)
    if shutil.which(resolved[0]) is None and not Path(resolved[0]).exists():
        return CommandResult(
            command=resolved,
            exit_code=127,
            stdout="",
            stderr=f"command not found: {resolved[0]}",
            duration_ms=0,
            timed_out=False,
        )

    started = time.monotonic()
    popen_kwargs: dict = {}
    if os.name == "posix":
        # Own process group so a runaway child tree dies with the timeout.
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(
        resolved,
        cwd=str(cwd),
        env=dict(env) if env is not None else build_env(),
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **popen_kwargs,
    )
    timed_out = False
    try:
        raw_out, raw_err = process.communicate(
            input=stdin_text.encode("utf-8") if stdin_text is not None else None,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(process)
        raw_out, raw_err = process.communicate()

    duration_ms = int((time.monotonic() - started) * 1000)
    exit_code = TIMEOUT_EXIT_CODE if timed_out else process.returncode
    return CommandResult(
        command=resolved,
        exit_code=exit_code,
        stdout=_capture(raw_out or b""),
        stderr=_capture(raw_err or b""),
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


def _kill_tree(process: subprocess.Popen) -> None:
    """Terminate a timed-out process, escalating to SIGKILL on the group."""
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        process.kill()
    except ProcessLookupError:
        pass
