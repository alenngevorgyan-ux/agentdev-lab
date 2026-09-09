"""Hidden acceptance tests pinning exact cent behaviour."""

import unittest
from decimal import Decimal

from src.invoicing import invoice_breakdown, invoice_total, tax_for
from src.money import round_money
from src.pricing import line_total, subtotal


class RoundingTest(unittest.TestCase):
    def test_round_money_returns_decimal(self):
        self.assertIsInstance(round_money(Decimal("1.005")), Decimal)

    def test_round_money_is_half_up_not_bankers(self):
        self.assertEqual(round_money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(round_money(Decimal("2.675")), Decimal("2.68"))
        self.assertEqual(round_money(Decimal("0.125")), Decimal("0.13"))

    def test_round_money_quantizes_to_two_places(self):
        self.assertEqual(str(round_money(Decimal("3"))), "3.00")


class LinePrecisionTest(unittest.TestCase):
    def test_rounding_happens_once_after_discount_and_quantity(self):
        # 0.335 * 3 = 1.005 at full precision -> 1.01. Rounding the unit price
        # first would give 0.34 * 3 = 1.02.
        self.assertEqual(line_total(Decimal("0.335"), 3), Decimal("1.01"))

    def test_percentage_discount_at_full_precision(self):
        # 19.99 * 0.85 = 16.9915 -> 16.99
        self.assertEqual(line_total(Decimal("19.99"), 1, 15), Decimal("16.99"))

    def test_many_small_lines_do_not_drift(self):
        lines = [{"unit_price": Decimal("0.07"), "quantity": 3} for _ in range(10)]
        self.assertEqual(subtotal(lines), Decimal("2.10"))

    def test_subtotal_sums_rounded_line_totals(self):
        lines = [
            {"unit_price": Decimal("0.335"), "quantity": 3},
            {"unit_price": Decimal("0.335"), "quantity": 3},
        ]
        self.assertEqual(subtotal(lines), Decimal("2.02"))


class InvoiceTest(unittest.TestCase):
    def setUp(self):
        self.lines = [
            {"unit_price": Decimal("19.99"), "quantity": 3, "discount_pct": 15},
            {"unit_price": Decimal("5.05"), "quantity": 7},
        ]

    def test_tax_is_computed_on_the_rounded_subtotal(self):
        net = subtotal(self.lines)
        self.assertEqual(invoice_total(self.lines, 20), net + tax_for(net, 20))

    def test_total_matches_the_breakdown_exactly(self):
        breakdown = invoice_breakdown(self.lines, 20)
        self.assertEqual(breakdown["subtotal"] + breakdown["tax"], breakdown["total"])
        self.assertEqual(invoice_total(self.lines, 20), breakdown["total"])

    def test_zero_tax_leaves_the_subtotal_untouched(self):
        self.assertEqual(invoice_total(self.lines, 0), subtotal(self.lines))

    def test_empty_invoice(self):
        self.assertEqual(invoice_total([], 20), Decimal("0.00"))

    def test_no_floats_leak_into_results(self):
        breakdown = invoice_breakdown(self.lines, 19)
        for value in breakdown.values():
            self.assertIsInstance(value, Decimal)


if __name__ == "__main__":
    unittest.main()
