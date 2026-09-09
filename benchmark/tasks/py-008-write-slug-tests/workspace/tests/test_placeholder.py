import unittest


class SanityTest(unittest.TestCase):
    """The real grading lives in the hidden acceptance suite."""

    def test_implementation_is_importable(self):
        from src.slugify import slugify

        self.assertEqual(slugify("Hello World"), "hello-world")


if __name__ == "__main__":
    unittest.main()
