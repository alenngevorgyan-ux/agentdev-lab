"""Token-bucket rate limiting with an injectable clock."""


class TokenBucket:
    """A token bucket that refills continuously.

    Args:
        capacity: maximum number of tokens held; the bucket starts full.
        refill_per_second: tokens added per second of elapsed clock time.
        clock: zero-argument callable returning a monotonic time in seconds.
    """

    def __init__(self, capacity, refill_per_second, clock):
        raise NotImplementedError

    def allow(self, cost=1.0):
        """Consume `cost` tokens if they are all available. Returns a bool."""
        raise NotImplementedError

    def retry_after(self, cost=1.0):
        """Seconds until `cost` tokens are available; 0.0 if available now."""
        raise NotImplementedError

    @property
    def tokens(self):
        """Tokens currently available, refilled to the current clock reading."""
        raise NotImplementedError
