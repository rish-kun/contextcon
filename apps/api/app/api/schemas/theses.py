"""Discover contract: thesis → criteria → search run → shortlist (filled by CP-17)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.api.schemas.common import (
    ApiModel,
    CriterionDimension,
    CriterionKind,
    CriterionOperator,
    CriterionResultState,
    EvidenceOut,
    FactFloat,
    FactInt,
    FactStr,
)
from app.api.schemas.company import FundingRoundOut, HeadcountSeriesOut, HiringOut
from app.api.schemas.runs import RunOut


class ThesisStatus(StrEnum):
    draft = "draft"
    searching = "searching"
    ready = "ready"
    failed = "failed"


class ThesisCreate(ApiModel):
    text: str = Field(min_length=10, max_length=4000)


class CriterionIn(ApiModel):
    """An editable criterion. Send `id` to keep an existing one, omit it to add."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=300)
    kind: CriterionKind
    dimension: CriterionDimension
    operator: CriterionOperator
    value: Any = Field(description="Operand; shape depends on operator (list for in/between).")
    crustdata_filter: dict[str, Any] | None = Field(
        default=None,
        description="Mapped provider filter, or null when the criterion is assessed from evidence.",
    )


class CriterionOut(ApiModel):
    id: str
    position: int
    label: str
    kind: CriterionKind
    dimension: CriterionDimension
    operator: CriterionOperator
    value: Any
    crustdata_filter: dict[str, Any] | None = None
    assessed_from_evidence: bool = Field(description="True when crustdata_filter is null.")
    edited: bool = False


class CriterionResultOut(ApiModel):
    criterion_id: str
    label: str
    kind: CriterionKind
    weight: int = Field(description="Policy weight: must 2, preference 1.")
    state: CriterionResultState
    reason: str
    evidence: list[EvidenceOut] = Field(default_factory=list)


class ReasonOut(ApiModel):
    text: str
    criterion_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ShortlistCardOut(ApiModel):
    business: FactStr | None = None
    location: FactStr | None = None
    headcount: FactInt | None = Field(default=None, description="Estimate.")
    headcount_growth_yoy_pct: FactFloat | None = Field(default=None, description="Estimate.")
    headcount_series: HeadcountSeriesOut | None = Field(
        default=None, description="Estimate. The provider's dated points, oldest first."
    )
    total_funding_usd: FactFloat | None = None
    funding_rounds: list[FundingRoundOut] = Field(default_factory=list)
    hiring: HiringOut | None = Field(default=None, description="Signal.")
    reasons: list[ReasonOut] = Field(default_factory=list, description="Criteria met.")
    unknowns: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(description="Latest retrieved_at across the card's sources.")


class ShortlistItemOut(ApiModel):
    id: str
    rank: int | None = Field(default=None, description="Null for excluded items.")
    crustdata_company_id: int
    name: str
    domain: str | None = None
    fit: int | None = Field(description="0-100; null means unavailable (nothing assessable).")
    fit_unavailable_reason: str | None = None
    assessable_pct: int
    excluded: bool = False
    exclusion_reason: str | None = Field(default=None, description="The verified must-have fail.")
    criterion_results: list[CriterionResultOut] = Field(default_factory=list)
    card: ShortlistCardOut
    case_id: str | None = Field(default=None, description="Set once a case was opened from it.")


class ThesisOut(ApiModel):
    id: str
    text: str
    status: ThesisStatus
    created_at: datetime
    criteria: list[CriterionOut]
    run: RunOut | None = Field(default=None, description="Latest discover run.")
    shortlist: list[ShortlistItemOut] = Field(
        default_factory=list, description="Ranked items first, then excluded items."
    )


class ThesisSummary(ApiModel):
    id: str
    text: str
    status: ThesisStatus
    created_at: datetime
    criteria_count: int
    shortlist_count: int
    latest_run_id: str | None = None
