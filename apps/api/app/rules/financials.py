"""Reading reported financial figures: period, unit and amount, growth and margins.

Pure functions shared by `verify.financials` (which stores what a page states) and the
financial assessment (which reports it). Nothing here estimates or values a company: a
figure is read as written, with its period and unit, and a growth rate or margin is
computed only between figures of the same length of period, in the same currency.

Indian fiscal years run April to March and are named by the year they end in: FY27 is
April 2026 to March 2027, so Q2 FY27 is July to September 2026.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

from app.rules.compare import parse_quantities

# --- Periods ---------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    label: str  # "Q2 FY27", "H1 FY26", "9M FY26", "FY24", "Q3 2026", "2025"
    end: date
    months: int  # 3, 6, 9 or 12


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    return _month_end(total // 12, total % 12 + 1)


def _fy_year(text: str) -> int | None:
    """`27` / `2027` / `2026-27` / `2026-2027` / `26-27` → the year the FY ends in."""
    text = text.strip()
    m = re.fullmatch(r"(\d{2}|\d{4})\s*[-–/]\s*(\d{2}|\d{4})", text)
    if m:
        text = m.group(2)
    if not text.isdigit():
        return None
    year = int(text)
    if year < 100:
        year += 2000
    return year if 1990 <= year <= 2100 else None


def fy_label(year: int) -> str:
    return f"FY{year % 100:02d}"


def indian_fy(d: date) -> int:
    """The Indian fiscal year a date falls in (named by its end year)."""
    return d.year + 1 if d.month >= 4 else d.year


_FY = (
    r"(?:FY|F\.Y\.?|fiscal(?:\s+year)?|financial\s+year)\s*'?\s*"
    r"((?:\d{4}|\d{2})(?:\s*[-–/]\s*(?:\d{4}|\d{2}))?)"
)
_Q_FY = re.compile(r"\bQ([1-4])\s*[,-]?\s*" + _FY, re.I)
_H_FY = re.compile(r"\bH([12])\s*[,-]?\s*" + _FY, re.I)
_9M_FY = re.compile(r"\b9\s*M\s*[,-]?\s*" + _FY, re.I)
_FY_ONLY = re.compile(r"\b" + _FY, re.I)
_Q_YEAR = re.compile(r"\bQ([1-4])\s*[,-]?\s*(?:CY\s*)?(20\d{2})\b", re.I)
_MONTHS = (
    "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    "sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_ENDED = re.compile(
    r"\b(quarter|three\s+months|half[\s-]year|six\s+months|nine\s+months|year|twelve\s+months)"
    r"\s+ended\s+(?:on\s+)?(?:(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTHS + r")\.?,?\s+(\d{4})"
    r"|(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}))",
    re.I,
)
_ENDED_MONTHS = {
    "quarter": 3,
    "three months": 3,
    "half year": 6,
    "half-year": 6,
    "six months": 6,
    "nine months": 9,
    "year": 12,
    "twelve months": 12,
}


def _month_no(name: str) -> int:
    return [m[:3] for m in calendar.month_abbr[1:]].index(name[:3].title()) + 1


def _fy_period(kind: str, n: int, fy: int) -> Period:
    """Q/H/9M/FY of Indian fiscal year ``fy`` (April to March)."""
    start = date(fy - 1, 4, 1)
    months = {"Q": 3, "H": 6, "9M": 9, "FY": 12}[kind]
    offset = (n - 1) * months if kind in ("Q", "H") else 0
    end = _add_months(start, offset + months - 1)
    prefix = {"Q": f"Q{n} ", "H": f"H{n} ", "9M": "9M ", "FY": ""}[kind]
    return Period(f"{prefix}{fy_label(fy)}", end, months)


def _period_from_end(months: int, end: date) -> Period:
    """A period named by its end date, labelled on the Indian fiscal calendar when it
    lines up with it (a quarter ending June, September, December or March)."""
    fy = indian_fy(end)
    if months == 12:
        label = fy_label(fy) if end.month == 3 else str(end.year)
    elif months == 3 and end.month in (6, 9, 12, 3):
        label = f"Q{[6, 9, 12, 3].index(end.month) + 1} {fy_label(fy)}"
    elif months == 6 and end.month in (9, 3):
        label = f"H{1 if end.month == 9 else 2} {fy_label(fy)}"
    elif months == 9 and end.month == 12:
        label = f"9M {fy_label(fy)}"
    else:
        label = f"{months} months to {end.strftime('%b %Y')}"
    return Period(label, end, months)


def parse_period(text: str | None) -> Period | None:
    """The first reporting period ``text`` states, most specific form first."""
    if not text:
        return None
    found: list[tuple[int, Period]] = []
    for pattern, kind in ((_Q_FY, "Q"), (_H_FY, "H")):
        for m in pattern.finditer(text):
            fy = _fy_year(m.group(2))
            if fy:
                found.append((m.start(), _fy_period(kind, int(m.group(1)), fy)))
    for m in _9M_FY.finditer(text):
        fy = _fy_year(m.group(1))
        if fy:
            found.append((m.start(), _fy_period("9M", 1, fy)))
    for m in _ENDED.finditer(text):
        months = _ENDED_MONTHS[re.sub(r"\s+", " ", m.group(1).lower())]
        if m.group(2):
            day, month, year = int(m.group(2)), _month_no(m.group(3)), int(m.group(4))
        else:
            day, month, year = int(m.group(6)), _month_no(m.group(5)), int(m.group(7))
        try:
            end = date(year, month, day)
        except ValueError:
            continue
        found.append((m.start(), _period_from_end(months, end)))
    for m in _Q_YEAR.finditer(text):
        q, year = int(m.group(1)), int(m.group(2))
        found.append((m.start(), Period(f"Q{q} {year}", _month_end(year, q * 3), 3)))
    if found:
        return min(found, key=lambda p: p[0])[1]
    covered = [m.span() for m in (*_Q_FY.finditer(text), *_H_FY.finditer(text))]
    for m in _FY_ONLY.finditer(text):
        if any(a <= m.start() < b for a, b in covered):
            continue
        fy = _fy_year(m.group(1))
        if fy:
            return _fy_period("FY", 1, fy)
    return None


def prior_period(p: Period, *, year_ago: bool) -> tuple[date, int]:
    """End date and length of the comparable earlier period: the same period a year
    earlier (YoY), or the one straight before it (sequential)."""
    return _add_months(p.end, -12 if year_ago else -p.months), p.months


# --- Amounts and units -------------------------------------------------------------


@dataclass(frozen=True)
class Amount:
    value: float  # in units of ``currency``
    currency: str | None  # "INR", "USD", ... or None when the text gives none
    unit: str | None  # "crore", "lakh", "million", "billion", "thousand" or None


_UNIT_WORDS = {
    "crore": "crore",
    "crores": "crore",
    "cr": "crore",
    "lakh": "lakh",
    "lakhs": "lakh",
    "lac": "lakh",
    "lacs": "lakh",
    "million": "million",
    "mn": "million",
    "m": "million",
    "billion": "billion",
    "bn": "billion",
    "b": "billion",
    "thousand": "thousand",
    "k": "thousand",
}
UNIT_SCALE = {"crore": 1e7, "lakh": 1e5, "million": 1e6, "billion": 1e9, "thousand": 1e3}
_UNIT_AFTER = re.compile(
    r"\s*(crores?|cr|lakhs?|lacs?|million|mn|billion|bn|thousand|k|m|b)\b\.?", re.I
)
# A table or statement heading that states the unit of every figure below it:
# "(₹ in crore)", "(Rs. in lakhs)", "All amounts in INR million", "₹ crore".
_UNIT_NOTE = re.compile(
    r"(?:(₹|rs\.?|inr|usd|us\$|\$)\s*(?:in\s+)?(crores?|lakhs?|lacs?|million|mn|billion|bn)\b"
    r"|amounts?\s+(?:are\s+)?in\s+(₹|rs\.?|inr|usd|us\$|\$)?\s*(crores?|lakhs?|lacs?|million|mn|billion|bn)\b"
    r"|\bin\s+(₹|rs\.?|inr|usd|us\$|\$)\s*(crores?|lakhs?|lacs?|million|mn|billion|bn)\b)",
    re.I,
)
_CURRENCY = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "usd": "USD",
    "us$": "USD",
    "$": "USD",
}


def parse_amount(text: str | None) -> Amount | None:
    """The first money figure in ``text``, with its unit word kept ("₹2,095 crore" →
    2.095e10 INR, unit crore). Percentages are not amounts."""
    if not text:
        return None
    for q in parse_quantities(text):
        if q.percent:
            continue
        unit = None
        if q.scale != 1.0:
            m = re.match(r"[\d,.]+" + _UNIT_AFTER.pattern, text[q.start :].lstrip("-−"), re.I)
            unit = _UNIT_WORDS.get(m.group(1).lower()) if m else None
        return Amount(value=q.value, currency=q.currency, unit=unit)
    return None


def unit_note(text: str | None) -> tuple[str, str | None, str] | None:
    """A heading that gives the unit of the figures under it: (unit, currency, quote)."""
    if not text:
        return None
    m = _UNIT_NOTE.search(text)
    if not m:
        return None
    groups = [g for g in m.groups()]
    cur = next((g for g in (groups[0], groups[2], groups[4]) if g), None)
    word = next(g for g in (groups[1], groups[3], groups[5]) if g)
    unit = _UNIT_WORDS[word.lower()]
    currency = _CURRENCY.get(cur.lower()) if cur else ("INR" if unit in ("crore", "lakh") else None)
    return unit, currency, m.group(0)


def scale_bare(amount: Amount, note: tuple[str, str | None, str] | None) -> Amount:
    """A bare number ("2,095.4") under a unit heading ("₹ in crore") takes that unit."""
    if amount.unit is not None or note is None:
        return amount
    unit, currency, _ = note
    return Amount(
        value=amount.value * UNIT_SCALE[unit], currency=amount.currency or currency, unit=unit
    )


_SYMBOL = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def display_amount(a: Amount) -> str:
    """Indian figures in crore or lakh, others in millions: "₹2,095 cr", "₹45 lakh",
    "$12.4M". The unit shown is the one the source used where it used one."""
    sym = _SYMBOL.get(a.currency or "", "")
    code = "" if sym or not a.currency else f"{a.currency} "
    v = a.value
    sign = "−" if v < 0 else ""
    v = abs(v)
    if a.currency == "INR" or a.unit in ("crore", "lakh"):
        if a.unit == "lakh" or (a.unit is None and v < 1e7):
            return f"{sign}{sym}{code}{_num(v / 1e5)} lakh"
        return f"{sign}{sym}{code}{_num(v / 1e7)} cr"
    if v >= 1e9:
        return f"{sign}{sym}{code}{_num(v / 1e9)}B"
    if v >= 1e6:
        return f"{sign}{sym}{code}{_num(v / 1e6)}M"
    return f"{sign}{sym}{code}{_num(v)}"


def _num(v: float) -> str:
    if v >= 100:
        return f"{v:,.0f}"
    return f"{v:,.1f}".rstrip("0").rstrip(".") if v >= 10 else f"{v:,.2f}".rstrip("0").rstrip(".")


def pct_change(new: float, old: float) -> float | None:
    if old == 0 or (old < 0) != (new < 0):
        return None  # growth from zero or across a sign change is not meaningful
    return round((new - old) / abs(old) * 100, 1)


def signed_pct(p: float) -> str:
    return f"{'+' if p > 0 else '−' if p < 0 else ''}{abs(p):g}%"
