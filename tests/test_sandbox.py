import unittest

from benchmark.sandbox import create_sandbox
from tests.helpers import TempDirTestCase


class SandboxTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.task = self.make_task()
        self.root = self.tmp / "sandboxes"

    def sandbox(self, keep=False):
        sandbox = create_sandbox(self.task, keep=keep, root=self.root)
        self.addCleanup(sandbox.cleanup)
        return sandbox

    def test_workspace_is_copied(self):
        sandbox = self.sandbox()
        self.assertTrue((sandbox.path / "src" / "thing.py").is_file())
        self.assertTrue((sandbox.path / "tests" / "test_thing.py").is_file())

    def test_sandboxes_are_isolated_from_each_other(self):
        first, second = self.sandbox(), self.sandbox()
        self.assertNotEqual(first.path, second.path)
        (first.path / "src" / "thing.py").write_text("changed\n")
        self.assertNotEqual(
            (first.path / "src" / "thing.py").read_text(),
            (second.path / "src" / "thing.py").read_text(),
        )

    def test_editing_a_sandbox_never_touches_the_fixture(self):
        original = (self.task.workspace_path / "src" / "thing.py").read_text()
        sandbox = self.sandbox()
        (sandbox.path / "src" / "thing.py").write_text("mutated\n")
        self.assertEqual((self.task.workspace_path / "src" / "thing.py").read_text(), original)

    def test_cleanup_removes_the_directory(self):
        sandbox = create_sandbox(self.task, root=self.root)
        path = sandbox.path
        sandbox.cleanup()
        self.assertFalse(path.exists())

    def test_keep_preserves_the_directory(self):
        sandbox = create_sandbox(self.task, keep=True, root=self.root)
        sandbox.cleanup()
        self.assertTrue(sandbox.path.exists())

    def test_context_manager_cleans_up(self):
        with create_sandbox(self.task, root=self.root) as sandbox:
            path = sandbox.path
        self.assertFalse(path.exists())

    def test_protected_snapshot_detects_test_edits(self):
        sandbox = self.sandbox()
        before = sandbox.snapshot_protected()
        (sandbox.path / "tests" / "test_thing.py").write_text("# gutted\n")
        self.assertNotEqual(before, sandbox.snapshot_protected())

    def test_protected_snapshot_ignores_source_edits(self):
        sandbox = self.sandbox()
        before = sandbox.snapshot_protected()
        (sandbox.path / "src" / "thing.py").write_text("def answer():\n    return 42\n")
        self.assertEqual(before, sandbox.snapshot_protected())

    def test_apply_overlay_writes_solution_files(self):
        sandbox = self.sandbox()
        written = sandbox.apply_overlay(self.task.solution_path)
        self.assertEqual(written, ["src/thing.py"])
        self.assertIn("42", (sandbox.path / "src" / "thing.py").read_text())

    def test_apply_missing_overlay_raises(self):
        sandbox = self.sandbox()
        with self.assertRaises(FileNotFoundError):
            sandbox.apply_overlay(self.tmp / "nope")


if __name__ == "__main__":
    unittest.main()
