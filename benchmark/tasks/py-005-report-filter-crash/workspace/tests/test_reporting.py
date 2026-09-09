import unittest

from src.api import sales_report
from src.errors import UnknownFilterError


class ReportingTest(unittest.TestCase):
    def test_filtered_report_is_built(self):
        report = sales_report(["hardware"])
        self.assertAlmostEqual(report["total"], 200.0)
        self.assertEqual([row["category"] for row in report["rows"]], ["hardware"])

    def test_rows_are_sorted_by_amount_descending(self):
        report = sales_report(["large"])
        amounts = [row["amount"] for row in report["rows"]]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_unknown_filter_is_rejected(self):
        with self.assertRaises(UnknownFilterError):
            sales_report(["nope"])


if __name__ == "__main__":
    unittest.main()
