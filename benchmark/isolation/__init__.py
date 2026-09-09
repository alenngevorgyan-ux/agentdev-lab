"""Isolation backend selection.

Selection is explicit and never degrades silently. ``auto`` picks the strongest
backend that can actually enforce a boundary here; if none can, it raises
rather than quietly running the agent on the bare host. Choosing to run without
isolation requires asking for ``none`` by name, and marks the run
NON-PUBLISHABLE in the stored record.
"""

from __future__ import annotations

from .base import (
    NETWORK_ALLOWED,
    NETWORK_DENIED,
    NETWORK_UNRESTRICTED_HOST,
    AgentSession,
    IsolationBackend,
    IsolationReport,
    IsolationUnavailable,
    SessionSpec,
)
from .docker import DockerBackend
from .none import NoIsolation
from .seatbelt import SeatbeltBackend

#: Strongest first. ``auto`` walks this order.
PREFERENCE: tuple[str, ...] = ("docker", "seatbelt")

_BACKENDS = {
    DockerBackend.name: DockerBackend,
    SeatbeltBackend.name: SeatbeltBackend,
    NoIsolation.name: NoIsolation,
}


def available_backends() -> list[str]:
    return ["auto", *_BACKENDS]


def get_backend(name: str) -> IsolationBackend:
    try:
        return _BACKENDS[name]()
    except KeyError:
        raise KeyError(
            f"unknown isolation backend {name!r}; available: {available_backends()}"
        ) from None


def probe_all() -> list[IsolationReport]:
    """Report on every backend, for `benchmark isolation`."""
    return [_BACKENDS[name]().probe() for name in (*PREFERENCE, NoIsolation.name)]


def select_backend(requested: str = "auto") -> IsolationBackend:
    """Resolve a backend, refusing to pretend when none can enforce anything."""
    if requested != "auto":
        backend = get_backend(requested)
        report = backend.probe()
        if requested != NoIsolation.name and not report.active:
            raise IsolationUnavailable(
                f"isolation backend {requested!r} cannot be used here: "
                f"{report.unavailable_reason}"
            )
        return backend

    for name in PREFERENCE:
        backend = _BACKENDS[name]()
        if backend.probe().active:
            return backend

    reasons = "; ".join(
        f"{report.backend}: {report.unavailable_reason}"
        for report in probe_all()
        if report.backend != NoIsolation.name
    )
    raise IsolationUnavailable(
        "no isolation backend can enforce a boundary on this machine "
        f"({reasons}). Re-run with --isolation none to measure anyway; such runs "
        "are recorded as NON-PUBLISHABLE."
    )


__all__ = [
    "AgentSession",
    "DockerBackend",
    "IsolationBackend",
    "IsolationReport",
    "IsolationUnavailable",
    "NoIsolation",
    "SeatbeltBackend",
    "SessionSpec",
    "NETWORK_ALLOWED",
    "NETWORK_DENIED",
    "NETWORK_UNRESTRICTED_HOST",
    "PREFERENCE",
    "available_backends",
    "get_backend",
    "probe_all",
    "select_backend",
]
