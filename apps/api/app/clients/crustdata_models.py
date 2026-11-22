"""Typed views of Crustdata API responses (API version 2025-11-01).

Only the fields DealProof reads are declared. Every model allows extra keys, so
nothing in the response is lost, and every field is optional because Crustdata
returns ``null`` (or omits a group) whenever it has no data.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


# --- Companies -----------------------------------------------------------------


class CompanyBasicInfo(_Model):
    crustdata_company_id: int | None = None
    name: str | None = None
    primary_domain: str | None = None
    all_domains: list[str] | None = None
    website: str | None = None
    professional_network_url: str | None = None
    professional_network_id: str | None = None
    description: str | None = None
    company_type: str | None = None
    status: str | None = None
    year_founded: int | None = None
    employee_count_range: str | None = None
    markets: list[str] | None = None
    industries: list[str] | None = None


class HeadcountPoint(_Model):
    date: str | None = None
    employee_count: int | None = None


class Headcount(_Model):
    total: int | None = None
    largest_headcount_country: str | None = None
    timeseries: list[HeadcountPoint] | None = None
    # Keys differ by endpoint: enrich uses mom/qoq/six_months/yoy/two_years,
    # search uses 1m/3m/6m/12m.
    growth_percent: dict[str, float | None] | None = None
    growth_absolute: dict[str, float | None] | None = None


class InvestorDetail(_Model):
    name: str | None = None
    type: str | None = None
    uuid: str | None = None
    permalink: str | None = None
    crunchbase_profile_url: str | None = None
    categories: list[str] | None = None


class FundingRound(_Model):
    """One entry of ``funding.milestones``."""

    round_type: str | None = None
    date: str | None = None
    funding_date: str | None = None
    amount_usd: float | None = None
    investors: list[str] | None = None
    lead_investors: list[str] | None = None
    investors_detailed: list[InvestorDetail] | None = None
    is_fund: bool | None = None
    permalink: str | None = None


class Funding(_Model):
    total_investment_usd: float | None = None
    last_round_amount_usd: float | None = None
    last_fundraise_date: str | None = None
    last_round_type: str | None = None
    num_funding_rounds: int | None = None
    investors: list[str] | None = None
    investors_detailed: list[InvestorDetail] | None = None
    milestones: list[FundingRound] | None = None


class Locations(_Model):
    country: str | None = None
    headquarters: str | None = None
    street_address: str | None = None
    state: str | None = None
    all_office_addresses: list[str] | None = None


class Hiring(_Model):
    openings_count: int | None = None
    recent_titles_csv: str | None = None
    openings_growth_percent: dict[str, float | None] | None = None
    open_jobs_timeseries: list[dict[str, Any]] | None = None
    recent_openings: list[dict[str, Any]] | None = None


class CompanyPeople(_Model):
    """``people`` group from enrich. Contact fields are stripped at ingestion."""

    founders: list[dict[str, Any]] | None = None
    cxos: list[dict[str, Any]] | None = None
    decision_makers: list[dict[str, Any]] | None = None


class CompanyRecord(_Model):
    crustdata_company_id: int | None = None
    updated_at: str | None = None
    indexed_at: str | None = None
    basic_info: CompanyBasicInfo | None = None
    headcount: Headcount | None = None
    funding: Funding | None = None
    locations: Locations | None = None
    hiring: Hiring | None = None
    people: CompanyPeople | None = None
    taxonomy: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class IdentifyCompanyData(_Model):
    crustdata_company_id: int | None = None
    basic_info: CompanyBasicInfo | None = None
    social_profiles: dict[str, Any] | None = None


class IdentifyMatch(_Model):
    confidence_score: float | None = None
    company_data: IdentifyCompanyData = Field(default_factory=IdentifyCompanyData)


class IdentifyResult(_Model):
    """One entry per submitted identifier."""

    matched_on: str | None = None
    match_type: str | None = None
    matches: list[IdentifyMatch] = Field(default_factory=list)


class EnrichMatch(_Model):
    confidence_score: float | None = None
    company_data: CompanyRecord = Field(default_factory=CompanyRecord)


class EnrichResult(_Model):
    matched_on: str | None = None
    match_type: str | None = None
    matches: list[EnrichMatch] = Field(default_factory=list)


class CompanySearchResult(_Model):
    companies: list[CompanyRecord] = Field(default_factory=list)
    next_cursor: str | None = None
    total_count: int | None = None
    # Set by the client: whether natural-language ranking was applied.
    natural_language: bool = False


# --- People --------------------------------------------------------------------


class Employment(_Model):
    """One position in ``experience.employment_details.current|past``."""

    name: str | None = None
    crustdata_company_id: int | None = None
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    seniority_level: str | None = None
    function_category: str | None = None
    employment_type: str | None = None
    company_website: str | None = None
    company_professional_network_profile_url: str | None = None
    years_at_company_raw: float | None = None


class EmploymentDetails(_Model):
    current: list[Employment] = Field(default_factory=list)
    past: list[Employment] = Field(default_factory=list)


class Experience(_Model):
    employment_details: EmploymentDetails = Field(default_factory=EmploymentDetails)


class PersonBasicProfile(_Model):
    name: str | None = None
    headline: str | None = None
    current_title: str | None = None
    location: dict[str, Any] | None = None


class PersonProfile(_Model):
    crustdata_person_id: int | None = None
    basic_profile: PersonBasicProfile | None = None
    experience: Experience | None = None
    education: dict[str, Any] | None = None
    social_handles: dict[str, Any] | None = None


class PersonSearchResult(_Model):
    profiles: list[PersonProfile] = Field(default_factory=list)
    next_cursor: str | None = None
    total_count: int | None = None


# --- Jobs ----------------------------------------------------------------------


class JobListing(_Model):
    crustdata_job_id: int | None = None
    job_details: dict[str, Any] | None = None
    company: dict[str, Any] | None = None
    location: dict[str, Any] | None = None
    content: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class JobSearchResult(_Model):
    job_listings: list[JobListing] = Field(default_factory=list)
    next_cursor: str | None = None
    total_count: int | None = None


# --- Web -----------------------------------------------------------------------


class WebSearchHit(_Model):
    source: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    position: int | None = None
    metadata: Any = None
    content: str | None = None


class WebSearchResult(_Model):
    success: bool | None = None
    query: str | None = None
    timestamp: float | None = None
    results: list[WebSearchHit] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class WebPage(_Model):
    success: bool | None = None
    url: str | None = None
    timestamp: float | None = None
    title: str | None = None
    content: str | None = None
