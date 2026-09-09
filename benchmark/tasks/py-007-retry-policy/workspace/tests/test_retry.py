import unittest

from src.retry import RetryPolicy, call_with_retry


class RecordingSleeper:
    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds):
        self.sleeps.append(seconds)


class Flaky:
    """An operation that fails a fixed number of times, then succeeds."""

    def __init__(self, failures, exception=ValueError):
        self.remaining = failures
        self.exception = exception
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise self.exception("boom")
        return "ok"


class PolicyTest(unittest.TestCase):
    def test_delays_grow_exponentially(self):
        policy = RetryPolicy(max_attempts=4, base_delay=1.0, multiplier=2.0)
        self.assertEqual([policy.delay_for(n) for n in (2, 3, 4)], [1.0, 2.0, 4.0])

    def test_delay_is_capped(self):
        policy = RetryPolicy(max_attempts=5, base_delay=1.0, multiplier=10.0, max_delay=5.0)
        self.assertEqual(policy.delay_for(4), 5.0)

    def test_invalid_max_attempts(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_attempts=0)


class CallWithRetryTest(unittest.TestCase):
    def setUp(self):
        self.sleeper = RecordingSleeper()

    def test_success_first_time(self):
        operation = Flaky(failures=0)
        self.assertEqual(call_with_retry(operation, RetryPolicy(), self.sleeper), "ok")
        self.assertEqual(self.sleeper.sleeps, [])

    def test_retries_until_success(self):
        operation = Flaky(failures=2)
        policy = RetryPolicy(max_attempts=3, base_delay=1.0, multiplier=2.0)
        self.assertEqual(call_with_retry(operation, policy, self.sleeper, (ValueError,)), "ok")
        self.assertEqual(operation.calls, 3)
        self.assertEqual(self.sleeper.sleeps, [1.0, 2.0])

    def test_exhausted_retries_reraise(self):
        operation = Flaky(failures=99)
        policy = RetryPolicy(max_attempts=2, base_delay=1.0)
        with self.assertRaises(ValueError):
            call_with_retry(operation, policy, self.sleeper, (ValueError,))
        self.assertEqual(operation.calls, 2)


if __name__ == "__main__":
    unittest.main()
