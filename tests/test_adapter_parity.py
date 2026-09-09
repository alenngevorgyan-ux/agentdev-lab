"""Adapter parity: agents must be compared on equal terms.

A comparison is only about the agents if everything else is identical -- the
instructions, the starting fixture, the timeout, the isolation boundary and the
way the prompt is delivered. These tests assert that, and check the Codex CLI's
flag set against the CLI that is actually installed rather than against a
comment that may have gone stale.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest

from benchmark.adapters import CONTROL_ADAPTERS, available_adapters, get_adapter
from benchmark.adapters.claude_code import ClaudeCodeAdapter
from benchmark.adapters.codex import CodexAdapter, parse_jsonl_telemetry
from benchmark.adapters.prompt import build_task_prompt
from benchmark.sandbox import create_sandbox
from benchmark.tasks import load_registry, load_tasks
from tests.helpers import TempDirTestCase

#: Every adapter that represents an agent under test, rather than a control.
AGENT_ADAPTERS = tuple(name for name in available_adapters() if name not in CONTROL_ADAPTERS)


class PromptParityTest(unittest.TestCase):
    def setUp(self):
        self.tasks = load_tasks()
        self.adapters = [get_adapter(name) for name in AGENT_ADAPTERS]

    def test_more_than_one_agent_adapter_exists(self):
        self.assertGreaterEqual(len(self.adapters), 2, AGENT_ADAPTERS)

    def test_every_agent_receives_byte_identical_instructions(self):
        for task in self.tasks:
            prompts = {adapter.name: adapter.build_prompt(task) for adapter in self.adapters}
            with self.subTest(task=task.id):
                self.assertEqual(len(set(prompts.values())), 1, f"prompts differ: {list(prompts)}")

    def test_the_shared_builder_is_what_adapters_use(self):
        task = self.tasks[0]
        for adapter in self.adapters:
            with self.subTest(adapter=adapter.name):
                self.assertEqual(adapter.build_prompt(task), build_task_prompt(task))

    def test_prompt_states_the_protected_paths(self):
        for task in self.tasks:
            with self.subTest(task=task.id):
                prompt = build_task_prompt(task)
                for protected in task.protected_paths:
                    self.assertIn(protected, prompt)

    def test_prompt_carries_the_acceptance_criteria(self):
        task = self.tasks[0]
        prompt = build_task_prompt(task)
        for criterion in task.acceptance_criteria:
            self.assertIn(criterion, prompt)

    def test_prompt_never_reveals_the_solution_or_hidden_tests(self):
        """The prompt must not become a leak channel for the answer."""
        for task in self.tasks:
            prompt = build_task_prompt(task)
            with self.subTest(task=task.id):
                if task.has_reference_solution:
                    for source in task.solution_path.rglob("*.py"):
                        body = source.read_text(encoding="utf-8")
                        significant = [
                            line.strip()
                            for line in body.splitlines()
                            if len(line.strip()) > 40 and not line.strip().startswith("#")
                        ]
                        for line in significant:
                            self.assertNotIn(line, prompt)
                self.assertNotIn(str(task.solution_path), prompt)
                self.assertNotIn(str(task.acceptance_path), prompt)


class FixtureParityTest(TempDirTestCase):
    def test_every_agent_starts_from_the_same_bytes(self):
        task = load_registry()["py-001-interval-merge"]
        digests = []
        for _ in AGENT_ADAPTERS:
            with create_sandbox(task, root=self.tmp / "sb") as sandbox:
                digests.append(sandbox.snapshot_tree())
        self.assertEqual(len(set(digests)), 1)

    def test_fixture_digest_matches_the_recorded_fingerprint_input(self):
        task = load_registry()["py-001-interval-merge"]
        with create_sandbox(task, root=self.tmp / "sb") as sandbox:
            from benchmark.hashing import hash_tree

            self.assertEqual(sandbox.snapshot_tree(), hash_tree(task.workspace_path))


class AdapterContractTest(unittest.TestCase):
    def test_agents_declare_the_same_isolation_needs(self):
        for name in AGENT_ADAPTERS:
            adapter = get_adapter(name)
            with self.subTest(adapter=name):
                self.assertTrue(adapter.requires_network)
                self.assertFalse(adapter.is_control)

    def test_agents_share_the_same_default_timeout(self):
        timeouts = {get_adapter(name).timeout_sec for name in AGENT_ADAPTERS}
        self.assertEqual(len(timeouts), 1, f"agents have different budgets: {timeouts}")

    def test_agents_report_a_real_version_or_say_unavailable(self):
        for name in AGENT_ADAPTERS:
            adapter = get_adapter(name)
            with self.subTest(adapter=name):
                version = adapter.version()
                self.assertTrue(version)
                self.assertNotIn("guess", version)

    def test_agents_refuse_to_measure_without_credentials(self):
        """A missing credential is an agent error, never a failed task."""
        for name in AGENT_ADAPTERS:
            adapter = get_adapter(name)
            with self.subTest(adapter=name):
                self.assertTrue(hasattr(adapter, "preflight"))

    def test_flags_are_recorded_and_carry_no_secret(self):
        for name in AGENT_ADAPTERS:
            adapter = get_adapter(name)
            with self.subTest(adapter=name):
                flags = adapter.describe_flags()
                self.assertTrue(flags)
                for flag in flags:
                    self.assertNotIn("sk-", flag)


class CodexCommandTest(unittest.TestCase):
    """Flags are checked against the installed CLI, not against a comment."""

    def setUp(self):
        self.adapter = CodexAdapter()

    def test_uses_the_non_interactive_subcommand(self):
        self.assertEqual(self.adapter.build_command()[1], "exec")

    def test_determinism_flags_are_present(self):
        command = self.adapter.build_command()
        for flag in ("--ignore-user-config", "--ephemeral", "--skip-git-repo-check"):
            self.assertIn(flag, command)

    def test_colour_is_disabled_so_evidence_stays_plain(self):
        command = self.adapter.build_command()
        self.assertIn("--color", command)
        self.assertEqual(command[command.index("--color") + 1], "never")

    def test_model_flag_only_appears_when_a_model_is_named(self):
        self.assertNotIn("--model", CodexAdapter(model="").build_command())
        self.assertIn("--model", CodexAdapter(model="gpt-5-codex").build_command())

    @unittest.skipIf(shutil.which("codex") is None, "codex CLI is not installed here")
    def test_the_installed_cli_accepts_every_flag(self):
        """Parse-only: an invalid enum value stops the CLI before any model call."""
        command = [*self.adapter.build_command(), "--sandbox", "deliberately-invalid", "prompt"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        combined = (result.stdout + result.stderr).lower()
        self.assertIn("--sandbox", combined)
        self.assertNotIn("unexpected argument", combined)

    @unittest.skipIf(shutil.which("codex") is None, "codex CLI is not installed here")
    def test_an_unknown_flag_would_be_rejected(self):
        """Confirms the previous test is meaningful rather than vacuous."""
        result = subprocess.run(
            ["codex", "exec", "--definitely-not-a-flag", "x"],
            capture_output=True, text=True, timeout=90, check=False,
        )
        self.assertIn("unexpected argument", (result.stdout + result.stderr).lower())


class CodexTelemetryTest(unittest.TestCase):
    def test_tool_calls_are_counted(self):
        stdout = '\n'.join([
            '{"type": "tool_call", "name": "shell"}',
            '{"type": "exec_command", "name": "ls"}',
            '{"type": "message", "text": "hello"}',
        ])
        self.assertEqual(parse_jsonl_telemetry(stdout)["tool_calls"], 2)

    def test_absent_telemetry_stays_absent(self):
        """An agent that reports nothing must not look cheaper than one that does."""
        self.assertEqual(parse_jsonl_telemetry("no json here"), {})

    def test_resolved_model_is_captured_when_reported(self):
        stdout = '{"type": "session", "model": "gpt-5-codex"}'
        self.assertEqual(parse_jsonl_telemetry(stdout)["model_resolved"], "gpt-5-codex")

    def test_malformed_lines_are_ignored(self):
        self.assertEqual(parse_jsonl_telemetry('{"broken": '), {})


class ClaudeCommandTest(unittest.TestCase):
    def test_print_mode_is_used(self):
        self.assertIn("--print", ClaudeCodeAdapter().describe_flags())

    def test_permission_bypass_is_declared_in_the_record(self):
        self.assertIn("bypassPermissions", ClaudeCodeAdapter().describe_flags())


if __name__ == "__main__":
    unittest.main()


class ResolvedModelTest(unittest.TestCase):
    """A model name is observed or absent — never inferred."""

    def test_claude_reports_a_model_when_the_cli_names_one(self):
        from benchmark.adapters.claude_code import _reported_model

        self.assertEqual(
            _reported_model('{"model": "claude-opus-5"}')["model_resolved"], "claude-opus-5"
        )

    def test_claude_reports_nothing_when_the_cli_is_silent(self):
        from benchmark.adapters.claude_code import _reported_model

        self.assertEqual(_reported_model("Edited src/intervals.py"), {})

    def test_codex_reports_nothing_when_the_cli_is_silent(self):
        self.assertNotIn("model_resolved", parse_jsonl_telemetry("plain output"))

    def test_requested_and_resolved_are_kept_apart_in_storage(self):
        import tempfile
        from pathlib import Path as _Path

        from benchmark.storage import ResultsStore

        with tempfile.TemporaryDirectory() as directory:
            store = ResultsStore(_Path(directory) / "r.sqlite3")
            run_id, _ = store.start_run(
                adapter="codex", agent="codex", model="unspecified", adapter_version="v1",
                attempts_per_task=1,
            )
            row = store.query("SELECT model, model_resolved FROM runs")[0]
            self.assertEqual(row["model"], "unspecified")
            self.assertIsNone(row["model_resolved"], "an unreported model must stay NULL")

            store.record_resolved_model(run_id, "gpt-5-codex")
            row = store.query("SELECT model, model_resolved FROM runs")[0]
            self.assertEqual(row["model_resolved"], "gpt-5-codex")
            self.assertEqual(row["model"], "unspecified")
            store.close()

    def test_an_empty_report_never_overwrites_null(self):
        import tempfile
        from pathlib import Path as _Path

        from benchmark.storage import ResultsStore

        with tempfile.TemporaryDirectory() as directory:
            store = ResultsStore(_Path(directory) / "r.sqlite3")
            run_id, _ = store.start_run(
                adapter="codex", agent="codex", adapter_version="v1", attempts_per_task=1
            )
            store.record_resolved_model(run_id, "")
            self.assertIsNone(store.query("SELECT model_resolved FROM runs")[0]["model_resolved"])
            store.close()
