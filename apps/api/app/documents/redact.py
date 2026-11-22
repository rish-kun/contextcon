"""PII stripping hook for extracted document text.

A redactor is any callable ``redactor(text) -> (redacted_text, log)`` where ``log``
maps a PII kind to how many spans were replaced. Redacted spans become
``[redacted:<kind>]``.

``regex_redactor`` is the deterministic default (emails, phone numbers, Aadhaar,
PAN, IFSC, bank account numbers). The LLM-assisted redactor lives in
``app/extraction/`` and plugs in through ``chain_redactors(regex_redactor, llm)``
so the model only ever sees text the regex pass has already cleaned.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol


class Redactor(Protocol):
    def __call__(self, text: str, /) -> tuple[str, dict[str, int]]: ...


RedactorFn = Callable[[str], tuple[str, dict[str, int]]]


def _tag(kind: str) -> str:
    return f"[redacted:{kind}]"


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# Account numbers only next to an account keyword, so revenue figures survive.
_BANK_ACCOUNT = re.compile(
    r"(?i)\b(?:a/c|acct|account)(?:\s*(?:no\.?|number|#))?\s*[:.#-]?\s*(\d[\d -]{6,22}\d)\b"
)

# Indian mobile: optional +91 / 91- / 0 prefix, 10 digits starting 6-9, optional 5-5 split.
_PHONE_IN = re.compile(r"(?<![\w+])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

# Other international numbers: + country code, then 7-14 more digits in groups.
_PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}(?:[\s-]?\(?\d{1,5}\)?){2,5}(?!\d)")

# Aadhaar: 12 digits, first 2-9, contiguous or 4-4-4 with one consistent separator.
_AADHAAR = re.compile(r"(?<![\d-])[2-9]\d{3}([ -]?)\d{4}\1\d{4}(?![\d-])")

_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")


def _sub(pattern: re.Pattern[str], kind: str, text: str, group: int = 0) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        if group == 0:
            return _tag(kind)
        start, end = m.span(group)
        base = m.start()
        whole = m.group(0)
        return whole[: start - base] + _tag(kind) + whole[end - base :]

    return pattern.sub(repl, text), count


def _sub_intl_phone(text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        digits = sum(ch.isdigit() for ch in m.group(0))
        if not 8 <= digits <= 15:
            return m.group(0)
        count += 1
        return _tag("phone")

    return _PHONE_INTL.sub(repl, text), count


def regex_redactor(text: str) -> tuple[str, dict[str, int]]:
    """Deterministic PII redaction. Order matters: wider patterns run first."""
    counts: dict[str, int] = {}

    def record(kind: str, n: int) -> None:
        if n:
            counts[kind] = counts.get(kind, 0) + n

    text, n = _sub(_EMAIL, "email", text)
    record("email", n)
    text, n = _sub(_BANK_ACCOUNT, "bank_account", text, group=1)
    record("bank_account", n)
    text, n = _sub(_PHONE_IN, "phone", text)
    record("phone", n)
    text, n = _sub_intl_phone(text)
    record("phone", n)
    text, n = _sub(_AADHAAR, "aadhaar", text)
    record("aadhaar", n)
    text, n = _sub(_PAN, "pan", text)
    record("pan", n)
    text, n = _sub(_IFSC, "ifsc", text)
    record("ifsc", n)
    return text, counts


def chain_redactors(*redactors: RedactorFn) -> RedactorFn:
    """Run redactors in order, each on the previous one's output; counts are summed."""
    if not redactors:
        raise ValueError("at least one redactor is required")

    def chained(text: str) -> tuple[str, dict[str, int]]:
        total: dict[str, int] = {}
        for redactor in redactors:
            text, log = redactor(text)
            for kind, n in log.items():
                total[kind] = total.get(kind, 0) + n
        return text, total

    return chained


def merge_counts(*logs: dict[str, int]) -> dict[str, int]:
    total: dict[str, int] = {}
    for log in logs:
        for kind, n in log.items():
            total[kind] = total.get(kind, 0) + n
    return dict(sorted(total.items()))
