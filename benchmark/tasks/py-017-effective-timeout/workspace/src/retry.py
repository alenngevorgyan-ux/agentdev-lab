"""Retry configuration."""

#: Total seconds a retried call may spend, across all attempts.
RETRY_BUDGET_SECONDS = 5

MAX_ATTEMPTS = 3


def budget():
    return RETRY_BUDGET_SECONDS
