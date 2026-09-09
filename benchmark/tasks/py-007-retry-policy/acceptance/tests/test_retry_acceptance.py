"""Hidden acceptance tests for retry semantics."""

import random
import unittest

from src.retry import RetryPolicy, call_with_retry
from tests.test_retry import Flaky, RecordingSleeper


class ForbiddenRandom(random.Random):
    """A Random that fails the test if it is consulted at all."""

    def __init__(self):
        super().__init__(0)
        self.used = False

    def uniform(self, a, b):
        self.used = True
        return super().uniform(a, b)

    def random(self):
        self.used = True
        return super().random()


class JitterTest(unittest.TestCase):
    def test_rng_untouched_when_jitter_disabled(self):
        rng = ForbiddenRandom()
        policy = RetryPolicy(max_attempts=4, base_delay=1.0, jitter=False, rng=rng)
        [policy.delay_for(n) for n in (2, 3, 4)]
        self.assertFalse(rng.used, "the rng must not be consulted when jitter is disabled")

    def test_jitter_scales_within_bounds(self):
        rng = random.Random(1234)
        policy = RetryPolicy(max_attempts=6, base_delay=2.0, multiplier=1.0, jitter=True, rng=rng)
        delays = [policy.delay_for(n) for n in range(2, 7)]
        for delay in delays:
            self.assertGreaterEqual(delay, 1.0)
            self.assertLessEqual(delay, 3.0)

    def test_jitter_is_reproducible_for_a_seeded_rng(self):
        def delays():
            policy = RetryPolicy(max_attempts=5, base_delay=1.0, jitter=True, rng=random.Random(7))
            return [policy.delay_for(n) for n in (2, 3, 4)]

        self.assertEqual(delays(), delays())

    def test_jitter_respects_the_cap_before_scaling(self):
        rng = random.Random(3)
        policy = RetryPolicy(
            max_attempts=5, base_delay=1.0, multiplier=100.0, max_delay=4.0, jitter=True, rng=rng
        )
        self.assertLessEqual(policy.delay_for(5), 6.0)


class SemanticsTest(unittest.TestCase):
    def setUp(self):
        self.sleeper = RecordingSleeper()

    def test_unlisted_exception_propagates_without_sleeping(self):
        operation = Flaky(failures=1, exception=KeyError)
        with self.assertRaises(KeyError):
            call_with_retry(operation, RetryPolicy(max_attempts=5), self.sleeper, (ValueError,))
        self.assertEqual(operation.calls, 1)
        self.assertEqual(self.sleeper.sleeps, [])

    def test_original_exception_instance_is_reraised(self):
        marker = ValueError("the original")
        def operation():
            raise marker

        with self.assertRaises(ValueError) as ctx:
            call_with_retry(operation, RetryPolicy(max_attempts=2, base_delay=0.0), self.sleeper,
                            (ValueError,))
        self.assertIs(ctx.exception, marker)

    def test_call_count_never_exceeds_max_attempts(self):
        operation = Flaky(failures=100)
        with self.assertRaises(ValueError):
            call_with_retry(operation, RetryPolicy(max_attempts=4, base_delay=0.0), self.sleeper,
                            (ValueError,))
        self.assertEqual(operation.calls, 4)
        self.assertEqual(len(self.sleeper.sleeps), 3)

    def test_single_attempt_policy_never_sleeps(self):
        operation = Flaky(failures=1)
        with self.assertRaises(ValueError):
            call_with_retry(operation, RetryPolicy(max_attempts=1), self.sleeper, (ValueError,))
        self.assertEqual(self.sleeper.sleeps, [])

    def test_negative_base_delay_rejected(self):
        with self.assertRaises(ValueError):
            RetryPolicy(base_delay=-1.0)

    def test_multiplier_below_one_rejected(self):
        with self.assertRaises(ValueError):
            RetryPolicy(multiplier=0.5)


if __name__ == "__main__":
    unittest.main()
