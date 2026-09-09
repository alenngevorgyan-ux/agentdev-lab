import unittest

from src.invoices import process_invoices
from src.orders import process_orders


class OrdersTest(unittest.TestCase):
    def test_valid_order_is_processed(self):
        processed, rejected = process_orders([{"id": " o1 ", "customer": "ACME", "amount": "10"}])
        self.assertEqual(rejected, [])
        self.assertEqual(processed, [{"id": "o1", "customer": "ACME", "amount": 10.0}])

    def test_missing_field_is_rejected(self):
        processed, rejected = process_orders([{"id": "o1", "customer": "ACME"}])
        self.assertEqual(processed, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("amount", rejected[0][1])

    def test_empty_field_is_rejected(self):
        _, rejected = process_orders([{"id": "  ", "customer": "ACME", "amount": "1"}])
        self.assertEqual(len(rejected), 1)

    def test_bad_amount_is_rejected(self):
        _, rejected = process_orders([{"id": "o1", "customer": "ACME", "amount": "ten"}])
        self.assertEqual(len(rejected), 1)

    def test_input_records_are_not_mutated(self):
        record = {"id": " o1 ", "customer": "ACME", "amount": "10"}
        process_orders([record])
        self.assertEqual(record, {"id": " o1 ", "customer": "ACME", "amount": "10"})


class InvoicesTest(unittest.TestCase):
    def test_valid_invoice_is_processed(self):
        processed, rejected = process_invoices([{"id": " i1 ", "vendor": "ACME", "amount": "10"}])
        self.assertEqual(rejected, [])
        self.assertEqual(processed, [{"id": "i1", "vendor": "ACME", "amount": 10.0}])

    def test_missing_field_is_rejected(self):
        _, rejected = process_invoices([{"id": "i1", "vendor": "ACME"}])
        self.assertEqual(len(rejected), 1)

    def test_empty_field_is_rejected_after_the_drift_is_fixed(self):
        """The invoice copy had drifted and never checked for empty fields."""
        processed, rejected = process_invoices([{"id": "  ", "vendor": "ACME", "amount": "1"}])
        self.assertEqual(processed, [])
        self.assertEqual(len(rejected), 1)

    def test_both_modules_share_one_implementation(self):
        import src.invoices as invoices
        import src.orders as orders
        import src.validation as validation

        self.assertIs(getattr(orders, "validate_record", None), validation.validate_record)
        self.assertIs(getattr(invoices, "validate_record", None), validation.validate_record)


if __name__ == "__main__":
    unittest.main()
