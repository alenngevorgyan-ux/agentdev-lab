"""Guards against recording a non-starting agent as a capability failure."""

import os
import unittest

from benchmark.adapters.claude_code import ClaudeCodeAdapter
from benchmark.runner import run_attempt
from benchmark.scoring import Status
from tests.helpers import TempDirTestCase


class NotReadyDetectionTest(unittest.TestCase):
    def setUp(self):
        self.adapter = ClaudeCodeAdapter()

    def test_login_prompt_is_detected(self):
        self.assertIn("never started", self.adapter._not_ready_reason("Not logged in · Please run /login"))

    def test_invalid_key_is_detected(self):
        self.assertTrue(self.adapter._not_ready_reason("error: Invalid API key"))

    def test_exhausted_credit_is_detected(self):
        self.assertTrue(self.adapter._not_ready_reason("Your credit balance is too low"))

    def test_ordinary_output_is_not_flagged(self):
        self.assertEqual(self.adapter._not_ready_reason("Edited src/intervals.py"), "")

    def test_detection_is_case_insensitive(self):
        self.assertTrue(self.adapter._not_ready_reason("NOT LOGGED IN"))


class PreflightTest(TempDirTestCase):
    def test_missing_binary_blocks(self):
        adapter = ClaudeCodeAdapter(binary="definitely-not-a-real-binary-xyz")
        self.assertIn("not found", adapter.preflight())

    def test_credentials_in_environment_satisfy_preflight(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-value"
        self.addCleanup(os.environ.pop, "ANTHROPIC_API_KEY", None)
        adapter = ClaudeCodeAdapter()
        if adapter.available():
            self.assertEqual(adapter.preflight(), "")

    def test_blocked_preflight_yields_agent_error_not_a_failed_task(self):
        """A misconfigured agent must never be scored as an agent that tried and failed."""
        adapter = ClaudeCodeAdapter(binary="definitely-not-a-real-binary-xyz")
        task = self.make_task()
        result = run_attempt(task, adapter, sandbox_root=self.tmp / "sb")
        self.assertIs(result.status, Status.AGENT_ERROR)
        self.assertIsNone(result.verification)


class PromptTest(TempDirTestCase):
    def test_prompt_names_the_protected_paths(self):
        task = self.make_task()
        prompt = ClaudeCodeAdapter().build_prompt(task)
        self.assertIn("tests", prompt)
        self.assertIn(task.prompt.strip(), prompt)


if __name__ == "__main__":
    unittest.main()
