import unittest
from decimal import Decimal

from src.pricing import line_total, subtotal


class LineTotalTest(unittest.TestCase):
    def test_simple_line(self):
        self.assertEqual(line_total(Decimal("10.00"), 3), Decimal("30.00"))

    def test_discounted_line(self):
        self.assertEqual(line_total(Decimal("10.00"), 2, 10), Decimal("18.00"))

    def test_subtotal_of_two_lines(self):
        lines = [
            {"unit_price": Decimal("10.00"), "quantity": 2},
            {"unit_price": Decimal("5.50"), "quantity": 4},
        ]
        self.assertEqual(subtotal(lines), Decimal("42.00"))


if __name__ == "__main__":
    unittest.main()
