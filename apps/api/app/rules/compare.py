"""Deterministic value parsing and comparison shared by validation and status rules."""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Literal

from app.domain.enums import ValueKind
from app.rules import policy

Relation = Literal["match", "conflict", "insufficient"]

_SYNONYMS = {
    "pvt": "private",
    "ltd": "limited",
    "co": "company",
    "corp": "corporation",
    "inc": "incorporated",
    "and": "and",
    "bengaluru": "bangalore",
    "bombay": "mumbai",
    "gurugram": "gurgaon",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(_SYNONYMS.get(tok, tok) for tok in text.split())


def contains_phrase(haystack: Any, needle: Any) -> bool:
    n = normalize_text(needle)
    return bool(n) and f" {n} " in f" {normalize_text(haystack)} "


# --- Numbers -----------------------------------------------------------------

_MULTIPLIERS = {
    "k": 1e3,
    "thousand": 1e3,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "mn": 1e6,
    "million": 1e6,
    "m": 1e6,
    "bn": 1e9,
    "billion": 1e9,
    "b": 1e9,
}
_NUMBER_RE = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*("
    + "|".join(sorted(_MULTIPLIERS, key=len, reverse=True))
    + r")?(?![a-z])",
    re.IGNORECASE,
)


def parse_numbers(text: str) -> list[float]:
    """Every number in the text, both as written and with its multiplier applied."""
    out: list[float] = []
    for raw, unit in _NUMBER_RE.findall(text):
        try:
            base = float(raw.replace(",", ""))
        except ValueError:
            continue
        out.append(base)
        if unit:
            out.append(base * _MULTIPLIERS[unit.lower()])
    return out


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        nums = parse_numbers(value)
        if not nums:
            return None
        # Prefer the multiplied reading when a unit is present.
        return nums[1] if len(nums) > 1 and _NUMBER_RE.search(value).group(2) else nums[0]
    return None


# --- Dates -------------------------------------------------------------------

_MONTHS: dict[str, int] = {}
for _i in range(1, 13):
    _MONTHS[calendar.month_name[_i].lower()] = _i
    _MONTHS[calendar.month_abbr[_i].lower()] = _i
_MONTHS["sept"] = 9
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO_DATE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_DMY_DATE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")
_D_MONTH_Y = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})\.?,?\s+(\d{{4}})\b", re.I
)
_MONTH_D_Y = re.compile(
    rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I
)
_MONTH_Y = re.compile(rf"\b({_MONTH_NAMES})\.?,?[\s-]+(\d{{4}})\b", re.I)
_ISO_MONTH = re.compile(r"\b(\d{4})-(\d{1,2})\b(?![-/.]\d)")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_dates(text: str) -> list[date]:
    out: list[date] = []
    for y, m, d in _ISO_DATE.findall(text):
        out.append(_safe_date(int(y), int(m), int(d)))
    for d, m, y in _DMY_DATE.findall(text):  # Indian convention: day first
        out.append(_safe_date(int(y), int(m), int(d)))
    for d, mon, y in _D_MONTH_Y.findall(text):
        out.append(_safe_date(int(y), _MONTHS[mon.lower()], int(d)))
    for mon, d, y in _MONTH_D_Y.findall(text):
        out.append(_safe_date(int(y), _MONTHS[mon.lower()], int(d)))
    return [d for d in out if d is not None]


def parse_months(text: str) -> list[tuple[int, int]]:
    out = [(d.year, d.month) for d in parse_dates(text)]
    out += [(int(y), _MONTHS[mon.lower()]) for mon, y in _MONTH_Y.findall(text)]
    out += [(int(y), int(m)) for y, m in _ISO_MONTH.findall(text) if 1 <= int(m) <= 12]
    return out


def parse_years(text: str) -> list[int]:
    return [int(y) for y in _YEAR.findall(text)] + [d.year for d in parse_dates(text)]


def to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        dates = parse_dates(value)
        return dates[0] if dates else None
    return None


def to_month(value: Any) -> tuple[int, int] | None:
    if isinstance(value, date | datetime):
        return (value.year, value.month)
    if isinstance(value, tuple) and len(value) == 2:
        return (int(value[0]), int(value[1]))
    if isinstance(value, str):
        months = parse_months(value)
        return months[0] if months else None
    return None


def to_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, date | datetime):
        return value.year
    if isinstance(value, str):
        years = parse_years(value)
        return years[0] if years else None
    return None


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = normalize_text(value)
        if v in {"true", "yes", "y", "1"}:
            return True
        if v in {"false", "no", "n", "0", "none"}:
            return False
    if isinstance(value, int | float):
        return value != 0
    return None


def to_stage(value: Any) -> str | None:
    v = normalize_text(value).replace(" ", "_")
    return v if v in policy.STAGE_ORDER else None


# --- Comparison --------------------------------------------------------------


def _ordered(c: float, f: float, op: str, tol: float) -> Relation:
    if op == "gte":
        return "match" if f >= c else "conflict"
    if op == "lte":
        return "match" if f <= c else "conflict"
    return "match" if abs(f - c) <= tol else "conflict"


def compare(
    kind: ValueKind,
    claimed: Any,
    op: str,
    fact_value: Any,
    *,
    fact_as_of: date | None = None,
    claim_context: dict[str, Any] | None = None,
) -> Relation:
    """Compare a claimed component value with a fact value."""
    if fact_value is None or claimed is None:
        return "insufficient"

    if kind is ValueKind.YEAR:
        c, f = to_year(claimed), to_year(fact_value)
        if c is None or f is None:
            return "insufficient"
        return _ordered(c, f, op, 0)

    if kind is ValueKind.MONTH:
        c = to_month(claimed)
        if c is None:
            return "insufficient"
        f = to_month(fact_value)
        if f is None:
            fy = to_year(fact_value)
            return "conflict" if fy is not None and fy != c[0] else "insufficient"
        return "match" if f == c else "conflict"

    if kind is ValueKind.DATE:
        c = to_date(claimed)
        if c is None:
            return "insufficient"
        f = to_date(fact_value)
        if f is None:
            fm = to_month(fact_value)
            if fm is not None and fm != (c.year, c.month):
                return "conflict"
            fy = to_year(fact_value)
            return "conflict" if fy is not None and fy != c.year else "insufficient"
        return "match" if f == c else "conflict"

    if kind in (ValueKind.COUNT, ValueKind.MONEY):
        c, f = to_number(claimed), to_number(fact_value)
        if c is None or f is None:
            return "insufficient"
        rel = policy.COUNT_TOLERANCE if kind is ValueKind.COUNT else policy.MONEY_TOLERANCE
        return _ordered(c, f, op, rel * max(abs(c), 1.0))

    if kind is ValueKind.PERCENT:
        c, f = to_number(claimed), to_number(fact_value)
        if c is None or f is None:
            return "insufficient"
        return _ordered(c, f, op, policy.PERCENT_TOLERANCE_POINTS)

    if kind is ValueKind.BOOL:
        c, f = to_bool(claimed), to_bool(fact_value)
        if c is None or f is None:
            return "insufficient"
        return "match" if c == f else "conflict"

    if kind is ValueKind.TEXT:
        if contains_phrase(fact_value, claimed) or contains_phrase(claimed, fact_value):
            return "match"
        return "conflict"

    if kind is ValueKind.TEXT_CONTAINS:
        # A record that names a different role does not contradict the claim:
        # people hold several roles. Only presence settles it.
        return "match" if contains_phrase(fact_value, claimed) else "insufficient"

    if kind is ValueKind.ENUM:
        return "match" if normalize_text(claimed) == normalize_text(fact_value) else "conflict"

    if kind is ValueKind.STAGE:
        c, f = to_stage(claimed), to_stage(fact_value)
        if c is None or f is None:
            return "insufficient"
        co, fo = policy.STAGE_ORDER[c], policy.STAGE_ORDER[f]
        if co == fo:
            return "match"
        if fo > co:
            return "conflict" if f == "closed" else "insufficient"
        # The fact shows an earlier stage. That is consistent with the claim if
        # it was true before the claimed date; it conflicts only if the record
        # still shows the earlier stage after the claimed date.
        claimed_month = to_month((claim_context or {}).get("event_date"))
        if fact_as_of is not None and claimed_month is not None:
            y, m = claimed_month
            month_end = date(y, m, calendar.monthrange(y, m)[1])
            return "conflict" if fact_as_of > month_end else "insufficient"
        return "insufficient"

    return "insufficient"
