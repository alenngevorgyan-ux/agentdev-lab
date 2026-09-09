import unittest

from src.pipeline.registry import stage_names
from src.pipeline.runner import run_pipeline

SAMPLE = [
    {"id": "1", "account": "EU-Alpha", "amount": "100", "email": "A@X.COM"},
    {"id": "2", "account": "eu-alpha ", "amount": "250.5"},
    {"id": "3", "account": "US-Beta", "amount": "2000"},
]


class PipelineTest(unittest.TestCase):
    def test_all_stages_registered(self):
        self.assertEqual(len(stage_names()), 16)

    def test_records_flow_through(self):
        records, context = run_pipeline(SAMPLE)
        self.assertEqual(len(records), 3)
        self.assertEqual(len(context["output"]), 3)

    def test_accounts_are_grouped(self):
        _, context = run_pipeline(SAMPLE)
        self.assertEqual(sorted(context["groups"]), ["eu-alpha", "us-beta"])

    def test_totals_are_computed(self):
        _, context = run_pipeline(SAMPLE)
        self.assertAlmostEqual(context["totals"]["eu-alpha"], 350.5)


if __name__ == "__main__":
    unittest.main()
