"""The scoring and verification policy, as data.

Every number and table the rules use lives here, so the policy page can show it
and a change to it is a change to ``POLICY_VERSION``. POLICY.md explains it in
words. Pure constants: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import (
    ClaimCategory,
    CompanyType,
    CriterionKind,
    Disposition,
    DocumentType,
    EffortLevel,
    SourceReliability,
    ValueKind,
)

POLICY_VERSION = "2026-11-22.8"

# Why each policy version changed, used as the reason on refreshed assessments.
POLICY_CHANGES: dict[str, str] = {
    "2026-11-22.4": "policy fix: country code normalisation",
    "2026-11-22.5": "Discover reads activity and expansion signals; ties break on signals",
    "2026-11-22.6": (
        "public lookups for partnerships, certifications, trademarks and customer claims; "
        "a company's own statement alone gives partially corroborated"
    ),
    "2026-11-22.7": (
        "certifications match on the standard itself and must be current: an expired "
        "certificate on a register contradicts the claim"
    ),
    "2026-11-22.8": "Financial assessment reads public filings and estimates",
}

# --- Discover: fit -----------------------------------------------------------

CRITERION_WEIGHTS: dict[CriterionKind, int] = {
    CriterionKind.MUST: 2,
    CriterionKind.PREFERENCE: 1,
}

# --- Discover: derived signals and tie-breaks (since 2026-11-22.5) -------------
# "Recent expansion" is a SIGNAL from profile headcount and job postings, never
# confirmed expansion. Derived results are estimates, so a fail never excludes.
EXPANSION_MIN_HEADCOUNT_GROWTH_PCT = 10.0  # growth of the headcount series over ~12 months
EXPANSION_GROWTH_WINDOW_DAYS = 365
EXPANSION_WINDOW_TOLERANCE_DAYS = 60  # the earlier point must be this close to 12 months back
EXPANSION_MIN_OPEN_ROLES = 5  # openings count or postings dated in the window below
EXPANSION_POSTING_WINDOW_DAYS = 180
# A description shorter than this never counts as contradicting the activity.
ACTIVITY_CONTRADICTION_MIN_WORDS = 12
# Ranking tie-break after fit and assessable share: number of sourced signals
# (these fields with evidence, dated rounds, dated postings, derived signals), then name.
DISCOVER_SIGNAL_KEYS: tuple[str, ...] = (
    "headcount.total",
    "headcount.timeseries",
    "headcount.growth_percent.12m",
    "hiring.openings_count",
    "hiring.recent_titles",
    "funding.last_fundraise_date",
)

# --- Evaluate: disposition thresholds ----------------------------------------

PRIORITISE_MIN_FIT = 70
# Kept for callers that display it. Since 2026-11-22.2 prioritise needs every
# v1-covered required check complete (V1_COVERED_CHECKS), not a share.
PRIORITISE_MIN_SUFFICIENCY = 80
DEPRIORITISE_MAX_FIT = 40  # strictly below this...
DEPRIORITISE_MIN_ASSESSABLE = 60  # ...on at least this share of verified criteria
CANNOT_ASSESS_MAX_ASSESSABLE = 30  # strictly below this share of criteria assessable

# What each situation leads to (POLICY.md §5). The rules read this table:
# ``decide_disposition`` blocks Prioritise for every situation whose outcome is
# Investigate further, and a contradicted claim on a must-have's dimension
# (COMPONENT_CRITERION_DIMENSIONS) is a verified failure of that must-have.


@dataclass(frozen=True)
class DispositionRow:
    key: str
    situation: str
    outcome: Disposition
    note: str


DISPOSITION_TABLE: tuple[DispositionRow, ...] = (
    DispositionRow(
        "unverified_optional_claim",
        "Unverified optional claim",
        Disposition.INVESTIGATE_FURTHER,
        "Investigate further if the claim is material",
    ),
    DispositionRow(
        "unverified_mandatory_criterion",
        "Unverified mandatory criterion",
        Disposition.INVESTIGATE_FURTHER,
        "Decision blocker: blocks Prioritise until it is verified, never Deprioritise",
    ),
    DispositionRow(
        "contradicted_optional_claim",
        "Contradicted non-mandatory claim",
        Disposition.INVESTIGATE_FURTHER,
        "Investigate further if the claim is material",
    ),
    DispositionRow(
        "verified_mandatory_failure",
        "Verified failure of a mandatory criterion",
        Disposition.DEPRIORITISE,
        "Including a contradicted claim on the must-have's dimension",
    ),
    DispositionRow(
        "poor_fit_on_good_evidence",
        "Poor thesis fit despite sufficient evidence",
        Disposition.DEPRIORITISE,
        "Counting verified results only",
    ),
    DispositionRow(
        "unresolved_identity",
        "Unresolved identity",
        Disposition.CANNOT_ASSESS,
        "Records cannot be attached to the company safely",
    ),
)
DISPOSITION_RULES: dict[str, DispositionRow] = {r.key: r for r in DISPOSITION_TABLE}

# A sourced field older than this (by its as_of date) is stale: it still counts
# toward fit, but a fail on it is not verified, so it never excludes a company
# or triggers deprioritise.
FIELD_STALE_AFTER_DAYS = 730

# The checks the first version actually runs (PRD "First version": identity,
# team, leadership, funding and dated events). Prioritise needs every one of
# these that is required for the company type to be complete.
V1_COVERED_CHECKS = frozenset(
    {
        ClaimCategory.IDENTITY_INCORPORATION,
        ClaimCategory.LOCATION,
        ClaimCategory.TEAM_SIZE,
        ClaimCategory.LEADERSHIP_HISTORY,
        ClaimCategory.FUNDING,
        ClaimCategory.DATED_EVENT,
    }
)

# --- Identity guard (design §5.4) ---------------------------------------------
# Evidence is attached to an entity only on one of these. A name match alone
# is never enough. "case_upload" is a document the seller uploaded to this case.
CORROBORATING_IDENTIFIERS = frozenset(
    {
        "crustdata_id",
        "domain",
        "profile_url",
        "registry_id",
        "cin",
        "hq_city",
        "founded_year",
        "case_upload",
    }
)

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
    # For classes listed here, the source must also be one of these document
    # types (a generic seller deck never settles a payroll count).
    document_types: dict[SourceReliability, frozenset[DocumentType]] = field(default_factory=dict)
    # Classes whose evidence must carry a date (as_of) to settle the question.
    needs_date: frozenset[SourceReliability] = frozenset()
    # Whether a document from the seller can resolve it.
    seller_resolvable: bool = True


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
# Since 2026-11-22.6 the company's own page counts for customer and partnership
# components, but a claim matched by company announcements alone is capped at
# partially corroborated (SELF_STATEMENT_CAPPED): "the company says so".
_CUSTOMER_SOURCES = frozenset(
    {
        R.COUNTERPARTY_CONFIRMATION,
        R.SELLER_DOCUMENT,
        R.AUDITED_STATEMENT,
        R.COMPANY_ANNOUNCEMENT,
    }
)
# A certification: the certification body's register or announcement
# (counterparty_confirmation), a public registry or a mirror of it, or the
# certificate itself; the company's trust page is a self-statement (capped).
_CERTIFICATION_SOURCES = frozenset(
    {
        R.REGISTRY,
        R.REGISTRY_MIRROR,
        R.COUNTERPARTY_CONFIRMATION,
        R.SELLER_DOCUMENT,
        R.COMPANY_ANNOUNCEMENT,
    }
)
# That a certificate is current: the register or the certification body's record, or
# the certificate (or auditor's report) itself. Never the company's own page.
_CERTIFICATE_VALIDITY_SOURCES = frozenset(
    {R.REGISTRY, R.REGISTRY_MIRROR, R.COUNTERPARTY_CONFIRMATION, R.SELLER_DOCUMENT}
)
# A trademark: the trademark registry or a public mirror of its records, or the
# registration certificate; the company's own "registered trademark" line is capped.
_TRADEMARK_SOURCES = frozenset(
    {R.REGISTRY, R.REGISTRY_MIRROR, R.SELLER_DOCUMENT, R.COMPANY_ANNOUNCEMENT}
)
# A customer count is the company's own figure; only an audited note or a dated
# customer list from the seller settles it. Case studies name customers, never count them.
_CUSTOMER_COUNT_SOURCES = frozenset({R.AUDITED_STATEMENT, R.SELLER_DOCUMENT})
# A listed company's results as filed with an exchange (registry_mirror) are reported,
# not audited, figures; they answer "what did the company report".
_FINANCIAL_SOURCES = frozenset({R.AUDITED_STATEMENT, R.REGISTRY, R.REGISTRY_MIRROR})
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
DOC_FUNDING = "Share allotment filing, closing statement or bank receipt of the funds"
DOC_FACILITY = "Lease or occupancy evidence for the facility"
DOC_EVENT = "Dated document showing the event took place"
DOC_CUSTOMER = "Customer confirmation or signed contract"
DOC_FINANCIALS = "Audited financial statements"
DOC_LENDER = "Lender statements"
DOC_LITIGATION = "Litigation disclosure signed by counsel"
DOC_FINANCIAL_INPUTS = DOC_FINANCIALS  # one document, so requests dedupe
DOC_IDENTITY = "Certificate of incorporation showing the CIN and registered office"
DOC_CERTIFICATION = (
    "Certificate from the certification body, with its number, scope and validity, "
    "or the auditor's report under NDA"
)
DOC_TRADEMARK = "Trademark registration certificate or IP assignment records"
CERTIFICATE_VALIDITY_CAVEAT = (
    "The company's own page names the standard; only the certification body's "
    "record or the certificate shows that it is current"
)
DOC_CUSTOMER_LIST = "Dated customer list, or audited revenue by customer"

D = DocumentType
_PAYROLL_DOCS = {R.SELLER_DOCUMENT: frozenset({D.PAYROLL_RECORD})}
_CERTIFICATE_DOCS = {R.SELLER_DOCUMENT: frozenset({D.COMPLIANCE_CERTIFICATE, D.AUDIT_REPORT})}
_PREMISES_DOCS = {
    R.SELLER_DOCUMENT: frozenset({D.LEASE, D.OCCUPANCY_EVIDENCE, D.INCORPORATION_CERTIFICATE})
}
_CAREER_DOCS = {R.SELLER_DOCUMENT: frozenset({D.CV, D.EMPLOYER_CONFIRMATION})}
# A completed round needs closing, allotment or receipt of funds. A term sheet
# is only an offer.
_FUNDING_DOCS = {
    R.SELLER_DOCUMENT: frozenset({D.SHARE_ALLOTMENT, D.FUNDING_CLOSING, D.FUNDS_RECEIPT})
}
# That an event happened, or a facility operates: occupancy evidence or a
# record of the event itself. A deck or announcement never shows it.
_OCCURRENCE_DOCS = {R.SELLER_DOCUMENT: frozenset({D.OCCUPANCY_EVIDENCE, D.EVENT_RECORD})}
_EVENT_DOCS = {R.SELLER_DOCUMENT: frozenset({D.OCCUPANCY_EVIDENCE, D.EVENT_RECORD, D.LEASE})}
_CUSTOMER_DOCS = {R.SELLER_DOCUMENT: frozenset({D.CUSTOMER_CONTRACT, D.CUSTOMER_CONFIRMATION})}
_DEBT_DOCS = {R.SELLER_DOCUMENT: frozenset({D.LENDER_STATEMENT})}
SELF_STATEMENT_CAVEAT = (
    "The company's own page shows that the company says it, not that the other party confirms it"
)

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
    # Public or private: a registry question. A contradicted ownership claim on a
    # must-have "privately held" is a verified failure of that must-have.
    "ownership": ComponentRule(
        ClaimCategory.IDENTITY_INCORPORATION, ValueKind.ENUM, _IDENTITY_SOURCES, DOC_INCORPORATION
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
        document_types=_PREMISES_DOCS,
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
        document_types=_PREMISES_DOCS,
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
        document_types=_PAYROLL_DOCS,
        needs_date=frozenset({R.SELLER_DOCUMENT}),
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
        document_types=_PAYROLL_DOCS,
        needs_date=frozenset({R.SELLER_DOCUMENT}),
    ),
    # Leadership and founder history: a professional record shows role and years.
    "person_name": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.TEXT,
        _CAREER_SOURCES,
        DOC_CV,
        document_types=_CAREER_DOCS,
    ),
    "role": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.TEXT_CONTAINS,
        _CAREER_SOURCES,
        DOC_CV,
        document_types=_CAREER_DOCS,
    ),
    "employer": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.TEXT,
        _CAREER_SOURCES,
        DOC_CV,
        document_types=_CAREER_DOCS,
    ),
    "employer_industry": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.TEXT_CONTAINS,
        _CAREER_SOURCES | {R.DATA_PROVIDER},
        DOC_CV,
        document_types=_CAREER_DOCS,
    ),
    # The scope of the employer itself (local, regional, national,
    # international) is a fact about the employer company, so it needs a
    # record about that company, not the person's profile.
    "employer_scope": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.ENUM,
        frozenset({R.DATA_PROVIDER, R.NEWS, R.REGISTRY, R.REGISTRY_MIRROR, R.AUDITED_STATEMENT}),
        DOC_CV,
    ),
    "start_year": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.YEAR,
        _CAREER_SOURCES,
        DOC_CV,
        document_types=_CAREER_DOCS,
    ),
    "end_year": ComponentRule(
        ClaimCategory.LEADERSHIP_HISTORY,
        ValueKind.YEAR,
        _CAREER_SOURCES,
        DOC_CV,
        document_types=_CAREER_DOCS,
    ),
    # Funding.
    "raised": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.BOOL,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
        document_types=_FUNDING_DOCS,
    ),
    "round_year": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.YEAR,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
        document_types=_FUNDING_DOCS,
    ),
    "round_date": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.MONTH,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
        document_types=_FUNDING_DOCS,
    ),
    "round_type": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.ROUND_TYPE,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        document_types=_FUNDING_DOCS,
    ),
    "amount_usd": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.MONEY,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        document_types=_FUNDING_DOCS,
    ),
    "investor": ComponentRule(
        ClaimCategory.FUNDING,
        ValueKind.TEXT,
        _FUNDING_SOURCES,
        DOC_FUNDING,
        document_types=_FUNDING_DOCS,
    ),
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
        document_types=_EVENT_DOCS,
    ),
    "event_date": ComponentRule(
        ClaimCategory.DATED_EVENT,
        ValueKind.MONTH,
        _EVENT_HAPPENED_SOURCES,
        DOC_EVENT,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
        document_types=_OCCURRENCE_DOCS,
    ),
    "stage": ComponentRule(
        ClaimCategory.DATED_EVENT,
        ValueKind.STAGE,
        _EVENT_HAPPENED_SOURCES,
        DOC_EVENT,
        caveats={R.COMPANY_ANNOUNCEMENT: ANNOUNCEMENT_CAVEAT},
        document_types=_OCCURRENCE_DOCS,
    ),
    # Customers and partnerships: the counterparty's own confirmation.
    "counterparty": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.TEXT,
        _CUSTOMER_SOURCES,
        DOC_CUSTOMER,
        document_types=_CUSTOMER_DOCS,
    ),
    "relationship": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.TEXT_CONTAINS,
        _CUSTOMER_SOURCES,
        DOC_CUSTOMER,
        document_types=_CUSTOMER_DOCS,
    ),
    "since_year": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.YEAR,
        _CUSTOMER_SOURCES,
        DOC_CUSTOMER,
        document_types=_CUSTOMER_DOCS,
    ),
    "contract_value": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.MONEY,
        _CUSTOMER_SOURCES,
        DOC_CUSTOMER,
        document_types=_CUSTOMER_DOCS,
    ),
    # Compliance: a named certification or standard (since 2026-11-22.6).
    # Matched on the standard itself (`app.rules.standards`): "ISO/IEC 27001:2022" on
    # a register states "ISO 27001"; "SOC 2 Type I" does not state "SOC 2 Type II".
    "certification": ComponentRule(
        ClaimCategory.COMPLIANCE,
        ValueKind.STANDARD,
        _CERTIFICATION_SOURCES,
        DOC_CERTIFICATION,
    ),
    # That the certificate is current (since 2026-11-22.7). The rules add it to every
    # compliance claim as "valid until on or after today", so an expired certificate
    # on a register contradicts the claim. The company's own page never settles it.
    "certificate_valid_until": ComponentRule(
        ClaimCategory.COMPLIANCE,
        ValueKind.DATE,
        _CERTIFICATE_VALIDITY_SOURCES,
        DOC_CERTIFICATION,
        caveats={R.COMPANY_ANNOUNCEMENT: CERTIFICATE_VALIDITY_CAVEAT},
        document_types=_CERTIFICATE_DOCS,
    ),
    # Intellectual property: a mark and its owner (since 2026-11-22.6).
    "trademark": ComponentRule(
        ClaimCategory.INTELLECTUAL_PROPERTY,
        ValueKind.TEXT,
        _TRADEMARK_SOURCES,
        DOC_TRADEMARK,
    ),
    "mark_owner": ComponentRule(
        ClaimCategory.INTELLECTUAL_PROPERTY,
        ValueKind.TEXT,
        _TRADEMARK_SOURCES,
        DOC_TRADEMARK,
    ),
    # Customer counts ("trusted by 100+ clients in 20+ countries").
    "customer_count": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.COUNT,
        _CUSTOMER_COUNT_SOURCES,
        DOC_CUSTOMER_LIST,
    ),
    "country_count": ComponentRule(
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ValueKind.COUNT,
        _CUSTOMER_COUNT_SOURCES,
        DOC_CUSTOMER_LIST,
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
    "net_worth": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.MONEY, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    # A registry mirror's turnover band ("INR 100 Cr - 500 Cr"), shown as written.
    "revenue_band": ComponentRule(
        ClaimCategory.FINANCIALS, ValueKind.TEXT, _FINANCIAL_SOURCES, DOC_FINANCIALS
    ),
    # Debt and security. Owing money is a lender/accounts question; a registry
    # charge only answers "was security given".
    "has_debt": ComponentRule(
        ClaimCategory.DEBT_SECURITY,
        ValueKind.BOOL,
        _DEBT_SOURCES,
        DOC_LENDER,
        document_types=_DEBT_DOCS,
    ),
    "debt_amount": ComponentRule(
        ClaimCategory.DEBT_SECURITY,
        ValueKind.MONEY,
        _DEBT_SOURCES,
        DOC_LENDER,
        document_types=_DEBT_DOCS,
    ),
    "security_registered": ComponentRule(
        ClaimCategory.DEBT_SECURITY,
        ValueKind.BOOL,
        frozenset({R.REGISTRY, R.REGISTRY_MIRROR}),
        "Registry charge record",
        related_caveat=CHARGE_CAVEAT,
        seller_resolvable=False,
    ),
    "lender": ComponentRule(
        ClaimCategory.DEBT_SECURITY,
        ValueKind.TEXT,
        _DEBT_SOURCES | {R.REGISTRY, R.REGISTRY_MIRROR},
        DOC_LENDER,
        document_types=_DEBT_DOCS,
    ),
    # Litigation: court or registry records and audited disclosures.
    "has_litigation": ComponentRule(
        ClaimCategory.LITIGATION,
        ValueKind.BOOL,
        frozenset({R.REGISTRY, R.AUDITED_STATEMENT}),
        DOC_LITIGATION,
    ),
    "case_reference": ComponentRule(
        ClaimCategory.LITIGATION,
        ValueKind.TEXT,
        frozenset({R.REGISTRY}),
        DOC_LITIGATION,
        seller_resolvable=False,
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
    ClaimCategory.COMPLIANCE: DOC_CERTIFICATION,
    ClaimCategory.INTELLECTUAL_PROPERTY: DOC_TRADEMARK,
    ClaimCategory.OTHER: "A dated document that states it directly",
}

# Claim component → criterion dimension (``Criterion.dimension``). A Contradicted
# claim whose component maps to a must-have's dimension is a verified failure of
# that must-have when the claimed value is exactly what the criterion requires
# (an equality, a single allowed value or "is true"); a contradicted number never
# says on which side of a threshold the real figure lies.
COMPONENT_CRITERION_DIMENSIONS: dict[str, str] = {
    "country": "geography",
    "ownership": "ownership",
    "employee_count": "size",
    "headcount_growth_pct": "growth_signal",
    "round_type": "funding_stage",
    "incorporation_year": "founded_year",
}

# A claim whose every matched component rests on the company's own announcements
# (its website, press release or trust page) is at most partially corroborated in
# these categories: a one-sided statement never makes a relationship, certificate
# or registration Supported (since 2026-11-22.6).
SELF_STATEMENT_CAPPED = frozenset(
    {
        ClaimCategory.CUSTOMER_PARTNERSHIP,
        ClaimCategory.COMPLIANCE,
        ClaimCategory.INTELLECTUAL_PROPERTY,
    }
)

# --- Public lookups (ProofGate source layer, since 2026-11-22.6) ---------------
# At most this many targeted web lookups per claim (one search each, plus at most
# one page fetch). Hard cap: a source module asking for more gets the first two.
MAX_LOOKUPS_PER_CLAIM = 2
MAX_FETCH_PER_LOOKUP = 1

# Coarse effort to obtain each document, for DecisionFlip's tie-break only.
# Anything not listed is medium; a re-run with no document is low.
DOCUMENT_EFFORT: dict[str, EffortLevel] = {
    DOC_INCORPORATION: EffortLevel.LOW,
    DOC_IDENTITY: EffortLevel.LOW,
    DOC_REGISTERED_OFFICE: EffortLevel.LOW,
    DOC_CV: EffortLevel.LOW,
    DOC_EVENT: EffortLevel.LOW,
    "Dated company announcement": EffortLevel.LOW,
    "Registry charge record": EffortLevel.LOW,
    DOC_PAYROLL: EffortLevel.MEDIUM,
    "Dated payroll summaries for both dates": EffortLevel.MEDIUM,
    DOC_FUNDING: EffortLevel.MEDIUM,
    DOC_FACILITY: EffortLevel.MEDIUM,
    DOC_LENDER: EffortLevel.MEDIUM,
    DOC_CUSTOMER: EffortLevel.HIGH,
    DOC_CERTIFICATION: EffortLevel.LOW,
    DOC_TRADEMARK: EffortLevel.LOW,
    DOC_CUSTOMER_LIST: EffortLevel.MEDIUM,
    DOC_FINANCIALS: EffortLevel.HIGH,
    DOC_LITIGATION: EffortLevel.HIGH,
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
        "launched",
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
