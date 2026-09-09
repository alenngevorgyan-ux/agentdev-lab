"""Hidden acceptance tests for the unassigned-account data loss."""

import inspect
import unittest

from src.pipeline.helpers import UNASSIGNED
from src.pipeline.registry import stage_names
from src.pipeline.runner import run_pipeline

MIXED = [
    {"id": "1", "account": "EU-Alpha", "amount": "100"},
    {"id": "2", "account": None, "amount": "50"},
    {"id": "3", "amount": "25"},
    {"id": "4", "account": "   ", "amount": "10"},
    {"id": "5", "account": "US-Beta", "amount": "2000"},
]


class UnassignedAccountTest(unittest.TestCase):
    def setUp(self):
        self.records, self.context = run_pipeline(MIXED)

    def test_no_record_is_lost(self):
        self.assertEqual(len(self.records), 5)
        self.assertEqual(len(self.context["output"]), 5)

    def test_unassigned_group_exists(self):
        self.assertIn(UNASSIGNED, self.context["groups"])

    def test_all_unassigned_records_are_grouped_together(self):
        self.assertEqual(len(self.context["groups"][UNASSIGNED]), 3)

    def test_unassigned_records_are_totalled(self):
        self.assertAlmostEqual(self.context["totals"][UNASSIGNED], 85.0)

    def test_named_accounts_are_unaffected(self):
        self.assertAlmostEqual(self.context["totals"]["eu-alpha"], 100.0)
        self.assertAlmostEqual(self.context["totals"]["us-beta"], 2000.0)

    def test_output_carries_the_unassigned_key(self):
        keys = [row["account_key"] for row in self.context["output"]]
        self.assertEqual(keys.count(UNASSIGNED), 3)

    def test_output_validation_passes(self):
        self.assertTrue(self.context["validated"])


class FixLocationTest(unittest.TestCase):
    """The defect is in a shared helper; the fix belongs there, once."""

    def test_coerce_key_never_returns_none(self):
        from src.pipeline.helpers import coerce_key

        self.assertEqual(coerce_key({}, "account"), UNASSIGNED)
        self.assertEqual(coerce_key({"account": None}, "account"), UNASSIGNED)
        self.assertEqual(coerce_key({"account": "  "}, "account"), UNASSIGNED)

    def test_keyed_yields_every_record(self):
        from src.pipeline.helpers import keyed

        records = [{"account": "a"}, {"account": None}, {}]
        self.assertEqual(len(list(keyed(records, "account"))), 3)

    def test_stages_were_not_individually_patched(self):
        import src.pipeline.stages.s09_group_by_account as grouping
        import src.pipeline.stages.s14_aggregate_totals as totals

        for module in (grouping, totals):
            source = inspect.getsource(module)
            self.assertNotIn(
                UNASSIGNED,
                source,
                f"{module.__name__} should rely on the shared helper, not repeat the fallback",
            )

    def test_stage_order_is_unchanged(self):
        self.assertEqual(len(stage_names()), 16)
        self.assertEqual(stage_names()[0], "s01_strip_whitespace")
        self.assertEqual(stage_names()[-1], "s16_validate_output")


if __name__ == "__main__":
    unittest.main()
