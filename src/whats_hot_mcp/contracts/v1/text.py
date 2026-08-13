"""Reference text normalization for Contract v1 literal history search."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_search_text(value: str) -> str:
    """Apply the Contract v1 NFKC/casefold/whitespace normalization."""

    if not isinstance(value, str):
        raise TypeError("search text must be a string")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _WHITESPACE_RE.sub(" ", normalized).strip()
