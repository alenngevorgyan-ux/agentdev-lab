import unittest

from src.export import export_csv
from src.reporting import build_rows


class ExportTest(unittest.TestCase):
    def test_returns_text(self):
        self.assertIsInstance(export_csv(build_rows()), str)

    def test_header_is_first(self):
        first_line = export_csv(build_rows()).splitlines()[0]
        self.assertIn("date", first_line)
        self.assertIn("customer", first_line)


if __name__ == "__main__":
    unittest.main()
