"""Per-claim live activity from the claim checks, and the confidentiality canary: no
claim text or deck text ever reaches `run_activities`."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.api.schemas.runs import ActivityOut
from app.db.models import Run, RunActivity
from app.jobs import activity as act
from tests.pipelines.verify.test_checks import (
    PUNE,
    _case,
    _registry_evidence,
    _verify,
    pune_crustdata,
)

pytestmark = pytest.mark.asyncio

CANARY = "ZEBRA-CANARY-7731"


async def _activities(sm, case) -> list[dict]:  # type: ignore[no-untyped-def]
    async with sm() as s:
        rows = await s.execute(
            select(RunActivity.payload)
            .join(Run, Run.id == RunActivity.run_id)
            .where(Run.case_id == case.id)
            .order_by(RunActivity.seq)
        )
        payloads = list(rows.scalars())
    for p in payloads:
        ActivityOut.model_validate(p)
    return payloads


@pytest.fixture(autouse=True)
def _every_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test run is faster than the 1/s status throttle; keep every status line."""
    monkeypatch.setattr(act, "STATUS_INTERVAL", 0.0)


async def test_each_claim_streams_checking_facts_and_its_status(sm, session) -> None:
    case = await _case(session)
    await _registry_evidence(session, case)
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE]
    claims, ledger, _ = await _verify(sm, session, case, sentences, pune_crustdata())
    events = await _activities(sm, case)
    by_claim: dict[str, list[dict]] = {}
    for e in events:
        if (e.get("ref") or {}).get("type") == "claim":
            by_claim.setdefault(e["ref"]["id"], []).append(e)
    assert set(by_claim) == {str(c.id) for c in claims}

    expected = {text: status for text, _, _, status in PUNE}
    for claim in claims:
        mine = by_claim[str(claim.id)]
        findings = [e for e in mine if e["kind"] == "finding"]
        stages = [e["items"][0]["stage"] for e in findings]
        # checking first, any facts while checking, then exactly one settled row last.
        assert stages[0] == "checking" and stages[-1] in ("settled", "not_checked"), stages
        assert set(stages[1:-1]) <= {"checking"}
        last = findings[-1]["items"][0]
        assert last["status"] == expected[claim.original_text]
        assert last["category"] == claim.category
        assert findings[-1]["label"].startswith(("Claim settled", "Claim not checked"))
        statuses = [e["label"] for e in mine if e["kind"] == "status"]
        assert statuses[0] == f"Checking: {claim.category.replace('_', ' ')}"
        # Facts carry their source, and an as-of date when the source has one.
        for fact in findings[1:-1]:
            assert fact["source"] is not None and fact["label"].startswith("Found a fact for")
        if expected[claim.original_text] == "supported":
            assert len(findings) > 2, claim.original_text  # at least one fact was found

    # Counts after the last settle: every claim settled or not checked.
    final = [e for e in events if e["kind"] == "finding" and e["subject"] == "claim"][-1]
    assert final["counts"]["queued"] == 0 and final["counts"]["checking"] == 0
    assert final["counts"]["settled"] + final["counts"]["not_checked"] == len(claims)

    # Sub-steps the Claims tab shows, scoped to the claim.
    labels = {e["label"] for e in events if e["kind"] == "status"}
    assert "Looking up leadership at the confirmed company" in labels
    assert any(label.startswith("Comparing ") for label in labels)
    assert any(label.startswith("Searching news for Pune Warehousing") for label in labels)


async def test_blocked_claims_say_they_are_waiting_for_identity(sm, session) -> None:
    case = await _case(session, identity="ambiguous")
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE[:1]]
    await _verify(sm, session, case, sentences, pune_crustdata())
    events = await _activities(sm, case)
    labels = [e["label"] for e in events if e["kind"] == "status"]
    assert "Waiting for identity" in labels
    settled = [e for e in events if e["kind"] == "finding" and e["subject"] == "claim"][-1]
    assert settled["items"][0]["stage"] == "not_checked"
    assert "Pune Warehousing" not in json.dumps(events)  # no name before identity


async def test_canary_never_reaches_the_activity_stream(sm, session) -> None:
    """§2.10 rule 1: claim text and document text never appear in any activity."""
    case = await _case(session)
    await _registry_evidence(session, case)
    sentences = [
        (
            f"We opened the {CANARY} facility for our anchor client Zentrix in October 2026",
            "dated_event",
            [("event", "facility"), ("event_date", "2026-10"), ("stage", "operating")],
        ),
        (
            f"We employ 250 people at {CANARY} sites",
            "team_size",
            [("employee_count", "250")],
        ),
        (
            f"We raised growth funding in 2025 from {CANARY} investors",
            "funding",
            [("raised", "true"), ("round_year", "2025")],
        ),
    ]
    await _verify(sm, session, case, sentences, pune_crustdata())
    events = await _activities(sm, case)
    assert events
    stored = json.dumps(events)
    # ("raised growth funding" may appear: it is in the public news page's own text.)
    for word in (CANARY, "Zentrix", "anchor client", "We employ", 'investors"'):
        assert word not in stored, word


async def test_the_run_ends_with_assessment_and_request_findings(sm, session) -> None:
    case = await _case(session)
    await _registry_evidence(session, case)
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE]
    await _verify(sm, session, case, sentences, pune_crustdata())
    events = await _activities(sm, case)
    subjects = [e["subject"] for e in events if e["kind"] == "finding"]
    assert "assessment" in subjects and "request_list" in subjects
    assert subjects.index("assessment") < subjects.index("request_list")
    assessment = next(e for e in events if e["subject"] == "assessment")["items"][0]
    assert assessment["stage"] == "written" and assessment["version"] >= 1
    assert assessment["disposition"]
    request = next(e for e in events if e["subject"] == "request_list")
    assert set(request["items"][0]) == {"id", "stage"}  # counts only, never item text
    assert "request_items" in request["counts"]
