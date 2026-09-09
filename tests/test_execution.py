import os
import sys
import unittest

from benchmark.execution import TIMEOUT_EXIT_CODE, build_env, resolve_command, run_command
from tests.helpers import TempDirTestCase


class RunCommandTest(TempDirTestCase):
    def test_successful_command(self):
        result = run_command([sys.executable, "-c", "print('hi')"], cwd=self.tmp, timeout_sec=30)
        self.assertTrue(result.ok)
        self.assertIn("hi", result.stdout)

    def test_nonzero_exit_is_captured(self):
        result = run_command([sys.executable, "-c", "raise SystemExit(3)"], cwd=self.tmp, timeout_sec=30)
        self.assertEqual(result.exit_code, 3)
        self.assertFalse(result.ok)

    def test_stderr_is_captured(self):
        result = run_command(
            [sys.executable, "-c", "import sys; sys.stderr.write('boom')"], cwd=self.tmp, timeout_sec=30
        )
        self.assertIn("boom", result.stderr)

    def test_timeout_is_reported_and_killed(self):
        result = run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"], cwd=self.tmp, timeout_sec=1
        )
        self.assertTrue(result.timed_out)
        self.assertEqual(result.exit_code, TIMEOUT_EXIT_CODE)
        self.assertLess(result.duration_ms, 20_000)

    def test_runs_in_the_given_directory(self):
        (self.tmp / "marker.txt").write_text("x")
        result = run_command(
            [sys.executable, "-c", "import os; print(os.path.exists('marker.txt'))"],
            cwd=self.tmp,
            timeout_sec=30,
        )
        self.assertIn("True", result.stdout)

    def test_missing_binary_reports_127(self):
        result = run_command(["definitely-not-a-real-binary-xyz"], cwd=self.tmp, timeout_sec=10)
        self.assertEqual(result.exit_code, 127)

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(ValueError):
            run_command([sys.executable, "-c", "pass"], cwd=self.tmp, timeout_sec=0)

    def test_stdin_is_delivered(self):
        result = run_command(
            [sys.executable, "-c", "import sys; print(sys.stdin.read().strip().upper())"],
            cwd=self.tmp,
            timeout_sec=30,
            stdin_text="hello",
        )
        self.assertIn("HELLO", result.stdout)

    def test_output_is_truncated(self):
        result = run_command(
            [sys.executable, "-c", "print('x' * 2_000_000)"], cwd=self.tmp, timeout_sec=60
        )
        self.assertIn("truncated", result.stdout)


class EnvironmentTest(TempDirTestCase):
    def test_pythonpath_is_not_leaked(self):
        os.environ["PYTHONPATH"] = "/nonsense"
        self.addCleanup(os.environ.pop, "PYTHONPATH", None)
        self.assertNotIn("PYTHONPATH", build_env())

    def test_unrelated_variables_are_dropped(self):
        os.environ["AGENTDEV_TEST_LEAK"] = "1"
        self.addCleanup(os.environ.pop, "AGENTDEV_TEST_LEAK", None)
        self.assertNotIn("AGENTDEV_TEST_LEAK", build_env())

    def test_hash_seed_is_pinned(self):
        self.assertEqual(build_env()["PYTHONHASHSEED"], "0")

    def test_sandbox_marker_is_set(self):
        self.assertEqual(build_env()["AGENTDEV_SANDBOX"], "1")


class ResolveCommandTest(unittest.TestCase):
    def test_python3_resolves_to_running_interpreter(self):
        self.assertEqual(resolve_command(["python3", "-V"])[0], sys.executable)

    def test_other_commands_are_untouched(self):
        self.assertEqual(resolve_command(["echo", "hi"]), ("echo", "hi"))


if __name__ == "__main__":
    unittest.main()
