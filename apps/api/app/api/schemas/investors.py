"""Investor discovery contract (filled by CP-18). Ranking is historical, not predictive."""

import datetime as dt
from enum import StrEnum

from pydantic import Field

from app.api.schemas.common import ApiModel, SourceRef
from app.api.schemas.runs import RunOut
from app.api.schemas.theses import ThesisStatus


class InvestorSearchIn(ApiModel):
    sector: str = Field(min_length=2, max_length=300)
    location: str = Field(min_length=2, max_length=200)
    stage: str = Field(min_length=2, max_length=100, description='E.g. "series_a".')
    size: str = Field(min_length=1, max_length=100, description='Headcount band, e.g. "51-200".')
    funding_sought: str = Field(
        min_length=2,
        max_length=200,
        description='Kind of funding, e.g. "equity growth", "venture", "debt".',
    )


class FundingCompatibility(StrEnum):
    """Whether dated records show the investor making rounds of the kind sought."""

    compatible = "compatible"
    incompatible = "incompatible"
    unknown = "unknown"


RANKING_BASIS = (
    "Ranked by comparable investments found in the record, weighted toward recent rounds. "
    "This describes past behaviour; it does not predict whether an investor will invest."
)


class ComparableRoundOut(ApiModel):
    company_id: int
    company_name: str
    round_type: str | None = None
    date: dt.date
    amount_usd: float | None = None
    source: SourceRef
    evidence_id: str | None = None


class InvestorEntryOut(ApiModel):
    id: str
    rank: int
    investor_name: str
    investor_key: str
    investor_uuid: str | None = None
    score: float = Field(description="Recency-weighted count of comparable rounds.")
    comparable_rounds: list[ComparableRoundOut]
    latest_sector_investment_found: dt.date | None = None
    latest_sector_investment_scope: str | None = Field(
        default=None,
        description="Search date and scope behind the latest date, e.g. "
        '"searched 2026-11-22 across 18 comparable companies (India; …)". Never an absolute '
        '"last invested".',
    )
    why: str
    compatibility: FundingCompatibility = FundingCompatibility.unknown
    funding_kind_compatibility: str = Field(
        description='E.g. "3 growth equity rounds in the record, latest 2025-08" or '
        '"Compatibility with debt unknown".'
    )
    unknowns: list[str] = Field(default_factory=list)
    possible_duplicate_of: str | None = Field(
        default=None, description="Entry id flagged as a possible duplicate; never merged."
    )
    possible_duplicates: list[str] = Field(
        default_factory=list, description="Every entry id this one may duplicate."
    )


class InvestorSearchOut(ApiModel):
    id: str
    profile: InvestorSearchIn
    status: ThesisStatus
    created_at: dt.datetime
    searched_at: dt.datetime | None = None
    scope_note: str | None = Field(
        default=None, description='E.g. "searched 2026-11-22 across 40 comparable companies".'
    )
    comparables_considered: int = 0
    funding_kind_sought: str | None = Field(
        default=None, description='"venture_equity", "growth_equity", "debt", "grant" or null.'
    )
    rounds_read: int = 0
    rounds_excluded: int = Field(
        default=0, description="Rounds left out because they had no date or no named investor."
    )
    ranking_basis: str = RANKING_BASIS
    run: RunOut | None = None
    entries: list[InvestorEntryOut] = Field(default_factory=list)


class InvestorSearchSummary(ApiModel):
    id: str
    sector: str
    location: str
    stage: str
    status: ThesisStatus
    created_at: dt.datetime
    entries_count: int
