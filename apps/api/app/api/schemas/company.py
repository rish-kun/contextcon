"""Company records shared by shortlist cards, investor entries and the case profile."""

import datetime as dt

from pydantic import Field

from app.api.schemas.common import (
    ApiModel,
    CompanyType,
    FactFloat,
    FactInt,
    FactStr,
    FactStrList,
    SourceRef,
)


class FundingRoundOut(ApiModel):
    """One dated funding round. Rounds without a date are never shown as dated."""

    round_type: str | None = None
    date: dt.date | None = None
    amount_usd: float | None = None
    investors: list[str] = Field(default_factory=list)
    source: SourceRef
    evidence_id: str | None = None


class HeadcountPointOut(ApiModel):
    date: dt.date
    employee_count: int


class HeadcountSeriesOut(ApiModel):
    """Profile-based headcount over time. Always an estimate, never a payroll count."""

    points: list[HeadcountPointOut]
    source: SourceRef
    estimate_basis: str = "from professional profiles, not a payroll count"


class JobPostingOut(ApiModel):
    title: str
    date_added: dt.date | None = None
    url: str | None = None
    location: str | None = None
    source: SourceRef


class HiringOut(ApiModel):
    """Hiring activity is a signal. It never feeds revenue or the financial assessment."""

    openings: FactInt | None = None
    recent_titles: FactStrList | None = None
    postings: list[JobPostingOut] = Field(default_factory=list)


class PersonOut(ApiModel):
    """A leadership record attached by company id plus name, never by name alone."""

    person_id: str | None = None
    name: str
    title: FactStr | None = None
    history: list[FactStr] = Field(
        default_factory=list, description='Dated roles, e.g. "Head of operations, 2009-2014".'
    )
    profile_url: str | None = None


class CompanyProfileOut(ApiModel):
    crustdata_company_id: int | None = None
    name: FactStr
    legal_name: FactStr | None = None
    domain: FactStr | None = None
    description: FactStr | None = None
    industries: FactStrList | None = None
    headquarters: FactStr | None = None
    country: FactStr | None = None
    year_founded: FactInt | None = None
    incorporation_date: FactStr | None = None
    registry_id: FactStr | None = Field(default=None, description="E.g. CIN.")
    company_type: CompanyType | None = None
    company_type_reason: str | None = None
    headcount: FactInt | None = Field(default=None, description="Estimate; is_estimate is true.")
    headcount_growth_yoy_pct: FactFloat | None = None
    headcount_series: HeadcountSeriesOut | None = None
    total_funding_usd: FactFloat | None = None
    funding_rounds: list[FundingRoundOut] = Field(default_factory=list)
    people: list[PersonOut] = Field(default_factory=list)
    hiring: HiringOut | None = None
