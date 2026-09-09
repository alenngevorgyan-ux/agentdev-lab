"""Health checking."""

from .settings import HEALTHCHECK_INTERVAL_SECONDS


def interval():
    return HEALTHCHECK_INTERVAL_SECONDS
