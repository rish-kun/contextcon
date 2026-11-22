"""Assessment versions keep seller-derived text in an expiring payload, and record the
documents and evidence they rest on."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db.models import AssessmentVersion, ConfidentialPayload, Document
from app.jobs.purge import purge_expired
from app.pipelines import evaluate
from tests.evaluate.builders import TODAY, api_client, check, confirmed_world, quote, source

pytestmark = pytest.mark.asyncio


async def _payroll_document(session, w, *, delete_after=None):
    doc = Document(
        case_id=w.t.case.id,
        kind="seller_response",
        filename="accounts.pdf",
        mime="application/pdf",
        gcs_path=f"cases/{w.t.case.id}/d/accounts.pdf",
        delete_after=delete_after or datetime.now(UTC) + timedelta(days=30),
    )
    session.add(doc)
    await session.flush()
    src = await source(
        session,
        w.t,
        provider="upload",
        endpoint="upload://accounts.pdf",
        source_class="seller_document",
        title="accounts.pdf, p. 2",
        request={"document_type": "payroll_record"},
        document_id=doc.id,
    )
    ev = await quote(session, w.t, src, "Total employees on payroll: 250", "250", page=2)
    await check(session, w.claim, "supported", [(ev, "employee_count")])
    await session.commit()
    return doc, ev


async def _evaluate(session, w, **kw):
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY, **kw)
    await session.commit()
    return out


async def test_version_records_its_trigger_documents_and_evidence(session) -> None:
    w = await confirmed_world(session)
    v1 = await _evaluate(session, w)
    assert v1.version.trigger_document_ids == [] and v1.version.document_ids == []
    assert v1.version.evidence_ids  # the profile evidence behind fit and the claim

    doc, ev = await _payroll_document(session, w)
    v2 = await _evaluate(session, w, trigger="seller documents accounts.pdf")
    assert v2.version.trigger_document_ids == [str(doc.id)]
    assert v2.version.document_ids == [str(doc.id)]
    assert str(ev.id) in v2.version.evidence_ids
    [view] = await evaluate.list_versions_out(session, w.t.case.id, [v2.version])
    assert view.trigger_document_ids == [str(doc.id)]
    assert str(ev.id) in view.evidence_ids


async def test_step_input_document_ids_are_recorded(session) -> None:
    w = await confirmed_world(session)
    spec = evaluate.evaluate_step(trigger="seller documents", document_ids=["d-1"])
    assert spec.input == {"trigger": "seller documents", "document_ids": ["d-1"]}
    out = await _evaluate(session, w, trigger_document_ids=["d-1"])
    assert out.version.trigger_document_ids == ["d-1"]


async def test_seller_text_is_not_in_the_immutable_version(session) -> None:
    w = await confirmed_world(session)
    await _evaluate(session, w)
    await _payroll_document(session, w)
    v2 = await _evaluate(session, w)
    stored = json.dumps([v2.version.judgments, v2.version.diff_from_previous])
    assert "Total employees on payroll" not in stored
    assert "accounts.pdf" not in stored
    assert '"250"' not in stored
    payload = (
        await session.execute(
            select(ConfidentialPayload).where(
                ConfidentialPayload.assessment_version_id == v2.version.id
            )
        )
    ).scalar_one()
    assert payload.kind == "assessment_snapshot"
    assert "accounts.pdf" in json.dumps(payload.payload)
    # While the payload lives, readers get the full snapshot.
    snap = await evaluate.load_snapshot(session, v2.version)
    assert snap.removed_on is None
    assert "accounts.pdf" in snap.diff.claim_changes[0].reason


async def test_old_version_reads_after_purge(sm, session) -> None:
    w = await confirmed_world(session)
    await _evaluate(session, w)
    await _payroll_document(session, w)
    v2 = await _evaluate(session, w, trigger="seller documents accounts.pdf")

    past = datetime.now(UTC) - timedelta(minutes=1)
    await session.execute(update(ConfidentialPayload).values(delete_after=past))
    await session.commit()
    report = await purge_expired(sm, None)
    assert report.confidential_payloads == 2

    async with api_client(sm, w.t.workspace.id) as client:
        res = await client.get(f"/cases/{w.t.case.id}/assessments")
        detail = await client.get(f"/cases/{w.t.case.id}")
    assert res.status_code == 200, res.text
    v1_out, v2_out = res.json()
    for v in (v1_out, v2_out):
        assert v["confidential_removed_on"]
    # Statuses, scores, ids and the documents it rested on survive; the wording does not.
    line = next(d for d in v2_out["diff_from_previous"] if d["kind"] == "claim")
    assert (line["before"], line["after"]) == ("cannot_verify", "supported")
    assert line["because"].startswith("Removed per retention on ")
    assert v2_out["trigger"] == "seller documents"
    assert "accounts.pdf" not in json.dumps([v2_out["judgments"], line["because"]])
    assert v2_out["trigger_document_ids"]
    assert v2_out["judgments"]["screening_disposition"]["disposition"]

    memo = detail.json()["memo"]
    claims = next(s for s in memo["sections"] if s["key"] == "claims")
    assert any("Removed per retention on" in line["text"] for line in claims["lines"])
    rows = (
        (await session.execute(select(AssessmentVersion).order_by(AssessmentVersion.version)))
        .scalars()
        .all()
    )
    assert [r.version for r in rows] == [1, 2] and rows[1].id == v2.version.id
