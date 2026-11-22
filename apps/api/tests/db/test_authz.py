import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repo
from app.db.models import Claim, Document, Evidence, RequestList, Source
from app.jobs import StepSpec, create_run
from tests.db.factories import days, tenant

pytestmark = pytest.mark.asyncio


async def test_case_is_invisible_to_other_workspaces(session: AsyncSession) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    assert (await repo.get_case(session, a.workspace.id, a.case.id)).id == a.case.id
    with pytest.raises(repo.NotFound):
        await repo.get_case(session, b.workspace.id, a.case.id)
    assert [c.id for c in await repo.list_cases(session, b.workspace.id)] == [b.case.id]


async def test_case_children_are_authorised_through_the_case(session: AsyncSession) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    doc = Document(
        case_id=a.case.id,
        filename="deck.pdf",
        mime="application/pdf",
        gcs_path=f"cases/{a.case.id}/x/deck.pdf",
        delete_after=days(30),
    )
    claim = Claim(
        case_id=a.case.id, original_text="We employ 250 people", origin="deck", category="team_size"
    )
    session.add_all([doc, claim])
    await session.commit()

    assert (await repo.get_document(session, a.workspace.id, doc.id)).id == doc.id
    with pytest.raises(repo.NotFound):
        await repo.get_document(session, b.workspace.id, doc.id)
    assert await repo.list_claims(session, b.workspace.id, a.case.id) == []
    # Even naming the right case id does not help from the wrong workspace.
    with pytest.raises(repo.NotFound):
        await repo.get_case_child(session, Claim, b.workspace.id, claim.id, case_id=a.case.id)


async def test_claim_check_cannot_cite_evidence_from_another_case(session: AsyncSession) -> None:
    a = await tenant(session, "a")
    other_case = await repo.create_case(session, a.workspace.id, company_name="other (fixture)")
    src = Source(
        workspace_id=a.workspace.id,
        case_id=other_case.id,
        provider="crustdata",
        endpoint_or_url="/company/enrich",
        source_class="data_provider_profile",
    )
    session.add(src)
    await session.flush()
    ev = Evidence(source_id=src.id, case_id=other_case.id, entity_ref="company:1", origin_key="k")
    claim = Claim(
        case_id=a.case.id,
        original_text="Founded 2014",
        origin="typed",
        category="identity_incorporation",
    )
    session.add_all([ev, claim])
    await session.commit()
    with pytest.raises(repo.NotFound):
        await repo.add_claim_check(
            session,
            a.workspace.id,
            claim_id=claim.id,
            status="supported",
            reason="registry",
            policy_version="p1",
            evidence_ids=[ev.id],
        )


async def test_approver_must_belong_to_the_workspace(session: AsyncSession) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    rl = RequestList(case_id=a.case.id)
    session.add(rl)
    await session.commit()
    rev = await repo.add_message_revision(
        session,
        a.workspace.id,
        rl.id,
        subject="Documents",
        body="Please send…",
        recipient="cfo@seller.test",
    )
    await session.commit()
    with pytest.raises(repo.Forbidden):
        await repo.approve_revision(session, a.workspace.id, rev.id, user_id=b.user.id)
    with pytest.raises(repo.NotFound):
        await repo.approve_revision(session, b.workspace.id, rev.id, user_id=b.user.id)
    approval = await repo.approve_revision(session, a.workspace.id, rev.id, user_id=a.user.id)
    assert approval.user_display_name == "a analyst"


async def test_runs_are_workspace_scoped(session: AsyncSession) -> None:
    a = await tenant(session, "a")
    b = await tenant(session, "b")
    run = await create_run(
        session,
        workspace_id=a.workspace.id,
        kind="verify",
        case_id=a.case.id,
        steps=[StepSpec("s", "noop")],
    )
    await session.commit()
    assert (await repo.get_run(session, a.workspace.id, run.id)).id == run.id
    with pytest.raises(repo.NotFound):
        await repo.get_run(session, b.workspace.id, run.id)
    with pytest.raises(LookupError):
        await create_run(
            session,
            workspace_id=b.workspace.id,
            kind="verify",
            case_id=a.case.id,
            steps=[StepSpec("s", "noop")],
        )


async def test_scoped_refuses_models_without_workspace() -> None:
    with pytest.raises(TypeError):
        repo.scoped(Claim, None)  # type: ignore[arg-type]
