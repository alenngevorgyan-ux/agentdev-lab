import unittest

from benchmark.adapters.base import AgentOutcome
from benchmark.execution import TIMEOUT_EXIT_CODE, CommandResult
from benchmark.scoring import Score, Status, score_attempt
from benchmark.testparse import SuiteResult, TestOutcome, TestResult


def verification(exit_code=0, timed_out=False):
    return CommandResult(
        command=("verify",),
        exit_code=TIMEOUT_EXIT_CODE if timed_out else exit_code,
        stdout="",
        stderr="",
        duration_ms=10,
        timed_out=timed_out,
    )


def agent(completed=True, error=""):
    return AgentOutcome(completed=completed, duration_ms=1, error=error)


def suite(passed=2, failed=0):
    tests = [TestResult(f"t.p{i}", TestOutcome.PASSED) for i in range(passed)]
    tests += [TestResult(f"t.f{i}", TestOutcome.FAILED) for i in range(failed)]
    return SuiteResult(tests=tuple(tests), reported_total=passed + failed)


def score(**kwargs):
    defaults = {
        "agent": agent(),
        "verification": verification(),
        "suite": suite(),
        "regressions": 0,
        "protected_before": "h",
        "protected_after": "h",
    }
    defaults.update(kwargs)
    return score_attempt(**defaults)


class ScoreAttemptTest(unittest.TestCase):
    def test_passing_verification(self):
        result = score()
        self.assertIs(result.status, Status.PASSED)
        self.assertTrue(result.passed)

    def test_failing_verification(self):
        result = score(verification=verification(exit_code=1))
        self.assertIs(result.status, Status.FAILED)
        self.assertFalse(result.passed)

    def test_verification_timeout(self):
        self.assertIs(score(verification=verification(timed_out=True)).status, Status.TIMEOUT)

    def test_agent_failure(self):
        result = score(agent=agent(completed=False, error="crashed"), verification=None)
        self.assertIs(result.status, Status.AGENT_ERROR)
        self.assertIn("crashed", result.reason)

    def test_regression_demotes_a_green_suite(self):
        """Breaking working behaviour is not success, whatever the exit code says."""
        result = score(verification=verification(exit_code=0), regressions=2)
        self.assertIs(result.status, Status.FAILED)
        self.assertIn("regression", result.reason)

    def test_uncollectable_suite_fails(self):
        broken = SuiteResult(tests=(), reported_total=None, collection_error=True)
        self.assertIs(score(suite=broken).status, Status.FAILED)

    def test_missing_verification_is_a_harness_error(self):
        self.assertIs(score(verification=None).status, Status.HARNESS_ERROR)

    def test_tampering_is_detected(self):
        result = score(protected_after="different")
        self.assertIs(result.status, Status.TAMPERED)
        self.assertTrue(result.tampered)

    def test_tampering_overrides_a_green_test_run(self):
        """Weakening the tests then passing them is never scored as a pass."""
        result = score(verification=verification(exit_code=0), protected_after="weakened")
        self.assertIs(result.status, Status.TAMPERED)
        self.assertFalse(result.passed)

    def test_tampering_outranks_agent_failure(self):
        result = score(
            agent=agent(completed=False, error="crashed"),
            verification=None,
            protected_after="different",
        )
        self.assertIs(result.status, Status.TAMPERED)

    def test_passed_flag_cannot_be_forged(self):
        with self.assertRaises(ValueError):
            Score(status=Status.FAILED, passed=True, tampered=False, reason="")


if __name__ == "__main__":
    unittest.main()
