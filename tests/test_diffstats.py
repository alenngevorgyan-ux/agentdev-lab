import unittest

from benchmark.diffstats import compute_diff
from tests.helpers import TempDirTestCase


class DiffStatsTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.before = self.tmp / "before"
        self.after = self.tmp / "after"
        for root in (self.before, self.after):
            (root / "src").mkdir(parents=True)
            (root / "src" / "a.py").write_text("one\ntwo\nthree\n")
            (root / "README.md").write_text("hello\n")

    def test_identical_trees_have_no_diff(self):
        stats = compute_diff(self.before, self.after)
        self.assertTrue(stats.is_empty)
        self.assertEqual(stats.lines_changed, 0)

    def test_modified_file_is_counted(self):
        (self.after / "src" / "a.py").write_text("one\nTWO\nthree\n")
        stats = compute_diff(self.before, self.after)
        self.assertEqual(stats.files_changed, 1)
        self.assertEqual(stats.lines_added, 1)
        self.assertEqual(stats.lines_deleted, 1)
        self.assertEqual(stats.changed_paths, ("src/a.py",))

    def test_added_file(self):
        (self.after / "src" / "b.py").write_text("new\nfile\n")
        stats = compute_diff(self.before, self.after)
        self.assertEqual(stats.files_added, 1)
        self.assertEqual(stats.lines_added, 2)

    def test_deleted_file(self):
        (self.after / "README.md").unlink()
        stats = compute_diff(self.before, self.after)
        self.assertEqual(stats.files_deleted, 1)
        self.assertEqual(stats.lines_deleted, 1)

    def test_pycache_is_ignored(self):
        cache = self.after / "src" / "__pycache__"
        cache.mkdir()
        (cache / "a.pyc").write_bytes(b"\x00")
        self.assertTrue(compute_diff(self.before, self.after).is_empty)

    def test_touched_counts_expected_files(self):
        (self.after / "src" / "a.py").write_text("changed\n")
        stats = compute_diff(self.before, self.after)
        self.assertEqual(stats.touched(("src/a.py",)), 1)
        self.assertEqual(stats.touched(("src/never.py",)), 0)

    def test_binary_file_is_counted_without_line_stats(self):
        (self.after / "blob.bin").write_bytes(b"\x00\x01\x02\xff")
        stats = compute_diff(self.before, self.after)
        self.assertEqual(stats.files_added, 1)
        self.assertEqual(stats.lines_added, 0)


if __name__ == "__main__":
    unittest.main()
