"""Hidden acceptance tests for timezone-aware scheduling."""

import unittest
from datetime import date, datetime, timedelta, timezone

from src.jobs import is_within_window, next_run_after, now
from src.scheduling import parse_window

UTC = timezone.utc
MOSCOW = timezone(timedelta(hours=3))


class AwarenessTest(unittest.TestCase):
    def test_parse_window_returns_aware_datetimes(self):
        start, end = parse_window("01:00-03:00", day=date(2026, 3, 1))
        self.assertIsNotNone(start.tzinfo)
        self.assertIsNotNone(end.tzinfo)

    def test_parse_window_is_utc(self):
        start, _ = parse_window("01:00-03:00", day=date(2026, 3, 1))
        self.assertEqual(start.utcoffset(), timedelta(0))

    def test_now_is_aware(self):
        self.assertIsNotNone(now().tzinfo)

    def test_next_run_after_stays_aware(self):
        result = next_run_after(datetime(2026, 3, 1, 12, 0, tzinfo=UTC), 30)
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.hour, 12)
        self.assertEqual(result.minute, 30)


class WindowMembershipTest(unittest.TestCase):
    def test_inside_the_window(self):
        moment = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
        self.assertTrue(is_within_window(moment, "01:00-03:00"))

    def test_outside_the_window(self):
        moment = datetime(2026, 3, 1, 5, 0, tzinfo=UTC)
        self.assertFalse(is_within_window(moment, "01:00-03:00"))

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            is_within_window(datetime(2026, 3, 1, 2, 0), "01:00-03:00")

    def test_non_utc_timezone_is_converted_not_compared_raw(self):
        # 04:00 Moscow is 01:00 UTC, which is inside the window.
        moment = datetime(2026, 3, 1, 4, 0, tzinfo=MOSCOW)
        self.assertTrue(is_within_window(moment, "01:00-03:00"))

    def test_non_utc_timezone_outside_the_window(self):
        # 07:00 Moscow is 04:00 UTC, which is outside.
        moment = datetime(2026, 3, 1, 7, 0, tzinfo=MOSCOW)
        self.assertFalse(is_within_window(moment, "01:00-03:00"))


class MidnightCrossingTest(unittest.TestCase):
    SPEC = "22:00-04:00"

    def test_late_evening_is_inside(self):
        self.assertTrue(is_within_window(datetime(2026, 3, 1, 23, 0, tzinfo=UTC), self.SPEC))

    def test_early_morning_is_inside(self):
        self.assertTrue(is_within_window(datetime(2026, 3, 2, 2, 0, tzinfo=UTC), self.SPEC))

    def test_midday_is_outside(self):
        self.assertFalse(is_within_window(datetime(2026, 3, 1, 12, 0, tzinfo=UTC), self.SPEC))

    def test_exact_boundaries_are_inside(self):
        self.assertTrue(is_within_window(datetime(2026, 3, 1, 22, 0, tzinfo=UTC), self.SPEC))
        self.assertTrue(is_within_window(datetime(2026, 3, 2, 4, 0, tzinfo=UTC), self.SPEC))


if __name__ == "__main__":
    unittest.main()
