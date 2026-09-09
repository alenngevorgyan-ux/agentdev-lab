"""Version parsing and comparison.

The authoritative specification is docs/VERSION_SPEC.md.
"""

from dataclasses import dataclass


class InvalidVersion(ValueError):
    """Raised when a version string does not match the specification."""


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple = ()
    build: str = ""


def parse_version(text):
    """Parse a version string into a Version. See docs/VERSION_SPEC.md."""
    raise NotImplementedError


def compare_versions(a, b):
    """Return -1, 0 or 1 comparing two versions. See docs/VERSION_SPEC.md."""
    raise NotImplementedError
