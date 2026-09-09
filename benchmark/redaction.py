"""Redaction of credentials from anything the lab stores or shows.

Captured output is evidence, and evidence gets written to SQLite, exported to
JSON and CSV, rendered in the dashboard and quoted in the session log. A
credential that reaches any of those has effectively been published.

Redaction happens once, at the point where a subprocess's output is captured,
so every downstream consumer inherits it. Two mechanisms run together:

* **Value matching** -- the actual values of secret-looking environment
  variables are replaced wherever they appear. This catches a token however it
  was echoed, including split across a line or embedded in JSON.
* **Pattern matching** -- known credential shapes and ``key = value``
  assignments are masked even when the value never passed through this
  process's environment.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Mapping

#: Environment variable names whose values must never appear in stored text.
SECRET_NAME_PATTERN = re.compile(
    r"(API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.IGNORECASE
)

#: Values shorter than this are too generic to mask without wrecking the logs.
MIN_SECRET_LENGTH = 8

#: Upper bound on every quantifier below. Real credentials are far shorter than
#: this, and an unbounded quantifier turns a large log into a hang: captured
#: output is attacker-influenced, so redaction has to be linear on it.
MAX_SECRET_LENGTH = 512

PLACEHOLDER = "[REDACTED]"

#: Recognisable credential shapes, masked regardless of their origin.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic-key", re.compile(rf"sk-ant-[A-Za-z0-9_\-]{{8,{MAX_SECRET_LENGTH}}}")),
    ("openai-key", re.compile(rf"\bsk-(?:proj-)?[A-Za-z0-9_\-]{{16,{MAX_SECRET_LENGTH}}}")),
    ("github-token", re.compile(rf"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{{20,{MAX_SECRET_LENGTH}}}")),
    ("github-pat", re.compile(rf"\bgithub_pat_[A-Za-z0-9_]{{20,{MAX_SECRET_LENGTH}}}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-key", re.compile(rf"\bAIza[0-9A-Za-z_\-]{{30,{MAX_SECRET_LENGTH}}}")),
    ("slack-token", re.compile(rf"\bxox[abprs]-[A-Za-z0-9-]{{10,{MAX_SECRET_LENGTH}}}")),
    ("jwt", re.compile(
        rf"\beyJ[A-Za-z0-9_\-]{{10,{MAX_SECRET_LENGTH}}}"
        rf"\.[A-Za-z0-9_\-]{{10,{MAX_SECRET_LENGTH}}}"
        rf"\.[A-Za-z0-9_\-]{{10,{MAX_SECRET_LENGTH}}}"
    )),
    ("bearer", re.compile(rf"(?i)\bbearer\s+[A-Za-z0-9._\-]{{16,{MAX_SECRET_LENGTH}}}")),
    ("private-key-block", re.compile(
        r"-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----[\s\S]{0,8192}?-----END [A-Z ]{0,32}PRIVATE KEY-----"
    )),
)

#: ``NAME=value``, ``name: value`` and ``"name": "value"`` assignments whose
#: left-hand side looks like a credential. The quoting around either side is
#: optional and is preserved, so redacted JSON stays parseable.
# Bounded on both sides of the keyword: an unbounded prefix made the engine
# retry every position of a long run of word characters.
_SECRET_NAME = (
    r"[A-Za-z0-9_\-]{0,32}(?:api[_-]?key|secret|token|password|passwd|credential|authorization)"
    r"[A-Za-z0-9_\-]{0,32}"
)
_ASSIGNMENT = re.compile(
    rf"(?i)(?P<name>{_SECRET_NAME})(?P<gap>[\"']?\s*[:=]\s*)(?P<quote>[\"']?)"
    rf"(?P<value>[^\s\"',;}}\]]{{{MIN_SECRET_LENGTH},{MAX_SECRET_LENGTH}}})(?P=quote)"
)


def secret_environment_values(env: Mapping[str, str] | None = None) -> list[str]:
    """Values of environment variables whose names look like credentials."""
    source = os.environ if env is None else env
    values = []
    for name, value in source.items():
        if not value or len(value) < MIN_SECRET_LENGTH:
            continue
        if SECRET_NAME_PATTERN.search(name):
            values.append(value)
    # Longest first, so a token containing another token is masked whole.
    return sorted(set(values), key=len, reverse=True)


def redact(text: str, *, extra_values: Iterable[str] = (), env: Mapping[str, str] | None = None) -> str:
    """Mask credentials in ``text``.

    Conservative by construction: it never returns text containing a known
    secret value, and prefers over-masking a long opaque token to letting one
    through.
    """
    if not text:
        return text

    for value in sorted(
        {v for v in (*secret_environment_values(env), *extra_values) if v and len(v) >= MIN_SECRET_LENGTH},
        key=len,
        reverse=True,
    ):
        text = text.replace(value, PLACEHOLDER)

    for _, pattern in _PATTERNS:
        text = pattern.sub(PLACEHOLDER, text)

    text = _ASSIGNMENT.sub(
        lambda m: f"{m['name']}{m['gap']}{m['quote']}{PLACEHOLDER}{m['quote']}", text
    )
    return text


def contains_secret(text: str, *, env: Mapping[str, str] | None = None) -> bool:
    """Whether ``text`` still carries something that looks like a credential."""
    if not text:
        return False
    for value in secret_environment_values(env):
        if value in text:
            return True
    return any(pattern.search(text) for _, pattern in _PATTERNS)
