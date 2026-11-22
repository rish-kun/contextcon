"""Trademark/IP claims ask for the mark's registration; customer counts ask for a list."""

from app.domain import Claim, ClaimCategory, ClaimCheck, ClaimComponent, ClaimStatus
from app.rules import policy
from app.rules.claim_status import decide_all, document_for, is_ip_claim
from app.rules.requests import build_request_list

TM_TEXT = (
    "PALMS™ is a registered trademark and Intellectual Property of "
    "Technoforte Software Private Limited"
)


def _claim(id, text, category, components):
    return Claim(
        id=id,
        text=text,
        category=category,
        components=[ClaimComponent(name=n, value=v) for n, v in components],
        entity_ids=["co"],
    )


def _documents(claims):
    checks = [ClaimCheck(claim=c) for c in claims]
    outcomes = decide_all(checks)
    return outcomes, build_request_list(outcomes, {c.id: c for c in claims})


def test_trademark_claim_requests_the_registration_not_incorporation():
    claim = _claim(
        "c-tm",
        TM_TEXT,
        ClaimCategory.OTHER,
        [("trademark", "PALMS"), ("mark_owner", "Technoforte Software Private Limited")],
    )
    outcomes, r = _documents([claim])
    assert outcomes[0].status is ClaimStatus.CANNOT_VERIFY
    assert [d.document for d in r.documents] == [policy.DOC_TRADEMARK]
    assert policy.DOC_INCORPORATION not in outcomes[0].settle_with


def test_ip_claim_categorised_as_identity_still_requests_the_registration():
    claim = _claim(
        "c-tm",
        TM_TEXT,
        ClaimCategory.IDENTITY_INCORPORATION,
        [("legal_name", "Technoforte Software Private Limited")],
    )
    assert is_ip_claim(claim)
    assert document_for("legal_name", claim) == policy.DOC_TRADEMARK
    _, r = _documents([claim])
    assert [d.document for d in r.documents] == [policy.DOC_TRADEMARK]


def test_ip_claim_without_components_falls_back_to_the_registration():
    claim = _claim("c-tm", TM_TEXT, ClaimCategory.OTHER, [])
    outcomes, _ = _documents([claim])
    assert outcomes[0].settle_with == [policy.DOC_TRADEMARK]


def test_plain_identity_claim_keeps_the_incorporation_certificate():
    claim = _claim(
        "c-id",
        "Technoforte Software Private Limited was incorporated in 2004",
        ClaimCategory.IDENTITY_INCORPORATION,
        [("legal_name", "Technoforte Software Private Limited")],
    )
    assert not is_ip_claim(claim)
    assert document_for("legal_name", claim) == policy.DOC_INCORPORATION


def test_customer_count_claim_requests_a_customer_list():
    claim = _claim(
        "c-cust",
        "Trusted by 100+ clients in 20+ countries",
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        [("customer_count", 100), ("country_count", 20)],
    )
    outcomes, r = _documents([claim])
    assert outcomes[0].status is ClaimStatus.CANNOT_VERIFY
    assert [d.document for d in r.documents] == [policy.DOC_CUSTOMER_LIST]
