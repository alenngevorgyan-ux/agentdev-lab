"""Filter registry and application."""

from .errors import UnknownFilterError

_REGISTRY = {
    "eu-only": lambda sale: sale.region == "eu",
    "large": lambda sale: sale.amount >= 100.0,
    "hardware": lambda sale: sale.category == "hardware",
}


def available_filters():
    return sorted(_REGISTRY)


def apply_filters(sales, filter_names):
    """Return the sales matching every named filter."""
    predicates = []
    for name in filter_names:
        if name not in _REGISTRY:
            raise UnknownFilterError(f"unknown filter: {name}")
        predicates.append(_REGISTRY[name])
    return [sale for sale in sales if all(predicate(sale) for predicate in predicates)]
