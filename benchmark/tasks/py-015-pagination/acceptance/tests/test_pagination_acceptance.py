"""Hidden acceptance tests for pagination boundaries."""

import unittest

from src.pagination import paginate


class PageContentsTest(unittest.TestCase):
    def test_full_page_has_exactly_per_page_items(self):
        self.assertEqual(len(paginate(range(25), 1, 10)["items"]), 10)

    def test_last_partial_page_has_the_remainder(self):
        self.assertEqual(paginate(range(25), 3, 10)["items"], [20, 21, 22, 23, 24])

    def test_no_item_is_lost_across_pages(self):
        collected = []
        for page in range(1, 4):
            collected.extend(paginate(range(25), page, 10)["items"])
        self.assertEqual(collected, list(range(25)))

    def test_exact_division_has_no_empty_trailing_page(self):
        result = paginate(range(20), 2, 10)
        self.assertEqual(result["total_pages"], 2)
        self.assertEqual(len(result["items"]), 10)
        self.assertFalse(result["has_next"])

    def test_single_item_page(self):
        result = paginate([42], 1, 10)
        self.assertEqual(result["items"], [42])
        self.assertEqual(result["total_pages"], 1)


class BoundaryTest(unittest.TestCase):
    def test_page_past_the_end_is_empty_not_an_error(self):
        result = paginate(range(25), 99, 10)
        self.assertEqual(result["items"], [])
        self.assertFalse(result["has_next"])
        self.assertTrue(result["has_prev"])

    def test_empty_collection(self):
        result = paginate([], 1, 10)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_items"], 0)
        self.assertEqual(result["total_pages"], 1)
        self.assertFalse(result["has_next"])
        self.assertFalse(result["has_prev"])

    def test_has_next_on_the_first_of_three_pages(self):
        self.assertTrue(paginate(range(25), 1, 10)["has_next"])

    def test_zero_page_is_rejected(self):
        with self.assertRaises(ValueError):
            paginate(range(10), 0, 10)

    def test_negative_per_page_is_rejected(self):
        with self.assertRaises(ValueError):
            paginate(range(10), 1, -5)

    def test_per_page_larger_than_the_collection(self):
        result = paginate(range(3), 1, 100)
        self.assertEqual(result["items"], [0, 1, 2])
        self.assertEqual(result["total_pages"], 1)

    def test_structure_is_unchanged(self):
        self.assertEqual(
            set(paginate(range(5), 1, 2)),
            {"items", "page", "per_page", "total_items", "total_pages", "has_next", "has_prev"},
        )

    def test_generators_are_accepted(self):
        self.assertEqual(paginate((n for n in range(5)), 1, 2)["items"], [0, 1])


if __name__ == "__main__":
    unittest.main()
