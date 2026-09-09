import unittest

from src.version import InvalidVersion, parse_version, compare_versions


class ParseTest(unittest.TestCase):
    def test_simple(self):
        version = parse_version("1.2.3")
        self.assertEqual((version.major, version.minor, version.patch), (1, 2, 3))

    def test_prerelease(self):
        self.assertEqual(parse_version("1.0.0-alpha.1").prerelease, ("alpha", 1))

    def test_missing_patch_is_invalid(self):
        with self.assertRaises(InvalidVersion):
            parse_version("1.2")


class CompareTest(unittest.TestCase):
    def test_ordering(self):
        self.assertEqual(compare_versions("1.0.0", "1.0.1"), -1)
        self.assertEqual(compare_versions("1.0.1", "1.0.0"), 1)
        self.assertEqual(compare_versions("1.0.0", "1.0.0"), 0)


if __name__ == "__main__":
    unittest.main()
