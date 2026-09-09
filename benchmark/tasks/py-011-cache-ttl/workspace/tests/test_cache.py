"""The existing suite. Every test here passes today and must keep passing."""

import unittest

from src.cache import LruCache


class BasicsTest(unittest.TestCase):
    def test_put_and_get(self):
        cache = LruCache(2)
        cache.put("a", 1)
        self.assertEqual(cache.get("a"), 1)

    def test_missing_key_returns_default(self):
        self.assertEqual(LruCache(2).get("nope", "fallback"), "fallback")

    def test_capacity_must_be_positive(self):
        with self.assertRaises(ValueError):
            LruCache(0)

    def test_len_counts_entries(self):
        cache = LruCache(3)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(len(cache), 2)

    def test_contains(self):
        cache = LruCache(2)
        cache.put("a", 1)
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)

    def test_update_replaces_value(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.put("a", 2)
        self.assertEqual(cache.get("a"), 2)
        self.assertEqual(len(cache), 1)


class EvictionTest(unittest.TestCase):
    def test_least_recently_used_is_evicted(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        self.assertNotIn("a", cache)
        self.assertIn("b", cache)
        self.assertIn("c", cache)

    def test_get_promotes_recency(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")
        cache.put("c", 3)
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)

    def test_peek_does_not_promote_recency(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.peek("a")
        cache.put("c", 3)
        self.assertNotIn("a", cache)

    def test_put_promotes_recency(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 11)
        cache.put("c", 3)
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)

    def test_eviction_count(self):
        cache = LruCache(1)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.stats()["evictions"], 1)

    def test_keys_are_ordered_least_recent_first(self):
        cache = LruCache(3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")
        self.assertEqual(cache.keys(), ["b", "a"])


class StatisticsTest(unittest.TestCase):
    def test_hits_and_misses(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.get("a")
        cache.get("b")
        stats = cache.stats()
        self.assertEqual((stats["hits"], stats["misses"]), (1, 1))

    def test_hit_rate(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.get("a")
        cache.get("a")
        cache.get("z")
        self.assertAlmostEqual(cache.stats()["hit_rate"], 2 / 3)

    def test_hit_rate_without_lookups(self):
        self.assertEqual(LruCache(2).stats()["hit_rate"], 0.0)

    def test_peek_does_not_affect_statistics(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.peek("a")
        cache.peek("zzz")
        stats = cache.stats()
        self.assertEqual((stats["hits"], stats["misses"]), (0, 0))

    def test_clear_empties_but_keeps_statistics(self):
        cache = LruCache(2)
        cache.put("a", 1)
        cache.get("a")
        cache.clear()
        self.assertEqual(len(cache), 0)
        self.assertEqual(cache.stats()["hits"], 1)

    def test_size_is_reported(self):
        cache = LruCache(2)
        cache.put("a", 1)
        self.assertEqual(cache.stats()["size"], 1)


if __name__ == "__main__":
    unittest.main()
