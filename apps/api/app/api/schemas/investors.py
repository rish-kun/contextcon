"""Investor discovery contract (filled by CP-18). Ranking is historical, not predictive."""

import datetime as dt

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
    why: str
    funding_kind_compatibility: str = Field(
        description='E.g. "led 3 growth-equity rounds, latest 2025-08" or "unknown".'
    )
    unknowns: list[str] = Field(default_factory=list)
    possible_duplicate_of: str | None = Field(
        default=None, description="Entry id flagged as a possible duplicate; never merged."
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
