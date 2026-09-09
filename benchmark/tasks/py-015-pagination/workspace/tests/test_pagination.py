import unittest

from src.pagination import paginate


class PaginationTest(unittest.TestCase):
    def test_first_page(self):
        result = paginate(range(25), page=1, per_page=10)
        self.assertEqual(result["items"], list(range(10)))

    def test_page_metadata(self):
        result = paginate(range(25), page=2, per_page=10)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["total_items"], 25)

    def test_has_prev(self):
        self.assertFalse(paginate(range(25), page=1, per_page=10)["has_prev"])
        self.assertTrue(paginate(range(25), page=2, per_page=10)["has_prev"])


if __name__ == "__main__":
    unittest.main()
