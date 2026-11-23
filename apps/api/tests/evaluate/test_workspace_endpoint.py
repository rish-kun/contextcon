"""`GET /workspace` returns, for every case, exactly what `GET /cases/{id}` gives for the
fields the cross-case screens read, in a fixed number of queries on one connection."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, update

from app.act.models import Actor
from app.act.pg_repository import PostgresActRepository
from app.act.service import ActService, SendConfig
from app.api.schemas.cases import CaseDetail
from app.api.workspace_records import record_from_detail
from app.db import repo
from app.db.models import ConfidentialPayload, Document, Event, Step
from app.jobs import create_run
from app.jobs.purge import purge_expired
from app.pipelines import evaluate
from app.pipelines.act.request_list import build_request_list_for_case
from app.pipelines.evaluate import flip as flip_service
from tests.act.fakes import send_current
from tests.db.factories import Tenant, tenant
from tests.evaluate.builders import (
    COMPANY_ID,
    INDIA_MUST,
    SIZE_PREF,
    TODAY,
    api_client,
    check,
    field,
    quote,
    source,
    thesis,
)
from tests.evaluate.builders import World as _World

pytestmark = pytest.mark.asyncio

CANDIDATES = [
    {"crustdata_company_id": 501, "name": "Shree One (fixture)", "confidence_score": 0.6},
    {"crustdata_company_id": 502, "name": "Shree Two (fixture)", "confidence_score": 0.5},
]


async def _case(session, base: Tenant, name: str, **fields) -> Tenant:
    case = await repo.create_case(
        session,
        base.workspace.id,
        company_name=f"{name} (fixture)",
        created_by=base.user.id,
        **fields,
    )
    await session.commit()
    return Tenant(base.workspace, base.user, case)


async def _confirmed(session, base: Tenant, name: str, *, with_thesis: bool = True) -> _World:
    """A confirmed company with profile fields and one team-size claim (as `confirmed_world`)."""
    from app.db.models import Claim

    t = await _case(
        session,
        base,
        name,
        crustdata_company_id=COMPANY_ID,
        identity_status="confirmed",
        website=f"https://{name.lower().replace(' ', '-')}.test",
    )
    enrich = await source(session, t, title="Company profile")
    await field(session, t, enrich, "basic_info.name", name)
    await field(session, t, enrich, "basic_info.primary_domain", f"{name.lower()}.test")
    await field(session, t, enrich, "locations.headquarters", "Pune, India")
    await field(session, t, enrich, "locations.country", "India")
    profile = await source(
        session, t, source_class="professional_profile_signal", title="Headcount estimate"
    )
    headcount = await field(session, t, profile, "headcount.total", 180)
    if with_thesis:
        await thesis(session, t, [INDIA_MUST, SIZE_PREF])
    claim = Claim(
        case_id=t.case.id,
        original_text="We have 250 employees",
        origin="deck",
        category="team_size",
        components={"employee_count": "250"},
    )
    session.add(claim)
    await session.flush()
    await check(session, claim, "cannot_verify", [(headcount, "employee_count")])
    unchecked = Claim(
        case_id=t.case.id,
        original_text="No pending litigation",
        origin="typed",
        category="litigation",
    )
    session.add(unchecked)
    await session.commit()
    return _World(t, claim)


async def _evaluate(session, w: _World):
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    await session.commit()
    return out


async def _payroll(session, w: _World, *, delete_after: datetime | None = None) -> Document:
    doc = Document(
        case_id=w.t.case.id,
        kind="seller_response",
        filename="payroll_summary.pdf",
        mime="application/pdf",
        gcs_path=f"cases/{w.t.case.id}/d/payroll_summary.pdf",
        delete_after=delete_after or datetime.now(UTC) + timedelta(days=30),
        uploaded_by=w.t.user.id,
    )
    session.add(doc)
    await session.flush()
    src = await source(
        session,
        w.t,
        provider="upload",
        endpoint="upload://payroll_summary.pdf",
        source_class="seller_document",
        title="payroll_summary.pdf, p. 2",
        request={"document_type": "payroll_record"},
        document_id=doc.id,
    )
    ev = await quote(session, w.t, src, "Total employees on payroll: 250", "250", page=2)
    await check(session, w.claim, "supported", [(ev, "employee_count")])
    await session.commit()
    return doc


async def _events(session, w: _World) -> None:
    news = await source(
        session,
        w.t,
        provider="web",
        endpoint="https://news.example.test/a",
        source_class="news",
        title="Expansion story",
        request={"q": "x"},
    )
    for k, (when, stage) in enumerate([(date(2026, 3, 1), None), (date(2026, 6, 1), "seed")]):
        ev = await quote(session, w.t, news, f"Opens site {k}", f"site {k}")
        session.add(
            Event(
                case_id=w.t.case.id,
                event_date=when,
                title=f"New site {k}",
                kind="funding" if stage else "expansion",
                stage=stage,
                evidence_id=ev.id,
            )
        )
    await session.commit()


async def _message(session, sm, w: _World, *, approve: bool, send: bool) -> None:
    built = await build_request_list_for_case(session, w.t.workspace.id, w.t.case.id, llm=None)
    await session.commit()
    if not approve:
        return
    case_id, message_id = str(w.t.case.id), str(built.request_list.id)
    actor = Actor(user_id=str(w.t.user.id), display_name=w.t.user.display_name)
    service = ActService(PostgresActRepository(sm), SendConfig(enabled=False))
    state = await service.get_state(case_id, message_id)
    edited = await service.revise(
        case_id,
        message_id,
        actor,
        subject=state.current_revision.subject,
        body=state.current_revision.body,
        recipient="cfo@seller.example",
    )
    await service.approve(case_id, message_id, actor, revision_id=edited.current_revision.id)
    if send:
        await send_current(service, case_id, message_id, actor)


async def _round(session, sm, base: Tenant, tag: str) -> None:
    """One case of every kind the screens tell apart."""
    # Assessed twice (a diff), with events, a document, a flip, and a sent request.
    full = await _confirmed(session, base, f"Full {tag}")
    await _evaluate(session, full)
    await _events(session, full)
    await _payroll(session, full)
    out = await _evaluate(session, full)
    await flip_service.flip_for_version(session, base.workspace.id, out.version)
    await session.commit()
    await _message(session, sm, full, approve=True, send=True)

    drafted = await _confirmed(session, base, f"Drafted {tag}")
    await _evaluate(session, drafted)
    await _message(session, sm, drafted, approve=False, send=False)

    approved = await _confirmed(session, base, f"Approved {tag}")
    await _evaluate(session, approved)
    await _message(session, sm, approved, approve=True, send=False)

    # No thesis: no criteria, so no fit score.
    direct = await _confirmed(session, base, f"Direct {tag}", with_thesis=False)
    await _evaluate(session, direct)

    # Purged document and expired confidential payloads: the skeleton snapshot.
    purged = await _confirmed(session, base, f"Purged {tag}")
    await _evaluate(session, purged)
    await _payroll(session, purged, delete_after=datetime.now(UTC) - timedelta(days=1))
    await _evaluate(session, purged)
    await session.execute(
        update(ConfidentialPayload)
        .where(ConfidentialPayload.case_id == purged.t.case.id)
        .values(delete_after=datetime.now(UTC) - timedelta(minutes=1))
    )
    await session.commit()

    # Identity open: candidates listed; and confirmed after a recorded pick.
    await _case(
        session,
        base,
        f"Ambiguous {tag}",
        identity_status="ambiguous",
        identity_candidates=CANDIDATES,
    )
    await _case(
        session,
        base,
        f"Picked {tag}",
        identity_status="confirmed",
        crustdata_company_id="501",
        identity_candidates=CANDIDATES,
        identity_identifiers={
            "pick": {
                "crustdata_company_id": 501,
                "user_id": str(base.user.id),
                "display_name": base.user.display_name,
                "picked_at": "2026-11-20T10:00:00+00:00",
                "matched_keys": ["domain"],
            }
        },
    )

    # A run in flight, part way through; and a finished run with no assessment (failed).
    verifying = await _case(
        session, base, f"Verifying {tag}", identity_status="confirmed", crustdata_company_id="77"
    )
    run = await create_run(
        session, workspace_id=base.workspace.id, kind="verify", case_id=verifying.case.id, steps=[]
    )
    for p, state in enumerate(["done", "running", "pending"]):
        session.add(
            Step(
                run_id=run.id, key=f"s{p}", label=f"Step {p}", handler="x", position=p, state=state
            )
        )
    run.state = "running"
    failed = await _case(
        session, base, f"Failed {tag}", identity_status="confirmed", crustdata_company_id="78"
    )
    done = await create_run(
        session, workspace_id=base.workspace.id, kind="verify", case_id=failed.case.id, steps=[]
    )
    done.state = "done"
    await session.commit()

    # A bare case with no owner and nothing else.
    await repo.create_case(session, base.workspace.id, company_name=f"Bare {tag} (fixture)")
    await session.commit()


async def _workspace(sm, session) -> Tenant:
    base = await tenant(session, "ws")
    await _round(session, sm, base, "a")
    other = await tenant(session, "other")  # another workspace's case must never show
    await _confirmed(session, other, "Elsewhere")
    return base


async def test_records_match_the_case_records_field_for_field(sm, session) -> None:
    base = await _workspace(sm, session)
    async with api_client(sm, base.workspace.id, base.user.id) as client:
        res = await client.get("/workspace")
        listed = await client.get("/cases")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["cases"] == listed.json()
        ids = [row["id"] for row in body["cases"]]
        assert [r["case_id"] for r in body["records"]] == ids
        assert len(ids) == 11  # ten kinds, plus the tenant's own bare case
        for record in body["records"]:
            detail = await client.get(f"/cases/{record['case_id']}")
            assert detail.status_code == 200, detail.text
            expected = record_from_detail(CaseDetail.model_validate(detail.json()))
            assert record == expected.model_dump(mode="json"), record["case_id"]

    by_name = {c["name"]: r for c, r in zip(body["cases"], body["records"], strict=True)}
    full = by_name["Full a (fixture)"]
    assert full["message"]["status"] == "suppressed_test_mode"
    assert full["message"]["send"]["test_mode"] is True
    assert full["assessment"]["version"] == 2 and full["assessment"]["diff_from_previous"]
    assert [e["title"] for e in full["events"]] == ["New site 1", "New site 0"]
    assert full["events"][0]["kind"] == "funding (seed)"
    assert full["documents"][0]["uploaded_by_name"] == base.user.display_name
    assert full["profile"]["country"] == "India" and full["profile"]["headcount"] == 180
    assert full["claim_counts"]["supported"] == 1 and full["claim_counts"]["not_checked"] == 1
    assert by_name["Drafted a (fixture)"]["message"]["status"] == "draft"
    assert by_name["Approved a (fixture)"]["message"]["status"] == "approved"
    assert by_name["Approved a (fixture)"]["request_list"]["items"]
    assert by_name["Direct a (fixture)"]["opportunity"]["fit_state"] == "awaiting_strategy_criteria"
    assert by_name["Purged a (fixture)"]["documents"][0]["purged"] is False  # not yet purged
    assert by_name["Ambiguous a (fixture)"]["identity_candidates"] == 2
    assert by_name["Picked a (fixture)"]["identity_candidates"] == 2
    assert by_name["Verifying a (fixture)"]["run"] == {
        "kind": "verify",
        "state": "running",
        "steps": 3,
        "steps_finished": 1,
    }
    assert by_name["Bare a (fixture)"]["owner"] == {"user_id": "", "display_name": "Unknown user"}
    assert "Elsewhere (fixture)" not in by_name


class _Deleter:
    async def delete(self, path: str) -> None:
        return None


async def test_records_match_after_purge(sm, session) -> None:
    """Purged files and scrubbed excerpts read the same through both paths."""
    base = await _workspace(sm, session)
    report = await purge_expired(sm, _Deleter())
    assert report.documents == 1
    async with api_client(sm, base.workspace.id) as client:
        body = (await client.get("/workspace")).json()
        for record in body["records"]:
            detail = (await client.get(f"/cases/{record['case_id']}")).json()
            expected = record_from_detail(CaseDetail.model_validate(detail))
            assert record == expected.model_dump(mode="json"), record["case_id"]
    purged = next(
        r
        for c, r in zip(body["cases"], body["records"], strict=True)
        if c["name"].startswith("Purged")
    )
    assert purged["documents"][0]["purged"] is True


def _counting(sm):
    engine = sm.kw["bind"].sync_engine
    seen = {"sql": 0, "checkouts": 0}

    def sql(*args, **kwargs):
        seen["sql"] += 1

    def checkout(*args, **kwargs):
        seen["checkouts"] += 1

    class Counter:
        def __enter__(self):
            seen.update(sql=0, checkouts=0)
            event.listen(engine, "before_cursor_execute", sql)
            event.listen(engine.pool, "checkout", checkout)
            return seen

        def __exit__(self, *exc):
            event.remove(engine, "before_cursor_execute", sql)
            event.remove(engine.pool, "checkout", checkout)

    return Counter()


async def test_queries_do_not_grow_with_the_number_of_cases(sm, session) -> None:
    base = await tenant(session, "grow")
    await _round(session, sm, base, "a")

    async def measure() -> dict[str, int]:
        async with api_client(sm, base.workspace.id) as client:
            with _counting(sm) as seen:
                res = await client.get("/workspace")
        assert res.status_code == 200, res.text
        return {**seen, "cases": len(res.json()["cases"])}

    one = await measure()
    await _round(session, sm, base, "b")
    two = await measure()
    assert two["cases"] == one["cases"] + 10
    assert two["sql"] == one["sql"], (one, two)
    assert one["checkouts"] == two["checkouts"] == 1


async def test_an_empty_workspace_has_no_cases(sm, session) -> None:
    empty = await repo.create_workspace(session, "empty")
    other = await tenant(session, "full")
    await _confirmed(session, other, "Theirs")
    await session.commit()
    async with api_client(sm, empty.id) as client:
        res = await client.get("/workspace")
    assert res.status_code == 200, res.text
    assert res.json() == {"cases": [], "records": []}


async def test_a_workspace_sees_only_its_own_cases(sm, session) -> None:
    mine = await tenant(session, "mine")
    theirs = await tenant(session, "theirs")
    await _confirmed(session, theirs, "Theirs")
    async with api_client(sm, mine.workspace.id) as client:
        body = (await client.get("/workspace")).json()
    assert [c["id"] for c in body["cases"]] == [str(mine.case.id)]
    assert [r["case_id"] for r in body["records"]] == [str(mine.case.id)]
    async with api_client(sm, uuid.uuid4()) as client:
        assert (await client.get("/workspace")).json() == {"cases": [], "records": []}
