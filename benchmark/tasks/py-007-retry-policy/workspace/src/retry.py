"""Retry with exponential backoff.

Both the clock and the randomness are injected so that retry behaviour is
fully deterministic under test.
"""


class RetryPolicy:
    """Backoff schedule for retried operations.

    Args:
        max_attempts: total number of calls, including the first.
        base_delay: delay in seconds before the second attempt.
        max_delay: upper bound on any single delay.
        multiplier: growth factor between consecutive delays.
        jitter: when True, scale each delay by a random factor in [0.5, 1.5].
        rng: a random.Random instance; consulted only when jitter is enabled.
    """

    def __init__(self, max_attempts=3, base_delay=1.0, max_delay=60.0, multiplier=2.0,
                 jitter=False, rng=None):
        raise NotImplementedError

    def delay_for(self, attempt):
        """Delay in seconds before ``attempt`` (2 is the first retry)."""
        raise NotImplementedError


def call_with_retry(operation, policy, sleeper, retry_on=(Exception,)):
    """Call ``operation`` under ``policy``, sleeping via ``sleeper``."""
    raise NotImplementedError
