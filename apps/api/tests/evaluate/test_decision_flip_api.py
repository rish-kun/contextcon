"""B2: DecisionFlip in the API — the case section, the board summary, GET and POST
`/cases/{id}/decision-flip`, workspace isolation, and the contract with schema.ts."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.api import fixture_decision_flip
from app.api.schemas import decision_flip as schemas
from app.domain import types as domain
from app.pipelines import evaluate
from app.pipelines.evaluate import flip as flip_service
from tests.db.factories import tenant
from tests.evaluate.builders import TODAY, add_payroll, api_client, confirmed_world

pytestmark = pytest.mark.asyncio

SCHEMA_TS = Path(__file__).resolve().parents[3] / "web" / "lib" / "api" / "schema.ts"


async def _assess_and_flip(session, w):
    out = await evaluate.evaluate_case(session, w.t.workspace.id, w.t.case.id, today=TODAY)
    result = await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    await session.commit()
    return out, result


def _ts_fields(component: str) -> set[str]:
    """Property names of one `components.schemas` entry in the generated schema.ts."""
    text = SCHEMA_TS.read_text(encoding="utf-8")
    start = text.index(f"\n        {component}: {{\n")
    end = text.index("\n        };\n", start)
    return set(re.findall(r"^ {12}(\w+)\??:", text[start:end], flags=re.M))


# --- Contract --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("out", "model"),
    [
        (schemas.DecisionFlipOut, domain.DecisionFlipAnalysis),
        (schemas.FlipItemOut, domain.UnresolvedItem),
        (schemas.FlipSetOut, domain.MinimalSet),
        (schemas.FlipDocumentOut, domain.SettleDocument),
        (schemas.FlipOutcomeOut, domain.ItemOutcome),
        (schemas.FlipNextBestActionOut, domain.NextBestAction),
    ],
)
async def test_api_models_cover_every_rules_field(
    out: type[BaseModel], model: type[BaseModel]
) -> None:
    assert set(model.model_fields) <= set(out.model_fields), out.__name__


@pytest.mark.parametrize(
    "out",
    [
        schemas.DecisionFlipOut,
        schemas.FlipItemOut,
        schemas.FlipSetOut,
        schemas.FlipOutcomeOut,
        schemas.FlipNextBestActionOut,
        schemas.FlipResolutionOut,
        schemas.DecisionFlipSummaryOut,
    ],
)
async def test_schema_ts_matches_the_api_models(out: type[BaseModel]) -> None:
    assert _ts_fields(out.__name__) == set(out.model_fields), (
        "apps/web/lib/api/schema.ts is stale: run `pnpm --filter web gen:api:export`"
    )


async def test_every_fixture_scenario_is_hypothetical_and_valid() -> None:
    for name, flip in fixture_decision_flip.scenarios().items():
        body = flip.model_dump(mode="json")
        assert body["hypothetical"] is True, name
        assert body["selection_label"] == (
            "Minimum set of checks required to change the screening outcome"
        )
        for s in body["minimal_sets"]:
            assert s["hypothetical"] is True and s["outcome"]["hypothetical"] is True
        for item in body["items"]:
            assert item["label"], (name, item["id"])
            for key in ("if_supported", "if_contradicted"):
                if item[key] is not None:
                    assert item[key]["hypothetical"] is True
    scenarios = fixture_decision_flip.scenarios()
    assert scenarios["no_blockers"].state == "no_blockers"
    assert scenarios["two_blockers"].blocker_count == 2
    risky = [i for i in scenarios["mapped_claim_risk"].items if i.disqualifier_risk]
    assert [i.id for i in risky] == ["claim:fx-claim-6"]
    threshold = next(
        i for i in scenarios["threshold_unknown"].items if i.id == "criterion:fx-crit-5"
    )
    assert "otherwise it fails" in (threshold.conditional_action or "")


# --- Live API --------------------------------------------------------------------------


async def test_case_section_and_board_summary(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    async with api_client(sm, w.t.workspace.id) as client:
        before = (await client.get(f"/cases/{case_id}")).json()
    assert before["decision_flip"] is None  # reading never computes

    out, result = await _assess_and_flip(session, w)
    async with api_client(sm, w.t.workspace.id) as client:
        detail = (await client.get(f"/cases/{case_id}")).json()
        board = (await client.get("/cases")).json()
    flip = detail["decision_flip"]
    assert flip["analysis_id"] == str(result.row.id)
    assert flip["assessment_version"] == out.version.version
    assert flip["hypothetical"] is True
    assert set(flip) == set(schemas.DecisionFlipOut.model_fields)
    assert set(flip) == _ts_fields("DecisionFlipOut")
    claim_item = next(i for i in flip["items"] if i["claim_id"] == str(w.claim.id))
    assert claim_item["label"] == "Team size"
    assert claim_item["claim_text"] == "We have 250 employees"
    [row] = [c for c in board if c["id"] == str(case_id)]
    assert row["decision_flip"] == {
        "state": flip["state"],
        "next_disposition": flip["target"],
        "blockers_to_next": flip["blocker_count"],
        "assessment_version": out.version.version,
    }


async def test_get_by_version_and_not_computed(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    out = await evaluate.evaluate_case(session, w.t.workspace.id, case_id, today=TODAY)
    await session.commit()
    async with api_client(sm, w.t.workspace.id) as client:
        missing = await client.get(f"/cases/{case_id}/decision-flip")
        no_version = await client.get(f"/cases/{case_id}/decision-flip?version=9")
    assert missing.status_code == 200 and missing.json() is None
    assert no_version.status_code == 404
    await flip_service.flip_for_version(session, w.t.workspace.id, out.version)
    await session.commit()
    async with api_client(sm, w.t.workspace.id) as client:
        got = await client.get(f"/cases/{case_id}/decision-flip?version=1")
    assert got.status_code == 200 and got.json()["assessment_version"] == 1


async def test_post_recomputes_once_and_costs_nothing(sm, session) -> None:
    w = await confirmed_world(session)
    case_id = w.t.case.id
    async with api_client(sm, w.t.workspace.id) as client:
        none_yet = await client.post(f"/cases/{case_id}/decision-flip")
    assert none_yet.status_code == 409
    await evaluate.evaluate_case(session, w.t.workspace.id, case_id, today=TODAY)
    await session.commit()
    async with api_client(sm, w.t.workspace.id) as client:
        first = await client.post(f"/cases/{case_id}/decision-flip")
        second = await client.post(f"/cases/{case_id}/decision-flip", json={"version": 1})
        runs = (await client.get(f"/cases/{case_id}")).json()["runs"]
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert runs == []  # no run, so no credits and no model


async def test_another_workspace_gets_404(sm, session) -> None:
    w = await confirmed_world(session)
    other = await tenant(session, "other")
    case_id = w.t.case.id
    await _assess_and_flip(session, w)
    async with api_client(sm, other.workspace.id) as client:
        got = await client.get(f"/cases/{case_id}/decision-flip")
        post = await client.post(f"/cases/{case_id}/decision-flip")
        bogus = await client.get(f"/cases/{uuid.uuid4()}/decision-flip")
    assert (got.status_code, post.status_code, bogus.status_code) == (404, 404, 404)


async def test_resolution_against_the_previous_version(sm, session) -> None:
    """v1 has the team-size claim open; the payroll summary supports it; v2's analysis
    says it was resolved and by which evidence."""
    w = await confirmed_world(session)
    case_id, claim_id = w.t.case.id, str(w.claim.id)
    await _assess_and_flip(session, w)
    payroll = await add_payroll(session, w)
    payroll_id = str(payroll.id)
    out, _ = await _assess_and_flip(session, w)
    assert out.version.version == 2
    async with api_client(sm, w.t.workspace.id) as client:
        flip = (await client.get(f"/cases/{case_id}/decision-flip")).json()
    resolution = flip["resolution"]
    assert resolution["previous_version"] == 1
    by_id = {i["item_id"]: i for i in resolution["items"]}
    team = by_id[f"claim:{claim_id}"]
    assert team["outcome"] == "resolved" and team["current_state"] == "supported"
    assert payroll_id in team["evidence_ids"]
    assert team["label"] == "Team size"


async def test_a_broken_analysis_never_breaks_the_case_page(sm, session, monkeypatch) -> None:
    from app.api import decision_flip as routes

    w = await confirmed_world(session)
    case_id = w.t.case.id
    await _assess_and_flip(session, w)

    def boom(row):
        raise ValueError("unreadable payload")

    monkeypatch.setattr(routes, "stored_analysis", boom)
    async with api_client(sm, w.t.workspace.id) as client:
        detail = await client.get(f"/cases/{case_id}")
        board = await client.get("/cases")
    assert detail.status_code == 200 and detail.json()["decision_flip"] is None
    assert detail.json()["case"]["id"] == str(case_id)
    assert board.status_code == 200
