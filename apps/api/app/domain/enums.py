"""Shared vocabulary. Values are stable strings: they are stored in the database,
sent to the web app and hashed into assessment versions, so never rename one."""

from enum import StrEnum


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    PARTIALLY_CORROBORATED = "partially_corroborated"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    CANNOT_VERIFY = "cannot_verify"
    NOT_CHECKED = "not_checked"


class Disposition(StrEnum):
    PRIORITISE = "prioritise"
    INVESTIGATE_FURTHER = "investigate_further"
    DEPRIORITISE = "deprioritise"
    CANNOT_ASSESS = "cannot_assess"


class CriterionKind(StrEnum):
    MUST = "must"
    PREFERENCE = "preference"


class CriterionResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class IdentityStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


# Names used by the implementation plan and the API contract tests.
TriState = CriterionResult
IdentityState = IdentityStatus


class SourceReliability(StrEnum):
    """What kind of record a source is. Adequacy is decided per question by the
    rule table in ``app.rules.policy``, never by the class alone."""

    REGISTRY = "registry"
    REGISTRY_MIRROR = "registry_mirror"
    AUDITED_STATEMENT = "audited_statement"
    COUNTERPARTY_CONFIRMATION = "counterparty_confirmation"
    COMPANY_ANNOUNCEMENT = "company_announcement"
    NEWS = "news"
    PROFESSIONAL_PROFILE_SIGNAL = "professional_profile_signal"
    DATA_PROVIDER = "data_provider"
    SELLER_DOCUMENT = "seller_document"
    SELLER_STATEMENT = "seller_statement"


# The API contract's ``SourceClass`` (app/api/schemas/common.py) mirrors these
# values exactly; tests/api/test_contract.py enforces it.


class ClaimCategory(StrEnum):
    IDENTITY_INCORPORATION = "identity_incorporation"
    LOCATION = "location"
    TEAM_SIZE = "team_size"
    LEADERSHIP_HISTORY = "leadership_history"
    FUNDING = "funding"
    DATED_EVENT = "dated_event"
    CUSTOMER_PARTNERSHIP = "customer_partnership"
    FINANCIALS = "financials"
    DEBT_SECURITY = "debt_security"
    LITIGATION = "litigation"
    OTHER = "other"


class CompanyType(StrEnum):
    STARTUP = "startup"
    ESTABLISHED = "established"


class NotCheckedReason(StrEnum):
    """Why a check did not run. Budget and errors are retried by the analyst;
    the others need something from outside (a document, or a resolved identity)."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    SOURCE_ERROR = "source_error"
    SOURCE_UNAVAILABLE = "source_unavailable"
    NO_SOURCE_IN_SCOPE = "no_source_in_scope"
    IDENTITY_UNRESOLVED = "identity_unresolved"


class ComponentState(StrEnum):
    """Result for one component of a claim (for example the year in
    "incorporated in 2014")."""

    MATCHED = "matched"
    CONTRADICTED = "contradicted"
    CONFLICTING = "conflicting"
    UNSETTLED = "unsettled"
    NOT_CHECKED = "not_checked"


class ValueKind(StrEnum):
    """How a component's value is compared and validated against a quote."""

    YEAR = "year"
    MONTH = "month"
    DATE = "date"
    COUNT = "count"
    MONEY = "money"
    PERCENT = "percent"
    TEXT = "text"
    TEXT_CONTAINS = "text_contains"
    BOOL = "bool"
    ENUM = "enum"
    STAGE = "stage"
    ROUND_TYPE = "round_type"


class DocumentType(StrEnum):
    """What a seller-provided document is. A generic deck or memo
    (``pitch_deck``, ``other``) never settles a question that needs a specific
    record, such as a payroll count or a completed funding round."""

    PAYROLL_RECORD = "payroll_record"
    LEASE = "lease"
    OCCUPANCY_EVIDENCE = "occupancy_evidence"
    SHARE_ALLOTMENT = "share_allotment"
    FUNDING_CLOSING = "funding_closing"
    FUNDS_RECEIPT = "funds_receipt"
    TERM_SHEET = "term_sheet"
    CV = "cv"
    EMPLOYER_CONFIRMATION = "employer_confirmation"
    CUSTOMER_CONTRACT = "customer_contract"
    CUSTOMER_CONFIRMATION = "customer_confirmation"
    LENDER_STATEMENT = "lender_statement"
    AUDITED_FINANCIALS = "audited_financials"
    MANAGEMENT_ACCOUNTS = "management_accounts"
    INCORPORATION_CERTIFICATE = "incorporation_certificate"
    LITIGATION_DISCLOSURE = "litigation_disclosure"
    EVENT_RECORD = "event_record"
    PITCH_DECK = "pitch_deck"
    OTHER = "other"


class CriterionOperator(StrEnum):
    EQ = "eq"
    IN = "in"
    GTE = "gte"
    LTE = "lte"
    BETWEEN = "between"
    CONTAINS_ANY = "contains_any"
    IS_TRUE = "is_true"


class FundingKind(StrEnum):
    VENTURE_EQUITY = "venture_equity"
    GROWTH_EQUITY = "growth_equity"
    DEBT = "debt"
    GRANT = "grant"


class Compatibility(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


# --- DecisionFlip (rules/decision_flip.py, POLICY.md §9) ----------------------


class ItemKind(StrEnum):
    """What an unresolved item is. Item ids are ``claim:<id>``, ``check:<category>``,
    ``criterion:<id>``, ``identity`` and ``financial_inputs``."""

    CLAIM = "claim"
    CHECK_GAP = "check_gap"
    CRITERION = "criterion"
    IDENTITY = "identity"
    FINANCIAL_INPUTS = "financial_inputs"


class ItemClass(StrEnum):
    DECISION_BLOCKER = "decision_blocker"
    DISQUALIFIER_RISK = "disqualifier_risk"
    NON_BLOCKING = "non_blocking"


class FlipState(StrEnum):
    HAS_BLOCKERS = "has_blockers"
    NO_BLOCKERS = "no_blockers"
    DISQUALIFIED = "disqualified"
    NOT_EVIDENCE_LIMITED = "not_evidence_limited"


class FlipSearch(StrEnum):
    EXHAUSTIVE = "exhaustive"
    GREEDY = "greedy"


class NextAction(StrEnum):
    REQUEST_DOCUMENTS = "request_documents"
    RESOLVE_IDENTITY = "resolve_identity"
    RERUN_CHECKS = "rerun_checks"
    ANALYST_FOLLOW_UP = "analyst_follow_up"
    REVIEW_DISQUALIFIER = "review_disqualifier"
    NONE = "none"


class EffortLevel(StrEnum):
    """Coarse effort to obtain a document (policy.DOCUMENT_EFFORT). A tie-break only:
    DecisionFlip's minimum set is the fewest checks, never "the cheapest"."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SelectionBasis(StrEnum):
    """How DecisionFlip picks the minimum set. Only ``fewest_checks`` exists; a later
    minimum-total-effort selection would add a value here."""

    FEWEST_CHECKS = "fewest_checks"


class PriorityReason(StrEnum):
    """Why a requested document sits where it does in the request list (DecisionFlip).
    A decision blocker settles an item that stands between the case and the next
    disposition; a disqualifier risk settles an item that, contradicted, would give
    Deprioritise; ``analyst_retry`` marks a document whose only open items are checks
    to re-run on our side."""

    DECISION_BLOCKER = "decision_blocker"
    DISQUALIFIER_RISK = "disqualifier_risk"
    NON_BLOCKING = "non_blocking"
    ANALYST_RETRY = "analyst_retry"
