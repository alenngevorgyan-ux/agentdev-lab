"""Version parsing and comparison.

The authoritative specification is docs/VERSION_SPEC.md.
"""

import re
from dataclasses import dataclass

_VERSION = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.\-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.\-]+))?$"
)
_IDENTIFIER = re.compile(r"^[0-9A-Za-z\-]+$")
_NUMERIC = re.compile(r"^(?:0|[1-9]\d*)$")


class InvalidVersion(ValueError):
    """Raised when a version string does not match the specification."""


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple = ()
    build: str = ""


def _parse_prerelease(raw, original):
    identifiers = []
    for part in raw.split("."):
        if not part or not _IDENTIFIER.match(part):
            raise InvalidVersion(f"invalid pre-release identifier in {original!r}")
        if part.isdigit():
            if not _NUMERIC.match(part):
                raise InvalidVersion(f"numeric identifier with leading zero in {original!r}")
            identifiers.append(int(part))
        else:
            identifiers.append(part)
    return tuple(identifiers)


def parse_version(text):
    """Parse a version string into a Version. See docs/VERSION_SPEC.md."""
    if isinstance(text, Version):
        return text
    match = _VERSION.match(str(text))
    if match is None:
        raise InvalidVersion(f"invalid version: {text!r}")

    build = match.group("build") or ""
    for part in build.split(".") if build else []:
        if not part or not _IDENTIFIER.match(part):
            raise InvalidVersion(f"invalid build metadata in {text!r}")

    prerelease = (
        _parse_prerelease(match.group("prerelease"), text) if match.group("prerelease") else ()
    )
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=prerelease,
        build=build,
    )


def _compare_identifier(left, right):
    left_numeric, right_numeric = isinstance(left, int), isinstance(right, int)
    if left_numeric and right_numeric:
        return (left > right) - (left < right)
    # A numeric identifier always has lower precedence than an alphanumeric one.
    if left_numeric != right_numeric:
        return -1 if left_numeric else 1
    return (left > right) - (left < right)


def _compare_prerelease(left, right):
    if not left and not right:
        return 0
    # Having a pre-release lowers precedence against the same release version.
    if not left:
        return 1
    if not right:
        return -1
    for a, b in zip(left, right):
        verdict = _compare_identifier(a, b)
        if verdict:
            return verdict
    return (len(left) > len(right)) - (len(left) < len(right))


def compare_versions(a, b):
    """Return -1, 0 or 1 comparing two versions. See docs/VERSION_SPEC.md."""
    left, right = parse_version(a), parse_version(b)
    left_core = (left.major, left.minor, left.patch)
    right_core = (right.major, right.minor, right.patch)
    if left_core != right_core:
        return -1 if left_core < right_core else 1
    # Build metadata is deliberately absent here: it never affects precedence.
    return _compare_prerelease(left.prerelease, right.prerelease)
