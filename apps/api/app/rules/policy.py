"""The scoring and verification policy, as data.

Every number and table the rules use lives here, so the policy page can show it
and a change to it is a change to ``POLICY_VERSION``. POLICY.md explains it in
words. Pure constants: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import ClaimCategory, CompanyType, CriterionKind, SourceReliability, ValueKind

POLICY_VERSION = "2026-11-22.1"

# --- Discover: fit -----------------------------------------------------------

CRITERION_WEIGHTS: dict[CriterionKind, int] = {
    CriterionKind.MUST: 2,
    CriterionKind.PREFERENCE: 1,
}

# --- Evaluate: disposition thresholds ----------------------------------------

PRIORITISE_MIN_FIT = 70
PRIORITISE_MIN_SUFFICIENCY = 80
DEPRIORITISE_MAX_FIT = 40  # strictly below this...
DEPRIORITISE_MIN_ASSESSABLE = 60  # ...on at least this share of verified criteria
CANNOT_ASSESS_MAX_ASSESSABLE = 30  # strictly below this share of criteria assessable

# --- Company type ------------------------------------------------------------

STARTUP_MAX_AGE_YEARS = 10
STARTUP_MAX_HEADCOUNT = 500
STARTUP_STAGES = frozenset(
    {"pre_seed", "angel", "seed", "series_a", "series_b", "series_c", "venture"}
)

# --- Source authority --------------------------------------------------------
# Lower rank = more authoritative. When adequate sources disagree, only the most
# authoritative rank present decides; disagreement inside that rank is
# "conflicting evidence". Syndicated copies of one origin take the LEAST
# authoritative class among them (republishing a press release does not make
# it independent news).

AUTHORITY_RANK: dict[SourceReliability, int] = {
    SourceReliability.REGISTRY: 1,
    SourceReliability.AUDITED_STATEMENT: 1,
    SourceReliability.COUNTERPARTY_CONFIRMATION: 1,
    SourceReliability.REGISTRY_MIRROR: 2,
    SourceReliability.SELLER_DOCUMENT: 2,
    SourceReliability.DATA_PROVIDER: 3,
    SourceReliability.NEWS: 3,
    SourceReliability.PROFESSIONAL_PROFILE_SIGNAL: 3,
    SourceReliability.COMPANY_ANNOUNCEMENT: 4,
    SourceReliability.SELLER_STATEMENT: 5,
}

# --- Claim components --------------------------------------------------------

R = SourceReliability


@dataclass(frozen=True)
class ComponentRule:
    check: ClaimCategory  # which required check this component answers
    kind: ValueKind
    adequate: frozenset[SourceReliability]
    document: str  # what would settle it, requested from the seller
    # Classes that are NOT adequate but deserve an explicit explanation.
    caveats: dict[SourceReliability, str] = field(default_factory=dict)
    # Shown when a fact for this component is related to, but does not settle,
    # another component of the same check (for example a registered charge
    # next to a "no debt" claim).
    related_caveat: str = ""


_IDENTITY_SOURCES = frozenset({R.REGISTRY, R.REGISTRY_MIRROR, R.AUDITED_STATEMENT})
_CAREER_SOURCES = frozenset(
    {R.PROFESSIONAL_PROFILE_SIGNAL, R.REGISTRY, R.REGISTRY_MIRROR, R.NEWS, R.SELLER_DOCUMENT}
)
_FUNDING_SOURCES = frozenset(
    {
        R.DATA_PROVIDER,
        R.REGISTRY,
        R.REGISTRY_MIRROR,
        R.NEWS,
        R.COUNTERPARTY_CONFIRMATION,
        R.AUDITED_STATEMENT,
        R.SELLER_DOCUMENT,
    }
)
_EVENT_HAPPENED_SOURCES = frozenset(
    {R.NEWS, R.REGISTRY, R.SELLER_DOCUMENT, R.COUNTERPARTY_CONFIRMATION}
)
_CUSTOMER_SOURCES = frozenset({R.COUNTERPARTY_CONFIRMATION, R.SELLER_DOCUMENT, R.AUDITED_STATEMENT})
_FINANCIAL_SOURCES = frozenset({R.AUDITED_STATEMENT, R.REGISTRY})
_DEBT_SOURCES = frozenset({R.AUDITED_STATEMENT, R.COUNTERPARTY_CONFIRMATION, R.SELLER_DOCUMENT})

HEADCOUNT_SIGNAL_CAVEAT = (
    "Profile-based headcount is a signal, not a payroll count: staff without "
    "professional profiles (for example warehouse staff) are not counted"
)
ANNOUNCEMENT_CAVEAT = (
    "A company announcement shows that the company announced it, not that it happened"
)
CHARGE_CAVEAT = "A registered charge shows security was given, not that money is owed"

DOC_INCORPORATION = "Certificate of incorporation"
DOC_REGISTERED_OFFICE = "Registered-office filing or premises lease"
DOC_PAYROLL = "Dated payroll summary"
DOC_CV = "Founder CV with dates, or an employer's confirmation"
DOC_FUNDING = "Share allotment filing or signed term sheet"
DOC_FACILITY = "Lease or occupancy evidence for the facility"
DOC_EVENT = "Dated document showing the event took place"
DOC_CUSTOMER = "Customer confirmation or signed contract"
DOC_FINANCIALS = "Audited financial statements"
DOC_LENDER = "Lender statements"
DOC_LITIGATION = "Litigation disclosure signed by counsel"
DOC_FINANCIAL_INPUTS = "Audited financial statements for the last three years"
DOC_IDENTITY = "Certificate of incorporation showing the CIN and registered office"

COMPONENT_RULES: dict[str, ComponentRule] = {
    # Identity and incorporation: registry questions.
    "legal_name": ComponentRule(
        ClaimCategory.IDENTITY_INCORPORATION, ValueKind.TEXT, _IDENTITY_SOURCES, DOC_INCORPORATION
    ),
    "cin": ComponentRule(
        ClaimCategory.IDENTITY_INCORPORATION,
        ValueKind.TEXT,
        frozenset({R.REGISTRY, R.REGISTRY_MIRROR}),
        DOC_INCORPORATION,
    ),
    "incorporation_year": ComponentRule(
        ClaimCategory.IDENTITY_INCORPORATION, ValueKind.YEAR, _IDENTITY_SOURCES, DOC_INCORPORATION
    ),
    "incorporation_date": ComponentRule(
        ClaimCategory.IDENTITY_INCORPORATION, ValueKind.DATE, _IDENTITY_SOURCES, DOC_INCORPORATION
    ),
    # Location.
    "registered_city": ComponentRule(
        ClaimCategory.LOCATION,
        ValueKind.TEXT,
        frozenset({R.REGISTRY, R.REGISTRY_MIRROR}),
        DOC_INCORPORATION,
    ),
    "hq_city": ComponentRule(
        ClaimCategory.LOCATION,
        ValueKind.TEXT,
        frozenset(
            {R.REGISTRY, R.REGISTRY_MIRROR, R.AUDITED_STATEMENT, R.DATA_PROVIDER, R.SELLER_DOCUMENT}
        ),
        DOC_REGISTERED_OFFICE,
    ),
    "country": ComponentRule(
        ClaimCategory.LOCATION,
        ValueKind.TEXT,
        frozenset({R.REGISTRY, R.REGISTRY_MIRROR, R.AUDITED_STATEMENT, R.DATA_PROVIDER}),
        DOC_INCORPORATION,
    ),
    "operating_city": ComponentRule(
        ClaimCategory.LOCATION,
        ValueKind.TEXT,
        frozenset({R.REGISTRY, R.NEWS, R.SELLER_DOCUMENT, R.COUNTERPARTY_CONFIRMATION}),
        DOC_REGISTERED_OFFICE,
    ),
    # Team size: profiles and data providers are signals and never adequate.
    "employee_count": ComponentRule(
        ClaimCategory.TEAM_SIZE,
        ValueKind.COUNT,
        frozenset({R.SELLER_DOCUMENT, R.AUDITED_STATEMENT, R.REGISTRY}),
        DOC_PAYROLL,
        caveats={
            R.PROFESSIONAL_PROFILE_SIGNAL: HEADCOUNT_SIGNAL_CAVEAT,
            R.DATA_PROVIDER: HEADCOUNT_SIGNAL_CAVEAT,
        },
    ),
    "headcount_growth_pct": ComponentRule(
        ClaimCategory.TEAM_SIZE,
        ValueKind.PERCENT,
        frozenset({R.SELLER_DOCUMENT, R.AUDITED_STATEMENT}),
        "Dated payroll summaries for both dates",
        caveats={
            R.PROFESSIONAL_PROFILE_SIGNAL: HEADCOUNT_SIGNAL_CAVEAT,
            R.DATA_PROVIDER: HEADCOUNT_SIGNAL_CAVEAT,
        },
    ),
    # Leadership and founder history: a professional record shows role and years.
    "person_name": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY, ValueKind.TEXT, _CAREER_SOURCES, DOC_CV
    ),
    "role": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY, ValueKind.TEXT_CONTAINS, _CAREER_SOURCES, DOC_CV
    ),
    "employer": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY, ValueKind.TEXT, _CAREER_SOURCES, DOC_CV
    ),
    "employer_industry": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.TEXT_CONTAINS,
        _CAREER_SOURCES | {R.DATA_PROVIDER},
        DOC_CV,
    ),
    "start_year": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY, ValueKind.YEAR, _CAREER_SOURCES, DOC_CV
    ),
    "end_year": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY, ValueKind.YEAR, _CAREER_SOURCES, DOC_CV
    ),
    # Funding.
    "raised": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.BOOL,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
    ),
    "round_year": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.YEAR,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
    ),
    "round_date": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.MONTH,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
    ),
    "round_type": ComponentRule(
        ClaimCategory.FUNDING, ValueKind.TEXT_CONTAINS, _FUNDING_SOURCES, DOC_FUNDING
    ),
    "amount_usd": ComponentRule(
        ClaimCategory.FUNDING, ValueKind.MONEY, _FUNDING_SOURCES, DOC_FUNDING
    ),
    "investor": ComponentRule(ClaimCategory.FUNDING, ValueKind.TEXT, _FUNDING_SOURCES, DOC_FUNDING),
    "announced": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.BOOL,
        frozenset({R.COMPANY_ANNOUNCEMENT, R.NEWS}),
        "Dated company announcement",
    ),
    # Dated events. An announcement is adequate for "what was announced" only;
    # when and whether it happened need an independent or documentary source.
    "event": ComponentRule(
        ClaimCategory.DATED_EVENT,
        ValueKind.TEXT_CONTAINS,
        _EVENT_HAPPENED_SOURCES | {R.COMPANY_ANNOUNCEMENT},
        DOC_EVENT,
    ),
    "event_date": ComponentRule(
        ClaimCategory.DATED_EVENT,
        ValueKind.MONTH,
        _EVENT_HAPPENED_SOURCES,
        DOC_EVENT,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
    ),
    "stage": ComponentRule(
        ClaimCategory.DATED_EVENT,
        ValueKind.STAGE,
        _EVENT_HAPPENED_SOURCES,
        DOC_EVENT,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
    ),
    # Customers and partnerships: the counterparty's own confirmation.
    "counterparty": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.TEXT,
        _CUSTOMER_SOURCES,
        DOC_CUSTOMER,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
    ),
    "relationship": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP, ValueKind.TEXT_CONTAINS, _CUSTOMER_SOURCES, DOC_CUSTOMER
    ),
    "since_year": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP, ValueKind.YEAR, _CUSTOMER_SOURCES, DOC_CUSTOMER
    ),
    "contract_value": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP, ValueKind.MONEY, _CUSTOMER_SOURCES, DOC_CUSTOMER
    ),
    # Financials: audited statements or registry filings only.
    "revenue": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.MONEY, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    "profit": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.MONEY, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    "ebitda": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.MONEY, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    "revenue_growth_pct": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.PERCENT, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    "fiscal_year": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.YEAR, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    # Debt and security. Owing money is a lender/accounts question; a registry
    # charge only answers "was security given".
    "has_debt": ComponentRule(
        ClaimCategory.DEBT_SECURITY, ValueKind.BOOL, _DEBT_SOURCES, DOC_LENDER
    ),
    "debt_amount": ComponentRule(
        ClaimCategory.DEBT_SECURITY, ValueKind.MONEY, _DEBT_SOURCES, DOC_LENDER
    ),
    "security_registered": ComponentRule(
        ClaimCategory.DEBT_SECURITY,
        ValueKind.BOOL,
        frozenset({R.REGISTRY, R.REGISTRY_MIRROR}),
        "Registry charge record",
        related_caveat=CHARGE_CAVEAT,
    ),
    "lender": ComponentRule(
        ClaimCategory.DEBT_SECURITY,
        ValueKind.TEXT,
        _DEBT_SOURCES | {R.REGISTRY, R.REGISTRY_MIRROR},
        DOC_LENDER,
    ),
    # Litigation: court or registry records and audited disclosures.
    "has_litigation": ComponentRule(
        ClaimCategory.LITIGATION,
        ValueKind.BOOL,
        frozenset({R.REGISTRY, R.AUDITED_STATEMENT}),
        DOC_LITIGATION,
    ),
    "case_reference": ComponentRule(
        ClaimCategory.LITIGATION, ValueKind.TEXT, frozenset({R.REGISTRY}), DOC_LITIGATION
    ),
}

# Fallback "what would settle it" when a claim has no known component.
CATEGORY_DOCUMENTS: dict[ClaimCategory, str] = {
    ClaimCategory.IDENTITY_INCORPORATION: DOC_INCORPORATION,
    ClaimCategory.LOCATION: DOC_REGISTERED_OFFICE,
    ClaimCategory.TEAM_SIZE: DOC_PAYROLL,
    ClaimCategory.LEADERSHIP_HISTORY: DOC_CV,
    ClaimCategory.FUNDING: DOC_FUNDING,
    ClaimCategory.DATED_EVENT: DOC_EVENT,
    ClaimCategory.CUSTOMER_PARTNERSHIP: DOC_CUSTOMER,
    ClaimCategory.FINANCIALS: DOC_FINANCIALS,
    ClaimCategory.DEBT_SECURITY: DOC_LENDER,
    ClaimCategory.LITIGATION: DOC_LITIGATION,
    ClaimCategory.OTHER: "A dated document that states it directly",
}

# A dated event about premises gets the premises document rather than the generic one.
FACILITY_WORDS = frozenset(
    {
        "facility",
        "warehouse",
        "plant",
        "factory",
        "hub",
        "site",
        "office",
        "depot",
        "centre",
        "center",
    }
)

# Lifecycle for ValueKind.STAGE, in order.
STAGE_ORDER: dict[str, int] = {
    "planned": 0,
    "announced": 0,
    "under_construction": 1,
    "operating": 2,
    "closed": 3,
}
STAGE_CUES: dict[str, tuple[str, ...]] = {
    "planned": ("plan", "will ", "upcoming", "proposed", "to open", "to be", "set to", "announce"),
    "announced": ("announce",),
    "under_construction": ("under construction", "being built", "construction"),
    "operating": (
        "operating",
        "operational",
        "opened",
        "inaugurated",
        "commenced",
        "started operations",
        "now live",
        "began operations",
    ),
    "closed": ("closed", "shut", "ceased"),
}

# Comparison tolerances.
COUNT_TOLERANCE = 0.05  # relative
MONEY_TOLERANCE = 0.02  # relative
PERCENT_TOLERANCE_POINTS = 2.0

# --- Evaluate: what each company type is judged on (PRD "Evaluate") ---------

EVALUATION_CRITERIA: dict[CompanyType, list[tuple[str, str, list[ClaimCategory]]]] = {
    CompanyType.STARTUP: [
        ("thesis_fit", "Thesis fit", []),
        ("founder_relevance", "Founder relevance", [ClaimCategory.LEADERSHIP_HISTORY]),
        ("team_development", "Team development", [ClaimCategory.TEAM_SIZE]),
        ("funding_history", "Funding history", [ClaimCategory.FUNDING]),
    ],
    CompanyType.ESTABLISHED: [
        ("strategic_fit", "Strategic fit", []),
        (
            "identity",
            "Identity",
            [ClaimCategory.IDENTITY_INCORPORATION, ClaimCategory.LOCATION],
        ),
        ("operating_scale", "Operating scale", [ClaimCategory.TEAM_SIZE]),
        ("financial_performance", "Financial performance", [ClaimCategory.FINANCIALS]),
        ("commercial_position", "Commercial position", [ClaimCategory.CUSTOMER_PARTNERSHIP]),
        ("leadership_continuity", "Leadership continuity", [ClaimCategory.LEADERSHIP_HISTORY]),
    ],
}

# Identity is always required, so startups get it on top of their criteria.
REQUIRED_CHECKS: dict[CompanyType, list[ClaimCategory]] = {
    CompanyType.STARTUP: [
        ClaimCategory.IDENTITY_INCORPORATION,
        ClaimCategory.LEADERSHIP_HISTORY,
        ClaimCategory.TEAM_SIZE,
        ClaimCategory.FUNDING,
    ],
    CompanyType.ESTABLISHED: [
        ClaimCategory.IDENTITY_INCORPORATION,
        ClaimCategory.LOCATION,
        ClaimCategory.TEAM_SIZE,
        ClaimCategory.LEADERSHIP_HISTORY,
        ClaimCategory.FINANCIALS,
        ClaimCategory.CUSTOMER_PARTNERSHIP,
    ],
}

# Financial inputs are reliable only from these classes.
RELIABLE_FINANCIAL_SOURCES = _FINANCIAL_SOURCES

# --- Investors ---------------------------------------------------------------

INVESTOR_LOOKBACK_YEARS = 6
INVESTOR_RECENCY_HALF_LIFE_YEARS = 2.0
INVESTOR_NAME_SUFFIXES = ("capital", "ventures", "venture", "partners", "fund", "llp", "llc")
