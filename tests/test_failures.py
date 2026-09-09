import unittest

from benchmark.failures import TAXONOMY, FailureCategory, FailureEvidence, classify


def evidence(**overrides):
    fields = {
        "status": "failed",
        "tests_total": 10,
        "tests_passed": 5,
        "regressions": 0,
        "files_changed": 1,
        "lines_changed": 20,
        "expected_files_touched": 1,
        "expected_files_declared": 1,
        "output": "",
    }
    fields.update(overrides)
    return FailureEvidence(**fields)


class ClassifierTest(unittest.TestCase):
    def test_passing_attempt_has_no_failure(self):
        self.assertIs(classify(evidence(status="passed")), FailureCategory.NONE)

    def test_tampering_is_test_gaming(self):
        self.assertIs(classify(evidence(status="tampered")), FailureCategory.TEST_GAMING)

    def test_timeout(self):
        self.assertIs(classify(evidence(status="timeout")), FailureCategory.TIMEOUT)

    def test_agent_error_is_environmental(self):
        self.assertIs(classify(evidence(status="agent_error")), FailureCategory.ENVIRONMENT_FAILURE)

    def test_regression_outranks_partial_progress(self):
        self.assertIs(classify(evidence(regressions=2)), FailureCategory.REGRESSION)

    def test_hallucinated_api_from_import_error(self):
        self.assertIs(
            classify(evidence(output="ModuleNotFoundError: no module named 'requests'")),
            FailureCategory.HALLUCINATED_API,
        )

    def test_attribute_error_is_hallucination(self):
        self.assertIs(
            classify(evidence(output="AttributeError: module 'x' has no attribute 'y'")),
            FailureCategory.HALLUCINATED_API,
        )

    def test_under_editing_when_nothing_changed(self):
        self.assertIs(classify(evidence(lines_changed=0)), FailureCategory.UNDER_EDITING)

    def test_wrong_location_when_expected_files_untouched(self):
        self.assertIs(
            classify(evidence(expected_files_touched=0, files_changed=2)),
            FailureCategory.WRONG_LOCATION,
        )

    def test_over_editing_on_a_sprawling_diff(self):
        self.assertIs(
            classify(evidence(files_changed=12, expected_files_declared=2, expected_files_touched=2)),
            FailureCategory.OVER_EDITING,
        )

    def test_incomplete_implementation_on_partial_pass(self):
        self.assertIs(classify(evidence()), FailureCategory.INCOMPLETE_IMPLEMENTATION)

    def test_unclassified_when_evidence_is_ambiguous(self):
        """No test passed and nothing else is diagnostic: a human must look."""
        self.assertIs(classify(evidence(tests_passed=0)), FailureCategory.UNCLASSIFIED)

    def test_environment_marker_beats_other_signals(self):
        self.assertIs(
            classify(evidence(output="Not logged in")), FailureCategory.ENVIRONMENT_FAILURE
        )

    def test_regression_outranks_hallucination_marker(self):
        self.assertIs(
            classify(evidence(regressions=1, output="ImportError: boom")),
            FailureCategory.REGRESSION,
        )


class TaxonomyTest(unittest.TestCase):
    def test_every_category_is_documented(self):
        for category in FailureCategory:
            with self.subTest(category=category):
                self.assertIn(category, TAXONOMY)
                self.assertTrue(TAXONOMY[category].strip())

    def test_taxonomy_has_no_extra_entries(self):
        self.assertEqual(set(TAXONOMY), set(FailureCategory))


if __name__ == "__main__":
    unittest.main()
