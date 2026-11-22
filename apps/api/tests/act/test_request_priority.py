"""Blocker-first request lists on Postgres: order, labels, email groups, no auto-send,
restart recovery."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select, update

from app.db.models import (
    Approval,
    AssessmentVersion,
    MessageRevision,
    RequestItem,
    RequestItemClaim,
    RequestList,
    SendAttempt,
    Step,
)
from app.db.models import DecisionFlipAnalysis as FlipRow
from app.domain.enums import PriorityReason
from app.domain.types import MinimalSet, SettleDocument
from app.jobs import StepSpec, create_run
from app.jobs import registry as default_registry
from app.pipelines import act as act_pipeline
from app.pipelines import evaluate
from app.pipelines.act import llm as llm_module
from app.pipelines.act.flip import analysis_for_version
from app.pipelines.act.request_list import build_request_list_for_case, load_context
from app.pipelines.evaluate.inputs import load_claim_checks
from app.rules.request_priority import NEEDED_HEADING
from tests.act.test_request_list import FakeLlm
from tests.evaluate.builders import TODAY, api_client, confirmed_world
from tests.jobs.helpers import make_worker

pytestmark = pytest.mark.asyncio


async def _world(session):
    w = await confirmed_world(session)
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    await session.commit()
    return w, out


async def _items(session, request_list_id) -> list[RequestItem]:
    rows = await session.execute(
        select(RequestItem)
        .where(RequestItem.request_list_id == request_list_id)
        .order_by(RequestItem.position)
    )
    return list(rows.scalars())


async def _links(session, item_id) -> list[str]:
    rows = await session.execute(
        select(RequestItemClaim.claim_id).where(RequestItemClaim.request_item_id == item_id)
    )
    return sorted(str(c) for c in rows.scalars())


async def _computed(session, w, version_row):
    ctx = await load_context(session, version_row)
    checks = await load_claim_checks(session, w.t.case)
    claims = {c.claim.id: c.claim for c in checks}
    analysis, source = await analysis_for_version(
        session, w.t.case, version_row, ctx.assessment, claims
    )
    assert source == "computed" and analysis is not None
    return analysis


async def _store(session, w, version_row, analysis, *, state: str | None = None) -> None:
    session.add(
        FlipRow(
            workspace_id=w.t.workspace.id,
            case_id=w.t.case.id,
            assessment_version_id=version_row.id,
            analysis_key=analysis.analysis_key,
            policy_version=analysis.policy_version,
            inputs_hash=analysis.inputs_hash,
            flip_version=analysis.flip_version,
            state=state or analysis.state.value,
            target=analysis.target.value if analysis.target else None,
            blocker_count=sum(1 for i in analysis.items if i.decision_blocker),
            payload=analysis.model_dump(mode="json"),
        )
    )
    await session.commit()


async def test_items_are_stored_blocker_first_and_deduplicated(session) -> None:
    w, out = await _world(session)
    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    assert built.analysis_source == "computed"  # no decision_flip row: computed in memory
    items = await _items(session, built.request_list.id)
    docs = [i.document_requested for i in items]
    expected = out.assessment.requests.documents
    # Same deduplicated documents as the rules gave, each with the same claims.
    assert sorted(docs) == sorted(d.document for d in expected) and len(set(docs)) == len(docs)
    by_doc = {d.document: sorted(d.claim_ids) for d in expected}
    for item in items:
        assert await _links(session, item.id) == by_doc[item.document_requested]
    assert [i.priority for i in items] == sorted(i.priority for i in items)
    assert {i.priority_reason for i in items} <= {r.value for r in PriorityReason}
    assert built.blocker_count == sum(
        1 for i in items if i.priority_reason == PriorityReason.DECISION_BLOCKER
    )


async def test_stored_analysis_orders_the_list_and_words_conditions(session, sm) -> None:
    w, _ = await _world(session)
    version = (await session.execute(select(AssessmentVersion))).scalar_one()
    analysis = await _computed(session, w, version)
    # Pick the request the plain order puts last and make its claim the only minimum
    # evidence, with a financial-style conditional action.
    rules_docs = (await load_context(session, version)).assessment.requests.documents
    target = next(d for d in reversed(rules_docs) if d.claim_ids)
    claim_id = target.claim_ids[0]
    item_id = f"claim:{claim_id}"
    condition = (
        f"Obtain {target.document.lower()}. If the verified figures match claim {claim_id}, it "
        "is supported; otherwise it is contradicted. Hypothetically, a match gives Prioritise "
        "and a mismatch gives Deprioritise."
    )
    items = [
        i.model_copy(
            update={"decision_blocker": True, "conditional_action": condition}
            if i.id == item_id
            else {"decision_blocker": False}
        )
        for i in analysis.items
    ]
    assert any(i.id == item_id for i in items)
    minimum = MinimalSet(
        item_ids=[item_id],
        documents=[
            SettleDocument(document=target.document, item_ids=[item_id], seller_resolvable=True)
        ],
        outcome=analysis.ceiling,
    )
    crafted = analysis.model_copy(update={"items": items, "minimum_evidence": minimum})
    await _store(session, w, version, crafted)

    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    assert built.analysis_source == "stored" and built.blocker_count == 1
    first, *rest = await _items(session, built.request_list.id)
    assert first.document_requested == target.document
    assert (first.priority, first.priority_reason) == (0, "decision_blocker")
    assert all(i.priority_reason != "decision_blocker" for i in rest)
    seller_said = (
        "If the verified figures match the claim, it is supported; otherwise it is contradicted."
    )
    assert seller_said in first.reason
    assert claim_id not in first.reason and "Hypothetically" not in first.reason

    revision = (
        await session.execute(
            select(MessageRevision).where(MessageRevision.request_list_id == built.request_list.id)
        )
    ).scalar_one()
    body = revision.body
    assert body.index(NEEDED_HEADING) < body.index(target.document)
    if rest:
        assert body.index(target.document) < body.index("Also helpful:")
    assert seller_said in body
    assert "Prioritise" not in body and "Deprioritise" not in body and claim_id not in body

    # The case detail and /requests label each item's priority and group.
    async with api_client(sm, w.t.workspace.id) as client:
        detail = (await client.get(f"/cases/{w.t.case.id}")).json()["request_list"]
    out = detail["items"]
    assert out[0]["document"] == target.document
    assert out[0]["priority"] == 0 and out[0]["priority_reason"] == "decision_blocker"
    assert out[0]["group"] == "needed" and out[0]["group_label"] == NEEDED_HEADING
    for i in out[1:]:
        assert i["group"] == "also_helpful" and i["group_label"] == "Also helpful"


async def test_a_not_reproducible_row_leaves_the_order_alone(session) -> None:
    w, out = await _world(session)
    version = (await session.execute(select(AssessmentVersion))).scalar_one()
    analysis = await _computed(session, w, version)
    await _store(session, w, version, analysis, state="not_reproducible")
    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    assert built.analysis_source == "none"
    items = await _items(session, built.request_list.id)
    assert [i.document_requested for i in items] == [
        d.document for d in out.assessment.requests.documents
    ]
    assert {(i.priority, i.priority_reason) for i in items} == {(3, "non_blocking")}


async def test_the_step_never_approves_or_sends(session, sm, monkeypatch) -> None:
    w, _ = await _world(session)
    llm = FakeLlm()

    @asynccontextmanager
    async def fake_factory(*_args):
        yield llm

    monkeypatch.setattr(llm_module, "llm_factory", fake_factory)
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="evaluate",
        case_id=w.t.case.id,
        steps=[StepSpec(act_pipeline.STEP_KEY, act_pipeline.HANDLER, uses_budget=False)],
    )
    await session.commit()
    assert await make_worker(sm, default_registry).drain() == 1
    async with sm() as s:
        step = (await s.execute(select(Step).where(Step.run_id == run.id))).scalar_one()
        assert step.state == "done", step.error
        assert step.output["blocker_items"] is not None
        assert step.output["analysis"] in ("stored", "computed", "none")
        revision = (await s.execute(select(MessageRevision))).scalar_one()
        assert revision.recipient == "" and revision.created_by is None
        assert await s.scalar(select(func.count()).select_from(Approval)) == 0
        assert await s.scalar(select(func.count()).select_from(SendAttempt)) == 0


async def test_restart_after_the_list_was_written_does_not_duplicate_items(
    session, sm, monkeypatch
) -> None:
    """A worker killed after the list committed but before the step was marked done:
    the re-claimed step finds the list for this version and writes nothing new."""
    w, _ = await _world(session)
    llm = FakeLlm()

    @asynccontextmanager
    async def fake_factory(*_args):
        yield llm

    monkeypatch.setattr(llm_module, "llm_factory", fake_factory)
    run = await create_run(
        session,
        workspace_id=w.t.workspace.id,
        kind="evaluate",
        case_id=w.t.case.id,
        steps=[StepSpec(act_pipeline.STEP_KEY, act_pipeline.HANDLER, uses_budget=False)],
    )
    await session.commit()
    first = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=llm)
    await session.commit()
    count = len(await _items(session, first.request_list.id))
    async with sm() as s:  # the dead worker's lease
        await s.execute(
            update(Step)
            .where(Step.run_id == run.id)
            .values(
                state="running",
                attempts=Step.attempts + 1,
                lease_owner="dead-worker",
                lease_until=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1),
            )
        )
        await s.commit()
    assert await make_worker(sm, default_registry).drain() == 1
    async with sm() as s:
        step = (await s.execute(select(Step).where(Step.run_id == run.id))).scalar_one()
        assert step.state == "done", step.error
        assert step.output["created"] is False
        assert step.output["request_list_id"] == str(first.request_list.id)
        assert await s.scalar(select(func.count()).select_from(RequestList)) == 1
        assert await s.scalar(select(func.count()).select_from(RequestItem)) == count
        assert await s.scalar(select(func.count()).select_from(MessageRevision)) == 1
    assert llm.calls == 1  # the email was drafted (and paid for) once
    assert uuid.UUID(step.output["request_list_id"])
