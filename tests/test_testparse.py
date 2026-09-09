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
