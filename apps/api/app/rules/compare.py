"""Deterministic value parsing and comparison shared by validation and status rules."""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
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
    "lacs": 1e5,
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
_INR_SCALES = frozenset({"lakh", "lakhs", "lac", "lacs", "crore", "crores", "cr"})

# A number token: Indian or western digit grouping, optional decimals. It must
# start a token (no letter, digit or decimal point straight before it), so
# "250" is never read inside "1250", "1,250" or "12.250".
_NUMBER_TOKEN = re.compile(
    r"(?<![\w])(?<!\d[.,])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)"
)
_SCALE_AFTER = re.compile(
    r"\s*(" + "|".join(sorted(_MULTIPLIERS, key=len, reverse=True)) + r")\b(?![.\-]?\d)",
    re.IGNORECASE,
)
_PERCENT_AFTER = re.compile(r"\s*(%|percent\b|per\s+cent\b|pc\b)", re.IGNORECASE)
_CURRENCY_AFTER = re.compile(r"\s*(inr|rupees?|usd|dollars?|eur|euros?|gbp)\b", re.IGNORECASE)
_CURRENCY_BEFORE = re.compile(r"(₹|rs\.?|inr|us\$|\$|usd|€|eur|£|gbp)\s*$", re.IGNORECASE)
_CURRENCY_CODES = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "us$": "USD",
    "$": "USD",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}
_MINUS = frozenset({"-", "−"})


@dataclass(frozen=True)
class Quantity:
    """A number as the text states it: sign, scale, unit and currency kept.

    ``value`` is the signed, scaled amount ("-5 million" → -5_000_000.0);
    ``written`` is the bare figure as printed (5.0). Offsets are into the text
    that was parsed.
    """

    value: float
    written: float
    scale: float = 1.0
    percent: bool = False
    currency: str | None = None
    start: int = 0
    end: int = 0


def currency_code(text: str | None) -> str | None:
    if not text:
        return None
    return _CURRENCY_CODES.get(text.strip().casefold())


def parse_quantities(text: str) -> list[Quantity]:
    """Every number in ``text`` with its sign, scale, percent unit and currency.

    A scale word ("5 million", "12 crore") is always applied: the bare "5" is
    not a separate reading. A minus counts as a sign only when it is attached
    to the number and does not follow a digit (so "2008-2013" is a range).
    Lakh and crore imply rupees when no currency is written.
    """
    out: list[Quantity] = []
    for m in _NUMBER_TOKEN.finditer(text):
        raw = m.group(1)
        try:
            written = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - the pattern only admits digits
            continue
        start, end = m.start(1), m.end(1)
        rest = text[end:]
        scale = 1.0
        scale_word = None
        sm = _SCALE_AFTER.match(rest)
        if sm:
            scale_word = sm.group(1).casefold()
            scale = _MULTIPLIERS[scale_word]
            end += sm.end()
            rest = text[end:]
        percent = False
        pm = _PERCENT_AFTER.match(rest)
        if pm and scale_word is None:
            percent = True
            end += pm.end()
            rest = text[end:]
        currency = None
        cm = _CURRENCY_BEFORE.search(text[max(0, start - 6) : start])
        sign_at = start
        if cm:
            currency = currency_code(cm.group(1))
            sign_at = max(0, start - 6) + cm.start()
        elif not percent:
            am = _CURRENCY_AFTER.match(rest)
            if am:
                currency = currency_code(am.group(1))
                end += am.end()
        if currency is None and scale_word in _INR_SCALES:
            currency = "INR"
        negative = False
        before = text[:sign_at].rstrip(" ") if cm else text[:sign_at]
        if before and before[-1] in _MINUS:
            prev = before[:-1]
            if not prev or not (prev[-1].isdigit() or prev[-1].isalpha()):
                negative = True
                start = len(before) - 1
        value = written * scale * (-1 if negative else 1)
        out.append(
            Quantity(
                value=value,
                written=written,
                scale=scale,
                percent=percent,
                currency=currency,
                start=start,
                end=end,
            )
        )
    return out


def parse_numbers(text: str) -> list[float]:
    """Every number in the text, signed and with its scale applied.

    "5 million" gives 5_000_000.0 only; the bare 5 is not a reading of it.
    """
    return [q.value for q in parse_quantities(text)]


def to_quantity(value: Any) -> Quantity | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Quantity(value=float(value), written=abs(float(value)))
    if isinstance(value, str):
        qs = parse_quantities(value)
        return qs[0] if qs else None
    return None


def to_number(value: Any) -> float | None:
    q = to_quantity(value)
    return q.value if q is not None else None


def same_number(a: float, b: float) -> bool:
    """Exact equality for parsed figures, allowing only float rounding."""
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


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


_GROWTH_ROUNDS = ("growth", "private equity", "pre ipo", "buyout", "pe")
_VENTURE_ROUNDS = ("pre seed", "seed", "angel", "venture", "series")
_DEBT_ROUNDS = ("debt", "loan", "credit facility", "debenture")


def round_kind(value: Any) -> str | None:
    """Broad kind of a funding round: growth, venture, debt or grant."""
    if value is None:
        return None
    text = f" {normalize_text(value)} "
    if " grant " in text:
        return "grant"
    if any(f" {w} " in text for w in _DEBT_ROUNDS):
        return "debt"
    if any(f" {w} " in text for w in _GROWTH_ROUNDS):
        return "growth"
    if any(f" {w} " in text for w in _VENTURE_ROUNDS):
        return "venture"
    return None


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

    if kind is ValueKind.ROUND_TYPE:
        if contains_phrase(fact_value, claimed):
            return "match"
        ck, fk = round_kind(claimed), round_kind(fact_value)
        if ck is None or fk is None:
            return "insufficient"
        return "match" if ck == fk else "conflict"

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
