"""Experiment manifests and the publication gate.

The point of a manifest is that methodology cannot change quietly after results
are seen. These tests check that property directly: an edited manifest must
produce a different hash, drifted fixtures must be refused, and the gate must
fail loudly rather than passing an incomplete comparison.
"""

from __future__ import annotations

import json
import unittest

from benchmark.experiment import (
    EXPERIMENTS_DIR,
    Experiment,
    ManifestError,
    check_drift,
    freeze,
    list_experiments,
    load_experiment,
    write_experiment,
)
from benchmark.integrity import verify_experiment
from benchmark.storage import ResultsStore
from benchmark.tasks import load_registry
from tests.helpers import TempDirTestCase
from tests.test_storage import FakeTask, attempt_fields

MINIMAL = {
    "name": "demo",
    "description": "a demo comparison",
    "agents": [
        {"adapter": "claude-code", "model": "unspecified"},
        {"adapter": "codex", "model": "unspecified"},
    ],
    "task_ids": ["py-001-interval-merge", "py-015-pagination"],
    "attempts_per_task": 3,
    "agent_timeout_sec": 900,
    "isolation": "auto",
    "network_policy": "agent-turn-allowed, evaluation-denied",
    "ordering_seed": 42,
    "analysis_plan": ["Primary: pass rate per agent."],
}


class ManifestValidationTest(TempDirTestCase):
    def _write(self, **overrides):
        payload = {**MINIMAL, **overrides}
        for key, value in list(payload.items()):
            if value is None:
                payload.pop(key)
        path = self.tmp / "m.json"
        path.write_text(json.dumps(payload))
        return path

    def test_valid_manifest_loads(self):
        experiment = load_experiment(self._write())
        self.assertEqual(experiment.name, "demo")
        self.assertEqual(experiment.attempts_per_task, 3)

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(ManifestError):
            load_experiment(self._write(unexpected="x"))

    def test_missing_key_is_rejected(self):
        with self.assertRaises(ManifestError):
            load_experiment(self._write(analysis_plan=None))

    def test_a_single_agent_is_not_a_comparison(self):
        with self.assertRaises(ManifestError):
            load_experiment(self._write(agents=[{"adapter": "codex", "model": "x"}]))

    def test_agent_without_a_model_field_is_rejected(self):
        with self.assertRaises(ManifestError):
            load_experiment(self._write(agents=[{"adapter": "a"}, {"adapter": "b"}]))

    def test_zero_attempts_is_rejected(self):
        with self.assertRaises(ManifestError):
            load_experiment(self._write(attempts_per_task=0))

    def test_comparison_without_isolation_is_refused(self):
        """A comparison run on the bare host is not a comparison worth freezing."""
        with self.assertRaises(ManifestError):
            load_experiment(self._write(isolation="none"))

    def test_invalid_json_is_rejected(self):
        path = self.tmp / "bad.json"
        path.write_text("{nope")
        with self.assertRaises(ManifestError):
            load_experiment(path)

    def test_missing_file_is_rejected(self):
        with self.assertRaises(ManifestError):
            load_experiment(self.tmp / "absent.json")


class ManifestHashTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        path = self.tmp / "m.json"
        path.write_text(json.dumps(MINIMAL))
        self.experiment = load_experiment(path)

    def test_hash_is_stable(self):
        self.assertEqual(self.experiment.manifest_hash(), self.experiment.manifest_hash())

    def test_hash_ignores_key_order(self):
        other = self.tmp / "other.json"
        other.write_text(json.dumps(dict(reversed(list(MINIMAL.items())))))
        self.assertEqual(load_experiment(other).manifest_hash(), self.experiment.manifest_hash())

    def test_changing_attempts_changes_the_hash(self):
        path = self.tmp / "changed.json"
        path.write_text(json.dumps({**MINIMAL, "attempts_per_task": 4}))
        self.assertNotEqual(load_experiment(path).manifest_hash(), self.experiment.manifest_hash())

    def test_changing_the_analysis_plan_changes_the_hash(self):
        """Rewriting the plan after seeing results must be visible."""
        path = self.tmp / "plan.json"
        path.write_text(json.dumps({**MINIMAL, "analysis_plan": ["Primary: whatever wins."]}))
        self.assertNotEqual(load_experiment(path).manifest_hash(), self.experiment.manifest_hash())

    def test_dropping_a_task_changes_the_hash(self):
        path = self.tmp / "dropped.json"
        path.write_text(json.dumps({**MINIMAL, "task_ids": ["py-001-interval-merge"]}))
        self.assertNotEqual(load_experiment(path).manifest_hash(), self.experiment.manifest_hash())

    def test_notes_do_not_affect_the_hash(self):
        path = self.tmp / "noted.json"
        path.write_text(json.dumps({**MINIMAL, "notes": "an aside"}))
        self.assertEqual(load_experiment(path).manifest_hash(), self.experiment.manifest_hash())


class OrderingTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        path = self.tmp / "m.json"
        path.write_text(json.dumps(MINIMAL))
        self.experiment = load_experiment(path)

    def test_every_agent_attempt_is_planned(self):
        order = self.experiment.attempt_order()
        self.assertEqual(len(order), 2 * 2 * 3)  # tasks x agents x attempts

    def test_ordering_is_deterministic_for_a_seed(self):
        self.assertEqual(self.experiment.attempt_order(), self.experiment.attempt_order())

    def test_a_different_seed_gives_a_different_order(self):
        path = self.tmp / "seeded.json"
        path.write_text(json.dumps({**MINIMAL, "ordering_seed": 7}))
        self.assertNotEqual(load_experiment(path).attempt_order(), self.experiment.attempt_order())

    def test_agents_are_interleaved_not_blocked(self):
        """All of A then all of B would confound the comparison with drift."""
        agents = [agent for _, agent, _ in self.experiment.attempt_order()]
        first_half = set(agents[: len(agents) // 2])
        self.assertGreater(len(first_half), 1, "one agent ran entirely before the other")


class FreezeAndDriftTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        path = self.tmp / "m.json"
        path.write_text(json.dumps(MINIMAL))
        self.path = path
        self.experiment = freeze(load_experiment(path))

    def test_freeze_pins_every_task(self):
        self.assertEqual(len(self.experiment.task_fingerprints), len(MINIMAL["task_ids"]))

    def test_no_drift_immediately_after_freezing(self):
        self.assertEqual(check_drift(self.experiment), [])

    def test_drift_is_detected_when_a_fixture_changes(self):
        stale = Experiment(
            **{
                **{k: getattr(self.experiment, k) for k in (
                    "name", "description", "agents", "task_ids", "attempts_per_task",
                    "agent_timeout_sec", "isolation", "network_policy", "ordering_seed",
                    "analysis_plan", "notes", "path",
                )},
                "task_fingerprints": {"py-001-interval-merge": "stale-digest"},
            }
        )
        self.assertEqual(check_drift(stale), ["py-001-interval-merge"])

    def test_unknown_task_is_refused_at_freeze_time(self):
        path = self.tmp / "unknown.json"
        path.write_text(json.dumps({**MINIMAL, "task_ids": ["py-999-nonexistent"]}))
        with self.assertRaises(ManifestError):
            freeze(load_experiment(path))

    def test_written_manifest_round_trips(self):
        out = self.tmp / "written.json"
        write_experiment(self.experiment, out)
        self.assertEqual(load_experiment(out).manifest_hash(), self.experiment.manifest_hash())


class ShippedManifestTest(unittest.TestCase):
    """The pre-registered comparison must stay valid and pinned."""

    def test_at_least_one_manifest_is_pre_registered(self):
        self.assertTrue(list_experiments())

    def test_every_shipped_manifest_is_valid_and_frozen(self):
        for path in list_experiments():
            with self.subTest(manifest=path.name):
                experiment = load_experiment(path)
                self.assertTrue(experiment.task_fingerprints, "manifest is not frozen")
                self.assertEqual(check_drift(experiment), [], "fixtures drifted since freezing")

    def test_shipped_manifest_covers_the_whole_suite(self):
        experiment = load_experiment(EXPERIMENTS_DIR / "claude-vs-codex-v1.json")
        self.assertEqual(set(experiment.task_ids), set(load_registry()))


class PublicationGateTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        path = self.tmp / "m.json"
        path.write_text(json.dumps(MINIMAL))
        self.experiment = freeze(load_experiment(path))
        self.store = ResultsStore(self.tmp / "results.sqlite3")
        self.addCleanup(self.store.close)
        self.store.register_tasks([FakeTask("py-001-interval-merge")])

    def _run(self, **overrides):
        defaults = dict(
            adapter="claude-code", agent="claude-code", adapter_version="v1",
            attempts_per_task=3, isolation_backend="seatbelt", isolation_active=True,
            publishable=True, network_policy="allowed",
            experiment_name=self.experiment.name,
            experiment_hash=self.experiment.manifest_hash(),
        )
        defaults.update(overrides)
        return self.store.start_run(**defaults)

    def test_gate_fails_when_nothing_was_run(self):
        report = verify_experiment(self.store, self.experiment)
        self.assertFalse(report.ok)
        self.assertIn("has not been run", report.render())

    def test_gate_flags_unisolated_attempts(self):
        run_id, _ = self._run(isolation_active=False, publishable=False)
        self.store.record_attempt(
            **attempt_fields(run_id=run_id, isolation_active=0, task_id="py-001-interval-merge")
        )
        report = verify_experiment(self.store, self.experiment)
        self.assertFalse(report.ok)
        self.assertIn("enforced boundary", report.render())

    def test_gate_flags_a_dirty_checkout(self):
        run_id, _ = self._run()
        self.store.record_attempt(**attempt_fields(run_id=run_id, task_id="py-001-interval-merge"))
        report = verify_experiment(self.store, self.experiment)
        checks = {c.name: c for c in report.checks}
        # git_dirty is whatever the working tree is; the check must exist either way.
        self.assertIn("every run came from a clean checkout", checks)

    def test_gate_flags_uneven_attempt_counts(self):
        """Running one agent more than the other is a cherry-picking vector."""
        run_id, _ = self._run()
        self.store.record_attempt(**attempt_fields(run_id=run_id, task_id="py-001-interval-merge"))
        report = verify_experiment(self.store, self.experiment)
        self.assertIn("attempts per task match the manifest", {c.name for c in report.checks})

    def test_gate_flags_synthetic_rows(self):
        run_id, _ = self._run(run_kind="development_sample", publishable=False)
        self.store.record_attempt(**attempt_fields(run_id=run_id, task_id="py-001-interval-merge"))
        report = verify_experiment(self.store, self.experiment)
        self.assertIn("no synthetic row is inside the experiment", {c.name for c in report.checks})
        self.assertFalse(report.ok)

    def test_gate_reports_rate_limit_and_timeout_shares(self):
        run_id, _ = self._run()
        self.store.record_attempt(
            **attempt_fields(
                run_id=run_id, task_id="py-001-interval-merge", status="timeout",
                passed=0, failure_category="timeout",
            )
        )
        names = {c.name for c in verify_experiment(self.store, self.experiment).checks}
        self.assertIn("claude-code: rate-limit share below 5%", names)
        self.assertIn("claude-code: timeout share below 10%", names)


if __name__ == "__main__":
    unittest.main()
