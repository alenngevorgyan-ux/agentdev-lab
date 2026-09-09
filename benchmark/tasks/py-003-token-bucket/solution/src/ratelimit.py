"""Token-bucket rate limiting with an injectable clock."""


class TokenBucket:
    """A token bucket that refills continuously."""

    def __init__(self, capacity, refill_per_second, clock):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second < 0:
            raise ValueError("refill_per_second must not be negative")
        if not callable(clock):
            raise ValueError("clock must be callable")

        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def _refill(self):
        now = self._clock()
        # A clock that moves backwards must not mint tokens; re-anchor instead.
        elapsed = max(0.0, now - self._last)
        self._last = now
        if elapsed and self.refill_per_second:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_second)

    @staticmethod
    def _check_cost(cost):
        cost = float(cost)
        if cost < 0:
            raise ValueError("cost must not be negative")
        return cost

    def allow(self, cost=1.0):
        cost = self._check_cost(cost)
        self._refill()
        if cost > self._tokens:
            return False
        self._tokens -= cost
        return True

    def retry_after(self, cost=1.0):
        cost = self._check_cost(cost)
        self._refill()
        if cost <= self._tokens:
            return 0.0
        if cost > self.capacity or self.refill_per_second == 0:
            return float("inf")
        return (cost - self._tokens) / self.refill_per_second

    @property
    def tokens(self):
        self._refill()
        return self._tokens
