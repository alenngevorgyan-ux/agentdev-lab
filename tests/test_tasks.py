import json
import unittest

from benchmark.tasks import TaskSpecError, load_task, load_tasks, select_tasks
from tests.helpers import TempDirTestCase, write_task


class LoadTaskTest(TempDirTestCase):
    def test_valid_task_loads(self):
        task = self.make_task()
        self.assertEqual(task.id, "demo-task")
        self.assertEqual(task.protected_paths, ("tests",))
        self.assertEqual(task.verify.timeout_sec, 60)
        self.assertTrue(task.has_reference_solution)

    def _corrupt(self, key, value, task_id="demo-task"):
        directory = write_task(self.tmp / "tasks", task_id=task_id)
        spec = json.loads((directory / "task.json").read_text())
        if value is None:
            spec.pop(key)
        else:
            spec[key] = value
        (directory / "task.json").write_text(json.dumps(spec))
        return directory

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("protected_path", ["tests"]))

    def test_missing_required_key_is_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("verify", None))

    def test_empty_protected_paths_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("protected_paths", []))

    def test_protected_path_escaping_workspace_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("protected_paths", ["../../etc"]))

    def test_nonexistent_protected_path_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("protected_paths", ["tests-typo"]))

    def test_id_must_match_directory_name(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("id", "something-else"))

    def test_invalid_category_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("category", "vibes"))

    def test_zero_timeout_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("verify", {"command": ["true"], "timeout_sec": 0}))

    def test_empty_verify_command_rejected(self):
        with self.assertRaises(TaskSpecError):
            load_task(self._corrupt("verify", {"command": [], "timeout_sec": 10}))

    def test_invalid_json_rejected(self):
        directory = write_task(self.tmp / "tasks")
        (directory / "task.json").write_text("{not json")
        with self.assertRaises(TaskSpecError):
            load_task(directory)


class FingerprintTest(TempDirTestCase):
    def test_fingerprint_is_stable(self):
        task = self.make_task()
        self.assertEqual(task.spec_fingerprint(), task.spec_fingerprint())

    def test_fixture_edit_changes_fingerprint(self):
        task = self.make_task()
        before = task.spec_fingerprint()
        (task.workspace_path / "src" / "thing.py").write_text("def answer():\n    return 1\n")
        self.assertNotEqual(before, task.spec_fingerprint())

    def test_prompt_edit_changes_fingerprint(self):
        directory = write_task(self.tmp / "tasks")
        before = load_task(directory).spec_fingerprint()
        spec = json.loads((directory / "task.json").read_text())
        spec["prompt"] = "A different prompt entirely."
        (directory / "task.json").write_text(json.dumps(spec))
        self.assertNotEqual(before, load_task(directory).spec_fingerprint())


class RegistryTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.tasks_dir = self.tmp / "tasks"
        write_task(self.tasks_dir, task_id="task-a")
        write_task(self.tasks_dir, task_id="task-b")

    def test_load_tasks_sorted(self):
        self.assertEqual([task.id for task in load_tasks(self.tasks_dir)], ["task-a", "task-b"])

    def test_select_all_when_empty_selection(self):
        self.assertEqual(len(select_tasks((), self.tasks_dir)), 2)

    def test_select_specific(self):
        self.assertEqual([t.id for t in select_tasks(("task-b",), self.tasks_dir)], ["task-b"])

    def test_unknown_task_id_rejected(self):
        with self.assertRaises(TaskSpecError):
            select_tasks(("task-z",), self.tasks_dir)


class RealTaskRegistryTest(unittest.TestCase):
    """The shipped task registry must always be well-formed."""

    def test_registry_loads(self):
        tasks = load_tasks()
        self.assertTrue(tasks, "the shipped registry must contain at least one task")
        for task in tasks:
            with self.subTest(task=task.id):
                self.assertTrue(task.has_reference_solution)
                self.assertTrue(task.protected_paths)
                self.assertTrue(task.prompt.strip())


if __name__ == "__main__":
    unittest.main()
