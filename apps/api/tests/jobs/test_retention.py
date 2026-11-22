"""Confidential step outputs and assessment payloads expire (retention, spec §7)."""

import pytest
from sqlalchemy import select, update

from app.db.models import (
    AssessmentVersion,
    ConfidentialPayload,
    DeletionRecord,
    Document,
    Step,
)
from app.jobs import StepContext, StepRegistry, StepSpec, create_run
from app.jobs.purge import purge_expired
from app.jobs.retention import load_confidential, payloads_for_assessment, ref_id
from tests.db.factories import days, tenant
from tests.jobs.helpers import make_worker, step

pytestmark = pytest.mark.asyncio

DECK_TEXT = "We employ 250 people across Pune and Nashik"


def _registry(seen: list) -> StepRegistry:
    reg = StepRegistry()

    @reg.handler("extract")
    async def extract(ctx: StepContext) -> dict:
        ctx.keep_output_confidential()
        return {"claims": [DECK_TEXT]}

    @reg.handler("use")
    async def use(ctx: StepContext) -> dict:
        seen.append(ctx.dependencies["extract"]["output"])
        return {"n": 1}

    return reg


async def _run(session, t):  # type: ignore[no-untyped-def]
    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="verify",
        case_id=t.case.id,
        steps=[StepSpec("extract", "extract"), StepSpec("use", "use", depends_on=["extract"])],
    )
    await session.commit()
    return run


async def test_confidential_output_lives_apart_from_the_step(session, sm) -> None:
    t = await tenant(session)
    seen: list = []
    run = await _run(session, t)
    await make_worker(sm, _registry(seen)).drain()

    extract = await step(sm, run.id, "extract")
    assert extract.output == {"_confidential": True}
    assert DECK_TEXT not in str(extract.output)
    assert seen == [{"claims": [DECK_TEXT]}]  # dependents still read it
    async with sm() as s:
        payload = await s.get(ConfidentialPayload, extract.confidential_output_id)
    assert payload.case_id == t.case.id and payload.delete_after <= days(30.01)


async def test_confidential_output_expires_with_the_case_documents(session, sm) -> None:
    t = await tenant(session)
    session.add(
        Document(
            case_id=t.case.id,
            filename="deck.pdf",
            mime="application/pdf",
            gcs_path="cases/x/deck.pdf",
            delete_after=days(2),
        )
    )
    await session.commit()
    run = await _run(session, t)
    await make_worker(sm, _registry([])).drain()
    extract = await step(sm, run.id, "extract")
    async with sm() as s:
        payload = await s.get(ConfidentialPayload, extract.confidential_output_id)
    assert payload.delete_after <= days(2.01)


async def test_purge_deletes_expired_outputs_and_dependents_see_expiry(session, sm) -> None:
    t = await tenant(session)
    run = await _run(session, t)
    await make_worker(sm, _registry([])).drain()
    async with sm() as s:
        await s.execute(update(ConfidentialPayload).values(delete_after=days(-1)))
        await s.commit()

    # Expired but not yet purged: already unreadable.
    from app.jobs.engine import dependency_outputs

    async with sm() as s:
        deps = await dependency_outputs(s, run.id, ["extract"])
    assert deps["extract"]["output"] == {"_retention_expired": True}

    report = await purge_expired(sm, None)
    assert report.confidential_payloads == 1
    async with sm() as s:
        assert (await s.execute(select(ConfidentialPayload))).first() is None
        extract = (
            await s.execute(select(Step).where(Step.run_id == run.id, Step.key == "extract"))
        ).scalar_one()
        assert extract.confidential_output_id is None and extract.state == "done"
        deps = await dependency_outputs(s, run.id, ["extract"])
        records = list(
            (
                await s.execute(
                    select(DeletionRecord).where(
                        DeletionRecord.object_type == "confidential_payload"
                    )
                )
            ).scalars()
        )
    assert deps["extract"]["output"] == {"_retention_expired": True}
    assert records[0].case_id == t.case.id and records[0].object_count == 1


async def test_assessment_snapshot_links_to_an_expiring_payload(session, sm) -> None:
    t = await tenant(session)
    reg = StepRegistry()

    @reg.handler("evaluate")
    async def evaluate(ctx: StepContext) -> dict:
        version = AssessmentVersion(
            case_id=t.case.id,
            version=1,
            policy_version="p1",
            inputs_hash="h",
            judgments={},
            disposition="investigate_further",
            run_id=ctx.run.id,
        )
        ctx.session.add(version)
        await ctx.session.flush()
        ref = await ctx.store_confidential(
            {"excerpts": [DECK_TEXT]}, kind="assessment_inputs", assessment_version_id=version.id
        )
        return {"version_id": str(version.id), "inputs": ref}

    run = await create_run(
        session,
        workspace_id=t.workspace.id,
        kind="evaluate",
        case_id=t.case.id,
        steps=[StepSpec("evaluate", "evaluate", uses_budget=False)],
    )
    await session.commit()
    await make_worker(sm, reg).drain()
    out = (await step(sm, run.id, "evaluate")).output
    assert DECK_TEXT not in str(out)
    import uuid

    version_id = uuid.UUID(out["version_id"])
    async with sm() as s:
        assert await payloads_for_assessment(s, version_id) == {
            "assessment_inputs": {"excerpts": [DECK_TEXT]}
        }
        assert await load_confidential(s, ref_id(out["inputs"])) == {"excerpts": [DECK_TEXT]}
        await s.execute(update(ConfidentialPayload).values(delete_after=days(-1)))
        await s.commit()
    await purge_expired(sm, None)
    async with sm() as s:
        assert await payloads_for_assessment(s, version_id) == {}
        assert await s.get(AssessmentVersion, version_id) is not None  # snapshot kept
