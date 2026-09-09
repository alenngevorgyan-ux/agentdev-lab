import unittest

from src.ratelimit import TokenBucket


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TokenBucketTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def bucket(self, capacity=10, rate=1.0):
        return TokenBucket(capacity, rate, self.clock)

    def test_starts_full(self):
        self.assertAlmostEqual(self.bucket().tokens, 10.0)

    def test_allows_up_to_capacity_then_denies(self):
        bucket = self.bucket(capacity=3)
        self.assertTrue(all(bucket.allow() for _ in range(3)))
        self.assertFalse(bucket.allow())

    def test_refills_over_time(self):
        bucket = self.bucket(capacity=5, rate=2.0)
        for _ in range(5):
            bucket.allow()
        self.assertFalse(bucket.allow())
        self.clock.advance(0.5)
        self.assertTrue(bucket.allow())

    def test_refill_is_capped_at_capacity(self):
        bucket = self.bucket(capacity=4, rate=100.0)
        bucket.allow(4)
        self.clock.advance(1000)
        self.assertAlmostEqual(bucket.tokens, 4.0)

    def test_partial_cost_is_not_consumed_on_denial(self):
        bucket = self.bucket(capacity=5, rate=0.0)
        self.assertFalse(bucket.allow(6))
        self.assertAlmostEqual(bucket.tokens, 5.0)

    def test_fractional_cost(self):
        bucket = self.bucket(capacity=1, rate=0.0)
        self.assertTrue(bucket.allow(0.25))
        self.assertAlmostEqual(bucket.tokens, 0.75)

    def test_backwards_clock_does_not_mint_tokens(self):
        bucket = self.bucket(capacity=5, rate=1.0)
        bucket.allow(5)
        self.clock.advance(-100)
        self.assertAlmostEqual(bucket.tokens, 0.0)
        self.assertFalse(bucket.allow())

    def test_retry_after_zero_when_available(self):
        self.assertEqual(self.bucket().retry_after(1), 0.0)

    def test_retry_after_estimates_wait(self):
        bucket = self.bucket(capacity=2, rate=4.0)
        bucket.allow(2)
        self.assertAlmostEqual(bucket.retry_after(1), 0.25)

    def test_retry_after_is_actionable(self):
        bucket = self.bucket(capacity=2, rate=4.0)
        bucket.allow(2)
        self.clock.advance(bucket.retry_after(1))
        self.assertTrue(bucket.allow(1))

    def test_retry_after_infinite_without_refill(self):
        bucket = self.bucket(capacity=1, rate=0.0)
        bucket.allow(1)
        self.assertEqual(bucket.retry_after(1), float("inf"))

    def test_cost_above_capacity_never_allowed(self):
        bucket = self.bucket(capacity=2, rate=1.0)
        self.assertFalse(bucket.allow(3))
        self.assertEqual(bucket.retry_after(3), float("inf"))

    def test_invalid_capacity_rejected(self):
        with self.assertRaises(ValueError):
            TokenBucket(0, 1.0, self.clock)

    def test_negative_rate_rejected(self):
        with self.assertRaises(ValueError):
            TokenBucket(1, -1.0, self.clock)

    def test_negative_cost_rejected(self):
        with self.assertRaises(ValueError):
            self.bucket().allow(-1)


if __name__ == "__main__":
    unittest.main()
