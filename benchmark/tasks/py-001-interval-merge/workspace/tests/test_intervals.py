import unittest

from src.intervals import merge_intervals


class MergeIntervalsTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])

    def test_single(self):
        self.assertEqual(merge_intervals([[1, 4]]), [[1, 4]])

    def test_disjoint_stay_separate(self):
        self.assertEqual(merge_intervals([[1, 2], [5, 6]]), [[1, 2], [5, 6]])

    def test_overlapping_merge(self):
        self.assertEqual(merge_intervals([[1, 4], [2, 6]]), [[1, 6]])

    def test_touching_boundaries_merge(self):
        self.assertEqual(merge_intervals([[1, 3], [3, 5]]), [[1, 5]])

    def test_unsorted_input(self):
        self.assertEqual(merge_intervals([[5, 6], [1, 3], [2, 4]]), [[1, 4], [5, 6]])

    def test_contained_interval(self):
        self.assertEqual(merge_intervals([[1, 10], [2, 3]]), [[1, 10]])

    def test_input_is_not_mutated(self):
        data = [[3, 4], [1, 2]]
        merge_intervals(data)
        self.assertEqual(data, [[3, 4], [1, 2]])


if __name__ == "__main__":
    unittest.main()
