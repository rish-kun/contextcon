"""The PRD's Pune illustration ("An example"), as rule inputs.

This is an illustration, not a real company. Each claim must produce exactly the
status the PRD reports.
"""

from datetime import date, datetime

from app.domain import (
    Claim,
    ClaimCategory,
    ClaimCheck,
    ClaimComponent,
    ClaimStatus,
    Evidence,
    ExtractedFact,
    Source,
    SourceReliability,
)

COMPANY = "co-pune"
FOUNDER = "person-founder"
RETRIEVED = datetime(2026, 11, 20, 10, 0, 0)

REGISTRY = Source(
    id="src-registry",
    provider="web",
    label="Company registry record",
    url="https://www.mca.gov.in/example-record",
    retrieved_at=RETRIEVED,
    reliability=SourceReliability.REGISTRY,
)
PROFILE_HEADCOUNT = Source(
    id="src-headcount",
    provider="crustdata:company_enrich",
    label="Profile-based headcount estimate",
    retrieved_at=RETRIEVED,
    reliability=SourceReliability.PROFESSIONAL_PROFILE_SIGNAL,
)
FOUNDER_PROFILE = Source(
    id="src-founder",
    provider="crustdata:person_search",
    label="Founder's professional record",
    retrieved_at=RETRIEVED,
    reliability=SourceReliability.PROFESSIONAL_PROFILE_SIGNAL,
)
FUNDING_DB = Source(
    id="src-funding",
    provider="crustdata:company_enrich",
    label="Funding record",
    retrieved_at=RETRIEVED,
    reliability=SourceReliability.DATA_PROVIDER,
)
FUNDING_PR = Source(
    id="src-funding-pr",
    provider="web",
    label="Company announcement, March 2025",
    url="https://example.com/news/growth-round",
    retrieved_at=RETRIEVED,
    reliability=SourceReliability.COMPANY_ANNOUNCEMENT,
)
FACILITY_PR = Source(
    id="src-facility-pr",
    provider="web",
    label="Company announcement, June 2026",
    url="https://example.com/news/new-facility",
    retrieved_at=RETRIEVED,
    reliability=SourceReliability.COMPANY_ANNOUNCEMENT,
)


def ev(id, source, *, quote=None, field_path=None, field_value=None, entity=COMPANY, as_of=None):
    return Evidence(
        id=id,
        source=source,
        entity_id=entity,
        quote=quote,
        field_path=field_path,
        field_value=field_value,
        as_of=as_of,
    )


def fact(id, evidence, component, value):
    return ExtractedFact(id=id, evidence=evidence, component=component, value=value)


REGISTRY_EV = ev(
    "ev-registry",
    REGISTRY,
    quote="Date of Incorporation: 12/06/2014. Registered Office: Baner Road, Pune, "
    "Maharashtra 411045.",
    as_of=date(2026, 11, 1),
)
HEADCOUNT_EV = ev(
    "ev-headcount",
    PROFILE_HEADCOUNT,
    field_path="headcount.linkedin_headcount",
    field_value=140,
    as_of=date(2026, 11, 1),
)
FOUNDER_EV = ev(
    "ev-founder",
    FOUNDER_PROFILE,
    quote="Head of Operations, National Freight Logistics Ltd, 2008 - 2013",
    entity=FOUNDER,
)
FUNDING_EV = ev(
    "ev-funding",
    FUNDING_DB,
    field_path="funding_milestones[0].funding_date",
    field_value="2025-03-14",
    as_of=date(2025, 3, 14),
)
FUNDING_PR_EV = ev(
    "ev-funding-pr",
    FUNDING_PR,
    quote="On 14 March 2025 the company announced it has raised growth funding.",
    as_of=date(2025, 3, 14),
)
FACILITY_EV = ev(
    "ev-facility",
    FACILITY_PR,
    quote="The company plans to open a new warehouse facility in Chakan in October 2026.",
    as_of=date(2026, 6, 2),
)
CHARGE_EV = ev(
    "ev-charge",
    REGISTRY,
    quote="Charge ID 100234567 created 01/08/2023, charge holder: a scheduled bank, "
    "amount 12 crore, status: open.",
    as_of=date(2026, 11, 1),
)


def claim(id, text, category, components, entity_ids=(COMPANY,)):
    return Claim(
        id=id,
        text=text,
        category=category,
        components=[ClaimComponent(name=k, value=v) for k, v in components.items()],
        entity_ids=list(entity_ids),
    )


INCORPORATION = ClaimCheck(
    claim=claim(
        "c-incorporation",
        "Incorporated in 2014, based in Pune",
        ClaimCategory.IDENTITY_INCORPORATION,
        {"incorporation_year": 2014, "hq_city": "Pune"},
    ),
    facts=[
        fact("f-inc-year", REGISTRY_EV, "incorporation_year", 2014),
        fact("f-inc-city", REGISTRY_EV, "hq_city", "Pune"),
    ],
    sources_read=[REGISTRY],
)

EMPLOYEES = ClaimCheck(
    claim=claim(
        "c-employees", "We employ 250 people", ClaimCategory.TEAM_SIZE, {"employee_count": 250}
    ),
    facts=[fact("f-headcount", HEADCOUNT_EV, "employee_count", 140)],
    sources_read=[PROFILE_HEADCOUNT],
)

FOUNDER_HISTORY = ClaimCheck(
    claim=claim(
        "c-founder",
        "Our founder ran operations at a national logistics firm",
        ClaimCategory.LEADERSHIP_HISTORY,
        {"role": "operations", "employer_industry": "logistics"},
        entity_ids=(FOUNDER,),
    ),
    facts=[
        fact("f-founder-role", FOUNDER_EV, "role", "Head of Operations"),
        fact("f-founder-industry", FOUNDER_EV, "employer_industry", "Logistics"),
        fact("f-founder-start", FOUNDER_EV, "start_year", 2008),
    ],
    sources_read=[FOUNDER_PROFILE],
)

FUNDING = ClaimCheck(
    claim=claim(
        "c-funding",
        "We raised growth funding in 2025",
        ClaimCategory.FUNDING,
        {"raised": True, "round_year": 2025},
    ),
    facts=[
        fact("f-fund-raised", FUNDING_EV, "raised", True),
        fact("f-fund-year", FUNDING_EV, "round_year", 2025),
        fact("f-pr-raised", FUNDING_PR_EV, "raised", True),
        fact("f-pr-year", FUNDING_PR_EV, "round_year", 2025),
    ],
    sources_read=[FUNDING_DB, FUNDING_PR],
)

FACILITY = ClaimCheck(
    claim=claim(
        "c-facility",
        "We opened a new facility in October 2026",
        ClaimCategory.DATED_EVENT,
        {"event": "facility", "event_date": "2026-10", "stage": "operating"},
    ),
    facts=[
        fact("f-fac-event", FACILITY_EV, "event", "new warehouse facility"),
        fact("f-fac-date", FACILITY_EV, "event_date", "2026-10"),
        fact("f-fac-stage", FACILITY_EV, "stage", "planned"),
    ],
    sources_read=[FACILITY_PR],
)

NO_DEBT = ClaimCheck(
    claim=claim("c-debt", "We have no debt", ClaimCategory.DEBT_SECURITY, {"has_debt": False}),
    facts=[fact("f-charge", CHARGE_EV, "security_registered", True)],
    sources_read=[REGISTRY],
)

PRD_CHECKS = [INCORPORATION, EMPLOYEES, FOUNDER_HISTORY, FUNDING, FACILITY, NO_DEBT]

PRD_EXPECTED = {
    "c-incorporation": ClaimStatus.SUPPORTED,
    "c-employees": ClaimStatus.CANNOT_VERIFY,
    "c-founder": ClaimStatus.SUPPORTED,
    "c-funding": ClaimStatus.SUPPORTED,
    "c-facility": ClaimStatus.PARTIALLY_CORROBORATED,
    "c-debt": ClaimStatus.CANNOT_VERIFY,
}
