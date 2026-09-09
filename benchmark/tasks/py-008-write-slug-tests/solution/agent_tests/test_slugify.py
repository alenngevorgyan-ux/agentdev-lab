import unittest

from src.slugify import slugify


class SlugifyTest(unittest.TestCase):
    def test_basic_lowercasing(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_uppercase_is_lowered(self):
        self.assertEqual(slugify("ALL CAPS TITLE"), "all-caps-title")

    def test_accents_are_normalised(self):
        self.assertEqual(slugify("Café Ünicode"), "cafe-unicode")

    def test_runs_of_punctuation_collapse_to_one_hyphen(self):
        self.assertEqual(slugify("a  --  b!!!c"), "a-b-c")

    def test_leading_and_trailing_separators_are_stripped(self):
        self.assertEqual(slugify("!!! trailing !!!"), "trailing")

    def test_truncation_happens_at_a_word_boundary(self):
        self.assertEqual(slugify("alpha beta gamma delta", max_length=14), "alpha-beta")

    def test_truncation_without_a_boundary_cuts_at_the_limit(self):
        self.assertEqual(slugify("abcdefghij", max_length=4), "abcd")

    def test_text_without_alphanumerics_is_empty(self):
        self.assertEqual(slugify("!!! ???"), "")

    def test_zero_max_length_is_rejected(self):
        with self.assertRaises(ValueError):
            slugify("anything", max_length=0)

    def test_negative_max_length_is_rejected(self):
        with self.assertRaises(ValueError):
            slugify("anything", max_length=-5)


if __name__ == "__main__":
    unittest.main()
