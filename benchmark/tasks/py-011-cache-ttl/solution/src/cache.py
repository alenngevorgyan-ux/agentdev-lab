"""An LRU cache used throughout the codebase."""

import time
from collections import OrderedDict

MISSING = object()


class LruCache:
    """Least-recently-used cache with hit/miss statistics and optional TTL.

    Args:
        capacity: maximum number of live entries.
        ttl: seconds after which an entry is treated as absent; None disables
            expiry entirely and restores the original behaviour exactly.
        clock: monotonic time source, injected so expiry is testable.
    """

    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if ttl is not None and ttl < 0:
            raise ValueError("ttl must not be negative")
        self.capacity = capacity
        self.ttl = ttl
        self._clock = clock
        self._entries = OrderedDict()   # key -> (value, stored_at)
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _is_expired(self, stored_at):
        return self.ttl is not None and (self._clock() - stored_at) > self.ttl

    def _purge(self):
        """Drop expired entries so they stop occupying capacity."""
        if self.ttl is None:
            return
        for key in [k for k, (_, at) in self._entries.items() if self._is_expired(at)]:
            del self._entries[key]

    def _live(self, key):
        """Return the entry for ``key`` if present and unexpired, else MISSING."""
        entry = self._entries.get(key)
        if entry is None:
            return MISSING
        value, stored_at = entry
        if self._is_expired(stored_at):
            del self._entries[key]
            return MISSING
        return value

    def get(self, key, default=None):
        """Return the value for ``key``, promoting it to most-recently-used."""
        value = self._live(key)
        if value is MISSING:
            self.misses += 1
            return default
        self._entries.move_to_end(key)
        self.hits += 1
        return value

    def peek(self, key, default=None):
        """Return the value without affecting recency or statistics."""
        value = self._live(key)
        return default if value is MISSING else value

    def put(self, key, value):
        """Insert or update ``key``, evicting the least-recently-used entry."""
        self._purge()
        if key in self._entries:
            self._entries.move_to_end(key)
        self._entries[key] = (value, self._clock())
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)
            self.evictions += 1

    def clear(self):
        """Drop every entry. Statistics are preserved."""
        self._entries.clear()

    def stats(self):
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": (self.hits / total) if total else 0.0,
            "size": len(self),
        }

    def keys(self):
        """Live keys, least-recently-used first."""
        self._purge()
        return list(self._entries)

    def __contains__(self, key):
        return self._live(key) is not MISSING

    def __len__(self):
        self._purge()
        return len(self._entries)
