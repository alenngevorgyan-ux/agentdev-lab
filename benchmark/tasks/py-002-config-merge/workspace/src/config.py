"""Layered configuration resolution."""


class ConfigError(ValueError):
    """Raised when two layers disagree about the shape of a key."""


def resolve_config(layers):
    """Merge configuration layers, later layers overriding earlier ones.

    Nested mappings merge recursively; all other values are replaced. Inputs
    are never mutated. A key that is a mapping in one layer and a non-mapping
    in another raises ConfigError naming the dotted path.
    """
    raise NotImplementedError
