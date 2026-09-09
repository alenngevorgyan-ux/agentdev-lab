"""Adapter registry."""

from __future__ import annotations

from .base import Adapter, AgentOutcome
from .canary import IsolationCanaryAdapter
from .claude_code import ClaudeCodeAdapter
from .noop import NoopAdapter
from .oracle import OracleAdapter

#: Adapters that measure the harness itself rather than an agent under test.
CONTROL_ADAPTERS = frozenset({"noop", "oracle", "canary"})

_FACTORIES = {
    NoopAdapter.name: NoopAdapter,
    OracleAdapter.name: OracleAdapter,
    ClaudeCodeAdapter.name: ClaudeCodeAdapter,
    IsolationCanaryAdapter.name: IsolationCanaryAdapter,
}


def available_adapters() -> list[str]:
    return sorted(_FACTORIES)


def get_adapter(name: str) -> Adapter:
    try:
        factory = _FACTORIES[name]
    except KeyError:
        raise KeyError(f"unknown adapter {name!r}; available: {available_adapters()}") from None
    return factory()


__all__ = [
    "Adapter",
    "AgentOutcome",
    "ClaudeCodeAdapter",
    "IsolationCanaryAdapter",
    "NoopAdapter",
    "OracleAdapter",
    "CONTROL_ADAPTERS",
    "available_adapters",
    "get_adapter",
]
