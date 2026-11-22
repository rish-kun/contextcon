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


def _norm_map(text: str) -> tuple[str, list[int]]:
    """``normalize`` character by character, keeping each output character's
    offset in the original text so a match can be mapped back to it."""
    chars: list[str] = []
    index: list[int] = []
    space = True  # drop leading whitespace
    for i, ch in enumerate(text):
        piece = unicodedata.normalize("NFKC", ch).translate(_QUOTES).casefold()
        for c in piece:
            if c.isspace():
                if space:
                    continue
                chars.append(" ")
                index.append(i)
                space = True
            else:
                chars.append(c)
                index.append(i)
                space = False
    if chars and chars[-1] == " ":
        chars.pop()
        index.pop()
    return "".join(chars), index


def _needles(span: str) -> list[str]:
    needle, _ = _norm_map(span)
    needle = needle.strip(" \"'")
    out = [needle] if len(needle) >= MIN_SPAN_CHARS else []
    trimmed = needle.rstrip(".,;:").rstrip()
    if trimmed != needle and len(trimmed) >= MIN_SPAN_CHARS:
        out.append(trimmed)
    return out


def _bounded(hay: str, start: int, end: int) -> bool:
    """The match starts and ends on token boundaries: "250" never matches
    inside "1250" or "1,250", and "Pune" never inside "Puneet"."""
    if hay[start].isalnum() and start > 0 and hay[start - 1].isalnum():
        return False
    if hay[start].isdigit() and start > 1 and hay[start - 1] in ",." and hay[start - 2].isdigit():
        return False
    if hay[end - 1].isalnum() and end < len(hay) and hay[end].isalnum():
        return False
    return not (
        hay[end - 1].isdigit()
        and end + 1 < len(hay)
        and hay[end] in ",."
        and hay[end + 1].isdigit()
    )


def locate_span(span: str | None, source: str) -> tuple[int, int] | None:
    """Offsets ``(start, end)`` of ``span`` in the ORIGINAL ``source`` text,
    matched after normalisation and on complete tokens, or None."""
    if not span or not source:
        return None
    hay, index = _norm_map(source)
    for needle in _needles(span):
        at = hay.find(needle)
        while at >= 0:
            end = at + len(needle)
            if _bounded(hay, at, end):
                return index[at], index[end - 1] + 1
            at = hay.find(needle, at + 1)
    return None


def span_in(span: str | None, source: str) -> bool:
    """True when `span` appears verbatim (after normalisation, on complete
    tokens) inside `source`."""
    return locate_span(span, source) is not None


# --- Sentences, clauses and injected instructions --------------------------------

_ABBREVIATIONS = frozenset(
    "pvt ltd inc co corp llp llc no nos mr mrs ms dr st rs approx est vs etc jan feb mar apr "
    "jun jul aug sep sept oct nov dec fy".split()
)
_SENTENCE_END = re.compile(r"[.!?](?=\s)|\n")


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand ``[start, end)`` to the sentence(s) containing it."""

    def is_break(m: re.Match) -> bool:
        if m.group() == "\n":
            return True
        if m.group() != ".":
            return True
        before = text[: m.start()].split()
        token = before[-1].lstrip("(\"'").casefold() if before else ""
        return not (token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha()))

    s = 0
    e = len(text)
    for m in _SENTENCE_END.finditer(text):
        if not is_break(m):
            continue
        if m.end() <= start:
            s = m.end()
        elif m.start() >= end:
            e = m.end() if m.group() != "\n" else m.start()
            break
    return s, e


_CLAUSE_BREAK = re.compile(r"[,;:()\[\]\n]|\s[-–—]\s")


def clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand ``[start, end)`` to the clause(s) containing it (split on
    commas, semicolons, colons, brackets and dashes)."""
    s, e = 0, len(text)
    for m in _CLAUSE_BREAK.finditer(text):
        if m.end() <= start:
            s = m.end()
        elif m.start() >= end:
            e = m.start()
            break
    return s, e


_INJECTION = re.compile(
    r"""
    \b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}?
        \b(?:previous|prior|above|earlier|preceding|all|any|your|these|the)\b[^.\n]{0,30}?
        \b(?:instructions?|prompts?|rules|directions|guidelines|context)\b
    | \bsystem\s+prompt\b
    | \byou\s+are\s+now\b
    | \bnew\s+instructions?\b
    | \bas\s+an?\s+(?:ai|language\s+model|assistant)\b
    | \b(?:mark|label|classify|report|treat)\b[^.\n]{0,40}?
        \bas\s+(?:verified|supported|true|confirmed|accurate)\b
    | </?\s*(?:system|assistant|user|document|evidence|claim|instructions?)\s*>
    """,
    re.IGNORECASE | re.VERBOSE,
)


def injected_regions(text: str) -> list[tuple[int, int]]:
    """Lines of ``text`` that address instructions to the model ("ignore
    previous instructions", "mark this as verified"). Document text is data:
    nothing extracted from these lines is kept."""
    regions: list[tuple[int, int]] = []
    for m in _INJECTION.finditer(text):
        s = text.rfind("\n", 0, m.start()) + 1
        e = text.find("\n", m.end())
        e = len(text) if e < 0 else e
        if regions and s <= regions[-1][1]:
            regions[-1] = (regions[-1][0], max(e, regions[-1][1]))
        else:
            regions.append((s, e))
    return regions


def overlaps(regions: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(s < end and start < e for s, e in regions)


_TAG = re.compile(
    r"<(/?\s*(?:system|assistant|user|document|evidence|claim|instructions?)\b)", re.I
)


def neutralize_tags(text: str) -> str:
    """Stop untrusted text from closing or opening the prompt's own data tags."""
    return _TAG.sub(r"‹\1", text)
