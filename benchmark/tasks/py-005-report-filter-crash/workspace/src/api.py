"""Entry point used by the web layer."""

from .reporting import build_report
from .storage import SalesRepository


def sales_report(filter_names=()):
    return build_report(SalesRepository(), list(filter_names))
