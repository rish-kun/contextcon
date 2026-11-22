"""Certification standards read from text, and compliance claim statuses."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.domain.enums import ClaimCategory, ClaimStatus, SourceReliability, ValueKind
from app.domain.types import Claim, ClaimCheck, ClaimComponent, Evidence, ExtractedFact, Source
from app.rules import claim_status
from app.rules.claim_status import decide_claim_status, effective_components
from app.rules.compare import compare
from app.rules.standards import standard_relation, standards_in, stated_in
from app.rules.validation import value_in_span

R = SourceReliability


def keys(text: str) -> list[tuple[str, str | None]]:
    return [(s.key, s.qualifier) for s in standards_in(text)]


def test_reads_the_common_ways_standards_are_written():
    assert keys("ISO 9001:2015 and ISO/IEC 27001:2022 certified") == [
        ("iso:9001", None),
        ("iso:27001", None),
    ]
    assert keys("SOC 2 Type II report") == [("soc:2", "type 2")]
    assert keys("SOC2 Type 2") == [("soc:2", "type 2")]
    assert keys("CMMI Level 5") == [("cmmi", "level 5")]
    assert keys("CMMI-DEV ML3") == [("cmmi", "level 3")]
    assert keys("PCI DSS v4.0 Level 1 service provider") == [("pci_dss", "level 1")]
    assert keys("HIPAA and GDPR compliant") == [("hipaa", None), ("gdpr", None)]
    assert keys("PCI express slot") == []
    assert keys("best-in-class security") == []


def test_a_qualified_claim_needs_the_same_qualifier():
    assert standard_relation("SOC 2 Type II", "SOC 2 Type 2 attestation") == "match"
    assert standard_relation("SOC 2 Type II", "SOC 2 Type I report") == "insufficient"
    assert standard_relation("SOC 2", "SOC 2 Type I report") == "match"
    assert standard_relation("ISO 27001", "ISO/IEC 27001:2013") == "match"
    # A page listing other standards is silent, never a contradiction.
    assert standard_relation("ISO 27001", "ISO 9001:2015") == "insufficient"
    assert compare(ValueKind.STANDARD, "ISO 27001", "eq", "ISO 9001") == "insufficient"


def test_span_must_name_the_standard():
    assert stated_in("ISO/IEC 27001:2022", "Standard: ISO/IEC 27001:2022")
    assert not stated_in("ISO 27001", "Standard: ISO 9001:2015")
    assert value_in_span(ValueKind.STANDARD, "ISO 27001", "We hold ISO 27001").valid


def test_expiry_compares_on_or_after():
    assert compare(ValueKind.DATE, "2026-11-22", "gte", "2028-03-14") == "match"
    assert compare(ValueKind.DATE, "2026-11-22", "gte", "2024-03-14") == "conflict"
    assert compare(ValueKind.DATE, "2026-11-22", "eq", "2026-11-22") == "match"


def _claim(value: str) -> Claim:
    return Claim(
        id="c1",
        text=f"We are {value} certified",
        category=ClaimCategory.COMPLIANCE,
        components=[ClaimComponent(name="certification", value=value)],
        entity_ids=["42"],
    )


def test_effective_components_split_standards_and_add_validity(monkeypatch):
    monkeypatch.setattr(claim_status, "today", lambda: date(2026, 11, 22))
    comps = effective_components(_claim("ISO 9001:2015 and ISO/IEC 27001:2022"))
    assert [(c.name, c.value, c.op) for c in comps] == [
        ("certification", "ISO 9001", "eq"),
        ("certification", "ISO 27001", "eq"),
        ("certificate_valid_until", "2026-11-22", "gte"),
    ]


def _fact(i: int, component: str, value: str, quote: str, reliability: R) -> ExtractedFact:
    src = Source(
        id=f"s{i}",
        provider="web",
        label=f"source {i}",
        retrieved_at=datetime(2026, 11, 22),
        reliability=reliability,
        origin_key=f"o{i}",
    )
    ev = Evidence(id=f"e{i}", source=src, entity_id="42", identity_basis=["domain"], quote=quote)
    return ExtractedFact(id=f"f{i}", evidence=ev, component=component, value=value)


@pytest.mark.parametrize(
    ("reliability", "expiry", "expected"),
    [
        (R.REGISTRY, "14 March 2028", ClaimStatus.SUPPORTED),
        (R.COUNTERPARTY_CONFIRMATION, "14 March 2028", ClaimStatus.SUPPORTED),
        (R.REGISTRY, "14 March 2024", ClaimStatus.CONTRADICTED),
        (R.COMPANY_ANNOUNCEMENT, "14 March 2028", ClaimStatus.PARTIALLY_CORROBORATED),
        (R.NEWS, "14 March 2028", ClaimStatus.CANNOT_VERIFY),
    ],
)
def test_compliance_status_by_source_class(monkeypatch, reliability, expiry, expected):
    monkeypatch.setattr(claim_status, "today", lambda: date(2026, 11, 22))
    iso = {"14 March 2028": "2028-03-14", "14 March 2024": "2024-03-14"}[expiry]
    facts = [
        _fact(1, "certification", "ISO/IEC 27001:2022", "ISO/IEC 27001:2022", reliability),
        _fact(1, "certificate_valid_until", iso, f"Valid until {expiry}", reliability),
    ]
    facts[1] = facts[1].model_copy(update={"id": "f2"})
    out = decide_claim_status(ClaimCheck(claim=_claim("ISO 27001"), facts=facts))
    assert out.status is expected, out.reason
    if expected is not ClaimStatus.SUPPORTED:
        assert "auditor's report under NDA" in out.settle_with[0]
