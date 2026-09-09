"""Hidden acceptance suite: grade the agent's tests by mutation testing.

A test suite that passes on correct code proves very little. The measure that
matters is whether it *fails* on broken code, so the agent's suite is run
against deliberately mutated implementations and must catch every one.
"""

import importlib
import io
import sys
import textwrap
import types
import unittest
from pathlib import Path

AGENT_TESTS = Path(__file__).resolve().parent.parent / "agent_tests" / "test_slugify.py"

# Each mutant breaks exactly one clause of the documented contract.
MUTANTS = {
    "no_lowercasing": """
        import re, unicodedata
        _NON_ALNUM = re.compile(r"[^a-zA-Z0-9]+")
        def slugify(text, max_length=60):
            if max_length <= 0:
                raise ValueError("max_length must be positive")
            ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
            slug = _NON_ALNUM.sub("-", ascii_text).strip("-")
            if len(slug) <= max_length:
                return slug
            truncated = slug[:max_length]
            if "-" in truncated:
                truncated = truncated[: truncated.rindex("-")]
            return truncated.strip("-")
    """,
    "keeps_trailing_hyphen": """
        import re, unicodedata
        _NON_ALNUM = re.compile(r"[^a-z0-9]+")
        def slugify(text, max_length=60):
            if max_length <= 0:
                raise ValueError("max_length must be positive")
            ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
            slug = _NON_ALNUM.sub("-", ascii_text.lower()).lstrip("-")
            return slug[:max_length]
    """,
    "no_unicode_normalisation": """
        import re
        _NON_ALNUM = re.compile(r"[^a-z0-9]+")
        def slugify(text, max_length=60):
            if max_length <= 0:
                raise ValueError("max_length must be positive")
            slug = _NON_ALNUM.sub("-", str(text).lower()).strip("-")
            if len(slug) <= max_length:
                return slug
            truncated = slug[:max_length]
            if "-" in truncated:
                truncated = truncated[: truncated.rindex("-")]
            return truncated.strip("-")
    """,
    "truncates_mid_word": """
        import re, unicodedata
        _NON_ALNUM = re.compile(r"[^a-z0-9]+")
        def slugify(text, max_length=60):
            if max_length <= 0:
                raise ValueError("max_length must be positive")
            ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
            slug = _NON_ALNUM.sub("-", ascii_text.lower()).strip("-")
            return slug[:max_length]
    """,
    "collapses_nothing": """
        import re, unicodedata
        _NON_ALNUM = re.compile(r"[^a-z0-9]")
        def slugify(text, max_length=60):
            if max_length <= 0:
                raise ValueError("max_length must be positive")
            ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
            slug = _NON_ALNUM.sub("-", ascii_text.lower()).strip("-")
            if len(slug) <= max_length:
                return slug
            truncated = slug[:max_length]
            if "-" in truncated:
                truncated = truncated[: truncated.rindex("-")]
            return truncated.strip("-")
    """,
    "accepts_zero_max_length": """
        import re, unicodedata
        _NON_ALNUM = re.compile(r"[^a-z0-9]+")
        def slugify(text, max_length=60):
            ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
            slug = _NON_ALNUM.sub("-", ascii_text.lower()).strip("-")
            if max_length <= 0 or len(slug) <= max_length:
                return slug
            truncated = slug[:max_length]
            if "-" in truncated:
                truncated = truncated[: truncated.rindex("-")]
            return truncated.strip("-")
    """,
}


def _load_agent_suite():
    """Import the agent's test module fresh, so mutants are picked up."""
    for name in list(sys.modules):
        if name.startswith("agent_tests"):
            del sys.modules[name]
    module = importlib.import_module("agent_tests.test_slugify")
    importlib.reload(module)
    return unittest.defaultTestLoader.loadTestsFromModule(module)


def _run_agent_suite():
    """Run the agent's suite quietly.

    The output is captured rather than sent to /dev/null: an unclosed handle
    would emit a ResourceWarning into the outer runner's own output stream.
    """
    suite = _load_agent_suite()
    return unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)


class AgentTestSuiteTest(unittest.TestCase):
    def setUp(self):
        if not AGENT_TESTS.is_file():
            self.fail("agent_tests/test_slugify.py was not written")

    def test_suite_has_enough_tests(self):
        suite = _load_agent_suite()
        self.assertGreaterEqual(suite.countTestCases(), 6, "write at least six tests")

    def test_suite_passes_against_the_correct_implementation(self):
        result = _run_agent_suite()
        self.assertTrue(
            result.wasSuccessful(),
            f"the suite must pass on correct code: {result.failures} {result.errors}",
        )

    def test_suite_imports_the_real_module(self):
        source = AGENT_TESTS.read_text(encoding="utf-8")
        self.assertIn("src.slugify", source, "import slugify from src.slugify")


class MutationTest(unittest.TestCase):
    """Each mutant must be caught by at least one of the agent's tests."""

    def setUp(self):
        if not AGENT_TESTS.is_file():
            self.fail("agent_tests/test_slugify.py was not written")
        import src.slugify as real

        self._real = real

    def tearDown(self):
        sys.modules["src.slugify"] = self._real

    def _install_mutant(self, source):
        module = types.ModuleType("src.slugify")
        exec(textwrap.dedent(source), module.__dict__)
        sys.modules["src.slugify"] = module

    def _assert_caught(self, name):
        self._install_mutant(MUTANTS[name])
        result = _run_agent_suite()
        self.assertFalse(
            result.wasSuccessful(),
            f"mutant {name!r} was not caught by any test",
        )

    def test_catches_no_lowercasing(self):
        self._assert_caught("no_lowercasing")

    def test_catches_keeps_trailing_hyphen(self):
        self._assert_caught("keeps_trailing_hyphen")

    def test_catches_no_unicode_normalisation(self):
        self._assert_caught("no_unicode_normalisation")

    def test_catches_truncates_mid_word(self):
        self._assert_caught("truncates_mid_word")

    def test_catches_collapses_nothing(self):
        self._assert_caught("collapses_nothing")

    def test_catches_accepts_zero_max_length(self):
        self._assert_caught("accepts_zero_max_length")


if __name__ == "__main__":
    unittest.main()
