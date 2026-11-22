"""Claim ledger contract (intake CP-20, statuses CP-21, rechecks CP-24)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.api.schemas.common import ApiModel, ClaimCategory, ClaimStatus, EvidenceOut


class ClaimOrigin(StrEnum):
    document = "document"
    typed = "typed"


class NotCheckedReason(StrEnum):
    budget_reached = "budget_reached"
    source_unavailable = "source_unavailable"
    step_failed = "step_failed"
    identity_unresolved = "identity_unresolved"


class SubstantiveResult(StrEnum):
    supports = "supports"
    conflicts = "conflicts"
    partial = "partial"
    silent = "silent"


class ClaimCreate(ApiModel):
    text: str = Field(min_length=3, max_length=2000)


class StatedInOut(ApiModel):
    """Where the claim was made: a document page, or typed by a named person."""

    document_id: str | None = None
    filename: str | None = None
    page: int | None = None
    quote: str | None = None
    typed_by_name: str | None = None
    typed_at: datetime | None = None


class SearchedResultOut(ApiModel):
    url: str | None = None
    title: str | None = None
    source_class: str
    attached: bool = Field(description="False: the page could not be tied to the company.")


class SearchedOut(ApiModel):
    """One public lookup the check made (public terms only)."""

    label: str = Field(description='What was searched, e.g. "Microsoft partner directory".')
    query: str | None = None
    results: list[SearchedResultOut] = Field(default_factory=list)
    skipped: str | None = Field(
        default=None, description="Why the lookup did not run: budget, identity, unsafe_query."
    )


class ClaimCheckOut(ApiModel):
    """One append-only status check. The latest row is the current status."""

    id: str
    run_id: str | None = None
    status: ClaimStatus
    reason: str
    not_checked_reason: NotCheckedReason | None = None
    settle_with: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    searched: list[SearchedOut] = Field(default_factory=list)
    assessment_version: int | None = None
    created_at: datetime


class ClaimOut(ApiModel):
    id: str
    number: int = Field(description="1-based position in the ledger.")
    original_text: str = Field(description="The seller's wording, verbatim.")
    normalised_text: str
    category: ClaimCategory
    components: dict[str, Any] = Field(default_factory=dict)
    material: bool = True
    origin: ClaimOrigin
    stated_in: StatedInOut
    status: ClaimStatus
    reason: str = Field(description="Always present; required for not_checked.")
    not_checked_reason: NotCheckedReason | None = None
    adequate_source_reached: bool | None = Field(
        default=None, description="Evidence adequacy, reported apart from the substantive result."
    )
    substantive_result: SubstantiveResult | None = None
    settle_with: str | None = Field(
        default=None, description="The document that would settle it; feeds the request list."
    )
    evidence: list[EvidenceOut] = Field(default_factory=list)
    searched: list[SearchedOut] = Field(
        default_factory=list,
        description="Public lookups the current check made; shown as 'searched: X, Y'.",
    )
    history: list[ClaimCheckOut] = Field(default_factory=list, description="Oldest first.")
    changed_in_version: int | None = None
