"""URL slug generation."""

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text, max_length=60):
    """Convert arbitrary text into a URL slug.

    Contract:

    * Unicode is normalised to ASCII: accents are stripped, so "Café"
      becomes "cafe". Characters with no ASCII equivalent are dropped.
    * The result is lowercase.
    * Every run of non-alphanumeric characters becomes a single hyphen.
    * Leading and trailing hyphens are removed.
    * The slug is truncated to at most ``max_length`` characters, and never
      ends mid-word: truncation happens at the last hyphen before the limit
      when one exists, otherwise at the limit.
    * Text that contains no alphanumeric characters yields an empty string.
    * ``max_length`` of 0 or less raises ValueError.
    """
    if max_length <= 0:
        raise ValueError("max_length must be positive")

    normalised = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM.sub("-", ascii_text.lower()).strip("-")

    if len(slug) <= max_length:
        return slug

    truncated = slug[:max_length]
    if "-" in truncated:
        truncated = truncated[: truncated.rindex("-")]
    return truncated.strip("-")
