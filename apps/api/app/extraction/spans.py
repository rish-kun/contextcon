"""Verbatim-span checks.

Principle 1 of the PRD: nothing comes from the AI's memory. Every claim, fact
or criterion the model returns must quote text that exists in the input. A
quote is accepted when it appears in the source after both are normalised:
Unicode NFKC, typographic quotes and dashes unified, whitespace collapsed and
case folded. Nothing else is forgiven: a paraphrase fails.
"""

from __future__ import annotations

import re
import unicodedata

_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "″": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        " ": " ",
        "­": "",
    }
)
_WS = re.compile(r"\s+")

# A quote shorter than this (after normalisation) is too weak to anchor a fact.
MIN_SPAN_CHARS = 3


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _WS.sub(" ", text).strip().casefold()


def span_in(span: str | None, source: str) -> bool:
    """True when `span` appears verbatim (after normalisation) inside `source`."""
    if not span:
        return False
    needle = normalize(span)
    # Models sometimes wrap a quote in quotation marks or add a trailing period.
    needle = needle.strip(" \"'")
    if len(needle) < MIN_SPAN_CHARS:
        return False
    hay = normalize(source)
    if needle in hay:
        return True
    trimmed = needle.rstrip(".,;:")
    return len(trimmed) >= MIN_SPAN_CHARS and trimmed in hay
