"""Uploaded document contract (filled by CP-20; recheck by CP-24)."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.api.schemas.common import ApiModel
from app.api.schemas.runs import RunOut


class DocumentKind(StrEnum):
    seller_deck = "seller_deck"
    seller_response = "seller_response"
    other = "other"


class DocumentOut(ApiModel):
    id: str
    case_id: str
    kind: DocumentKind
    filename: str
    mime: str
    size_bytes: int
    pages: int | None = None
    uploaded_at: datetime
    uploaded_by_name: str | None = None
    delete_after: datetime = Field(description="Retention deletion date shown on the case.")
    purged: bool = False
    redaction_counts: dict[str, int] = Field(
        default_factory=dict, description='Personal details removed, by kind, e.g. {"email": 2}.'
    )
    answers_request_item_ids: list[str] = Field(default_factory=list)
    claims_extracted: int = 0
    run: RunOut | None = Field(default=None, description="Intake or recheck run.")


class DocumentUrlOut(ApiModel):
    """A short-lived, case-scoped signed URL."""

    url: str
    expires_at: datetime


class DeletionRecordOut(ApiModel):
    artifact_kind: str = Field(description='"document", "extracted_text", "quote", ...')
    artifact_id: str
    original_filename: str | None = None
    deleted_at: datetime
    reason: str
