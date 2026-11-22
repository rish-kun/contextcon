"""Certification and compliance standards, read from text. Pure; no I/O.

A compliance claim names one or more standards ("ISO 9001:2015 and ISO/IEC
27001:2022", "SOC 2 Type II", "CMMI Level 5"). Evidence writes them in many ways
("ISO/IEC 27001:2022", "ISO 27001", "SOC 2 Type 2"). Both sides are read into
`Standard` values so they compare on the standard itself:

- `key` names the standard ("iso:27001", "soc:2", "cmmi", "pci_dss", "hipaa").
- `qualifier` is the part a claim may be specific about: the SOC report type
  ("type 2"), the CMMI maturity level ("level 5"), the PCI DSS level. A claim
  that names a qualifier is matched only by evidence with the same one; a claim
  without one is matched by any.
- The edition year (":2015", ":2022") is kept for display but never decides a
  match: certification bodies re-issue under new editions.

`label` is the short public name used in search queries ("ISO 27001", "SOC 2").
Only labels built here ever leave the system, never the claim's own wording.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.rules.compare import normalize_text


@dataclass(frozen=True)
class Standard:
    key: str
    label: str
    qualifier: str | None = None
    edition: str | None = None

    @property
    def display(self) -> str:
        parts = [self.label]
        if self.qualifier:
            parts.append(self.qualifier.title())
        return " ".join(parts)


_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}

# Patterns run on the raw text (case-insensitive). Order matters only for display.
_ISO = re.compile(
    r"\bISO(?:\s*/\s*(?:IEC|TS|TR))?(?:\s*/\s*IEC)?[\s-]*(\d{4,5})(?:[-‐](\d{1,2}))?"
    r"(?:\s*:\s*((?:19|20)\d{2}))?",
    re.IGNORECASE,
)
_SOC = re.compile(
    r"\bSOC\s*-?\s*([123])\b(?:\s*,?\s*Type\s*-?\s*(I{1,2}|[12])\b)?",
    re.IGNORECASE,
)
_CMMI = re.compile(
    r"\bCMMI(?:\s*(?:-|for)?\s*(?:DEV|SVC|Development|Services))?"
    r"(?:\s*(?:\(|,|-)?\s*(?:Maturity\s+)?(?:Level|ML)\s*-?\s*([1-5]|I{1,3}|IV|V)\b)?",
    re.IGNORECASE,
)
_PCI = re.compile(
    r"\bPCI(?:\s*[-‐]?\s*DSS)?\b(?:\s*(?:v\s*\d(?:\.\d)?))?"
    r"(?:\s*(?:\(|,|-)?\s*Level\s*([1-4])\b)?",
    re.IGNORECASE,
)
_SIMPLE: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\bHIPAA\b", re.IGNORECASE), "hipaa", "HIPAA"),
    (re.compile(r"\bGDPR\b", re.IGNORECASE), "gdpr", "GDPR"),
    (re.compile(r"\bHITRUST\b", re.IGNORECASE), "hitrust", "HITRUST"),
    (re.compile(r"\bFedRAMP\b", re.IGNORECASE), "fedramp", "FedRAMP"),
    (re.compile(r"\bCSA\s+STAR\b", re.IGNORECASE), "csa_star", "CSA STAR"),
)


def _level(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip().casefold()
    return _ROMAN.get(raw, raw)


def standards_in(text: Any) -> list[Standard]:
    """Every standard named in `text`, in order of first appearance, de-duplicated
    on (key, qualifier)."""
    if text is None:
        return []
    s = str(text)
    found: list[tuple[int, Standard]] = []
    for m in _ISO.finditer(s):
        number = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
        found.append((m.start(), Standard(f"iso:{number}", f"ISO {number}", None, m.group(3))))
    for m in _SOC.finditer(s):
        kind = _level(m.group(2))
        found.append(
            (
                m.start(),
                Standard(
                    f"soc:{m.group(1)}", f"SOC {m.group(1)}", f"type {kind}" if kind else None
                ),
            )
        )
    for m in _CMMI.finditer(s):
        level = _level(m.group(1))
        found.append((m.start(), Standard("cmmi", "CMMI", f"level {level}" if level else None)))
    for m in _PCI.finditer(s):
        # A bare "PCI" is not a standard name; "PCI DSS" is.
        if "dss" not in m.group(0).casefold():
            continue
        level = m.group(1)
        found.append(
            (m.start(), Standard("pci_dss", "PCI DSS", f"level {level}" if level else None))
        )
    for pattern, key, label in _SIMPLE:
        for m in pattern.finditer(s):
            found.append((m.start(), Standard(key, label)))
    seen: set[tuple[str, str | None]] = set()
    out: list[Standard] = []
    for _, std in sorted(found, key=lambda t: t[0]):
        ident = (std.key, std.qualifier)
        if ident in seen:
            continue
        # "SOC 2" next to "SOC 2 Type II" adds nothing.
        if std.qualifier is None and any(o.key == std.key for o in out):
            continue
        if std.qualifier is not None:
            out = [o for o in out if not (o.key == std.key and o.qualifier is None)]
            seen.discard((std.key, None))
        seen.add(ident)
        out.append(std)
    return out


def satisfies(claimed: Standard, found: Standard) -> bool:
    """Does `found` (from evidence) state the standard `claimed` asserts?"""
    if claimed.key != found.key:
        return False
    return claimed.qualifier is None or claimed.qualifier == found.qualifier


def standard_relation(claimed: Any, fact_value: Any) -> str:
    """`match` when the fact names every standard the claimed value names (with
    any qualifier the claim gives), else `insufficient`. A page that lists other
    standards is silent about this one, never a contradiction."""
    wanted = standards_in(claimed)
    have = standards_in(fact_value)
    if not wanted or not have:
        # Neither side reads as a known standard: fall back to the words.
        a, b = normalize_text(claimed), normalize_text(fact_value)
        return "match" if a and f" {a} " in f" {b} " else "insufficient"
    if all(any(satisfies(w, h) for h in have) for w in wanted):
        return "match"
    return "insufficient"


def stated_in(value: Any, span: str) -> bool:
    """Is every standard in `value` stated by `span`? (span validation)"""
    return standard_relation(value, span) == "match"
