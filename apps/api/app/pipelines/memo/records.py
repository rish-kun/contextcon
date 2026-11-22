"""The case's source record, documents and deletion records (retention).

Every source is listed with what reproduces it: the URL, or the provider endpoint with
its request parameters and a hash of the canonical request, plus `retrieved_at` and an
excerpt that was used. Confidential detail is deleted on a schedule; once it is gone
the row says when and why instead of showing a broken link.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.documents import DeletionRecordOut, DocumentKind, DocumentOut
from app.db.models import (
    Case,
    Claim,
    DeletionRecord,
    Document,
    DocumentRequestItem,
    Evidence,
    ExtractedText,
    Source,
    User,
)
from app.settings import get_settings

ARTIFACT_WORDS = {
    "document": "Attachment",
    "extracted_text": "Extracted document text",
    "evidence_span": "Quoted excerpt",
    "claim_text": "Seller claim wording",
    "source_detail": "Source detail",
    "api_cache": "Cached provider response",
}


def request_hash(src: Source) -> str | None:
    """sha256 of the canonical request (provider, endpoint, parameters). Null for a plain
    URL with no parameters, where the URL itself reproduces the fetch."""
    params = src.request if isinstance(src.request, dict) else {}
    if not params and src.endpoint_or_url.startswith("http"):
        return None
    canonical = json.dumps(
        {"provider": src.provider, "endpoint": src.endpoint_or_url, "request": params},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def retention_reason(record: DeletionRecord) -> str:
    days = get_settings().upload_retention_days
    what = ARTIFACT_WORDS.get(record.object_type, record.object_type.replace("_", " "))
    filename = (record.detail or {}).get("filename")
    subject = f"{what} '{filename}'" if filename else what
    return (
        f"{subject} deleted {record.deleted_at.date().isoformat()} under the {days}-day "
        f"retention schedule ({record.reason})"
    )


def deletion_out(record: DeletionRecord, artifact_id: str | None = None) -> DeletionRecordOut:
    ids = record.object_ids or []
    return DeletionRecordOut(
        artifact_kind=record.object_type,
        artifact_id=artifact_id or (ids[0] if len(ids) == 1 else str(record.id)),
        original_filename=(record.detail or {}).get("filename"),
        deleted_at=record.deleted_at,
        reason=retention_reason(record),
    )


@dataclass
class Retention:
    """Deletion records of one case, indexed by what they deleted."""

    records: list[DeletionRecord] = field(default_factory=list)
    by_object: dict[str, DeletionRecord] = field(default_factory=dict)

    def for_object(self, object_id: uuid.UUID | str) -> DeletionRecord | None:
        return self.by_object.get(str(object_id))


async def load_retention(session: AsyncSession, case: Case) -> Retention:
    rows = list(
        (
            await session.execute(
                select(DeletionRecord)
                .where(
                    DeletionRecord.case_id == case.id,
                    DeletionRecord.workspace_id == case.workspace_id,
                )
                .order_by(DeletionRecord.deleted_at, DeletionRecord.id)
            )
        ).scalars()
    )
    out = Retention(records=rows)
    for r in rows:
        for oid in r.object_ids or []:
            out.by_object.setdefault(str(oid), r)
    return out


def deletions_out(ret: Retention) -> list[DeletionRecordOut]:
    return [deletion_out(r) for r in ret.records]


# --- Documents -------------------------------------------------------------------


def _kind(value: str) -> DocumentKind:
    try:
        return DocumentKind(value)
    except ValueError:
        return DocumentKind.other


async def documents_out(session: AsyncSession, case: Case) -> list[DocumentOut]:
    docs = list(
        (
            await session.execute(
                select(Document, User.display_name)
                .outerjoin(User, User.id == Document.uploaded_by)
                .where(Document.case_id == case.id)
                .order_by(Document.created_at, Document.id)
            )
        ).all()
    )
    if not docs:
        return []
    ids = [d.id for d, _ in docs]
    redactions: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    for doc_id, counts in (
        await session.execute(
            select(ExtractedText.document_id, ExtractedText.redaction_counts).where(
                ExtractedText.document_id.in_(ids)
            )
        )
    ).all():
        for k, v in (counts or {}).items():
            redactions[doc_id][k] = redactions[doc_id].get(k, 0) + int(v)
    claims = dict(
        (
            await session.execute(
                select(Claim.document_id, func.count())
                .where(Claim.document_id.in_(ids))
                .group_by(Claim.document_id)
            )
        ).all()
    )
    answers: dict[uuid.UUID, list[str]] = defaultdict(list)
    for doc_id, item_id in (
        await session.execute(
            select(DocumentRequestItem.document_id, DocumentRequestItem.request_item_id)
            .where(DocumentRequestItem.document_id.in_(ids))
            .order_by(DocumentRequestItem.request_item_id)
        )
    ).all():
        answers[doc_id].append(str(item_id))
    return [
        DocumentOut(
            id=str(d.id),
            case_id=str(d.case_id),
            kind=_kind(d.kind),
            filename=d.filename,
            mime=d.mime,
            size_bytes=d.size_bytes or 0,
            pages=d.pages,
            uploaded_at=d.created_at,
            uploaded_by_name=name,
            delete_after=d.delete_after,
            purged=d.deleted_at is not None,
            redaction_counts=d.redaction_counts or redactions.get(d.id, {}),
            answers_request_item_ids=answers.get(d.id, []),
            claims_extracted=int(claims.get(d.id, 0)),
        )
        for d, name in docs
    ]


def retention_notice(documents: list[DocumentOut]) -> str | None:
    """Deletion dates of uploaded documents, in the memo's confidentiality wording."""
    if not documents:
        return None
    pending = sorted({d.delete_after.date().isoformat() for d in documents if not d.purged})
    gone = [d.filename for d in documents if d.purged]
    parts = [
        "Uploaded seller documents were used only for this case, were not used to train AI "
        "models and were not shared across customers."
    ]
    if pending:
        parts.append(f"They are scheduled for deletion on {', '.join(pending)}.")
    if gone:
        parts.append(f"Already deleted under the retention schedule: {', '.join(gone)}.")
    return " ".join(parts)


# --- Sources ---------------------------------------------------------------------


async def source_retention(
    session: AsyncSession, case: Case, ret: Retention
) -> dict[str, dict[str, Any]]:
    """Per source id: the request hash, an excerpt used from it, and its retention state
    (when confidential detail is deleted, or when and why it already was)."""
    rows = list(
        (
            await session.execute(
                select(Source, Document)
                .outerjoin(Document, Document.id == Source.document_id)
                .where(Source.case_id == case.id, Source.workspace_id == case.workspace_id)
            )
        ).all()
    )
    if not rows:
        return {}
    evidence: dict[uuid.UUID, list[Evidence]] = defaultdict(list)
    for e in (
        await session.execute(
            select(Evidence)
            .where(Evidence.source_id.in_([s.id for s, _ in rows]))
            .order_by(Evidence.created_at, Evidence.id)
        )
    ).scalars():
        evidence[e.source_id].append(e)

    out: dict[str, dict[str, Any]] = {}
    for src, doc in rows:
        evs = evidence.get(src.id, [])
        live = next((e for e in evs if e.span and e.scrubbed_at is None), None)
        scrubbed = next((e for e in evs if e.scrubbed_at is not None), None)
        deleted_at: datetime | None = None
        reason: str | None = None
        if doc is not None and doc.deleted_at is not None:
            record = ret.for_object(doc.id)
            deleted_at = doc.deleted_at
            reason = retention_reason(record) if record else "Attachment deleted under retention"
        elif live is None and scrubbed is not None:
            record = ret.for_object(scrubbed.id)
            deleted_at = scrubbed.scrubbed_at
            reason = retention_reason(record) if record else "Excerpt deleted under retention"
        out[str(src.id)] = {
            "request_hash": request_hash(src),
            "excerpt": live.span if live else None,
            "delete_after": src.delete_after or (doc.delete_after if doc else None),
            "deleted_at": deleted_at,
            "deletion_reason": reason,
        }
    return out
