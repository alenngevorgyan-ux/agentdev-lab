"""Layered configuration resolution."""

import copy
from collections.abc import Mapping


class ConfigError(ValueError):
    """Raised when two layers disagree about the shape of a key."""


def _merge(base, override, path):
    result = dict(base)
    for key, incoming in override.items():
        dotted = f"{path}.{key}" if path else str(key)
        if key not in result:
            result[key] = copy.deepcopy(incoming)
            continue

        existing = result[key]
        existing_is_map = isinstance(existing, Mapping)
        incoming_is_map = isinstance(incoming, Mapping)
        if existing_is_map != incoming_is_map:
            raise ConfigError(
                f"conflicting types for key {dotted!r}: "
                f"{type(existing).__name__} vs {type(incoming).__name__}"
            )
        result[key] = (
            _merge(existing, incoming, dotted) if existing_is_map else copy.deepcopy(incoming)
        )
    return result


def resolve_config(layers):
    """Merge configuration layers, later layers overriding earlier ones."""
    resolved = {}
    for layer in layers:
        if not isinstance(layer, Mapping):
            raise ConfigError(f"configuration layer must be a mapping, got {type(layer).__name__}")
        resolved = _merge(resolved, layer, "")
    return resolved
