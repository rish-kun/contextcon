"""CP-21: evidence gathering, fact extraction and claim statuses.

The Pune case below is the PRD's illustration ("An example"), not a real company.
Provider clients are fakes; nothing leaves the process.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

import app.pipelines.verify.checks.steps  # noqa: F401  (registers the handler)
from app.db import repo
from app.db.models import Claim, ClaimCheck, ClaimCheckEvidence, Evidence, Run, Source, Step
from app.jobs import registry
from app.pipelines.verify.checks.clients import set_client_factory
from app.pipelines.verify.checks.query import PublicTerms, UnsafeQuery, assert_public, build_query
from app.pipelines.verify.claims.intake import (
    add_typed_claim,
    schedule_claim_checks,
    verify_run_for_case,
)
from app.pipelines.verify.claims.ledger import build_claims_section
from app.rules.policy import POLICY_VERSION
from tests.jobs.helpers import make_worker
from tests.pipelines.verify.fakes import (
    FakeCrustdata,
    FakeFactory,
    RoutedLlm,
    claim_block,
    evidence_block,
)

pytestmark = pytest.mark.asyncio

CID = 4242
DOMAIN = "pune-warehousing.test"
NAME = "Pune Warehousing (illustration)"
FOUNDER_ID = 701
NAMESAKE_ID = 702

REGISTRY_SPAN = (
    "Date of Incorporation: 12/06/2014. Registered Office: Baner Road, Pune, Maharashtra 411045."
)
CHARGE_SPAN = (
    "Charge ID 100234567 created 01/08/2023, charge holder: a scheduled bank, "
    "amount 12 crore, status: open."
)
FACILITY_HTML = (
    "<html><nav>Menu</nav><article><p>Pune Warehousing (illustration) news.</p>"
    "<p>The company plans to open a new warehouse facility in Chakan in October 2026.</p>"
    "</article><footer>(c)</footer></html>"
)

# The PRD's six claims: (sentence, category, components) and the expected status.
PUNE = [
    (
        "Incorporated in 2014, based in Pune",
        "identity_incorporation",
        [("incorporation_year", "2014"), ("hq_city", "Pune")],
        "supported",
    ),
    ("We employ 250 people", "team_size", [("employee_count", "250")], "cannot_verify"),
    (
        "Our founder ran operations at a national logistics firm",
        "leadership_history",
        [("role", "operations"), ("employer_industry", "logistics")],
        "supported",
    ),
    (
        "We raised growth funding in 2025",
        "funding",
        [("raised", "true"), ("round_year", "2025")],
        "supported",
    ),
    (
        "We opened a new facility in October 2026",
        "dated_event",
        [("event", "facility"), ("event_date", "2026-10"), ("stage", "operating")],
        "partially_corroborated",
    ),
    ("We have no debt", "debt_security", [("has_debt", "false")], "cannot_verify"),
]


def _position(company_id, name, title, start, end=None):
    return {
        "crustdata_company_id": company_id,
        "name": name,
        "title": title,
        "start_date": start,
        "end_date": end,
    }


def founder(person_id=FOUNDER_ID, *, at=CID, name="Asha Rao (fixture)"):
    return {
        "crustdata_person_id": person_id,
        "basic_profile": {"name": name, "headline": "Founder"},
        "experience": {
            "employment_details": {
                "current": [_position(at, "Some company", "Founder & CEO", "2014-06-01")],
                "past": [
                    _position(
                        555,
                        "National Freight Logistics Ltd",
                        "Head of Operations",
                        "2008-01-01",
                        "2013-12-31",
                    )
                ],
            }
        },
    }


ENRICH = {
    "crustdata_company_id": CID,
    "updated_at": "2026-11-01T00:00:00Z",
    "basic_info": {
        "crustdata_company_id": CID,
        "name": NAME,
        "primary_domain": DOMAIN,
        "year_founded": 2014,
    },
    "headcount": {
        "total": 140,
        "timeseries": [{"date": "2026-11-01", "employee_count": 140}],
    },
    "funding": {
        "investors": ["Fixture Growth Partners"],
        "milestones": [
            {"round_type": "seed", "funding_date": "2019-05-02", "amount_usd": 1000000},
            {
                "round_type": "growth",
                "funding_date": "2025-03-14",
                "amount_usd": 12000000,
                "investors": ["Fixture Growth Partners"],
            },
        ],
    },
    "locations": {"headquarters": "Pune, Maharashtra, India", "country": "India"},
    "people": {"founders": [{"name": "Asha Rao (fixture)"}]},
}

FUNDING_HITS = [
    {
        "title": "Pune Warehousing (illustration) raises growth funding",
        "url": f"https://{DOMAIN}/news/growth-round",
        "snippet": "On 14 March 2025 the company announced it has raised growth funding.",
        "date": "2025-03-14",
    },
    {  # a syndicated copy of the same announcement on another site
        "title": "Pune Warehousing (illustration) raises growth funding - Wire",
        "url": "https://newswire.example/pune-warehousing-growth",
        "snippet": "Pune Warehousing (illustration), based in Pune, has raised growth funding.",
        "date": "2025-03-14",
    },
    {  # same name, nothing else: must stay unattached
        "title": "Pune Warehousing (illustration) wins award",
        "url": "https://elsewhere.example/award",
        "snippet": "Pune Warehousing (illustration) wins a regional award.",
    },
]
FACILITY_HITS = [
    {
        "title": "Pune Warehousing (illustration) plans new Chakan facility",
        "url": f"https://{DOMAIN}/news/new-facility",
        "snippet": "Plans for a new facility in Chakan.",
        "date": "2026-06-02",
    }
]


def _fact(name, value, span):
    return {"name": name, "value": value, "span": span}


def facts_responder(system: str, user: str) -> dict:
    """What the fake model reads from each evidence text, for each claim."""
    claim = claim_block(user)["claim"]
    text = evidence_block(user)
    silent = {"speaks_to_claim": False, "facts": []}
    if claim.startswith("Incorporated") and "Date of Incorporation" in text:
        return {
            "speaks_to_claim": True,
            "facts": [
                _fact("incorporation_year", "2014", "Date of Incorporation: 12/06/2014"),
                _fact("hq_city", "Pune", "Registered Office: Baner Road, Pune"),
            ],
        }
    if claim.startswith("Our founder") and "National Freight Logistics" in text:
        return {
            "speaks_to_claim": True,
            "facts": [
                _fact("role", "Founder & CEO", "Founder & CEO at Some company"),
                _fact("role", "Head of Operations", "Head of Operations at National Freight"),
                _fact("employer_industry", "Logistics", "National Freight Logistics Ltd"),
                _fact(
                    "start_year",
                    "2008",
                    "Head of Operations at National Freight Logistics Ltd (2008",
                ),
                _fact("start_year", "2014", "Founder & CEO at Some company (2014"),
            ],
        }
    if claim.startswith("We raised") and "raised growth funding" in text:
        return {
            "speaks_to_claim": True,
            "effective_date": "2025-03-14" if "14 March 2025" in text else None,
            "effective_date_span": "14 March 2025" if "14 March 2025" in text else None,
            "facts": [_fact("raised", "true", "raised growth funding")]
            + (
                [_fact("round_year", "2025", "On 14 March 2025")] if "14 March 2025" in text else []
            ),
        }
    if claim.startswith("We opened") and "Chakan" in text:
        return {
            "speaks_to_claim": True,
            "facts": [
                _fact("event", "new warehouse facility", "new warehouse facility"),
                _fact("event_date", "2026-10", "in October 2026"),
                _fact("stage", "planned", "plans to open"),
            ],
        }
    if claim.startswith("We have no debt") and "Charge ID" in text:
        return {
            "speaks_to_claim": True,
            "facts": [_fact("security_registered", "true", "Charge ID 100234567")],
        }
    return silent


def intake_llm(sentences: list[tuple[str, str, list[tuple[str, str]]]]) -> RoutedLlm:
    by_text = {s: (cat, comps) for s, cat, comps in sentences}

    def find(user: str) -> str:
        return next(s for s in by_text if s in user)

    def claims(system, user):
        s = find(user)
        return {"claims": [{"assertion": s, "category": by_text[s][0], "quote": s}]}

    def normalise(system, user):
        s = find(user)
        comps = [{"name": n, "value": v} for n, v in by_text[s][1]]
        return {"claims": [{"index": 0, "components": comps}]}

    return RoutedLlm(
        responders={
            "ClaimsDraft": claims,
            "NormaliseDraft": normalise,
            "EvidenceFactsDraft": facts_responder,
        }
    )


async def _case(session, *, identity="confirmed", budget=None, website=f"https://{DOMAIN}"):
    ws = await repo.create_workspace(session, "fund")
    user = await repo.create_user(session, ws.id, email="a@fund.example", display_name="Analyst")
    case = await repo.create_case(
        session,
        ws.id,
        company_name=NAME,
        website=website,
        created_by=user.id,
        crustdata_company_id=str(CID),
        identity_status=identity,
        credit_budget=budget,
    )
    await session.commit()
    return case


async def _registry_evidence(session, case) -> None:
    """What CP-19's registry step stores: a registry page attached to the company."""
    src = Source(
        workspace_id=case.workspace_id,
        case_id=case.id,
        provider="web",
        endpoint_or_url="https://www.mca.gov.in/example-record",
        request={"query": f'"{NAME}" CIN incorporated'},
        source_class="registry",
        title="Company registry record",
    )
    session.add(src)
    await session.flush()
    for i, span in enumerate([REGISTRY_SPAN, CHARGE_SPAN]):
        session.add(
            Evidence(
                source_id=src.id,
                case_id=case.id,
                entity_ref=f"cin:{CID}",  # attached on the registry id
                span=span,
                as_of=date(2026, 11, 1),
                origin_key=f"registry:{i}",
            )
        )
    await session.commit()


async def _claims(session, case, llm, sentences) -> list[Claim]:
    out = []
    for sentence, *_ in sentences:
        out.append(
            await add_typed_claim(session, case=case, text=sentence, llm=llm, retention_days=30)
        )
    run = await verify_run_for_case(session, case)
    await schedule_claim_checks(session, run_id=run.id, claims=out)
    await session.commit()
    return out


def pune_crustdata(**overrides) -> FakeCrustdata:
    data = {
        "enrich": ENRICH,
        "people": [founder(), founder(NAMESAKE_ID, at=9999)],
        "search_hits": {"funding": FUNDING_HITS, "facility": FACILITY_HITS},
        "pages": {f"https://{DOMAIN}/news/new-facility": FACILITY_HTML},
    }
    data.update(overrides)
    return FakeCrustdata(**data)


async def _verify(sm, session, case, sentences, crust, llm=None):
    llm = llm or intake_llm(sentences)
    claims = await _claims(session, case, llm, sentences)
    set_client_factory(FakeFactory(llm_client=llm, crustdata_client=crust))
    await make_worker(sm, registry).drain()
    session.expire_all()
    await session.refresh(case)
    ledger = await build_claims_section(session, case)
    return claims, {o.original_text: o for o in ledger}, llm


# --- The PRD illustration, end to end --------------------------------------------


async def test_pune_illustration_end_to_end(sm, session):
    case = await _case(session)
    await _registry_evidence(session, case)
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE]
    crust = pune_crustdata()
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)

    assert {text: o.status.value for text, o in ledger.items()} == {
        s: expected for s, _, _, expected in PUNE
    }

    inc = ledger["Incorporated in 2014, based in Pune"]
    assert inc.settle_with is None
    assert any(e.source.source_class == "registry" and e.quote for e in inc.evidence)
    assert inc.adequate_source_reached is True and inc.substantive_result == "supports"

    team = ledger["We employ 250 people"]
    assert "signal, not a payroll count" in team.reason
    assert team.settle_with == "Dated payroll summary"
    headcount = [e for e in team.evidence if e.field_path == "headcount.total"]
    assert headcount and headcount[0].value == 140

    founder_claim = ledger["Our founder ran operations at a national logistics firm"]
    assert {e.attached_to.entity_name for e in founder_claim.evidence} == {"Asha Rao (fixture)"}

    funding = ledger["We raised growth funding in 2025"]
    classes = {e.source.source_class for e in funding.evidence}
    assert {"data_provider", "company_announcement"} <= classes

    facility = ledger["We opened a new facility in October 2026"]
    assert "Lease or occupancy evidence for the facility" in (facility.settle_with or "")

    debt = ledger["We have no debt"]
    assert "security was given, not that money is owed" in debt.reason
    assert debt.settle_with == "Lender statements"

    # Every row carries the policy version and stores the inputs that reproduce it.
    checks = list((await session.execute(select(ClaimCheck))).scalars())
    assert len(checks) == 6 and {c.policy_version for c in checks} == {POLICY_VERSION}
    for c in checks:
        step = await session.get(Step, c.step_id)
        meta = step.output["checks"][str(c.claim_id)]
        assert meta["inputs"]["claim"]["id"] == str(c.claim_id)
        assert meta["inputs"]["claim"]["text"] is None  # referenced by id, never copied
        assert all("value" not in comp for comp in meta["inputs"]["claim"]["components"])
        assert meta["outcome"]["status"] == c.status


async def test_inputs_replay_to_the_same_statuses(sm, session):
    """The evaluate reader rebuilds the same ClaimCheck from the stored rows."""
    from app.pipelines.evaluate.inputs import load_claim_checks
    from app.rules import decide_all

    case = await _case(session)
    await _registry_evidence(session, case)
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE]
    await _verify(sm, session, case, sentences, pune_crustdata())
    rebuilt = await load_claim_checks(session, case)
    replayed = {
        c.claim.text: o.status.value for c, o in zip(rebuilt, decide_all(rebuilt), strict=True)
    }
    assert replayed == {s: expected for s, _, _, expected in PUNE}


# --- Identity guard -----------------------------------------------------------------


async def test_same_name_at_another_company_is_not_attached(sm, session):
    case = await _case(session)
    sentences = [
        (
            "Our founder ran operations at a national logistics firm",
            "leadership_history",
            [("role", "operations"), ("employer_industry", "logistics")],
        )
    ]
    # Only the namesake comes back: same name and career, but at company 9999.
    crust = pune_crustdata(people=[founder(NAMESAKE_ID, at=9999)])
    _, ledger, llm = await _verify(sm, session, case, sentences, crust)
    [out] = ledger.values()
    assert out.status == "cannot_verify"
    refs = (await session.execute(select(Evidence.entity_ref))).scalars().all()
    assert not any(str(NAMESAKE_ID) in r for r in refs)
    assert not llm.users("EvidenceFactsDraft")  # the namesake's record was never read
    titles = (await session.execute(select(Source.title))).scalars().all()
    assert not any("Asha" in (t or "") for t in titles)


async def test_named_person_needs_company_id_and_name(sm, session):
    from app.clients.crustdata_models import PersonProfile
    from app.domain.types import Claim as DomainClaim
    from app.domain.types import ClaimComponent
    from app.pipelines.verify.checks.gather import select_people

    people = [
        PersonProfile.model_validate(founder(FOUNDER_ID)),
        PersonProfile.model_validate(founder(NAMESAKE_ID, at=9999)),
        PersonProfile.model_validate(founder(703, name="Ravi Menon (fixture)")),
    ]
    claim = DomainClaim(
        id="c",
        text="Asha Rao ran operations at a logistics firm",
        category="leadership_history",
        components=[ClaimComponent(name="person_name", value="Asha Rao")],
    )
    picked = select_people(claim, people, CID)
    assert [p.crustdata_person_id for p in picked] == [FOUNDER_ID]


async def test_identity_not_confirmed_gives_not_checked(sm, session):
    case = await _case(session, identity="ambiguous")
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE[:2]]
    crust = pune_crustdata()
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)
    assert {o.status for o in ledger.values()} == {"not_checked"}
    assert {o.not_checked_reason for o in ledger.values()} == {"identity_unresolved"}
    assert crust.calls == []


# --- Confidentiality ---------------------------------------------------------------


async def test_confidential_claim_text_never_reaches_web_search(sm, session):
    case = await _case(session)
    secret = "Project Falcon"
    sentences = [
        (
            f"We opened the {secret} facility for our anchor client Zentrix in October 2026",
            "dated_event",
            [("event", "facility"), ("event_date", "2026-10"), ("stage", "operating")],
        ),
        (
            f"We raised growth funding in 2025 from {secret} investors",
            "funding",
            [("raised", "true"), ("round_year", "2025")],
        ),
    ]
    crust = pune_crustdata()
    await _verify(sm, session, case, sentences, crust)
    searches = [params for name, params in crust.calls if name == "web_search"]
    assert searches
    terms = PublicTerms(company_name=NAME, domain=DOMAIN)
    for params in searches:
        flat = repr(params)
        for word in ("Falcon", "Project", "Zentrix", "anchor", "client", "opened"):
            assert word not in flat
        assert_public(params["query"], terms)  # only name, domain, city, topic


async def test_query_builder_refuses_anything_but_public_terms():
    terms = PublicTerms(company_name=NAME, domain=DOMAIN)
    assert build_query(terms, "funding") == f'"{NAME}" funding'
    assert build_query(terms, "facility", city="Chakan") == f'"{NAME}" facility Chakan'
    assert build_query(terms, "facility", city="our secret Falcon site in Chakan") == (
        f'"{NAME}" facility'
    )
    with pytest.raises(UnsafeQuery):
        build_query(terms, "Project Falcon")
    with pytest.raises(UnsafeQuery):
        assert_public(f'"{NAME}" funding Falcon', terms)


# --- Budget -------------------------------------------------------------------------


async def test_budget_exhaustion_marks_not_checked(sm, session):
    case = await _case(session, budget=Decimal("0"))
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE[1:4]] + [
        (
            "Tata Steel is our largest customer",
            "customer_partnership",
            [("counterparty", "Tata Steel")],
        )
    ]
    crust = pune_crustdata()
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)
    for text, out in ledger.items():
        if text.startswith("Tata"):
            # No paid source exists for it in v1: answered, with what would settle it.
            assert out.status == "cannot_verify"
            assert out.settle_with == "Customer confirmation or signed contract"
        else:
            assert out.status == "not_checked", text
            assert out.not_checked_reason == "budget_reached"
            assert "budget" in out.reason
    assert crust.calls == []  # nothing was paid for
    steps = list((await session.execute(select(Step))).scalars())
    assert {s.state for s in steps} == {"done"}
    run = (await session.execute(select(Run))).scalar_one()
    assert run.state == "done"


async def test_provider_failure_is_not_checked_with_reason(sm, session):
    from app.clients.crustdata import CrustdataError

    case = await _case(session)
    err = CrustdataError("boom", status=500, error_type=None, record=None)
    crust = pune_crustdata(fail={"enrich_company": err})
    sentences = [("We employ 250 people", "team_size", [("employee_count", "250")])]
    _, ledger, _ = await _verify(sm, session, case, sentences, crust)
    [out] = ledger.values()
    assert out.status == "not_checked"
    assert out.not_checked_reason == "step_failed"


# --- Evidence handling ----------------------------------------------------------------


async def test_syndicated_copies_share_an_origin_and_unattached_pages_give_no_evidence(sm, session):
    case = await _case(session)
    sentences = [(s, c, comps) for s, c, comps, _ in PUNE if c == "funding"]
    await _verify(sm, session, case, sentences, pune_crustdata())
    web = {
        s.endpoint_or_url: s
        for s in (await session.execute(select(Source).where(Source.provider == "web"))).scalars()
    }
    own = web[f"https://{DOMAIN}/news/growth-round"]
    wire = web["https://newswire.example/pune-warehousing-growth"]
    award = web["https://elsewhere.example/award"]
    assert own.request["origin_key"] == wire.request["origin_key"]
    assert own.source_class == "company_announcement" and wire.source_class == "news"
    assert award.request["attached"] is False
    award_evidence = await session.execute(select(Evidence).where(Evidence.source_id == award.id))
    assert award_evidence.first() is None


async def test_silent_adequate_source_is_recorded_as_read(sm, session):
    case = await _case(session)
    await _registry_evidence(session, case)
    sentences = [
        (
            "Our legal name is Pune Warehousing Private Limited",
            "identity_incorporation",
            [("legal_name", "Pune Warehousing Private Limited")],
        )
    ]
    _, ledger, _ = await _verify(sm, session, case, sentences, pune_crustdata())
    [out] = ledger.values()
    assert out.status == "cannot_verify"
    assert "was read and does not state it" in out.reason
    assert out.substantive_result == "silent"
    links = (await session.execute(select(ClaimCheckEvidence.relation))).scalars().all()
    assert "read" in links


async def test_rejected_fact_cannot_drive_a_status(sm, session):
    """A model value that is not in its span is rejected by validation."""
    case = await _case(session)
    await _registry_evidence(session, case)

    def lying(system, user):
        if "Date of Incorporation" in evidence_block(user):
            # The span is real, but "Mumbai" is not in it.
            return {
                "speaks_to_claim": True,
                "facts": [_fact("hq_city", "Mumbai", "Registered Office: Baner Road")],
            }
        return {"speaks_to_claim": False, "facts": []}

    sentences = [("We are based in Mumbai", "location", [("hq_city", "Mumbai")])]
    llm = intake_llm(sentences)
    llm.responders["EvidenceFactsDraft"] = lying
    crust = pune_crustdata(enrich={k: v for k, v in ENRICH.items() if k != "locations"})
    _, ledger, _ = await _verify(sm, session, case, sentences, crust, llm=llm)
    [out] = ledger.values()
    assert out.status == "cannot_verify"
    check = (await session.execute(select(ClaimCheck))).scalar_one()
    step = await session.get(Step, check.step_id)
    # The value never reaches the rules: extraction drops it, and span validation
    # would reject it if it did.
    outcome = step.output["checks"][str(check.claim_id)]["outcome"]
    assert all(r["role"] == "rejected" for r in outcome["evidence"])
    assert not any(c["state"] == "matched" for c in outcome["components"])


async def test_check_waits_for_verify_steps_appended_after_it(sm, session):
    """CP-19 appends profile/registry steps once identity confirms; checks wait."""
    from app.jobs import StepSpec, append_steps

    case = await _case(session)
    sentences = [("We employ 250 people", "team_size", [("employee_count", "250")])]
    llm = intake_llm(sentences)
    [claim] = await _claims(session, case, llm, sentences)
    run = (await session.execute(select(Run))).scalar_one()
    await append_steps(session, run.id, [StepSpec("verify.profile", "noop")])
    await session.commit()
    set_client_factory(FakeFactory(llm_client=llm, crustdata_client=pune_crustdata()))
    await make_worker(sm, registry).drain()
    steps = {s.key: s for s in (await session.execute(select(Step))).scalars()}
    first, later = steps[f"checks.claim:{claim.id}"], steps[f"checks.claim:{claim.id}~1"]
    assert first.output["deferred_to"] == later.key
    assert "verify.profile" in later.depends_on and later.state == "done"
    # The assessment that waited for the first check also waits for its successor.
    assessments = [s for s in steps.values() if s.handler == "evaluate.assess"]
    assert assessments and all(later.key in s.depends_on for s in assessments)
    assert all(s.finished_at >= later.finished_at for s in assessments)
    checks = list((await session.execute(select(ClaimCheck))).scalars())
    assert len(checks) == 1 and checks[0].step_id == later.id


async def test_free_text_hq_address_never_contradicts_a_city(sm, session):
    """Found live: Crustdata gave `DLF QE, Haryana, India` for a Gurugram company."""
    case = await _case(session)
    enrich = {**ENRICH, "locations": {"headquarters": "DLF QE, Haryana, India", "country": "India"}}
    sentences = [
        ("We are headquartered in Gurugram", "location", [("hq_city", "Gurugram")]),
        ("We are headquartered in India", "location", [("country", "India")]),
    ]
    _, ledger, _ = await _verify(sm, session, case, sentences, pune_crustdata(enrich=enrich))
    city = ledger["We are headquartered in Gurugram"]
    assert city.status == "cannot_verify"
    assert "was read and does not state it" in city.reason
    assert ledger["We are headquartered in India"].status == "supported"


async def test_recheck_after_identity_pick_gets_new_steps(sm, session):
    from app.pipelines.verify.claims.intake import schedule_case_checks

    case = await _case(session, identity="ambiguous")
    sentences = [("We employ 250 people", "team_size", [("employee_count", "250")])]
    [claim], ledger, llm = await _verify(sm, session, case, sentences, pune_crustdata())
    assert ledger["We employ 250 people"].not_checked_reason == "identity_unresolved"
    case.identity_status = "confirmed"
    run = (await session.execute(select(Run))).scalar_one()
    [step, assess, flip, request] = await schedule_case_checks(session, case=case, run_id=run.id)
    await session.commit()
    assert step.key == f"checks.claim:{claim.id}@2"
    assert assess.key == "evaluate@2" and step.key in assess.depends_on
    assert flip.key == "decision_flip@2" and flip.depends_on == ["evaluate@2"]
    assert request.key == "request_list@2"
    assert request.depends_on == ["evaluate@2", "decision_flip@2"]
    await make_worker(sm, registry).drain()
    session.expire_all()
    await session.refresh(case)
    [out] = await build_claims_section(session, case)
    assert out.status == "cannot_verify" and len(out.history) == 2


async def test_claim_checks_end_in_an_assessment_version(sm, session):
    """Spec: `evaluate.assess` runs last in verify runs. Each batch of checks gets its own
    assessment step, after the last check, recording the documents that caused it."""
    from app.db.models import AssessmentVersion, Step

    case = await _case(session)
    sentences = [("We employ 250 people", "team_size", [("employee_count", "250")])]
    await _verify(sm, session, case, sentences, pune_crustdata())
    steps = {s.key: s for s in (await session.execute(select(Step))).scalars()}
    assert steps["evaluate"].state == "done"
    assert steps["evaluate"].tolerate_failed_deps is True
    [v1] = (await session.execute(select(AssessmentVersion))).scalars().all()
    assert v1.version == 1 and v1.trigger_document_ids == []

    doc_id = uuid.uuid4()
    llm = intake_llm([("We employ 300 people", "team_size", [("employee_count", "300")])])
    run = (await session.execute(select(Run))).scalar_one()
    claim = await add_typed_claim(
        session, case=case, text="We employ 300 people", llm=llm, retention_days=30
    )
    created = await schedule_claim_checks(
        session, run_id=run.id, claims=[claim], document_ids=[doc_id]
    )
    await session.commit()
    assert [s.key for s in created] == [
        f"checks.claim:{claim.id}",
        "evaluate@2",
        "decision_flip@2",
        "request_list@2",
    ]
    assert created[1].input["document_ids"] == [str(doc_id)]
    await make_worker(sm, registry).drain()
    session.expire_all()
    versions = (
        (await session.execute(select(AssessmentVersion).order_by(AssessmentVersion.version)))
        .scalars()
        .all()
    )
    assert [v.version for v in versions] == [1, 2]
    assert versions[1].trigger_document_ids == [str(doc_id)]
    assert versions[1].diff_from_previous is not None


# --- Confidentiality canary ---------------------------------------------------------

CANARY = "Project Falcon"


async def test_seller_words_never_reach_a_provider_request(sm, session):
    """A deal code name in the case name, the typed website and every claim component
    never appears in any request to the data provider (queries, fetches, lookups)."""
    case = await _case(session, website="https://project-falcon.example")
    case.company_name = CANARY
    await session.commit()
    sentences = [
        (
            f"{CANARY} opened a new facility in {CANARY} in October 2026",
            "dated_event",
            [
                ("event", f"{CANARY} facility"),
                ("event_date", "2026-10"),
                ("operating_city", CANARY),
                ("stage", "operating"),
            ],
        ),
        (
            f"{CANARY} raised growth funding from {CANARY} Capital in 2025",
            "funding",
            [("raised", "true"), ("round_year", "2025"), ("investor", f"{CANARY} Capital")],
        ),
        (
            f"{CANARY} is based in {CANARY}",
            "location",
            [("hq_city", CANARY), ("operating_city", CANARY)],
        ),
        (
            f"{CANARY} founder ran operations at {CANARY} Logistics",
            "leadership_history",
            [("person_name", CANARY), ("employer", f"{CANARY} Logistics"), ("role", "ops")],
        ),
        (f"{CANARY} employs 250 people", "team_size", [("employee_count", "250")]),
    ]
    crust = pune_crustdata()
    await _verify(sm, session, case, sentences, crust)

    names = [name for name, _ in crust.calls]
    assert "web_search" in names and "enrich_company" in names
    for name, params in crust.calls:
        assert CANARY.casefold() not in repr(params).casefold(), (name, params)
        assert "falcon" not in repr(params).casefold(), (name, params)
    queries = [p["query"] for n, p in crust.calls if n == "web_search"]
    assert all(NAME in q for q in queries)


async def test_registry_and_news_queries_use_the_confirmed_record_name(session):
    """The verify registry/news steps search by the confirmed record's name only."""
    from app.pipelines.verify import common

    case = await _case(session)
    case.company_name = CANARY
    with pytest.raises(common.IdentityNotConfirmed):  # no public name recorded yet
        common.PublicTerms.of(common.ConfirmedEntity.of(case))
    case.identity_identifiers = {"entity": {"name": NAME, "domains": [DOMAIN]}}
    terms = common.PublicTerms.of(common.ConfirmedEntity.of(case))
    for query in (common.news_query(terms), common.registry_query(terms)):
        assert NAME in query and "falcon" not in query.casefold()


async def test_iso_country_code_matches_a_claimed_country_name(sm, session):
    """Found live (PALMS WMS, 22 Nov 2026): the record's country is the ISO code `IND`,
    and "Head Quartered in Bangalore, India" was marked contradicted by it."""
    case = await _case(session)
    locations = {"headquarters": "HSR Layout, Karnataka, India", "country": "IND"}
    enrich = {**ENRICH, "locations": locations}
    sentences = [
        ("We are headquartered in India", "location", [("country", "India")]),
        ("We are headquartered in Singapore", "location", [("country", "Singapore")]),
    ]
    _, ledger, _ = await _verify(sm, session, case, sentences, pune_crustdata(enrich=enrich))
    assert ledger["We are headquartered in India"].status == "supported"
    assert ledger["We are headquartered in Singapore"].status == "contradicted"
