"""Hidden acceptance tests.

The ticket was ambiguous, so these tests pin only the invariants that any
defensible interpretation must satisfy. They deliberately do not dictate a
delimiter beyond comma, a quoting style beyond correctness, or whether the
output ends with a newline -- only that the result parses back losslessly.
"""

import csv
import io
import unittest

from src.export import export_csv
from src.reporting import build_rows


def parse(text):
    return list(csv.reader(io.StringIO(text)))


class CsvContractTest(unittest.TestCase):
    def setUp(self):
        self.rows = build_rows()
        self.text = export_csv(self.rows)
        self.parsed = parse(self.text)

    def test_header_names_every_column(self):
        self.assertEqual(self.parsed[0], list(self.rows[0].keys()))

    def test_one_line_per_row(self):
        self.assertEqual(len(self.parsed), len(self.rows) + 1)

    def test_input_order_is_preserved(self):
        dates = [row[0] for row in self.parsed[1:]]
        self.assertEqual(dates, [row["date"] for row in self.rows])

    def test_commas_are_quoted_and_survive_a_round_trip(self):
        self.assertEqual(self.parsed[1][1], "Acme, Inc.")

    def test_embedded_quotes_survive_a_round_trip(self):
        self.assertEqual(self.parsed[2][1], 'Bob "The Builder" Ltd')

    def test_embedded_newlines_survive_a_round_trip(self):
        self.assertEqual(self.parsed[3][1], "Zeta\nHoldings")

    def test_empty_values_are_preserved(self):
        self.assertEqual(self.parsed[1][3], "")

    def test_record_terminators_are_consistent(self):
        """One terminator style for every record.

        A newline inside a quoted field is legitimate, so this counts record
        terminators rather than raw newlines.
        """
        records = len(self.parsed)
        crlf = self.text.count("\r\n")
        self.assertIn(
            crlf,
            (0, records),
            "records must all end with the same terminator",
        )
        self.assertEqual(self.text.count("\r"), crlf, "no bare carriage returns")


class EdgeCaseTest(unittest.TestCase):
    def test_empty_input_still_emits_a_header(self):
        text = export_csv([])
        parsed = parse(text)
        self.assertGreaterEqual(len(parsed), 1)
        self.assertTrue(parsed[0], "the header row must not be empty")

    def test_single_row(self):
        parsed = parse(export_csv([{"a": "1", "b": "2"}]))
        self.assertEqual(parsed[0], ["a", "b"])
        self.assertEqual(parsed[1], ["1", "2"])

    def test_interpretation_choices_are_documented(self):
        import src.export as module

        self.assertTrue(
            (module.__doc__ or "").strip(),
            "document the choices the ticket left open in the module docstring",
        )
        self.assertGreater(len((module.__doc__ or "").split()), 15)


if __name__ == "__main__":
    unittest.main()
