"""Contract fixtures: fictional, clearly labelled, validated by the response schemas.

Served by the API only when `DEALPROOF_FIXTURES=1`, and exported to
`apps/web/lib/api/fixtures.json` for the web app's `NEXT_PUBLIC_API_MODE=fixtures` mode.
Every company and investor here is invented and named "… (fixture)". URLs use the reserved
`.example` TLD. Nothing here is real data.

The story: a logistics thesis produces a shortlist; one company is opened as a case, its
eight claims cover all six statuses, a seller request went out in test mode, and a payroll
summary arrived, producing assessment version 2 with a diff. A second case is stuck on an
ambiguous identity.
"""

from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Any

from app.act.models import MessageStatus, SendStatus
from app.act.router import ApprovalOut, MessageOut, RevisionOut, SendOut
from app.api.schemas.assessments import (
    AssessmentVersionOut,
    BusinessAssessmentOut,
    BusinessSignalOut,
    DiffLineOut,
    DispositionReasonOut,
    EvidenceSufficiencyOut,
    FinancialAssessmentOut,
    FitState,
    JudgmentsOut,
    OpportunityFitOut,
    ScreeningDispositionOut,
    SufficiencyItemOut,
)
from app.api.schemas.auth import UserOut
from app.api.schemas.cases import (
    CaseCostOut,
    CaseDetail,
    CaseOut,
    CaseStatus,
    CaseSummary,
    ComparableCompanyOut,
    ComparablesOut,
    ComparisonBasisOut,
    CostLineOut,
    EventOut,
    IdentityCandidateOut,
    IdentityKeyOut,
    IdentityOut,
    OpportunityOut,
    RiskItemOut,
    SharedCostOut,
)
from app.api.schemas.claims import (
    ClaimCheckOut,
    ClaimOrigin,
    ClaimOut,
    NotCheckedReason,
    StatedInOut,
    SubstantiveResult,
)
from app.api.schemas.common import (
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    CostTotalsOut,
    CriterionDimension,
    CriterionKind,
    CriterionOperator,
    CriterionResultState,
    Disposition,
    EntityAttachment,
    EstimateKind,
    EvidenceOut,
    FactFloat,
    FactInt,
    FactStr,
    FactStrList,
    IdentityState,
    NamedUserOut,
    RunKind,
    RunState,
    SourceClass,
    SourceRecordOut,
    SourceRef,
    StepState,
)
from app.api.schemas.company import (
    CompanyProfileOut,
    FundingRoundOut,
    HeadcountPointOut,
    HeadcountSeriesOut,
    HiringOut,
    JobPostingOut,
    PersonOut,
)
from app.api.schemas.documents import DocumentKind, DocumentOut, DocumentUrlOut
from app.api.schemas.investors import (
    ComparableRoundOut,
    InvestorEntryOut,
    InvestorSearchIn,
    InvestorSearchOut,
    InvestorSearchSummary,
)
from app.api.schemas.policy import (
    AdequateSourcesOut,
    BudgetsOut,
    DispositionRuleOut,
    PolicyOut,
    PolicyThresholdsOut,
    PolicyWeightsOut,
    RequiredChecksOut,
    SettleWithOut,
)
from app.api.schemas.requests import (
    AnalystRetryOut,
    DraftEmailOut,
    RequestItemOut,
    RequestListOut,
)
from app.api.schemas.runs import RunOut, RunSummaryOut, StepOut
from app.api.schemas.theses import (
    CriterionOut,
    CriterionResultOut,
    ReasonOut,
    ShortlistCardOut,
    ShortlistItemOut,
    ThesisOut,
    ThesisStatus,
    ThesisSummary,
)

T0 = datetime(2026, 11, 22, 9, 30, tzinfo=UTC)


def _t(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


# ---------------------------------------------------------------- ids

USER_ID = "fx-user-1"
THESIS_ID = "fx-thesis-logistics"
INVESTOR_SEARCH_ID = "fx-investor-search-1"
CASE_ID = "fx-case-harbourline"
CASE_AMBIGUOUS_ID = "fx-case-shree"
DISCOVER_RUN_ID = "fx-run-discover"
INVESTOR_RUN_ID = "fx-run-investors"
VERIFY_RUN_ID = "fx-run-verify"
RECHECK_RUN_ID = "fx-run-recheck"
AMBIGUOUS_RUN_ID = "fx-run-verify-shree"
REQUEST_ID = "fx-request-1"
DECK_DOC_ID = "fx-doc-deck"
PAYROLL_DOC_ID = "fx-doc-payroll"

HARBOURLINE = "Harbourline Warehousing (fixture)"
HARBOURLINE_ID = 900001
HARBOURLINE_DOMAIN = "harbourline.example"

USER = UserOut(id=USER_ID, email="analyst@dealproof.example", display_name="Asha Analyst")
NAMED_USER = NamedUserOut(user_id=USER_ID, display_name=USER.display_name)


# ---------------------------------------------------------------- sources


def _src(
    sid: str,
    provider: str,
    label: str,
    url: str,
    cls: SourceClass,
    minutes: int = 2,
    origin: str | None = None,
) -> SourceRef:
    return SourceRef(
        source_id=sid,
        provider=provider,
        label=label,
        url_or_endpoint=url,
        retrieved_at=_t(minutes),
        source_class=cls,
        origin_id=origin,
    )


S_PROFILE = _src(
    "fx-src-enrich",
    "crustdata",
    "Company profile",
    "POST /company/enrich",
    SourceClass.data_provider,
)
S_HEADCOUNT = _src(
    "fx-src-headcount",
    "crustdata",
    "Headcount estimate",
    "POST /company/enrich#headcount",
    SourceClass.professional_profile_signal,
)
S_FUNDING = _src(
    "fx-src-funding",
    "crustdata",
    "Funding record",
    "POST /company/enrich#funding",
    SourceClass.data_provider,
)
S_REGISTRY = _src(
    "fx-src-registry",
    "web",
    "Registry mirror",
    "https://registry-mirror.example/company/harbourline-warehousing",
    SourceClass.registry_mirror,
    minutes=3,
)
S_CHARGE = _src(
    "fx-src-charge",
    "web",
    "Registry mirror: charges",
    "https://registry-mirror.example/company/harbourline-warehousing/charges",
    SourceClass.registry_mirror,
    minutes=3,
)
S_PEOPLE = _src(
    "fx-src-people",
    "crustdata",
    "Professional profile",
    "POST /person/search",
    SourceClass.professional_profile_signal,
    minutes=4,
)
S_JOBS = _src(
    "fx-src-jobs",
    "crustdata",
    "Job postings",
    "POST /job/search",
    SourceClass.data_provider,
    minutes=4,
)
S_NEWS_FUNDING = _src(
    "fx-src-news-funding",
    "web",
    "Logistics Daily",
    "https://logistics-daily.example/2024/02/harbourline-series-a",
    SourceClass.news,
    minutes=5,
    origin="fx-origin-funding-story",
)
S_ANNOUNCE = _src(
    "fx-src-announce",
    "web",
    "Company announcement",
    "https://harbourline.example/press/cold-storage-nashik",
    SourceClass.company_announcement,
    minutes=5,
    origin="fx-origin-cold-storage",
)
S_DECK = _src(
    "fx-src-deck",
    "upload",
    "Seller deck",
    "upload:harbourline_deck (fixture).pdf",
    SourceClass.seller_document,
    minutes=1,
)
S_PAYROLL = _src(
    "fx-src-payroll",
    "upload",
    "Payroll summary p. 1",
    "upload:payroll_summary_oct_2026 (fixture).pdf",
    SourceClass.seller_document,
    minutes=600,
)

ALL_SOURCES = [
    S_PROFILE,
    S_HEADCOUNT,
    S_FUNDING,
    S_REGISTRY,
    S_CHARGE,
    S_PEOPLE,
    S_JOBS,
    S_NEWS_FUNDING,
    S_ANNOUNCE,
    S_DECK,
    S_PAYROLL,
]

ATTACHED = EntityAttachment(
    entity_name=HARBOURLINE,
    matched_on=["crustdata_company_id", "domain"],
    identity_confidence=0.94,
)


def _fact(value: Any, source: SourceRef, as_of: date | None = None, **kw: Any) -> dict:
    return {"value": value, "source": source, "as_of": as_of, **kw}


def _est(value: int | float, source: SourceRef, as_of: date | None, basis: str) -> dict:
    return _fact(
        value,
        source,
        as_of,
        is_estimate=True,
        estimate_kind=EstimateKind.estimate,
        estimate_basis=basis,
    )


def _ev(
    eid: str,
    source: SourceRef,
    *,
    quote: str | None = None,
    page: int | None = None,
    field_path: str | None = None,
    value: Any = None,
    as_of: date | None = None,
) -> EvidenceOut:
    return EvidenceOut(
        evidence_id=eid,
        source=source,
        quote=quote,
        page=page,
        field_path=field_path,
        value=value,
        as_of=as_of,
        attached_to=ATTACHED,
    )


E_REG_INC = _ev(
    "fx-ev-reg-inc",
    S_REGISTRY,
    quote="Date of incorporation: 14 March 2016. Registered office: Nashik, Maharashtra.",
    as_of=date(2016, 3, 14),
)
E_HEADCOUNT = _ev(
    "fx-ev-headcount",
    S_HEADCOUNT,
    field_path="headcount.total",
    value=160,
    as_of=date(2026, 11, 1),
)
E_FOUNDER = _ev(
    "fx-ev-founder",
    S_PEOPLE,
    field_path="experience.employment_details.past[0]",
    value={"title": "Head of operations", "start": "2009", "end": "2015"},
    as_of=date(2015, 12, 31),
)
E_FUNDING_DB = _ev(
    "fx-ev-funding-db",
    S_FUNDING,
    field_path="funding.milestones[0]",
    value={"round_type": "series_a", "date": "2023-11-20"},
    as_of=date(2023, 11, 20),
)
E_FUNDING_NEWS = _ev(
    "fx-ev-funding-news",
    S_NEWS_FUNDING,
    quote="Harbourline closed its Series A round this month",
    as_of=date(2024, 2, 9),
)
E_FACILITY = _ev(
    "fx-ev-facility",
    S_ANNOUNCE,
    quote="We plan to open a 60,000 sq ft cold-storage facility in Nashik",
    as_of=date(2026, 7, 2),
)
E_CHARGE = _ev(
    "fx-ev-charge",
    S_CHARGE,
    quote="Charge created 2025-06-11 in favour of a scheduled bank",
    as_of=date(2025, 6, 11),
)
E_PAYROLL = _ev(
    "fx-ev-payroll",
    S_PAYROLL,
    quote="Employees on payroll as of 31 October 2026: 304",
    page=1,
    as_of=date(2026, 10, 31),
)


# ---------------------------------------------------------------- runs


def _cost(credits: float = 0, usd: float = 0, unknown: int = 0) -> CostTotalsOut:
    return CostTotalsOut(
        crustdata_credits=credits,
        llm_usd=usd,
        input_tokens=int(usd * 4_000_000),
        output_tokens=int(usd * 400_000),
        unknown_cost_calls=unknown,
    )


def _steps(run_id: str, specs: list[tuple[str, str, str | None, float, float]]) -> list[StepOut]:
    steps = []
    for i, (key, label, result, credits, usd) in enumerate(specs):
        steps.append(
            StepOut(
                id=f"{run_id}-step-{i + 1}",
                run_id=run_id,
                key=key,
                label=label,
                position=i,
                state=StepState.done,
                attempts=1,
                result=result,
                cost=_cost(credits, usd),
                started_at=_t(i),
                finished_at=_t(i + 1),
            )
        )
    return steps


def _run(
    run_id: str,
    kind: RunKind,
    subject: str,
    steps: list[StepOut],
    budget: float,
    **kw: Any,
) -> RunOut:
    credits = sum(s.cost.crustdata_credits for s in steps)
    usd = round(sum(s.cost.llm_usd for s in steps), 4)
    return RunOut(
        id=run_id,
        kind=kind,
        state=kw.pop("state", RunState.done),
        subject=subject,
        budget_credits=budget,
        cost=_cost(credits, usd, kw.pop("unknown", 0)),
        created_at=T0,
        finished_at=kw.pop("finished_at", _t(len(steps))),
        steps=steps,
        **kw,
    )


THESIS_TEXT = (
    "Privately held Indian warehousing and supply-chain software companies that serve "
    "enterprise customers and show recent expansion."
)


@cache
def runs() -> dict[str, RunOut]:
    discover = _run(
        DISCOVER_RUN_ID,
        RunKind.discover,
        THESIS_TEXT,
        _steps(
            DISCOVER_RUN_ID,
            [
                ("discover.search", "Search live company data", "48 companies found", 6.2, 0),
                ("discover.dedupe_gate", "Remove duplicates, apply must-haves", "41 kept", 0, 0),
                ("discover.enrich", "Enrich the top 15", "15 profiles read", 30, 0),
                ("discover.score", "Score fit and coverage", "4 ranked, 1 excluded", 0, 0),
                ("discover.cards", "Write shortlist cards", "4 cards", 0, 0.0021),
            ],
        ),
        60,
        thesis_id=THESIS_ID,
    )
    investors = _run(
        INVESTOR_RUN_ID,
        RunKind.investor_discover,
        "Warehousing and supply-chain software, India, Series A",
        _steps(
            INVESTOR_RUN_ID,
            [
                ("investors.comparables", "Find comparable companies", "40 companies", 6.5, 0),
                ("investors.enrich", "Read funding rounds", "25 enriched", 50, 0),
                ("investors.rank", "Rank investors by dated rounds", "3 investors", 0, 0),
            ],
        ),
        60,
        investor_search_id=INVESTOR_SEARCH_ID,
    )
    verify_steps = _steps(
        VERIFY_RUN_ID,
        [
            ("verify.identity", "Confirm identity", "matched on domain + company id", 0.4, 0),
            ("verify.registry", "Read registry evidence", "2 registry pages", 4, 0.0012),
            ("verify.profile", "Build public profile", "profile read", 2, 0),
            ("verify.people", "Check leadership records", "6 leaders", 5.5, 0),
            ("verify.jobs", "Read dated job postings", "10 postings", 0.3, 0),
            (
                "claims.extract:fx-doc-deck",
                "Extract claims from the deck",
                "8 claims, 1 dropped (quote not found)",
                0,
                0.0046,
            ),
            ("evidence.claim:fx-claim-1", "Check: incorporated 2016", "supported", 0, 0.0008),
            ("evidence.claim:fx-claim-2", "Check: 300 employees", "cannot verify", 0, 0.0004),
            ("evidence.claim:fx-claim-3", "Check: founder history", "supported", 0, 0.0007),
            ("evidence.claim:fx-claim-4", "Check: Series A in 2024", "conflicting", 2, 0.0013),
            ("evidence.claim:fx-claim-5", "Check: cold-storage facility", "partial", 3, 0.0019),
            ("evidence.claim:fx-claim-7", "Check: registered office", "contradicted", 0, 0.0006),
            ("evidence.claim:fx-claim-8", "Check: no debt", "cannot verify", 1, 0.0009),
            ("evidence.events", "Collect dated events", "3 events", 0, 0.0011),
            ("evidence.comparables", "Find fair comparables", "2 peers", 1.3, 0),
            ("evaluate.assess", "Assess (version 1)", "investigate further", 0, 0),
        ],
    )
    skipped = StepOut(
        id=f"{VERIFY_RUN_ID}-step-skipped",
        run_id=VERIFY_RUN_ID,
        key="evidence.claim:fx-claim-6",
        label="Check: 40 enterprise customers",
        position=len(verify_steps),
        state=StepState.skipped_budget,
        attempts=1,
        result="budget reached",
    )
    verify = _run(
        VERIFY_RUN_ID,
        RunKind.verify,
        HARBOURLINE,
        [*verify_steps, skipped],
        150,
        case_id=CASE_ID,
        checks_not_run=1,
        unknown=1,
        resumed_at=_t(7),
    )
    recheck = _run(
        RECHECK_RUN_ID,
        RunKind.recheck,
        HARBOURLINE,
        _steps(
            RECHECK_RUN_ID,
            [
                ("claims.extract_text:fx-doc-payroll", "Read payroll summary", "1 page", 0, 0),
                ("recheck.facts:fx-claim-2", "Re-check: 300 employees", "supported", 0, 0.0005),
                ("evaluate.assess", "Assess (version 2)", "investigate further", 0, 0),
            ],
        ),
        150,
        case_id=CASE_ID,
    )
    ambiguous = _run(
        AMBIGUOUS_RUN_ID,
        RunKind.verify,
        "Shree Cargo Links (fixture)",
        _steps(
            AMBIGUOUS_RUN_ID,
            [("verify.identity", "Confirm identity", "2 close candidates: ambiguous", 0.4, 0)],
        ),
        150,
        case_id=CASE_AMBIGUOUS_ID,
    )
    return {r.id: r for r in (discover, investors, verify, recheck, ambiguous)}


def run_summary(run: RunOut) -> RunSummaryOut:
    return RunSummaryOut(
        id=run.id,
        kind=run.kind,
        state=run.state,
        created_at=run.created_at,
        finished_at=run.finished_at,
        cost=run.cost,
    )


# ---------------------------------------------------------------- discover


def _criterion(i: int, label: str, kind, dim, op, value, filt) -> CriterionOut:
    return CriterionOut(
        id=f"fx-crit-{i}",
        position=i - 1,
        label=label,
        kind=kind,
        dimension=dim,
        operator=op,
        value=value,
        crustdata_filter=filt,
        assessed_from_evidence=filt is None,
    )


M, P = CriterionKind.must, CriterionKind.preference
CRITERIA = [
    _criterion(
        1,
        "Headquartered in India",
        M,
        CriterionDimension.geography,
        CriterionOperator.eq,
        "India",
        {"field": "locations.country", "type": "=", "value": "India"},
    ),
    _criterion(
        2,
        "Warehousing or supply-chain software",
        M,
        CriterionDimension.industry_activity,
        CriterionOperator.contains_any,
        ["warehousing", "supply chain", "logistics software"],
        None,
    ),
    _criterion(
        3, "Privately held", M, CriterionDimension.ownership, CriterionOperator.is_true, True, None
    ),
    _criterion(
        4,
        "Serves enterprise customers",
        P,
        CriterionDimension.customer_type,
        CriterionOperator.is_true,
        True,
        None,
    ),
    _criterion(
        5,
        "50 to 1,000 employees",
        P,
        CriterionDimension.size,
        CriterionOperator.between,
        [50, 1000],
        {"field": "headcount.total", "type": "=>", "value": 50},
    ),
    _criterion(
        6,
        "Recent expansion",
        P,
        CriterionDimension.growth_signal,
        CriterionOperator.is_true,
        True,
        None,
    ),
]

_PASS, _FAIL, _UNK = (
    CriterionResultState.pass_,
    CriterionResultState.fail,
    CriterionResultState.unknown,
)


def _results(states: list[CriterionResultState], evidence: dict[int, list[EvidenceOut]]):
    reasons = {
        _PASS: "Record matches",
        _FAIL: "Record conflicts with the criterion",
        _UNK: "No record states this; assessed from evidence later",
    }
    return [
        CriterionResultOut(
            criterion_id=c.id,
            label=c.label,
            kind=c.kind,
            weight=2 if c.kind == M else 1,
            state=s,
            reason=reasons[s],
            evidence=evidence.get(i, []),
        )
        for i, (c, s) in enumerate(zip(CRITERIA, states, strict=True))
    ]


HARBOURLINE_RESULTS = _results(
    [_PASS, _PASS, _UNK, _UNK, _PASS, _FAIL], {0: [E_REG_INC], 4: [E_HEADCOUNT]}
)


def _card(name: str, city: str, headcount: int, growth: float | None, **kw: Any):
    src = S_PROFILE.model_copy(update={"source_id": f"fx-src-enrich-{name[:4].lower()}"})
    hsrc = S_HEADCOUNT.model_copy(update={"source_id": f"fx-src-headcount-{name[:4].lower()}"})
    basis = "from professional profiles, not a payroll count"
    return ShortlistCardOut(
        business=FactStr(**_fact(kw.pop("business"), src, date(2026, 11, 1))),
        location=FactStr(**_fact(f"{city}, India", src, date(2026, 11, 1))),
        headcount=FactInt(**_est(headcount, hsrc, date(2026, 11, 1), basis)),
        headcount_growth_yoy_pct=(
            FactFloat(**_est(growth, hsrc, date(2026, 11, 1), basis))
            if growth is not None
            else None
        ),
        last_updated=_t(3),
        **kw,
    )


@cache
def shortlist() -> list[ShortlistItemOut]:
    harbour_rounds = [
        FundingRoundOut(
            round_type="series_a",
            date=date(2023, 11, 20),
            amount_usd=6_000_000,
            investors=["Northgate Ventures (fixture)"],
            source=S_FUNDING,
            evidence_id=E_FUNDING_DB.evidence_id,
        )
    ]
    hiring = HiringOut(
        openings=FactInt(
            **_fact(
                12,
                S_PROFILE,
                date(2026, 11, 1),
                is_estimate=True,
                estimate_kind=EstimateKind.signal,
                estimate_basis="open roles are a hiring signal, not revenue",
            )
        ),
        postings=[
            JobPostingOut(
                title="Warehouse operations manager",
                date_added=date(2026, 10, 28),
                location="Nashik",
                source=S_JOBS,
            )
        ],
    )
    return [
        ShortlistItemOut(
            id="fx-sl-kestrel",
            rank=1,
            crustdata_company_id=900002,
            name="Kestrel Supply Systems (fixture)",
            domain="kestrel-supply.example",
            fit=100,
            assessable_pct=50,
            criterion_results=_results([_PASS, _PASS, _UNK, _UNK, _PASS, _UNK], {}),
            card=_card(
                "Kestrel Supply Systems (fixture)",
                "Bengaluru",
                85,
                None,
                business="Warehouse management software for mid-size distributors",
                reasons=[ReasonOut(text="Headquartered in India", criterion_id="fx-crit-1")],
                unknowns=["Ownership not stated", "Customer type not stated", "No growth data"],
            ),
        ),
        ShortlistItemOut(
            id="fx-sl-harbourline",
            rank=2,
            crustdata_company_id=HARBOURLINE_ID,
            name=HARBOURLINE,
            domain=HARBOURLINE_DOMAIN,
            fit=83,
            assessable_pct=67,
            criterion_results=HARBOURLINE_RESULTS,
            card=_card(
                HARBOURLINE,
                "Nashik",
                160,
                18.5,
                business="Contract warehousing and cold storage for manufacturers",
                funding_rounds=harbour_rounds,
                total_funding_usd=FactFloat(**_fact(6_000_000.0, S_FUNDING, date(2023, 11, 20))),
                hiring=hiring,
                reasons=[
                    ReasonOut(
                        text="Headquartered in India",
                        criterion_id="fx-crit-1",
                        evidence_ids=[E_REG_INC.evidence_id],
                    ),
                    ReasonOut(text="Warehousing operator", criterion_id="fx-crit-2"),
                    ReasonOut(
                        text="About 160 employees (estimate)",
                        criterion_id="fx-crit-5",
                        evidence_ids=[E_HEADCOUNT.evidence_id],
                    ),
                ],
                unknowns=["Ownership not stated", "Enterprise customers not on record"],
            ),
            case_id=CASE_ID,
        ),
        ShortlistItemOut(
            id="fx-sl-morrow",
            rank=3,
            crustdata_company_id=900003,
            name="Morrow Docks (fixture)",
            fit=None,
            fit_unavailable_reason="No criterion could be assessed from the records found",
            assessable_pct=0,
            criterion_results=_results([_UNK] * 6, {}),
            card=_card(
                "Morrow Docks (fixture)",
                "Kochi",
                40,
                None,
                business="Port-side storage",
                unknowns=["Most profile fields are empty"],
            ),
        ),
        ShortlistItemOut(
            id="fx-sl-tarawade",
            rank=None,
            crustdata_company_id=900004,
            name="Tarawade Freight Software (fixture)",
            fit=40,
            assessable_pct=50,
            excluded=True,
            exclusion_reason="Must-have failed: headquartered in Singapore, not India",
            criterion_results=_results([_FAIL, _PASS, _UNK, _UNK, _FAIL, _UNK], {}),
            card=_card(
                "Tarawade Freight Software (fixture)",
                "Singapore",
                1400,
                None,
                business="Freight booking software",
            ),
        ),
    ]


@cache
def thesis() -> ThesisOut:
    return ThesisOut(
        id=THESIS_ID,
        text=THESIS_TEXT,
        status=ThesisStatus.ready,
        created_at=T0,
        criteria=CRITERIA,
        run=runs()[DISCOVER_RUN_ID],
        shortlist=shortlist(),
    )


def thesis_draft(text: str) -> ThesisOut:
    """`POST /theses` in fixture mode: criteria extracted, no run yet."""
    return thesis().model_copy(
        update={"text": text, "status": ThesisStatus.draft, "run": None, "shortlist": []}
    )


def thesis_summaries() -> list[ThesisSummary]:
    t = thesis()
    return [
        ThesisSummary(
            id=t.id,
            text=t.text,
            status=t.status,
            created_at=t.created_at,
            criteria_count=len(t.criteria),
            shortlist_count=len([s for s in t.shortlist if not s.excluded]),
            latest_run_id=DISCOVER_RUN_ID,
        )
    ]


# ---------------------------------------------------------------- investors

INVESTOR_PROFILE = InvestorSearchIn(
    sector="Warehousing and supply-chain software",
    location="India",
    stage="series_a",
    size="51-200",
    funding_sought="equity venture",
)


def _round(cid: int, name: str, rt: str, d: date, amt: float | None, n: int) -> ComparableRoundOut:
    return ComparableRoundOut(
        company_id=cid,
        company_name=name,
        round_type=rt,
        date=d,
        amount_usd=amt,
        source=S_FUNDING.model_copy(update={"source_id": f"fx-src-funding-{n}"}),
        evidence_id=f"fx-ev-round-{n}",
    )


@cache
def investor_search() -> InvestorSearchOut:
    entries = [
        InvestorEntryOut(
            id="fx-inv-northgate",
            rank=1,
            investor_name="Northgate Ventures (fixture)",
            investor_key="uuid:fx-northgate",
            investor_uuid="fx-northgate",
            score=1.62,
            comparable_rounds=[
                _round(HARBOURLINE_ID, HARBOURLINE, "series_a", date(2023, 11, 20), 6e6, 1),
                _round(
                    900002, "Kestrel Supply Systems (fixture)", "seed", date(2025, 4, 2), None, 2
                ),
            ],
            latest_sector_investment_found=date(2025, 4, 2),
            why="2 comparable rounds in warehousing software, latest 2025-04",
            funding_kind_compatibility="led 1 venture round in this record, latest 2023-11",
            unknowns=["Cheque size unknown for 1 round"],
        ),
        InvestorEntryOut(
            id="fx-inv-banyan",
            rank=2,
            investor_name="Banyan Seed Partners (fixture)",
            investor_key="name:banyan seed partners (fixture)",
            score=0.84,
            comparable_rounds=[
                _round(900005, "Ridgeway Cold Chain (fixture)", "seed", date(2024, 9, 1), 1.5e6, 3)
            ],
            latest_sector_investment_found=date(2024, 9, 1),
            why="1 comparable seed round in cold-chain logistics",
            funding_kind_compatibility="compatibility with equity venture unknown",
            unknowns=["No round larger than seed found"],
        ),
        InvestorEntryOut(
            id="fx-inv-banyan-llp",
            rank=3,
            investor_name="Banyan Seed Partners LLP (fixture)",
            investor_key="name:banyan seed partners llp (fixture)",
            score=0.5,
            comparable_rounds=[
                _round(900006, "Lattice Yards (fixture)", "pre_seed", date(2022, 1, 15), None, 4)
            ],
            latest_sector_investment_found=date(2022, 1, 15),
            why="1 comparable pre-seed round",
            funding_kind_compatibility="compatibility with equity venture unknown",
            unknowns=["Cheque size unknown"],
            possible_duplicate_of="fx-inv-banyan",
        ),
    ]
    return InvestorSearchOut(
        id=INVESTOR_SEARCH_ID,
        profile=INVESTOR_PROFILE,
        status=ThesisStatus.ready,
        created_at=T0,
        searched_at=_t(3),
        scope_note="searched 2026-11-22 across 40 comparable companies",
        comparables_considered=40,
        run=runs()[INVESTOR_RUN_ID],
        entries=entries,
    )


def investor_summaries() -> list[InvestorSearchSummary]:
    s = investor_search()
    return [
        InvestorSearchSummary(
            id=s.id,
            sector=s.profile.sector,
            location=s.profile.location,
            stage=s.profile.stage,
            status=s.status,
            created_at=s.created_at,
            entries_count=len(s.entries),
        )
    ]


# ---------------------------------------------------------------- case: claims


def _check(n: int, status: ClaimStatus, reason: str, version: int, **kw: Any) -> ClaimCheckOut:
    return ClaimCheckOut(
        id=f"fx-check-{n}-v{version}",
        run_id=VERIFY_RUN_ID if version == 1 else RECHECK_RUN_ID,
        status=status,
        reason=reason,
        assessment_version=version,
        created_at=_t(10) if version == 1 else _t(610),
        **kw,
    )


def _claim(
    n: int,
    text: str,
    category: ClaimCategory,
    page: int,
    history: list[ClaimCheckOut],
    evidence: list[EvidenceOut],
    **kw: Any,
) -> ClaimOut:
    latest = history[-1]
    return ClaimOut(
        id=f"fx-claim-{n}",
        number=n,
        original_text=text,
        normalised_text=kw.pop("normalised", text),
        category=category,
        components=kw.pop("components", {}),
        origin=ClaimOrigin.document,
        stated_in=StatedInOut(
            document_id=DECK_DOC_ID,
            filename="harbourline_deck (fixture).pdf",
            page=page,
            quote=text,
        ),
        status=latest.status,
        reason=latest.reason,
        not_checked_reason=latest.not_checked_reason,
        settle_with=latest.settle_with,
        evidence=evidence,
        history=history,
        **kw,
    )


S, CV, PC, CE, CT, NC = (
    ClaimStatus.supported,
    ClaimStatus.cannot_verify,
    ClaimStatus.partially_corroborated,
    ClaimStatus.conflicting_evidence,
    ClaimStatus.contradicted,
    ClaimStatus.not_checked,
)

TEAM_CV_REASON = "Profile-based estimate of 160; warehouse staff rarely have professional profiles"


def claims(version: int = 2) -> list[ClaimOut]:
    team_history = [_check(2, CV, TEAM_CV_REASON, 1, settle_with="Dated payroll summary")]
    team_evidence = [E_HEADCOUNT]
    team_kw: dict[str, Any] = {
        "adequate_source_reached": False,
        "substantive_result": SubstantiveResult.silent,
    }
    if version >= 2:
        team_history.append(
            _check(
                2,
                S,
                "Dated payroll summary states 304 employees as of 31 October 2026",
                2,
                evidence_ids=[E_PAYROLL.evidence_id],
            )
        )
        team_evidence = [E_PAYROLL, E_HEADCOUNT]
        team_kw = {
            "adequate_source_reached": True,
            "substantive_result": SubstantiveResult.supports,
            "changed_in_version": 2,
        }
    return [
        _claim(
            1,
            "Incorporated in 2016",
            ClaimCategory.identity_incorporation,
            2,
            [_check(1, S, "The registry record states the incorporation date", 1)],
            [E_REG_INC],
            components={"incorporation_year": 2016},
            adequate_source_reached=True,
            substantive_result=SubstantiveResult.supports,
        ),
        _claim(
            2,
            "We employ 300 people",
            ClaimCategory.team_size,
            3,
            team_history,
            team_evidence,
            components={"employees": 300},
            **team_kw,
        ),
        _claim(
            3,
            "Our founder ran operations at a national courier firm",
            ClaimCategory.leadership_history,
            4,
            [_check(3, S, "A professional record shows the role and the years", 1)],
            [E_FOUNDER],
            adequate_source_reached=True,
            substantive_result=SubstantiveResult.supports,
        ),
        _claim(
            4,
            "We raised our Series A in 2024",
            ClaimCategory.funding,
            5,
            [
                _check(
                    4,
                    CE,
                    "The funding record dates the round to November 2023; a news report "
                    "dates it to February 2024",
                    1,
                    settle_with="Share allotment filing or term sheet",
                )
            ],
            [E_FUNDING_DB, E_FUNDING_NEWS],
            components={"round_type": "series_a", "year": 2024},
            adequate_source_reached=True,
            substantive_result=SubstantiveResult.conflicts,
        ),
        _claim(
            5,
            "We opened a cold-storage facility in Nashik in August 2026",
            ClaimCategory.dated_event,
            7,
            [
                _check(
                    5,
                    PC,
                    "A dated announcement describes a planned facility; nothing found shows "
                    "it is operating",
                    1,
                    settle_with="Lease or occupancy evidence for the facility",
                )
            ],
            [E_FACILITY],
            components={"event": "facility", "stage": "operating", "date": "2026-08"},
            adequate_source_reached=True,
            substantive_result=SubstantiveResult.partial,
        ),
        _claim(
            6,
            "We serve 40 enterprise customers",
            ClaimCategory.customer_partnership,
            8,
            [
                _check(
                    6,
                    NC,
                    "Budget reached before this check ran",
                    1,
                    not_checked_reason=NotCheckedReason.budget_reached,
                )
            ],
            [],
        ),
        _claim(
            7,
            "Registered office in Pune",
            ClaimCategory.location,
            2,
            [
                _check(
                    7,
                    CT,
                    "The registry record gives the registered office as Nashik",
                    1,
                    settle_with="Certificate of incorporation",
                )
            ],
            [E_REG_INC],
            components={"registered_city": "Pune"},
            adequate_source_reached=True,
            substantive_result=SubstantiveResult.conflicts,
        ),
        _claim(
            8,
            "We have no debt",
            ClaimCategory.debt_security,
            9,
            [
                _check(
                    8,
                    CV,
                    "A registered charge shows security was given, not that money is owed",
                    1,
                    settle_with="Lender statements",
                )
            ],
            [E_CHARGE],
            adequate_source_reached=False,
            substantive_result=SubstantiveResult.silent,
        ),
    ]


# ---------------------------------------------------------------- case: assessment


def _assessment(version: int) -> AssessmentVersionOut:
    team_settled = version >= 2
    settled = [
        SufficiencyItemOut(
            category=ClaimCategory.identity_incorporation, status=S, claim_ids=["fx-claim-1"]
        ),
        SufficiencyItemOut(
            category=ClaimCategory.leadership_history, status=S, claim_ids=["fx-claim-3"]
        ),
    ]
    gaps = [
        SufficiencyItemOut(
            category=ClaimCategory.funding,
            status=CE,
            claim_ids=["fx-claim-4"],
            settle_with="Share allotment filing or term sheet",
        )
    ]
    team_item = SufficiencyItemOut(
        category=ClaimCategory.team_size,
        status=S if team_settled else CV,
        claim_ids=["fx-claim-2"],
        settle_with=None if team_settled else "Dated payroll summary",
    )
    (settled if team_settled else gaps).append(team_item)
    pct = 75 if team_settled else 50
    signal_kw = {"is_estimate": True, "estimate_kind": EstimateKind.signal}
    judgments = JudgmentsOut(
        opportunity_fit=OpportunityFitOut(
            state=FitState.scored,
            fit=83,
            assessable_pct=67,
            criterion_results=HARBOURLINE_RESULTS,
        ),
        evidence_sufficiency=EvidenceSufficiencyOut(
            pct=pct,
            required_categories=[
                ClaimCategory.identity_incorporation,
                ClaimCategory.leadership_history,
                ClaimCategory.team_size,
                ClaimCategory.funding,
            ],
            settled=settled,
            gaps=gaps,
        ),
        business_assessment=BusinessAssessmentOut(
            assessed=True,
            signals=[
                BusinessSignalOut(
                    label="Headcount trend",
                    fact=FactStr(
                        **_fact(
                            "+18.5% year on year",
                            S_HEADCOUNT,
                            date(2026, 11, 1),
                            estimate_basis="profile-based headcount series",
                            **signal_kw,
                        )
                    ),
                ),
                BusinessSignalOut(
                    label="Hiring",
                    fact=FactStr(
                        **_fact(
                            "12 open roles",
                            S_JOBS,
                            date(2026, 10, 28),
                            estimate_basis="open roles, not revenue",
                            **signal_kw,
                        )
                    ),
                ),
            ],
        ),
        financial_assessment=FinancialAssessmentOut(
            assessed=False,
            reason="No reliable financial inputs",
            would_need=["Audited financial statements"],
        ),
        screening_disposition=ScreeningDispositionOut(
            disposition=Disposition.investigate_further,
            reasons=[
                DispositionReasonOut(text="Strong fit with the thesis (83, 67% assessable)"),
                DispositionReasonOut(
                    text=f"Evidence sufficiency {pct}%, below the 80% needed to prioritise"
                ),
                DispositionReasonOut(
                    text="Funding timing has conflicting evidence", claim_ids=["fx-claim-4"]
                ),
            ],
        ),
    )
    diff = None
    if version >= 2:
        diff = [
            DiffLineOut(
                kind="claim",
                subject="We employ 300 people",
                subject_id="fx-claim-2",
                before=CV.value,
                after=S.value,
                because="payroll_summary_oct_2026 (fixture).pdf, p. 1",
                evidence=[E_PAYROLL],
            ),
            DiffLineOut(
                kind="judgment",
                subject="evidence_sufficiency",
                before="50",
                after="75",
                because="Team size is now settled",
            ),
        ]
    return AssessmentVersionOut(
        id=f"fx-assessment-v{version}",
        version=version,
        created_at=_t(16) if version == 1 else _t(612),
        policy_version="2026-11-22.1",
        inputs_hash=f"sha256:fixture-v{version}",
        trigger="initial verify"
        if version == 1
        else "seller documents payroll_summary_oct_2026 (fixture).pdf",
        company_type=CompanyType.startup,
        judgments=judgments,
        diff_from_previous=diff,
    )


def assessments(case_id: str) -> list[AssessmentVersionOut]:
    if case_id == CASE_ID:
        return [_assessment(1), _assessment(2)]
    return []


# ---------------------------------------------------------------- case: act


REQUEST_ITEMS = [
    RequestItemOut(
        id="fx-item-payroll",
        document="Dated payroll summary",
        reason="Profile counts under-count warehouse staff",
        categories=[ClaimCategory.team_size],
        claim_ids=["fx-claim-2"],
        questions=["How many people are on payroll today?"],
    ),
    RequestItemOut(
        id="fx-item-lease",
        document="Lease or occupancy evidence for the facility",
        reason="The announcement describes a planned facility",
        categories=[ClaimCategory.dated_event],
        claim_ids=["fx-claim-5"],
        questions=["Is the Nashik cold-storage facility operating?"],
    ),
    RequestItemOut(
        id="fx-item-lender",
        document="Lender statements",
        reason="A registered charge exists; the balance owed is not on record",
        categories=[ClaimCategory.debt_security],
        claim_ids=["fx-claim-8"],
        questions=["Is any amount outstanding under the registered charge?"],
    ),
    RequestItemOut(
        id="fx-item-allotment",
        document="Share allotment filing or term sheet",
        reason="Sources disagree on when the Series A closed",
        categories=[ClaimCategory.funding],
        claim_ids=["fx-claim-4"],
        questions=["When did the Series A close?"],
    ),
    RequestItemOut(
        id="fx-item-coi",
        document="Certificate of incorporation",
        reason="The registry gives a different registered office",
        categories=[ClaimCategory.location],
        claim_ids=["fx-claim-7"],
        questions=["Where is the registered office?"],
    ),
]

DRAFT_BODY = (
    "Hello,\n\nThank you for the meeting. To complete our first-pass screening we would be "
    "grateful for the following documents:\n\n"
    "1. A dated payroll summary\n"
    "2. Lease or occupancy evidence for the Nashik cold-storage facility\n"
    "3. Lender statements for the registered charge\n"
    "4. The share allotment filing or term sheet for the Series A\n"
    "5. The certificate of incorporation\n\nKind regards,\nAsha Analyst"
)


SUBJECT = "Documents for our screening of Harbourline Warehousing (fixture)"
MESSAGE_ID = "fx-message-1"


def request_list() -> RequestListOut:
    return RequestListOut(
        id=REQUEST_ID,
        case_id=CASE_ID,
        assessment_version=1,
        items=REQUEST_ITEMS,
        analyst_retries=[
            AnalystRetryOut(
                claim_id="fx-claim-6",
                label="Check: 40 enterprise customers",
                reason="Budget reached",
                estimated_credits=1.0,
            )
        ],
        draft=DraftEmailOut(subject=SUBJECT, body=DRAFT_BODY),
        message_id=MESSAGE_ID,
        email_send_enabled=False,
        created_at=_t(20),
    )


def _revision(n: int, recipient: str) -> RevisionOut:
    return RevisionOut(
        id=f"fx-rev-{n}",
        number=n,
        subject=SUBJECT,
        body=DRAFT_BODY,
        recipient=recipient,
        entered_by_user_id=USER_ID,
        created_at=_t(20 + n),
    )


def message(state: str = "suppressed") -> MessageOut:
    """The Act message in one of: draft, edited, approved, suppressed (test-mode send)."""
    revs = [_revision(1, "")]
    if state != "draft":
        revs.append(_revision(2, "cfo@harbourline.example"))
    approval = None
    send = None
    status = MessageStatus.DRAFT
    if state in ("approved", "suppressed"):
        approval = ApprovalOut(
            revision_id=revs[-1].id,
            approver_user_id=USER_ID,
            approver_display_name=USER.display_name,
            approved_at=_t(25),
        )
        status = MessageStatus.APPROVED
    if state == "suppressed":
        status = MessageStatus.SUPPRESSED_TEST_MODE
        send = SendOut(
            id="fx-send-1",
            revision_id=revs[-1].id,
            status=SendStatus.SUPPRESSED_TEST_MODE,
            test_mode=True,
            attempts=1,
            provider_message_id=None,
            error=None,
            created_at=_t(26),
            dispatched_at=None,
            completed_at=_t(26),
        )
    return MessageOut(
        id=MESSAGE_ID,
        case_id=CASE_ID,
        status=status,
        current_revision=revs[-1],
        approval=approval,
        send=send,
        revisions=revs,
    )


# ---------------------------------------------------------------- case: documents


def documents() -> list[DocumentOut]:
    return [
        DocumentOut(
            id=DECK_DOC_ID,
            case_id=CASE_ID,
            kind=DocumentKind.seller_deck,
            filename="harbourline_deck (fixture).pdf",
            mime="application/pdf",
            size_bytes=2_400_000,
            pages=12,
            uploaded_at=T0,
            uploaded_by_name=USER.display_name,
            delete_after=T0 + timedelta(days=30),
            redaction_counts={"email": 2, "phone": 3},
            claims_extracted=8,
        ),
        DocumentOut(
            id=PAYROLL_DOC_ID,
            case_id=CASE_ID,
            kind=DocumentKind.seller_response,
            filename="payroll_summary_oct_2026 (fixture).pdf",
            mime="application/pdf",
            size_bytes=180_000,
            pages=1,
            uploaded_at=_t(600),
            uploaded_by_name=USER.display_name,
            delete_after=_t(600) + timedelta(days=30),
            redaction_counts={"pan": 1},
            answers_request_item_ids=["fx-item-payroll"],
            claims_extracted=1,
            run=runs()[RECHECK_RUN_ID],
        ),
    ]


def uploaded_document(kind: DocumentKind) -> DocumentOut:
    doc = documents()[1 if kind == DocumentKind.seller_response else 0]
    return doc


def document_url(document_id: str) -> DocumentUrlOut:
    return DocumentUrlOut(
        url=f"https://storage.example/fixture/{document_id}?signature=fixture",
        expires_at=_t(15),
    )


# ---------------------------------------------------------------- case: detail


def _profile() -> CompanyProfileOut:
    basis = "from professional profiles, not a payroll count"
    return CompanyProfileOut(
        crustdata_company_id=HARBOURLINE_ID,
        name=FactStr(**_fact(HARBOURLINE, S_PROFILE)),
        legal_name=FactStr(
            **_fact("Harbourline Warehousing Private Limited (fixture)", S_REGISTRY)
        ),
        domain=FactStr(**_fact(HARBOURLINE_DOMAIN, S_PROFILE)),
        description=FactStr(
            **_fact("Contract warehousing and cold storage for manufacturers", S_PROFILE)
        ),
        industries=FactStrList(**_fact(["Warehousing", "Logistics"], S_PROFILE)),
        headquarters=FactStr(**_fact("Nashik, Maharashtra", S_PROFILE, date(2026, 11, 1))),
        country=FactStr(**_fact("India", S_PROFILE)),
        year_founded=FactInt(**_fact(2016, S_REGISTRY, date(2016, 3, 14))),
        incorporation_date=FactStr(**_fact("2016-03-14", S_REGISTRY, date(2016, 3, 14))),
        registry_id=FactStr(**_fact("U00000MH2016PTC000000", S_REGISTRY)),
        company_type=CompanyType.startup,
        company_type_reason="Founded 2016 (within 10 years) and last round Series A",
        headcount=FactInt(**_est(160, S_HEADCOUNT, date(2026, 11, 1), basis)),
        headcount_growth_yoy_pct=FactFloat(**_est(18.5, S_HEADCOUNT, date(2026, 11, 1), basis)),
        headcount_series=HeadcountSeriesOut(
            points=[
                HeadcountPointOut(date=date(2025, 11, 1), employee_count=135),
                HeadcountPointOut(date=date(2026, 5, 1), employee_count=148),
                HeadcountPointOut(date=date(2026, 11, 1), employee_count=160),
            ],
            source=S_HEADCOUNT,
        ),
        total_funding_usd=FactFloat(**_fact(6_000_000.0, S_FUNDING, date(2023, 11, 20))),
        funding_rounds=shortlist()[1].card.funding_rounds,
        people=[
            PersonOut(
                person_id="fx-person-1",
                name="R. Founder (fixture)",
                title=FactStr(**_fact("Founder and CEO", S_PEOPLE)),
                history=[
                    FactStr(
                        **_fact(
                            "Head of operations, national courier firm, 2009-2015",
                            S_PEOPLE,
                            date(2015, 12, 31),
                        )
                    )
                ],
            )
        ],
        hiring=shortlist()[1].card.hiring,
    )


def _case_out(case_id: str) -> CaseOut:
    if case_id == CASE_AMBIGUOUS_ID:
        return CaseOut(
            id=CASE_AMBIGUOUS_ID,
            name="Shree Cargo Links (fixture)",
            website="shreecargo.example",
            status=CaseStatus.awaiting_identity,
            identity_state=IdentityState.ambiguous,
            credit_budget=150,
            created_at=_t(30),
            owner=NAMED_USER,
            run=runs()[AMBIGUOUS_RUN_ID],
        )
    return CaseOut(
        id=CASE_ID,
        name=HARBOURLINE,
        website=f"https://{HARBOURLINE_DOMAIN}",
        status=CaseStatus.assessed,
        identity_state=IdentityState.confirmed,
        crustdata_company_id=HARBOURLINE_ID,
        thesis_id=THESIS_ID,
        shortlist_item_id="fx-sl-harbourline",
        credit_budget=150,
        created_at=T0,
        owner=NAMED_USER,
        run=runs()[RECHECK_RUN_ID],
    )


def _ambiguous_detail() -> CaseDetail:
    candidates = [
        IdentityCandidateOut(
            crustdata_company_id=900010,
            name="Shree Cargo Links Private Limited (fixture)",
            confidence_score=0.82,
            matching=[IdentityKeyOut(key="name", label="Name", value="Shree Cargo Links")],
            differing=[
                IdentityKeyOut(key="domain", label="Domain", value="shreecargolinks.example")
            ],
        ),
        IdentityCandidateOut(
            crustdata_company_id=900011,
            name="Shree Cargo Links LLP (fixture)",
            confidence_score=0.79,
            matching=[
                IdentityKeyOut(key="name", label="Name", value="Shree Cargo Links"),
                IdentityKeyOut(key="hq_city", label="HQ city", value="Surat"),
            ],
            differing=[IdentityKeyOut(key="founded_year", label="Founded", value="2009")],
        ),
    ]
    claim = ClaimOut(
        id="fx-claim-shree-1",
        number=1,
        original_text="We run 6 warehouses in Gujarat",
        normalised_text="Operates 6 warehouses in Gujarat",
        category=ClaimCategory.dated_event,
        origin=ClaimOrigin.typed,
        stated_in=StatedInOut(typed_by_name=USER.display_name, typed_at=_t(31)),
        status=NC,
        reason="Identity unresolved",
        not_checked_reason=NotCheckedReason.identity_unresolved,
        history=[
            ClaimCheckOut(
                id="fx-check-shree-1",
                run_id=AMBIGUOUS_RUN_ID,
                status=NC,
                reason="Identity unresolved",
                not_checked_reason=NotCheckedReason.identity_unresolved,
                created_at=_t(32),
            )
        ],
    )
    run = runs()[AMBIGUOUS_RUN_ID]
    return CaseDetail(
        case=_case_out(CASE_AMBIGUOUS_ID),
        opportunity=OpportunityOut(fit_state=FitState.awaiting_strategy_criteria),
        identity=IdentityOut(
            state=IdentityState.ambiguous,
            candidates=candidates,
            note="Two companies match the name closely. Pick one to continue.",
        ),
        claims=[claim],
        comparables=ComparablesOut(
            basis=ComparisonBasisOut(),
            no_fair_comparison_reason="Identity unresolved",
        ),
        risks=[RiskItemOut(kind="not_checked", text="Identity unresolved; checks paused")],
        cost=CaseCostOut(
            crustdata_credits=run.cost.crustdata_credits,
            llm_usd=run.cost.llm_usd,
            credit_budget=150,
        ),
        runs=[run_summary(run)],
    )


def case_detail(case_id: str) -> CaseDetail | None:
    if case_id == CASE_AMBIGUOUS_ID:
        return _ambiguous_detail()
    if case_id != CASE_ID:
        return None
    verify, recheck, discover = (
        runs()[VERIFY_RUN_ID],
        runs()[RECHECK_RUN_ID],
        runs()[DISCOVER_RUN_ID],
    )
    by_step = [
        CostLineOut(
            run_id=r.id,
            run_kind=r.kind,
            step_key=s.key,
            step_label=s.label,
            cost=s.cost,
            at=s.finished_at or r.created_at,
        )
        for r in (verify, recheck)
        for s in r.steps
        if s.cost.crustdata_credits or s.cost.llm_usd
    ]
    case_runs = (verify, recheck)
    return CaseDetail(
        case=_case_out(CASE_ID),
        opportunity=OpportunityOut(
            thesis_id=THESIS_ID,
            thesis_text=THESIS_TEXT,
            criteria=CRITERIA,
            fit_state=FitState.scored,
            fit=83,
            assessable_pct=67,
            criterion_results=HARBOURLINE_RESULTS,
            relevance=["Warehousing operator in India", "Growing headcount (estimate)"],
        ),
        identity=IdentityOut(
            state=IdentityState.confirmed,
            entity_name=HARBOURLINE,
            crustdata_company_id=HARBOURLINE_ID,
            keys=[
                IdentityKeyOut(key="domain", label="Domain", value=HARBOURLINE_DOMAIN, evidence=[]),
                IdentityKeyOut(
                    key="cin",
                    label="Registration number",
                    value="U00000MH2016PTC000000",
                    evidence=[E_REG_INC],
                ),
                IdentityKeyOut(key="hq_city", label="HQ city", value="Nashik"),
                IdentityKeyOut(key="founded_year", label="Founded", value="2016"),
            ],
        ),
        profile=_profile(),
        claims=claims(2),
        events=[
            EventOut(
                id="fx-event-1",
                event_date=date(2024, 2, 9),
                title="Series A reported",
                kind="funding",
                evidence=E_FUNDING_NEWS,
            ),
            EventOut(
                id="fx-event-2",
                event_date=date(2026, 7, 2),
                title="Cold-storage facility announced (planned)",
                kind="facility",
                evidence=E_FACILITY,
            ),
        ],
        comparables=ComparablesOut(
            basis=ComparisonBasisOut(
                industry="Warehousing", country="India", headcount_band="80-320"
            ),
            companies=[
                ComparableCompanyOut(
                    crustdata_company_id=900005,
                    name="Ridgeway Cold Chain (fixture)",
                    observation=FactStr(
                        **_est(
                            "About 210 employees, 2 dated expansions since 2024",
                            S_PROFILE,
                            date(2026, 11, 1),
                            "profile-based estimate",
                        )
                    ),
                ),
            ],
        ),
        assessment=_assessment(2),
        risks=[
            RiskItemOut(kind="gap", text="Funding timing unsettled", claim_ids=["fx-claim-4"]),
            RiskItemOut(
                kind="estimate_used",
                text="Headcount trend is a profile-based estimate",
            ),
            RiskItemOut(
                kind="not_checked",
                text="Enterprise customers claim not checked (budget reached)",
                claim_ids=["fx-claim-6"],
            ),
        ],
        request_list=request_list(),
        message=message("suppressed"),
        documents=documents(),
        sources=[
            SourceRecordOut(
                **s.model_dump(),
                request={"crustdata_company_ids": [HARBOURLINE_ID]}
                if s.provider == "crustdata"
                else None,
                run_id=VERIFY_RUN_ID,
            )
            for s in ALL_SOURCES
        ]
        + [
            SourceRecordOut(
                source_id="fx-src-unattached",
                provider="web",
                label="News: Harbourline Logistics (fixture)",
                url_or_endpoint="https://logistics-daily.example/2025/harbourline-logistics-dubai",
                retrieved_at=_t(5),
                source_class=SourceClass.news,
                attached=False,
                unattached_reason="Name match only; no shared domain, id or city",
                run_id=VERIFY_RUN_ID,
            )
        ],
        cost=CaseCostOut(
            crustdata_credits=sum(r.cost.crustdata_credits for r in case_runs),
            llm_usd=round(sum(r.cost.llm_usd for r in case_runs), 4),
            unknown_cost_calls=sum(r.cost.unknown_cost_calls for r in case_runs),
            credit_budget=150,
            checks_not_run=1,
            by_step=by_step,
            shared_discovery=SharedCostOut(
                run_id=discover.id, thesis_id=THESIS_ID, cost=discover.cost
            ),
        ),
        runs=[run_summary(r) for r in case_runs],
    )


def case_out(case_id: str) -> CaseOut | None:
    if case_id in (CASE_ID, CASE_AMBIGUOUS_ID):
        return _case_out(case_id)
    return None


def case_summaries() -> list[CaseSummary]:
    out = []
    for cid in (CASE_ID, CASE_AMBIGUOUS_ID):
        detail = case_detail(cid)
        assert detail is not None
        a = detail.assessment
        out.append(
            CaseSummary(
                id=cid,
                name=detail.case.name,
                website=detail.case.website,
                status=detail.case.status,
                identity_state=detail.case.identity_state,
                disposition=(
                    a.judgments.screening_disposition.disposition
                    if a
                    else Disposition.cannot_assess
                ),
                fit_state=detail.opportunity.fit_state,
                fit=detail.opportunity.fit,
                assessable_pct=detail.opportunity.assessable_pct,
                claim_count=len(detail.claims),
                cost=CostTotalsOut(
                    crustdata_credits=detail.cost.crustdata_credits,
                    llm_usd=detail.cost.llm_usd,
                    unknown_cost_calls=detail.cost.unknown_cost_calls,
                ),
                latest_run_state=detail.case.run.state if detail.case.run else None,
                created_at=detail.case.created_at,
                updated_at=_t(612),
            )
        )
    return out


def typed_claim(text: str) -> ClaimOut:
    return ClaimOut(
        id="fx-claim-typed",
        number=9,
        original_text=text,
        normalised_text=text,
        category=ClaimCategory.other,
        origin=ClaimOrigin.typed,
        stated_in=StatedInOut(typed_by_name=USER.display_name, typed_at=_t(40)),
        status=NC,
        reason="Queued; the check has not run yet",
    )


# ---------------------------------------------------------------- policy


def policy() -> PolicyOut:
    C = ClaimCategory
    SC = SourceClass
    return PolicyOut(
        policy_version="2026-11-22.1",
        weights=PolicyWeightsOut(must=2, preference=1),
        fit_formula="fit = round(100 × Σ weight(pass) / Σ weight(pass ∪ fail)); "
        "unavailable when nothing is assessable",
        assessable_formula="assessable% = round(100 × |pass ∪ fail| / |all criteria|)",
        thresholds=PolicyThresholdsOut(
            prioritise_fit_min=70,
            prioritise_sufficiency_min=80,
            deprioritise_fit_below=40,
            deprioritise_assessable_min=60,
            cannot_assess_assessable_below=30,
        ),
        disposition_rules=[
            DispositionRuleOut(
                order=1,
                disposition=Disposition.cannot_assess,
                rule="Identity not confirmed, fit unavailable, or assessable below 30%",
            ),
            DispositionRuleOut(
                order=2,
                disposition=Disposition.deprioritise,
                rule="A must-have verifiably failed, or fit below 40 with assessable ≥ 60%",
            ),
            DispositionRuleOut(
                order=3,
                disposition=Disposition.prioritise,
                rule="Fit ≥ 70, sufficiency ≥ 80%, no material claim contradicted or conflicting",
            ),
            DispositionRuleOut(
                order=4, disposition=Disposition.investigate_further, rule="Everything else"
            ),
        ],
        required_checks=RequiredChecksOut(
            startup=[C.identity_incorporation, C.leadership_history, C.team_size, C.funding],
            established=[
                C.identity_incorporation,
                C.location,
                C.team_size,
                C.leadership_history,
                C.financials,
                C.customer_partnership,
            ],
        ),
        adequate_sources=[
            AdequateSourcesOut(
                category=C.identity_incorporation,
                component="*",
                source_classes=[SC.registry, SC.registry_mirror],
            ),
            AdequateSourcesOut(
                category=C.team_size,
                component="*",
                source_classes=[SC.seller_document, SC.audited_statement],
            ),
            AdequateSourcesOut(
                category=C.leadership_history,
                component="*",
                source_classes=[SC.professional_profile_signal],
            ),
            AdequateSourcesOut(
                category=C.funding,
                component="*",
                source_classes=[SC.data_provider, SC.registry, SC.news],
            ),
        ],
        settle_with=[
            SettleWithOut(category=C.team_size, document="Dated payroll summary"),
            SettleWithOut(category=C.debt_security, document="Lender statements"),
            SettleWithOut(
                category=C.dated_event, document="Lease or occupancy evidence for the facility"
            ),
        ],
        company_type_rule="Startup if founded within 10 years and (≤ 500 employees or last "
        "round seed to Series C); otherwise established",
        investor_ranking_rule="Σ 0.5^(years since round / 2) over dated, named comparable "
        "rounds in the last 6 years",
        comparables_rule="Same top industry, same HQ country, headcount within ×0.5–×2",
        budgets=BudgetsOut(case_credits=150, discover_credits=60, investor_credits=60),
    )


# ---------------------------------------------------------------- export for the web app


def export() -> dict[str, Any]:
    """Everything the web fixture mode needs, as JSON-ready data keyed by client call."""

    def dump(obj: Any) -> Any:
        if isinstance(obj, list):
            return [dump(o) for o in obj]
        if isinstance(obj, dict):
            return {k: dump(v) for k, v in obj.items()}
        return obj.model_dump(mode="json")

    return dump(
        {
            "me": USER,
            "theses": thesis_summaries(),
            "thesis": thesis(),
            "investorSearches": investor_summaries(),
            "investorSearch": investor_search(),
            "cases": case_summaries(),
            "caseDetails": {cid: case_detail(cid) for cid in (CASE_ID, CASE_AMBIGUOUS_ID)},
            "assessments": {CASE_ID: assessments(CASE_ID), CASE_AMBIGUOUS_ID: []},
            "runs": runs(),
            "requestList": request_list(),
            "message": {
                "draft": message("draft"),
                "edited": message("edited"),
                "approved": message("approved"),
                "suppressed": message("suppressed"),
            },
            "documents": documents(),
            "policy": policy(),
        }
    )
