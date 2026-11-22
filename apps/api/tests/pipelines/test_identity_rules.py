"""CP-19 identity rules without a database: corroboration, ambiguity, public terms."""

from __future__ import annotations

import pytest

from app.clients.crustdata_models import IdentifyResult
from app.pipelines.verify.common import PublicTerms
from app.pipelines.verify.comparables import same_activity
from app.pipelines.verify.identity import Expected, decide_identity
from app.pipelines.verify.registry import reliability_for
from tests.pipelines.case_fakes import company

ACME = "Acme Freight (fixture)"
ACME_DOMAIN = "acmefreight.example"
ACME_ID = 700001
CONFIDENTIAL = "We secretly hold a 40 crore unannounced contract with BigRetail"


# --- identity decisions (pure) ------------------------------------------------------


def _results(*matches: dict) -> list[IdentifyResult]:
    return [IdentifyResult.model_validate({"matched_on": "x", "matches": list(matches)})]


def test_name_only_match_not_confirmed() -> None:
    only = company(1, ACME, "other.example")
    decision = decide_identity(Expected(name=ACME), [], _results(only))
    assert decision.state == "unresolved"
    assert decision.chosen is None
    assert decision.candidates[0].matched_keys == []
    assert any(k["key"] == "name" for k in decision.candidates[0].matching)


def test_name_only_several_matches_ambiguous_never_confirmed() -> None:
    decision = decide_identity(
        Expected(name="Shree Logistics (fixture)"),
        [],
        _results(
            company(1, "Shree Logistics (fixture)", "shree-a.example", confidence=0.82),
            company(2, "Shree Logistics (fixture)", "shree-b.example", confidence=0.79),
        ),
    )
    assert decision.state == "ambiguous" and decision.chosen is None


def test_domain_and_id_confirmed() -> None:
    acme = company(ACME_ID, ACME, ACME_DOMAIN)
    expected = Expected(name=ACME, domain=ACME_DOMAIN, crustdata_company_id=ACME_ID)
    decision = decide_identity(expected, _results(acme), _results(acme))
    assert decision.state == "confirmed"
    assert set(decision.chosen.matched_keys) == {"crustdata_company_id", "domain"}


def test_domain_and_name_disagree_unresolved() -> None:
    expected = Expected(name="Beta Cargo (fixture)", domain=ACME_DOMAIN)
    decision = decide_identity(
        expected,
        _results(company(ACME_ID, ACME, ACME_DOMAIN)),
        _results(company(2, "Beta Cargo (fixture)", "betacargo.example")),
    )
    assert decision.state == "unresolved"
    assert {c.crustdata_company_id for c in decision.candidates} == {ACME_ID, 2}


def test_ambiguous_group_domain_decision() -> None:
    group = "groupco.example"
    expected = Expected(name="GroupCo Logistics (fixture)", domain=group)
    decision = decide_identity(
        expected,
        _results(
            company(11, "GroupCo Logistics (fixture)", group),
            company(12, "GroupCo Warehousing (fixture)", group),
        ),
        [],
    )
    assert decision.state == "ambiguous"
    assert all("domain" in c.matched_keys for c in decision.candidates)


def test_registry_reliability_by_host() -> None:
    assert reliability_for("https://www.mca.gov.in/mcafoportal/x") == "registry"
    assert reliability_for("https://www.zaubacorp.com/company/x") == "registry_mirror"
    assert reliability_for("https://news.example/x") is None


def test_public_terms_reject_free_text() -> None:
    with pytest.raises(ValueError):
        PublicTerms(name=CONFIDENTIAL + " " * 100 + "x" * 50)
    with pytest.raises(ValueError):
        PublicTerms(name=ACME, domain="https://acme.example/path?q=secret")
    with pytest.raises(ValueError):
        PublicTerms(name=ACME, cin="not-a-cin")


def test_primary_domain_holder_beats_secondary_domain_listing() -> None:
    expected = Expected(name="Acme Freight", domain=ACME_DOMAIN)
    main = company(ACME_ID, "Acme Freight", ACME_DOMAIN, confidence=1.0)
    side = company(2, "Acme Freight Services (fixture)", "afs.example", all_domains=[ACME_DOMAIN])
    decision = decide_identity(expected, _results(main, side), _results(main))
    assert decision.state == "confirmed"
    assert decision.chosen.crustdata_company_id == ACME_ID
    assert "secondary domain" in decision.note


def test_secondary_listing_alone_with_stronger_rival_stays_ambiguous() -> None:
    # The secondary-domain record matches on more identifiers: no tie-break.
    expected = Expected(name="Acme Freight", domain=ACME_DOMAIN, founded_year=2001)
    main = company(ACME_ID, "Acme Freight", ACME_DOMAIN, founded=2014)
    side = company(
        2, "Acme Freight Services", "afs.example", all_domains=[ACME_DOMAIN], founded=2001
    )
    decision = decide_identity(expected, _results(main, side), [])
    assert decision.state == "ambiguous"


def test_name_found_record_claiming_the_domain_is_a_possible_duplicate() -> None:
    # Seen live: a thin record found by name lists the company's domain on its profile,
    # but the domain lookup returns only the real owner.
    expected = Expected(name="Acme Freight", domain=ACME_DOMAIN)
    owner = company(ACME_ID, "Acme Freight", ACME_DOMAIN, confidence=1.0)
    squatter = company(2, "E Commerce Acme Freight Services", ACME_DOMAIN, confidence=0.8)
    decision = decide_identity(expected, _results(owner), _results(owner, squatter))
    assert decision.state == "confirmed" and decision.chosen.crustdata_company_id == ACME_ID
    assert "Possible duplicate" in decision.note
    other = next(c for c in decision.candidates if c.crustdata_company_id == 2)
    assert other.matched_keys == []
    assert any(k["key"] == "domain_claimed" for k in other.matching)


def test_name_found_domain_claimer_counts_when_domain_lookup_finds_nothing() -> None:
    expected = Expected(name="Acme Freight", domain=ACME_DOMAIN)
    only = company(ACME_ID, "Acme Freight", ACME_DOMAIN)
    decision = decide_identity(expected, [], _results(only))
    assert decision.state == "confirmed" and decision.chosen.matched_keys == ["domain"]


def test_same_activity_needs_more_than_generic_overlap() -> None:
    parcel = [
        "E-Commerce",
        "Freight Service",
        "Last Mile Transportation",
        "Logistics",
        "Shipping",
        "Supply Chain Management",
        "Transportation",
        "Warehousing",
    ]
    airline = ["Airlines", "Air Transportation", "Transportation", "Logistics", "Travel"]
    courier = ["Courier", "Logistics", "Last Mile Transportation", "Shipping", "Freight Service"]
    assert not same_activity(parcel, airline)
    assert same_activity(parcel, courier)
    assert not same_activity(parcel, [])
