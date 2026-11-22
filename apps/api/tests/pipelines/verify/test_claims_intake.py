"""CP-20: claim intake from uploads and typed claims."""

import uuid

import pytest
from sqlalchemy import select

import app.pipelines.verify.claims.steps  # noqa: F401  (registers the step handler)
from app.api.claims import typed_claim_llm
from app.api.documents import max_upload_mb
from app.db.models import Claim, ClaimCheck, Document, ExtractedText, Step
from app.documents.extract import NO_TEXT_LAYER_REASON
from app.jobs import registry
from app.pipelines.verify.checks.clients import set_client_factory
from app.pipelines.verify.claims.components import public_components
from app.pipelines.verify.claims.intake import CHECK_HANDLER, EXTRACT_HANDLER
from app.pipelines.verify.claims.ledger import build_claims_section
from tests.auth.helpers import account, login
from tests.documents.conftest import make_pdf, make_scanned_pdf
from tests.jobs.helpers import make_worker
from tests.pipelines.verify.fakes import FakeFactory, RoutedLlm

pytestmark = pytest.mark.asyncio

PDF = "application/pdf"


async def _signed_in(client, session, name="asha"):
    acct = await account(session, name)
    assert (await login(client, acct.email)).status_code == 200
    return acct


def _upload(client, case_id, data: bytes, filename="deck.pdf", kind="seller_deck"):
    return client.post(
        f"/cases/{case_id}/documents",
        files={"file": (filename, data, PDF)},
        data={"kind": kind},
    )


async def _drain(sm) -> None:
    worker = make_worker(sm, registry)
    await worker.drain()


# --- Typed claims ---------------------------------------------------------------


def _typed_llm(sentence: str, category: str, raw: list[dict], normalised: list[dict]):
    return RoutedLlm(
        responders={
            "ClaimsDraft": {
                "claims": [
                    {
                        "assertion": sentence,
                        "category": category,
                        "components": raw,
                        "quote": sentence,
                        "page": None,
                    }
                ]
            },
            "NormaliseDraft": {"claims": [{"index": 0, "components": normalised}]},
        }
    )


async def test_typed_claim_is_stored_with_origin_typed_and_queued(api, client, session):
    acct = await _signed_in(client, session)
    sentence = "Incorporated in 2014, based in Pune"
    llm = _typed_llm(
        sentence,
        "identity_incorporation",
        [{"name": "year", "value": "2014"}, {"name": "city", "value": "Pune"}],
        [
            {"name": "incorporation_year", "value": "2014"},
            {"name": "hq_city", "value": "Pune"},
            {"name": "employer", "value": "Acme"},  # not in the claim: dropped
        ],
    )
    api.dependency_overrides[typed_claim_llm] = lambda: lambda case: llm

    response = await client.post(f"/cases/{acct.case.id}/claims", json={"text": sentence})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["origin"] == "typed"
    assert body["original_text"] == sentence
    assert body["category"] == "identity_incorporation"
    assert body["components"] == {"incorporation_year": 2014, "hq_city": "Pune"}
    assert body["stated_in"]["quote"] == sentence
    assert body["stated_in"]["typed_by_name"] == acct.user.display_name
    assert body["status"] == "not_checked"  # queued, never shown as clean

    row = (await session.execute(select(Claim).where(Claim.case_id == acct.case.id))).scalar_one()
    assert row.origin == "typed"
    assert row.delete_after is not None
    steps = list((await session.execute(select(Step))).scalars())
    assert [(s.handler, s.key) for s in steps] == [(CHECK_HANDLER, f"checks.claim:{row.id}")]
    assert steps[0].uses_budget is False and steps[0].tolerate_failed_deps is True


async def test_typed_claim_text_is_regex_redacted_before_the_model(api, client, session):
    acct = await _signed_in(client, session)
    llm = RoutedLlm()
    api.dependency_overrides[typed_claim_llm] = lambda: lambda case: llm
    text = "Our CFO is reachable at cfo@example.com or +91 98765 43210"
    response = await client.post(f"/cases/{acct.case.id}/claims", json={"text": text})
    assert response.status_code == 201, response.text
    sent = " ".join(u for _, u in llm.calls)
    assert "cfo@example.com" not in sent and "98765" not in sent
    assert response.json()["category"] == "other"  # nothing checkable: kept, not dropped


async def test_typed_claim_needs_a_session_and_the_right_workspace(api, client, session):
    other = await account(session, "bea")
    acct = await _signed_in(client, session)
    api.dependency_overrides[typed_claim_llm] = lambda: lambda case: RoutedLlm()
    assert (
        await client.post(f"/cases/{other.case.id}/claims", json={"text": "x y z"})
    ).status_code == 404
    client.cookies.clear()
    assert (
        await client.post(f"/cases/{acct.case.id}/claims", json={"text": "x y z"})
    ).status_code == 401


# --- Uploads: size and type -------------------------------------------------------


async def test_upload_too_large_is_rejected_413(api, client, session, storage):
    acct = await _signed_in(client, session)
    api.dependency_overrides[max_upload_mb] = lambda: 1
    big = make_pdf(["x"]) + b"0" * (1024 * 1024 + 10)
    response = await _upload(client, acct.case.id, big)
    assert response.status_code == 413, response.text
    assert (await session.execute(select(Document))).first() is None
    assert not storage.root.exists() or not list(storage.root.rglob("*.pdf"))


async def test_upload_unsupported_type_is_rejected_415(api, client, session):
    acct = await _signed_in(client, session)
    exe = await _upload(client, acct.case.id, b"MZ\x90\x00binary", filename="deck.exe")
    assert exe.status_code == 415, exe.text
    disguised = await _upload(client, acct.case.id, b"just text, not a pdf", filename="deck.pdf")
    assert disguised.status_code == 415, disguised.text
    assert (await session.execute(select(Document))).first() is None


# --- Uploads: scanned and text PDFs -------------------------------------------------


async def test_scanned_pdf_gives_a_not_checked_claim_with_the_reason(api, client, session, sm):
    acct = await _signed_in(client, session)
    llm = RoutedLlm()
    set_client_factory(FakeFactory(llm_client=llm))
    response = await _upload(client, acct.case.id, make_scanned_pdf(2), filename="scan.pdf")
    assert response.status_code == 201, response.text
    assert response.json()["run"]["kind"] == "verify"

    await _drain(sm)

    assert llm.calls == []  # nothing readable, so nothing sent to the model
    claim = (await session.execute(select(Claim))).scalar_one()
    assert claim.origin == "deck"
    assert "no text layer" in claim.original_text
    check = (await session.execute(select(ClaimCheck))).scalar_one()
    assert check.status == "not_checked"
    assert "no text layer" in check.reason
    case = acct.case
    [out] = await build_claims_section(session, case)
    assert out.status == "not_checked"
    assert out.not_checked_reason == "source_unavailable"
    assert NO_TEXT_LAYER_REASON.split(" (")[0] in out.reason
    # No check step was scheduled for the unreadable claim.
    handlers = [s.handler for s in (await session.execute(select(Step))).scalars()]
    assert handlers == [EXTRACT_HANDLER]


def _deck_llm():
    def claims(system, user):
        return {
            "claims": [
                {
                    "assertion": "We employ 250 people",
                    "category": "team_size",
                    "components": [{"name": "count", "value": "250"}],
                    "quote": "We employ 250 people",
                    "page": 2,
                },
                {
                    "assertion": "Tata Steel is our largest customer",
                    "category": "customer_partnership",
                    "components": [{"name": "customer", "value": "Tata Steel"}],
                    "quote": "Tata Steel is our largest customer",
                    "page": 2,
                },
                {
                    "assertion": "We have no debt",
                    "category": "debt_security",
                    "components": [],
                    "quote": "We have no debt",
                    "page": 1,
                },
                {
                    "assertion": "FY25 revenue was INR 80 crore",
                    "category": "financials",
                    "components": [],
                    "quote": "FY25 revenue was INR 80 crore",
                    "page": 1,
                },
                {
                    "assertion": "We serve 40 enterprise clients",
                    "category": "customer_partnership",
                    "components": [],
                    "quote": "We serve forty enterprise clients",  # not in the document
                    "page": 1,
                },
            ]
        }

    normalised = {
        "claims": [
            {"index": 0, "components": [{"name": "employee_count", "value": "250"}]},
            {"index": 1, "components": [{"name": "counterparty", "value": "Tata Steel"}]},
            {"index": 2, "components": [{"name": "has_debt", "value": "false"}]},
            {"index": 3, "components": [{"name": "revenue", "value": "80 crore"}]},
        ]
    }
    return RoutedLlm(responders={"ClaimsDraft": claims, "NormaliseDraft": normalised})


async def test_document_claims_keep_assertion_quote_page_components_and_retention(
    api, client, session, sm
):
    acct = await _signed_in(client, session)
    llm = _deck_llm()
    set_client_factory(FakeFactory(llm_client=llm))
    pages = [
        "We have no debt. FY25 revenue was INR 80 crore. Contact ceo@example.com",
        "We employ 250 people. Tata Steel is our largest customer. Call 9876543210",
    ]
    response = await _upload(client, acct.case.id, make_pdf(pages))
    assert response.status_code == 201, response.text
    doc_out = response.json()
    assert doc_out["redaction_counts"].get("email") == 1
    assert doc_out["delete_after"]

    await _drain(sm)

    doc = (await session.execute(select(Document))).scalar_one()
    texts = list((await session.execute(select(ExtractedText))).scalars())
    assert texts and all(t.delete_after == doc.delete_after for t in texts)
    assert all("ceo@example.com" not in t.text and "9876543210" not in t.text for t in texts)
    # Personal details never reach the model.
    sent = " ".join(u for _, u in llm.calls)
    assert "ceo@example.com" not in sent and "9876543210" not in sent

    claims = {
        c.original_text: c
        for c in (await session.execute(select(Claim).order_by(Claim.created_at))).scalars()
    }
    # The unquoted claim was dropped; every category is kept, including ones
    # with no v1 source.
    assert set(claims) == {
        "We employ 250 people",
        "Tata Steel is our largest customer",
        "We have no debt",
        "FY25 revenue was INR 80 crore",
    }
    team = claims["We employ 250 people"]
    assert (team.category, team.page, team.quote) == ("team_size", 2, "We employ 250 people")
    assert team.components["components"] == [{"name": "employee_count", "value": 250, "op": "eq"}]
    assert team.components["raw"] == {"count": "250"}
    assert team.origin == "deck" and team.document_id == doc.id
    assert all(c.delete_after == doc.delete_after for c in claims.values())
    assert public_components(claims["We have no debt"].components) == {"has_debt": False}
    revenue = public_components(claims["FY25 revenue was INR 80 crore"].components)
    assert revenue == {"revenue": 800_000_000}

    steps = {s.key: s for s in (await session.execute(select(Step))).scalars()}
    for c in claims.values():
        step = steps[f"checks.claim:{c.id}"]
        assert step.handler == CHECK_HANDLER
        assert f"claims.extract:{doc.id}" in step.depends_on

    ledger = await build_claims_section(session, acct.case)
    assert [o.number for o in ledger] == [1, 2, 3, 4]
    assert {o.origin for o in ledger} == {"document"}
    assert all(o.stated_in.filename == "deck.pdf" for o in ledger)


async def test_document_url_is_scoped_to_the_workspace(api, client, session, sm):
    acct = await _signed_in(client, session)
    set_client_factory(FakeFactory(llm_client=RoutedLlm()))
    response = await _upload(client, acct.case.id, make_pdf(["Founded in 2014."]))
    doc_id = response.json()["id"]
    ok = await client.get(f"/documents/{doc_id}/url")
    assert ok.status_code == 200 and f"cases/{acct.case.id}/" in ok.json()["url"]
    other = await account(session, "bea")
    await client.post("/auth/logout")
    await login(client, other.email)
    assert (await client.get(f"/documents/{doc_id}/url")).status_code == 404
    assert (await client.get(f"/documents/{uuid.uuid4()}/url")).status_code == 404
