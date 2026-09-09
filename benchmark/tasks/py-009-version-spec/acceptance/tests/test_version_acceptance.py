"""Hidden acceptance tests: one per clause of the specification."""

import unittest

from src.version import InvalidVersion, Version, compare_versions, parse_version


class ParsingClausesTest(unittest.TestCase):
    def test_leading_zero_in_major_is_rejected(self):
        with self.assertRaises(InvalidVersion):
            parse_version("01.0.0")

    def test_leading_zero_in_patch_is_rejected(self):
        with self.assertRaises(InvalidVersion):
            parse_version("1.0.00")

    def test_zero_itself_is_valid(self):
        self.assertEqual(parse_version("0.0.0").major, 0)

    def test_empty_prerelease_identifier_is_rejected(self):
        with self.assertRaises(InvalidVersion):
            parse_version("1.0.0-alpha..1")

    def test_numeric_prerelease_leading_zero_is_rejected(self):
        with self.assertRaises(InvalidVersion):
            parse_version("1.0.0-alpha.01")

    def test_build_metadata_may_have_leading_zeroes(self):
        self.assertEqual(parse_version("1.0.0+007").build, "007")

    def test_prerelease_and_build_together(self):
        version = parse_version("1.0.0-rc.1+build.5")
        self.assertEqual(version.prerelease, ("rc", 1))
        self.assertEqual(version.build, "build.5")

    def test_invalid_characters_are_rejected(self):
        with self.assertRaises(InvalidVersion):
            parse_version("1.0.0-al pha")

    def test_error_message_quotes_the_input(self):
        with self.assertRaises(InvalidVersion) as ctx:
            parse_version("nonsense")
        self.assertIn("nonsense", str(ctx.exception))

    def test_hyphen_is_allowed_inside_an_identifier(self):
        self.assertEqual(parse_version("1.0.0-x-y.2").prerelease, ("x-y", 2))


class ComparisonClausesTest(unittest.TestCase):
    def test_build_metadata_is_ignored(self):
        self.assertEqual(compare_versions("1.0.0+a", "1.0.0+b"), 0)

    def test_prerelease_sorts_before_release(self):
        self.assertEqual(compare_versions("1.0.0-alpha", "1.0.0"), -1)
        self.assertEqual(compare_versions("1.0.0", "1.0.0-alpha"), 1)

    def test_numeric_identifiers_compare_numerically(self):
        self.assertEqual(compare_versions("1.0.0-alpha.2", "1.0.0-alpha.10"), -1)

    def test_numeric_sorts_before_alphanumeric(self):
        self.assertEqual(compare_versions("1.0.0-1", "1.0.0-alpha"), -1)

    def test_longer_chain_sorts_after(self):
        self.assertEqual(compare_versions("1.0.0-alpha", "1.0.0-alpha.1"), -1)

    def test_accepts_parsed_versions(self):
        self.assertEqual(compare_versions(parse_version("1.0.0"), Version(1, 0, 0)), 0)

    def test_canonical_ordering(self):
        versions = [
            "1.0.0",
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            "1.0.0-beta",
            "1.0.0-beta.2",
            "1.0.0-beta.11",
            "1.0.0-rc.1",
            "2.0.0",
            "1.1.0",
        ]
        import functools

        ordered = sorted(versions, key=functools.cmp_to_key(compare_versions))
        self.assertEqual(
            ordered,
            [
                "1.0.0-alpha",
                "1.0.0-alpha.1",
                "1.0.0-alpha.beta",
                "1.0.0-beta",
                "1.0.0-beta.2",
                "1.0.0-beta.11",
                "1.0.0-rc.1",
                "1.0.0",
                "1.1.0",
                "2.0.0",
            ],
        )


if __name__ == "__main__":
    unittest.main()
