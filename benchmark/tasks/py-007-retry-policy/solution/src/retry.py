"""Retry with exponential backoff."""


class RetryPolicy:
    """Backoff schedule for retried operations."""

    def __init__(self, max_attempts=3, base_delay=1.0, max_delay=60.0, multiplier=2.0,
                 jitter=False, rng=None):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if base_delay < 0:
            raise ValueError("base_delay must not be negative")
        if max_delay < 0:
            raise ValueError("max_delay must not be negative")
        if multiplier < 1:
            raise ValueError("multiplier must be at least 1")

        self.max_attempts = max_attempts
        self.base_delay = float(base_delay)
        self.max_delay = float(max_delay)
        self.multiplier = float(multiplier)
        self.jitter = jitter
        self.rng = rng

    def delay_for(self, attempt):
        """Delay in seconds before ``attempt`` (2 is the first retry)."""
        if attempt < 2:
            return 0.0
        raw = self.base_delay * (self.multiplier ** (attempt - 2))
        delay = min(raw, self.max_delay)
        if not self.jitter:
            return delay
        if self.rng is None:
            raise ValueError("jitter requires an rng")
        # The cap applies to the schedule; jitter then spreads calls around it.
        return delay * self.rng.uniform(0.5, 1.5)


def call_with_retry(operation, policy, sleeper, retry_on=(Exception,)):
    """Call ``operation`` under ``policy``, sleeping via ``sleeper``."""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except retry_on:
            if attempt == policy.max_attempts:
                raise
            sleeper(policy.delay_for(attempt + 1))
    raise AssertionError("unreachable: the loop always returns or raises")
