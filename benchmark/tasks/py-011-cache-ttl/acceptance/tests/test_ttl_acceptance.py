"""Hidden acceptance tests for the new TTL behaviour."""

import unittest

from src.cache import LruCache


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TtlTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def cache(self, capacity=3, ttl=10.0):
        return LruCache(capacity, ttl=ttl, clock=self.clock)

    def test_entry_is_live_before_expiry(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(9)
        self.assertEqual(cache.get("a"), 1)

    def test_entry_is_gone_after_expiry(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(11)
        self.assertIsNone(cache.get("a"))

    def test_expired_entry_is_not_contained(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(11)
        self.assertNotIn("a", cache)

    def test_expired_entry_does_not_count_towards_len(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(11)
        self.assertEqual(len(cache), 0)

    def test_expired_entry_counts_as_a_miss(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(11)
        cache.get("a")
        self.assertEqual(cache.stats()["misses"], 1)
        self.assertEqual(cache.stats()["hits"], 0)

    def test_expired_entries_free_capacity(self):
        cache = self.cache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.clock.advance(11)
        cache.put("c", 3)
        cache.put("d", 4)
        self.assertIn("c", cache)
        self.assertIn("d", cache)
        self.assertEqual(len(cache), 2)

    def test_refreshing_a_key_resets_its_age(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(9)
        cache.put("a", 2)
        self.clock.advance(9)
        self.assertEqual(cache.get("a"), 2)

    def test_peek_respects_expiry(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(11)
        self.assertIsNone(cache.peek("a"))

    def test_peek_still_does_not_promote_recency(self):
        cache = self.cache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.peek("a")
        cache.put("c", 3)
        self.assertNotIn("a", cache)

    def test_ttl_none_never_expires(self):
        cache = LruCache(2, ttl=None, clock=self.clock)
        cache.put("a", 1)
        self.clock.advance(10_000)
        self.assertEqual(cache.get("a"), 1)

    def test_wall_clock_is_not_consulted(self):
        """Expiry must be driven by the injected clock only."""
        cache = self.cache()
        cache.put("a", 1)
        self.assertEqual(cache.get("a"), 1)
        self.clock.advance(10.0001)
        self.assertIsNone(cache.get("a"))

    def test_keys_excludes_expired_entries(self):
        cache = self.cache()
        cache.put("a", 1)
        self.clock.advance(11)
        cache.put("b", 2)
        self.assertEqual(cache.keys(), ["b"])

    def test_negative_ttl_rejected(self):
        with self.assertRaises(ValueError):
            LruCache(2, ttl=-1, clock=self.clock)


if __name__ == "__main__":
    unittest.main()
