"""CP-25: memo, case detail, cost readout, retention notice and the policy route."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2 as httpx
import pytest
from sqlalchemy import select

from app.db import ledger
from app.db.models import (
    AssessmentVersion,
    Candidate,
    Case,
    DiscoveryRun,
    Document,
    Evidence,
    Run,
    Thesis,
)
from app.drafting import check_citations
from app.jobs.purge import purge_expired
from app.main import create_app
from app.pipelines import evaluate
from app.pipelines.memo import detail, drafting
from app.rules import policy
from tests.evaluate.builders import (
    TODAY,
    api_client,
    check,
    confirmed_world,
    quote,
    source,
)

pytestmark = pytest.mark.asyncio


class ScriptedLlm:
    """Returns the scripted drafts in order (the last one repeats)."""

    def __init__(self, *drafts: str) -> None:
        self.drafts = list(drafts)
        self.calls = 0

    async def draft_text(self, system: str, user: str):
        text = self.drafts[min(self.calls, len(self.drafts) - 1)]
        self.calls += 1
        return text, None


async def _evaluate(session, w, llm=None, **kw):
    out = await evaluate.evaluate_case(
        session,
        w.t.workspace.id,
        w.t.case.id,
        today=TODAY,
        enrich=drafting.build_memo_document,
        enrich_arg=llm,
        **kw,
    )
    await session.commit()
    return out


async def test_case_detail_sections_complete(sm, session) -> None:
    w = await confirmed_world(session)
    v1 = await _evaluate(session, w)
    stored = v1.version.judgments["memo"]
    assert set(stored["drafted"]) == {"relevance", "profile"}
    assert stored["drafted"]["profile"]["used_fallback"] is True  # no model configured

    async with api_client(sm, w.t.workspace.id) as client:
        res = await client.get(f"/cases/{w.t.case.id}")
    assert res.status_code == 200, res.text
    body = res.json()
    m = body["memo"]
    assert [s["key"] for s in m["sections"]] == [
        "summary",
        "opportunity",
        "identity",
        "claims",
        "events",
        "comparables",
        "financial",
        "risks",
        "next_step",
        "requests",
        "sources",
    ]
    assert [s["number"] for s in m["sections"][1:]] == list(range(1, 11))
    assert m["assessment_version"] == 1 and m["policy_version"] == policy.POLICY_VERSION
    profile = next(s for s in m["sections"] if s["key"] == "identity")
    assert "Year founded: 2014 [F" in profile["drafted_text"]
    cited = {c["id"]: c for c in m["citations"]}
    assert cited and all(c["evidence"]["source"]["retrieved_at"] for c in cited.values())
    claims = next(s for s in m["sections"] if s["key"] == "claims")
    assert any("We have 250 employees" in line["text"] for line in claims["lines"])
    assert any("Cannot verify" in line["text"] for line in claims["lines"])

    assert body["assessment"]["version"] == 1
    assert body["opportunity"]["fit_state"] == "scored"
    assert body["claims"][0]["status"] == "cannot_verify"
    assert {r["kind"] for r in body["risks"]} >= {"gap", "estimate_used"}
    src = body["sources"][0]
    assert src["request_hash"] and len(src["request_hash"]) == 64
    assert src["retrieved_at"] and src["url_or_endpoint"] == "/company/enrich"
    assert body["cost"]["credit_budget"] == 150


async def test_uncited_memo_sentence_is_rejected(session) -> None:
    w = await confirmed_world(session)
    llm = ScriptedLlm(
        "The company is a strong logistics player.",
        "Founded in 2014, it has 900 staff [F3].",
    )
    out = await _evaluate(session, w, llm=llm)
    for section in out.version.judgments["memo"]["drafted"].values():
        assert section["used_fallback"] is True
        assert section["rejected_attempts"] == 2
        assert "strong logistics player" not in section["text"]
    report = check_citations("The company is a strong logistics player.", {"F1": "Founded 2014"})
    assert not report.ok and "sentence has no citation" in report.issues[0]


async def test_cited_draft_is_kept(session) -> None:
    w = await confirmed_world(session)
    book, facts = await drafting.accepted_facts(
        session,
        await session.get(Case, w.t.case.id),
        await evaluate.load_inputs(session, await session.get(Case, w.t.case.id), today=TODAY),
        (await _evaluate(session, w)).assessment,
    )
    ids = {f.citation_id: f.statement for f in facts["profile"]}
    year = next(cid for cid, text in ids.items() if text.startswith("Year founded"))
    good = f"The company was founded in 2014 [{year}]."
    out = await drafting._draft(ScriptedLlm(good), "profile", facts["profile"])
    assert out.text == good and not out.used_fallback


async def test_memo_is_kept_per_version(session) -> None:
    w = await confirmed_world(session)
    v1 = await _evaluate(session, w)
    doc_src = await source(
        session,
        w.t,
        provider="upload",
        endpoint="upload://payroll_summary.pdf",
        source_class="seller_document",
        title="payroll_summary.pdf, p. 2",
        request={"document_type": "payroll_record"},
    )
    ev = await quote(session, w.t, doc_src, "Total employees on payroll: 250", "250", page=2)
    await check(session, w.claim, "supported", [(ev, "employee_count")])
    await session.commit()
    v2 = await _evaluate(session, w)
    assert v2.created
    rows = (
        (
            await session.execute(
                select(AssessmentVersion)
                .where(AssessmentVersion.case_id == w.t.case.id)
                .order_by(AssessmentVersion.version)
            )
        )
        .scalars()
        .all()
    )
    assert [("memo" in r.judgments) for r in rows] == [True, True]
    assert rows[0].id == v1.version.id
    built = await detail.build_case_detail(session, w.t.workspace.id, w.t.case.id)
    keys = [s.key for s in built.memo.sections]
    assert keys[1] == "changes"
    changes = built.memo.sections[1]
    assert any("payroll_summary.pdf, p. 2" in line.text for line in changes.lines)


async def test_cost_is_not_double_counted(session) -> None:
    w = await confirmed_world(session)
    thesis = Thesis(workspace_id=w.t.workspace.id, text="Logistics (fixture)")
    session.add(thesis)
    await session.flush()
    dr = DiscoveryRun(workspace_id=w.t.workspace.id, thesis_id=thesis.id)
    session.add(dr)
    await session.flush()
    discover_run = Run(workspace_id=w.t.workspace.id, kind="discover", discovery_run_id=dr.id)
    cand = Candidate(discovery_run_id=dr.id, crustdata_company_id="4242", name="Example")
    session.add_all([discover_run, cand])
    await session.flush()
    case = await session.get(Case, w.t.case.id)
    case.candidate_id = cand.id
    verify_run = Run(workspace_id=w.t.workspace.id, kind="verify", case_id=case.id)
    session.add(verify_run)
    await session.flush()

    shared = ledger.CostContext(workspace_id=w.t.workspace.id, discovery_run_id=dr.id)
    await ledger.record_cost(
        session,
        shared.for_step(discover_run.id, None),
        provider="crustdata",
        endpoint="/company/search",
        credits=Decimal("37"),
    )
    own = ledger.CostContext(workspace_id=w.t.workspace.id, case_id=case.id)
    ctx = own.for_step(verify_run.id, None)
    await ledger.record_cost(
        session, ctx, provider="crustdata", endpoint="/company/enrich", credits=Decimal("12")
    )
    await ledger.record_cost(
        session,
        ctx,
        provider="anthropic",
        endpoint="messages",
        usd=Decimal("0.0042"),
        input_tokens=900,
        output_tokens=120,
    )
    # Reusing discovery's cached enrich: zero cost, linked to the run that paid.
    await ledger.record_cost(
        session,
        ctx,
        provider="crustdata",
        endpoint="/company/enrich",
        cached=True,
        shared_from_run_id=discover_run.id,
    )
    await ledger.record_cost(
        session, ctx, provider="crustdata", endpoint="/web/search/live", unknown=True
    )
    await session.commit()

    cost = (await detail.build_case_detail(session, w.t.workspace.id, case.id)).cost
    assert cost.crustdata_credits == 12.0
    assert cost.llm_usd == pytest.approx(0.0042)
    assert cost.unknown_cost_calls == 1
    assert cost.shared_discovery is not None
    assert cost.shared_discovery.run_id == str(discover_run.id)
    assert cost.shared_discovery.cost.crustdata_credits == 37.0
    assert sum(line.cost.crustdata_credits for line in cost.by_step) == 12.0
    # Workspace spend counts every credit once.
    assert (await ledger.workspace_totals(session, w.t.workspace.id)).credits == Decimal("49")


class Deleter:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, path: str) -> None:
        self.deleted.append(path)


async def test_purged_document_shows_its_deletion_record(sm, session) -> None:
    w = await confirmed_world(session)
    past = datetime.now(UTC) - timedelta(days=1)
    doc = Document(
        case_id=w.t.case.id,
        kind="seller_response",
        filename="payroll_summary.pdf",
        mime="application/pdf",
        gcs_path=f"cases/{w.t.case.id}/doc/payroll_summary.pdf",
        delete_after=past,
    )
    session.add(doc)
    await session.flush()
    doc_src = await source(
        session,
        w.t,
        provider="upload",
        endpoint="upload://payroll_summary.pdf",
        source_class="seller_document",
        title="payroll_summary.pdf, p. 2",
        request={"document_type": "payroll_record"},
        document_id=doc.id,
    )
    ev = await quote(session, w.t, doc_src, "Total employees on payroll: 250", "250", page=2)
    ev_row = await session.get(Evidence, ev.id)
    ev_row.delete_after = past
    await check(session, w.claim, "supported", [(ev, "employee_count")])
    await session.commit()
    await _evaluate(session, w)  # version 1 rests on the payroll page

    deleter = Deleter()
    report = await purge_expired(sm, deleter)
    assert report.documents == 1 and report.evidence_scrubbed == 1
    assert deleter.deleted == [doc.gcs_path]

    async with api_client(sm, w.t.workspace.id) as client:
        detail = (await client.get(f"/cases/{w.t.case.id}")).json()
        history = (await client.get(f"/cases/{w.t.case.id}/assessments")).json()

    [d] = detail["documents"]
    assert d["purged"] is True and d["delete_after"]
    record = next(r for r in detail["deletions"] if r["artifact_kind"] == "document")
    assert record["artifact_id"] == str(doc.id)
    assert record["original_filename"] == "payroll_summary.pdf"
    assert "Attachment 'payroll_summary.pdf' deleted" in record["reason"]
    assert "30-day retention schedule" in record["reason"]
    src = next(s for s in detail["sources"] if s["source_id"] == str(doc_src.id))
    assert src["excerpt"] is None and src["deleted_at"]
    assert "payroll_summary.pdf" in src["deletion_reason"]
    assert (
        "Already deleted under the retention schedule: payroll_summary.pdf"
        in (detail["memo"]["retention_notice"])
    )
    # Version 1 still explains itself: the excerpt it rested on is marked deleted.
    assert history[0]["version"] == 1
    claim = detail["claims"][0]
    [chip] = [e for e in claim["evidence"] if e["evidence_id"] == str(ev.id)]
    assert chip["deleted"] is True and chip["quote"] is None


async def test_get_policy_is_public_and_matches_the_rules() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.get("/policy")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["policy_version"] == policy.POLICY_VERSION
    assert body["markdown"].startswith("# DealProof scoring")
    assert policy.POLICY_VERSION in body["markdown"]
    assert body["thresholds"]["prioritise_fit_min"] == policy.PRIORITISE_MIN_FIT
    assert [r["disposition"] for r in body["disposition_rules"]] == [
        "cannot_assess",
        "deprioritise",
        "prioritise",
        "investigate_further",
    ]
    payroll = next(a for a in body["adequate_sources"] if a["component"] == "employee_count")
    assert "professional_profile_signal" not in payroll["source_classes"]


async def test_case_detail_needs_a_session() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.get("/cases/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 401
