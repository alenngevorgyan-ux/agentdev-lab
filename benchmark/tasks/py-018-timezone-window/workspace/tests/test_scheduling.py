import unittest
from datetime import date, timedelta

from src.scheduling import parse_window, window_length


class ParseWindowTest(unittest.TestCase):
    def test_simple_window(self):
        start, end = parse_window("01:00-03:00", day=date(2026, 3, 1))
        self.assertEqual(end - start, timedelta(hours=2))

    def test_window_length(self):
        self.assertEqual(window_length("01:00-03:00"), timedelta(hours=2))

    def test_midnight_crossing_window_is_positive(self):
        start, end = parse_window("22:00-04:00", day=date(2026, 3, 1))
        self.assertEqual(end - start, timedelta(hours=6))


if __name__ == "__main__":
    unittest.main()
