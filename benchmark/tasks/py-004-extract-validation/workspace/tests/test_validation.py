import unittest

from src.validation import ValidationError, validate_record


class ValidateRecordTest(unittest.TestCase):
    def test_returns_normalised_copy(self):
        record = {"id": " a1 ", "amount": "12.5"}
        result = validate_record(record, ("id", "amount"))
        self.assertEqual(result, {"id": "a1", "amount": 12.5})

    def test_does_not_mutate_input(self):
        record = {"id": " a1 ", "amount": "12.5"}
        validate_record(record, ("id", "amount"))
        self.assertEqual(record, {"id": " a1 ", "amount": "12.5"})

    def test_missing_field_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_record({"id": "a1"}, ("id", "amount"))
        self.assertIn("amount", str(ctx.exception))

    def test_empty_field_raises(self):
        with self.assertRaises(ValidationError):
            validate_record({"id": "   ", "amount": "1"}, ("id", "amount"))

    def test_non_numeric_amount_raises(self):
        with self.assertRaises(ValidationError):
            validate_record({"id": "a1", "amount": "twelve"}, ("id", "amount"))

    def test_amount_is_only_coerced_when_present(self):
        self.assertEqual(validate_record({"id": "a1"}, ("id",)), {"id": "a1"})

    def test_validation_error_is_a_value_error(self):
        self.assertTrue(issubclass(ValidationError, ValueError))


if __name__ == "__main__":
    unittest.main()
