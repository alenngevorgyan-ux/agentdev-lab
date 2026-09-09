"""Hidden acceptance tests for the empty-filter crash."""

import unittest

from src.api import sales_report
from src.models import Sale
from src.reporting import build_report
from src.storage import SalesRepository


class EmptyFilterTest(unittest.TestCase):
    def test_no_filters_covers_every_record(self):
        report = sales_report([])
        self.assertAlmostEqual(report["total"], 500.0)
        self.assertEqual(len(report["rows"]), 3)

    def test_shares_sum_to_one(self):
        report = sales_report([])
        self.assertAlmostEqual(sum(row["share"] for row in report["rows"]), 1.0, places=6)

    def test_empty_result_set_does_not_crash(self):
        empty = SalesRepository([])
        report = build_report(empty, [])
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["rows"], [])

    def test_filters_matching_nothing_report_zero(self):
        repository = SalesRepository([Sale("x", "services", "us", 10.0)])
        report = build_report(repository, ["eu-only"])
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["rows"], [])

    def test_zero_amount_rows_report_zero_share(self):
        repository = SalesRepository([Sale("x", "services", "eu", 0.0)])
        report = build_report(repository, [])
        self.assertEqual(report["rows"][0]["share"], 0.0)

    def test_filters_are_echoed_back(self):
        self.assertEqual(sales_report(["hardware"])["filters"], ["hardware"])


if __name__ == "__main__":
    unittest.main()
