"""Shared contract vocabulary: enums, provenance and cost shapes.

Enum values are the shared vocabulary from the design spec (§5.0) and the plan (CP-01).
`app.domain.enums` is the canonical home; these mirror it so the contract can be fixed
before the domain package lands. `tests/api/test_contract.py` asserts the two agree
whenever `app.domain.enums` is importable.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base for every request/response schema. Unknown request keys are rejected.

    In responses every field is always present (defaults are serialised), so the
    generated TypeScript marks response fields as required, not optional.
    """

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


# ---------------------------------------------------------------- shared enums (§5.0)


class ClaimStatus(StrEnum):
    supported = "supported"
    contradicted = "contradicted"
    partially_corroborated = "partially_corroborated"
    conflicting_evidence = "conflicting_evidence"
    cannot_verify = "cannot_verify"
    not_checked = "not_checked"


class Disposition(StrEnum):
    prioritise = "prioritise"
    investigate_further = "investigate_further"
    deprioritise = "deprioritise"
    cannot_assess = "cannot_assess"


class CriterionKind(StrEnum):
    must = "must"
    preference = "preference"


class CriterionResultState(StrEnum):
    """Tri-state result of one criterion (`TriState` in the domain package)."""

    pass_ = "pass"
    fail = "fail"
    unknown = "unknown"


class IdentityState(StrEnum):
    confirmed = "confirmed"
    unresolved = "unresolved"
    ambiguous = "ambiguous"


# ---------------------------------------------------------------- other vocabulary


class ClaimCategory(StrEnum):
    identity_incorporation = "identity_incorporation"
    location = "location"
    team_size = "team_size"
    leadership_history = "leadership_history"
    funding = "funding"
    dated_event = "dated_event"
    customer_partnership = "customer_partnership"
    financials = "financials"
    debt_security = "debt_security"
    litigation = "litigation"
    compliance = "compliance"
    intellectual_property = "intellectual_property"
    other = "other"


class SourceClass(StrEnum):
    """What kind of record a source is. Equal to `app.domain.enums.SourceReliability`,
    which is the source of truth; `tests/api/test_contract.py` asserts they match."""

    registry = "registry"
    registry_mirror = "registry_mirror"
    audited_statement = "audited_statement"
    counterparty_confirmation = "counterparty_confirmation"
    company_announcement = "company_announcement"
    news = "news"
    professional_profile_signal = "professional_profile_signal"
    data_provider = "data_provider"
    seller_document = "seller_document"
    seller_statement = "seller_statement"


class CompanyType(StrEnum):
    startup = "startup"
    established = "established"


class CriterionDimension(StrEnum):
    geography = "geography"
    ownership = "ownership"
    industry_activity = "industry_activity"
    customer_type = "customer_type"
    size = "size"
    growth_signal = "growth_signal"
    funding_stage = "funding_stage"
    founded_year = "founded_year"
    other = "other"


class CriterionOperator(StrEnum):
    eq = "eq"
    in_ = "in"
    gte = "gte"
    lte = "lte"
    between = "between"
    contains_any = "contains_any"
    is_true = "is_true"


class RunKind(StrEnum):
    discover = "discover"
    investor_discover = "investor_discover"
    verify = "verify"
    evaluate = "evaluate"
    recheck = "recheck"
    org_research = "org_research"


class RunState(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class StepState(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped_budget = "skipped_budget"


class EstimateKind(StrEnum):
    """How a non-recorded value is labelled in the UI."""

    estimate = "estimate"
    signal = "signal"


# ---------------------------------------------------------------- provenance


class SourceRef(ApiModel):
    """Where a fact came from. Every displayed fact carries one."""

    source_id: str
    provider: str = Field(description='"crustdata", "web", "upload", "user".')
    label: str = Field(description='Short chip text, e.g. "Registry mirror" or "Deck p. 7".')
    url_or_endpoint: str = Field(description="Public URL, or the provider endpoint called.")
    retrieved_at: datetime
    source_class: SourceClass
    origin_id: str | None = Field(
        default=None,
        description="Copies of one announcement share an origin and count as one source.",
    )


class Fact[T](ApiModel):
    """A displayed value with its source and the date of the underlying fact."""

    value: T
    source: SourceRef
    evidence_id: str | None = None
    as_of: date | None = Field(
        default=None, description="Date of the underlying fact, not of retrieval."
    )
    is_estimate: bool = False
    estimate_kind: EstimateKind | None = Field(
        default=None, description="Set when is_estimate: 'estimate' or 'signal'."
    )
    estimate_basis: str | None = Field(
        default=None,
        description='Plain-words basis, e.g. "from professional profiles, not a payroll count".',
    )


class FactStr(Fact[str]):
    pass


class FactInt(Fact[int]):
    pass


class FactFloat(Fact[float]):
    pass


class FactDate(Fact[date]):
    pass


class FactStrList(Fact[list[str]]):
    pass


class EntityAttachment(ApiModel):
    """Which entity a piece of evidence is attached to, and the identifiers that justify it."""

    entity_name: str
    matched_on: list[str] = Field(
        description='Corroborating identifiers, e.g. ["crustdata_company_id", "domain"].'
    )
    identity_confidence: float | None = None


class EvidenceOut(ApiModel):
    """One evidence row: a source plus exactly what was taken from it."""

    evidence_id: str
    source: SourceRef
    quote: str | None = Field(default=None, description="Exact excerpt from the source.")
    page: int | None = None
    field_path: str | None = Field(default=None, description="For structured sources.")
    value: Any | None = None
    as_of: date | None = None
    attached_to: EntityAttachment | None = None
    deleted: bool = Field(
        default=False,
        description="True when the excerpt was purged under retention; quote is then null.",
    )


class SourceRecordOut(ApiModel):
    """A full, reproducible source row for the Sources tab."""

    source_id: str
    provider: str
    label: str
    url_or_endpoint: str
    request: dict[str, Any] | None = Field(
        default=None, description="Request parameters, for API calls."
    )
    retrieved_at: datetime
    source_class: SourceClass
    origin_id: str | None = None
    title: str | None = None
    publisher: str | None = None
    run_id: str | None = None
    attached: bool = Field(
        default=True,
        description="False for unattached candidates: records with no corroborating identifier.",
    )
    unattached_reason: str | None = None
    request_hash: str | None = Field(
        default=None,
        description="sha256 of the canonical provider request, so the call can be replayed.",
    )
    excerpt: str | None = Field(
        default=None, description="An exact excerpt used from this source; null once purged."
    )
    delete_after: datetime | None = Field(
        default=None, description="When confidential detail of this source is deleted."
    )
    deleted_at: datetime | None = None
    deletion_reason: str | None = Field(
        default=None, description="Why the excerpt or attachment is gone (retention record)."
    )


# ---------------------------------------------------------------- cost


class CostTotalsOut(ApiModel):
    """Crustdata credits and model dollars are separate currencies and never added."""

    crustdata_credits: float = 0
    llm_usd: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    unknown_cost_calls: int = Field(
        default=0, description="Calls whose cost was lost; shown as unknown, never as zero."
    )


class NamedUserOut(ApiModel):
    user_id: str
    display_name: str


class ErrorOut(ApiModel):
    detail: str
