import unittest

from benchmark import hashing
from tests.helpers import TempDirTestCase


class HashTreeTest(TempDirTestCase):
    def _tree(self, name: str) -> object:
        root = self.tmp / name
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "a.py").write_text("print('a')\n")
        (root / "b.txt").write_text("b\n")
        return root

    def test_identical_trees_hash_identically(self):
        self.assertEqual(hashing.hash_tree(self._tree("x")), hashing.hash_tree(self._tree("y")))

    def test_content_change_changes_hash(self):
        tree = self._tree("x")
        before = hashing.hash_tree(tree)
        (tree / "b.txt").write_text("different\n")
        self.assertNotEqual(before, hashing.hash_tree(tree))

    def test_rename_changes_hash(self):
        tree = self._tree("x")
        before = hashing.hash_tree(tree)
        (tree / "b.txt").rename(tree / "c.txt")
        self.assertNotEqual(before, hashing.hash_tree(tree))

    def test_pycache_is_ignored(self):
        tree = self._tree("x")
        before = hashing.hash_tree(tree)
        cache = tree / "pkg" / "__pycache__"
        cache.mkdir()
        (cache / "a.cpython-311.pyc").write_bytes(b"\x00\x01")
        self.assertEqual(before, hashing.hash_tree(tree))


class HashPathsTest(TempDirTestCase):
    def test_deleting_a_protected_path_changes_the_digest(self):
        root = self.tmp / "ws"
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "test_x.py").write_text("assert True\n")
        before = hashing.hash_paths(root, ["tests"])
        (root / "tests" / "test_x.py").unlink()
        self.assertNotEqual(before, hashing.hash_paths(root, ["tests"]))

    def test_missing_path_is_recorded_not_skipped(self):
        root = self.tmp / "ws"
        root.mkdir()
        self.assertNotEqual(hashing.hash_paths(root, ["gone"]), hashing.hash_paths(root, []))

    def test_unprotected_edits_do_not_change_the_digest(self):
        root = self.tmp / "ws"
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "test_x.py").write_text("assert True\n")
        (root / "src.py").write_text("x = 1\n")
        before = hashing.hash_paths(root, ["tests"])
        (root / "src.py").write_text("x = 2\n")
        self.assertEqual(before, hashing.hash_paths(root, ["tests"]))


class HashJsonTest(unittest.TestCase):
    def test_key_order_is_canonical(self):
        self.assertEqual(hashing.hash_json({"a": 1, "b": 2}), hashing.hash_json({"b": 2, "a": 1}))

    def test_value_change_changes_digest(self):
        self.assertNotEqual(hashing.hash_json({"a": 1}), hashing.hash_json({"a": 2}))


if __name__ == "__main__":
    unittest.main()
