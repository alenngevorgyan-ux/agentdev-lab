import unittest

from benchmark.testparse import TestOutcome, parse_unittest_output

VERBOSE = """\
test_alpha (tests.test_x.AlphaTest.test_alpha) ... ok
test_beta (tests.test_x.AlphaTest.test_beta) ... FAIL
test_gamma (tests.test_x.AlphaTest.test_gamma) ... ERROR
test_delta (tests.test_x.AlphaTest.test_delta) ... skipped 'not today'
test_epsilon (tests.test_x.AlphaTest.test_epsilon) ... expected failure

======================================================================
FAIL: test_beta (tests.test_x.AlphaTest.test_beta)
----------------------------------------------------------------------
AssertionError: nope

Ran 5 tests in 0.003s

FAILED (failures=1, errors=1, skipped=1, expected failures=1)
"""


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.result = parse_unittest_output(VERBOSE)

    def test_every_test_is_parsed(self):
        self.assertEqual(self.result.total, 5)

    def test_reported_total_matches(self):
        self.assertTrue(self.result.parse_is_complete)

    def test_outcomes(self):
        outcomes = {test.test_id.rsplit(".", 1)[-1]: test.outcome for test in self.result.tests}
        self.assertEqual(outcomes["test_alpha"], TestOutcome.PASSED)
        self.assertEqual(outcomes["test_beta"], TestOutcome.FAILED)
        self.assertEqual(outcomes["test_gamma"], TestOutcome.ERROR)
        self.assertEqual(outcomes["test_delta"], TestOutcome.SKIPPED)
        self.assertEqual(outcomes["test_epsilon"], TestOutcome.EXPECTED_FAILURE)

    def test_expected_failure_counts_as_satisfied(self):
        self.assertEqual(self.result.passed, 2)

    def test_skipped_is_not_satisfied(self):
        """A skipped test proves nothing, so it never counts as a pass."""
        satisfied = self.result.satisfied_ids()
        self.assertNotIn("tests.test_x.AlphaTest.test_delta", satisfied)

    def test_pass_fraction(self):
        self.assertAlmostEqual(self.result.pass_fraction, 0.4)

    def test_failure_traceback_lines_are_not_counted_as_tests(self):
        self.assertEqual(self.result.total, 5)


class InterleavedOutputTest(unittest.TestCase):
    """A test that prints lands between its header and its outcome."""

    NOISY = """\
test_a (tests.t.T.test_a) ... ok
test_b (tests.t.T.test_b) ... /path/x.py:171: ResourceWarning: unclosed file
  self._assert_caught("x")
ResourceWarning: Enable tracemalloc to get the object allocation traceback
ok
test_c (tests.t.T.test_c) ... FAIL

Ran 3 tests in 0.274s
"""

    def setUp(self):
        self.result = parse_unittest_output(self.NOISY)

    def test_split_outcome_is_stitched_back(self):
        self.assertEqual(self.result.total, 3)
        self.assertTrue(self.result.parse_is_complete)

    def test_the_noisy_test_keeps_its_outcome(self):
        outcomes = {t.test_id: t.outcome for t in self.result.tests}
        self.assertEqual(outcomes["tests.t.T.test_b"], TestOutcome.PASSED)

    def test_noise_lines_do_not_become_tests(self):
        self.assertEqual(len({t.test_id for t in self.result.tests}), 3)


class DocstringFormatTest(unittest.TestCase):
    """unittest prints a documented test across two lines."""

    TEXT = """\
test_documented (mod.T.test_documented)
This one has a docstring. ... ok
test_plain (mod.T.test_plain) ... ok
test_failing_doc (mod.T.test_failing_doc)
Another description. ... FAIL

Ran 3 tests in 0.001s
"""

    def setUp(self):
        self.result = parse_unittest_output(self.TEXT)

    def test_documented_tests_are_counted(self):
        self.assertEqual(self.result.total, 3)
        self.assertTrue(self.result.parse_is_complete)

    def test_documented_test_keeps_its_identity(self):
        self.assertIn("mod.T.test_documented", {t.test_id for t in self.result.tests})

    def test_documented_failure_is_recorded(self):
        outcomes = {t.test_id: t.outcome for t in self.result.tests}
        self.assertEqual(outcomes["mod.T.test_failing_doc"], TestOutcome.FAILED)

    def test_a_stray_ellipsis_line_invents_nothing(self):
        """Only a line following an open header may supply an outcome."""
        text = "Loading fixtures ... ok\n\nRan 0 tests in 0.0s\n"
        self.assertEqual(parse_unittest_output(text).total, 0)


class EffectiveTotalTest(unittest.TestCase):
    """An incomplete parse must never shrink the denominator."""

    def test_effective_total_uses_the_runner_count(self):
        text = "test_a (tests.t.T.test_a) ... ok\n\nRan 9 tests in 0.1s\n"
        result = parse_unittest_output(text)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.effective_total, 9)

    def test_effective_total_matches_when_complete(self):
        text = "test_a (tests.t.T.test_a) ... ok\n\nRan 1 test in 0.1s\n"
        self.assertEqual(parse_unittest_output(text).effective_total, 1)


class EdgeCaseTest(unittest.TestCase):
    def test_empty_output_is_a_collection_error(self):
        result = parse_unittest_output("")
        self.assertTrue(result.collection_error)
        self.assertEqual(result.total, 0)

    def test_import_error_output_is_a_collection_error(self):
        text = "Traceback (most recent call last):\nModuleNotFoundError: no module named 'src'\n"
        self.assertTrue(parse_unittest_output(text).collection_error)

    def test_zero_tests_is_a_collection_error(self):
        self.assertTrue(parse_unittest_output("Ran 0 tests in 0.000s\n\nOK\n").collection_error)

    def test_truncated_output_is_detected(self):
        text = "test_a (tests.t.T.test_a) ... ok\n\nRan 9 tests in 0.1s\n"
        self.assertFalse(parse_unittest_output(text).parse_is_complete)

    def test_old_style_header_is_normalised(self):
        result = parse_unittest_output("test_a (tests.t.T) ... ok\n\nRan 1 test in 0.1s\n")
        self.assertEqual(result.tests[0].test_id, "tests.t.T.test_a")

    def test_pass_fraction_without_tests(self):
        self.assertEqual(parse_unittest_output("").pass_fraction, 0.0)


if __name__ == "__main__":
    unittest.main()
