"""Secret hygiene: credentials must not survive into anything the lab stores."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from benchmark import config
from benchmark.execution import run_command
from benchmark.export import build_export
from benchmark.integrity import check_recorded_results
from benchmark.redaction import PLACEHOLDER, contains_secret, redact, secret_environment_values
from benchmark.storage import ResultsStore
from tests.helpers import TempDirTestCase
from tests.test_storage import FakeTask, attempt_fields

FAKE_KEY = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 2


class PatternRedactionTest(unittest.TestCase):
    def test_anthropic_key_is_masked(self):
        self.assertNotIn(FAKE_KEY, redact(f"using {FAKE_KEY} now"))

    def test_openai_key_is_masked(self):
        text = "sk-proj-" + "x" * 30
        self.assertNotIn(text, redact(text))

    def test_github_token_is_masked(self):
        text = "ghp_" + "b" * 30
        self.assertNotIn(text, redact(text))

    def test_aws_access_key_is_masked(self):
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redact("id AKIAIOSFODNN7EXAMPLE end"))

    def test_bearer_header_is_masked(self):
        token = "abcdefghij0123456789ABCDEF"
        self.assertNotIn(token, redact(f"Authorization: Bearer {token}"))

    def test_jwt_is_masked(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"
        self.assertNotIn(jwt, redact(jwt))

    def test_private_key_block_is_masked(self):
        block = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"
        self.assertNotIn("MIIabc", redact(block))

    def test_named_assignment_is_masked(self):
        out = redact('ANTHROPIC_API_KEY=hunter2hunter2hunter2')
        self.assertNotIn("hunter2hunter2hunter2", out)
        self.assertIn("ANTHROPIC_API_KEY", out)

    def test_json_style_assignment_is_masked(self):
        out = redact('{"api_key": "abcd1234abcd1234"}')
        self.assertNotIn("abcd1234abcd1234", out)

    def test_ordinary_text_survives(self):
        text = "Ran 12 tests in 0.4s\nOK\nEdited src/intervals.py"
        self.assertEqual(redact(text), text)

    def test_short_values_are_not_over_masked(self):
        self.assertIn("token=abc", redact("token=abc"))

    def test_empty_text(self):
        self.assertEqual(redact(""), "")


class EnvironmentValueRedactionTest(unittest.TestCase):
    def setUp(self):
        self.value = "totally-opaque-value-9876543210"
        os.environ["AGENTDEV_TEST_API_KEY"] = self.value
        self.addCleanup(os.environ.pop, "AGENTDEV_TEST_API_KEY", None)

    def test_secret_named_variable_is_collected(self):
        self.assertIn(self.value, secret_environment_values())

    def test_value_is_masked_wherever_it_appears(self):
        self.assertNotIn(self.value, redact(f"prefix {self.value} suffix"))

    def test_non_secret_variable_is_not_collected(self):
        os.environ["AGENTDEV_TEST_PLAIN"] = "not-a-secret-value"
        self.addCleanup(os.environ.pop, "AGENTDEV_TEST_PLAIN", None)
        self.assertNotIn("not-a-secret-value", secret_environment_values())

    def test_contains_secret_detects_the_raw_value(self):
        self.assertTrue(contains_secret(f"leak {self.value}"))
        self.assertFalse(contains_secret("nothing to see here"))


class CaptureChokePointTest(TempDirTestCase):
    """Redaction happens where output enters the harness, not per consumer."""

    def test_subprocess_output_is_redacted(self):
        result = run_command(
            [sys.executable, "-c", f"print('key {FAKE_KEY}')"],
            cwd=self.tmp,
            timeout_sec=30,
        )
        self.assertNotIn(FAKE_KEY, result.stdout)
        self.assertIn(PLACEHOLDER, result.stdout)

    def test_stderr_is_redacted_too(self):
        result = run_command(
            [sys.executable, "-c", f"import sys; sys.stderr.write('{FAKE_KEY}')"],
            cwd=self.tmp,
            timeout_sec=30,
        )
        self.assertNotIn(FAKE_KEY, result.stderr)

    def test_environment_secret_echoed_by_a_child_is_redacted(self):
        secret = "child-echoed-secret-1234567890"
        os.environ["AGENTDEV_CHILD_TOKEN"] = secret
        self.addCleanup(os.environ.pop, "AGENTDEV_CHILD_TOKEN", None)
        result = run_command(
            [sys.executable, "-c", "import os; print(os.environ.get('AGENTDEV_CHILD_TOKEN'))"],
            cwd=self.tmp,
            timeout_sec=30,
            env={"PATH": os.environ["PATH"], "AGENTDEV_CHILD_TOKEN": secret},
        )
        self.assertNotIn(secret, result.stdout)


class StoredEvidenceTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)
        self.store.register_tasks([FakeTask()])
        self.run_id, _ = self.store.start_run(
            adapter="noop", agent="noop", adapter_version="v1", attempts_per_task=1,
            run_kind="control",
        )

    def test_integrity_audit_flags_a_stored_secret(self):
        attempt_id = self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        self.store.record_logs(attempt_id, {"agent_stdout": f"leaked {FAKE_KEY}"})
        report = check_recorded_results(self.store)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("credential-shaped" in check.name or "credential-shaped" in check.detail
                for check in report.checks if not check.ok)
        )

    def test_clean_evidence_passes_the_audit(self):
        attempt_id = self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        self.store.record_logs(attempt_id, {"agent_stdout": "Ran 3 tests\nOK"})
        checks = {c.name: c for c in check_recorded_results(self.store).checks}
        self.assertTrue(checks["no credential-shaped value is stored"].ok)

    def test_export_carries_no_secret(self):
        attempt_id = self.store.record_attempt(**attempt_fields(run_id=self.run_id))
        self.store.record_logs(attempt_id, {"agent_stdout": redact(f"key {FAKE_KEY}")})
        import json

        self.assertNotIn(FAKE_KEY, json.dumps(build_export(self.store), default=str))


class TrackedFilesTest(unittest.TestCase):
    """Nothing credential-shaped may be committed."""

    ALLOWED = {
        "tests/test_redaction.py",   # constructs deliberately fake credentials
        "benchmark/redaction.py",    # contains the detection patterns themselves
    }

    def test_no_tracked_file_contains_a_credential(self):
        listing = subprocess.run(
            ["git", "ls-files"],
            cwd=str(config.REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if listing.returncode != 0:
            self.skipTest("not a git checkout")

        offenders = []
        for relative in listing.stdout.split():
            if relative in self.ALLOWED:
                continue
            path = config.REPO_ROOT / relative
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if contains_secret(text, env={}):
                offenders.append(relative)
        self.assertEqual(offenders, [], f"credential-shaped content in: {offenders}")

    def test_generated_databases_are_not_tracked(self):
        listing = subprocess.run(
            ["git", "ls-files"],
            cwd=str(config.REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if listing.returncode != 0:
            self.skipTest("not a git checkout")
        tracked = listing.stdout.split()
        self.assertFalse([p for p in tracked if p.endswith((".sqlite3", ".env"))])


if __name__ == "__main__":
    unittest.main()


class RedactionPerformanceTest(unittest.TestCase):
    """Captured output is attacker-influenced, so redaction must stay linear.

    Unbounded quantifiers made a large log take minutes, which is a denial of
    service in the measurement path: an agent that prints enough noise would
    stall the harness that is grading it.
    """

    def test_a_large_plain_log_is_redacted_promptly(self):
        import time

        from benchmark.config import MAX_CAPTURED_BYTES

        blob = "x" * MAX_CAPTURED_BYTES
        started = time.monotonic()
        redact(blob)
        self.assertLess(time.monotonic() - started, 5.0)

    def test_a_realistic_log_with_a_secret_is_fast_and_masked(self):
        import time

        log = ("2026-09-09 running task step\n" * 4000) + FAKE_KEY
        started = time.monotonic()
        result = redact(log)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertNotIn(FAKE_KEY, result)

    def test_every_pattern_is_bounded(self):
        """An unbounded quantifier is what caused the hang; none may return."""
        from benchmark.redaction import _ASSIGNMENT, _PATTERNS

        for name, pattern in _PATTERNS:
            with self.subTest(pattern=name):
                self.assertNotRegex(pattern.pattern, r"\{\d+,\}", "unbounded quantifier")
        self.assertNotRegex(_ASSIGNMENT.pattern, r"\{\d+,\}")

    def test_a_long_run_of_word_characters_does_not_stall(self):
        import time

        started = time.monotonic()
        redact("token=" + "a" * 100_000)
        self.assertLess(time.monotonic() - started, 3.0)
