"""An LRU cache used throughout the codebase."""

import time
from collections import OrderedDict

MISSING = object()


class LruCache:
    """Least-recently-used cache with hit/miss statistics.

    Args:
        capacity: maximum number of live entries.
    """

    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._entries = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key, default=None):
        """Return the value for ``key``, promoting it to most-recently-used."""
        if key not in self._entries:
            self.misses += 1
            return default
        self._entries.move_to_end(key)
        self.hits += 1
        return self._entries[key]

    def peek(self, key, default=None):
        """Return the value without affecting recency or statistics."""
        return self._entries.get(key, default)

    def put(self, key, value):
        """Insert or update ``key``, evicting the least-recently-used entry."""
        if key in self._entries:
            self._entries.move_to_end(key)
        self._entries[key] = value
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
        return list(self._entries)

    def __contains__(self, key):
        return key in self._entries

    def __len__(self):
        return len(self._entries)
