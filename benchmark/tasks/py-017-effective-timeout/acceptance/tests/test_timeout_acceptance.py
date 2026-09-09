"""Hidden acceptance tests for the effective timeout change."""

import unittest

from src.client import HttpClient


class EffectiveDefaultTest(unittest.TestCase):
    def test_default_timeout_is_thirty(self):
        self.assertEqual(HttpClient().timeout, 30)

    def test_default_reaches_the_transport(self):
        self.assertEqual(HttpClient().get("http://x")["timeout"], 30)

    def test_explicit_timeout_still_wins(self):
        self.assertEqual(HttpClient(timeout=3).timeout, 3)

    def test_explicit_none_still_means_no_timeout(self):
        self.assertIsNone(HttpClient(timeout=None).timeout)


class BlastRadiusTest(unittest.TestCase):
    """The other defaults are for different things and must not move."""

    def test_pool_idle_timeout_unchanged(self):
        from src.settings import POOL_IDLE_TIMEOUT_SECONDS

        self.assertEqual(POOL_IDLE_TIMEOUT_SECONDS, 5)

    def test_healthcheck_interval_unchanged(self):
        from src.health import interval

        self.assertEqual(interval(), 5)

    def test_retry_budget_unchanged(self):
        from src.retry import budget

        self.assertEqual(budget(), 5)

    def test_transport_fallback_unchanged(self):
        from src.transport import FALLBACK_TIMEOUT_SECONDS

        self.assertEqual(FALLBACK_TIMEOUT_SECONDS, 5)


if __name__ == "__main__":
    unittest.main()
