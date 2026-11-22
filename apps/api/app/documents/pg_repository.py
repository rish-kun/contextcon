"""`AsyncDocumentRepository` over Postgres.

- `documents`: one row per upload. It outlives the stored object, so a case can still
  show "deck.pdf, deleted on <date>". `purged` means `deleted_at` is set.
- `extracted_texts`: the redacted text, one row per page / slide / paragraph, each with
  the document's `delete_after`, so the retention sweep removes it on schedule.
- `deletion_records`: written by `mark_purged`, in the same shape as the worker's
  retention sweep (`app.jobs.purge`), which purges expired documents directly in SQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Case, DeletionRecord, Document, ExtractedText
from app.documents.extract import PageText
from app.documents.repository import DocumentRecord


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _record(doc: Document, texts: list[ExtractedText]) -> DocumentRecord:
    purged = doc.deleted_at is not None
    return DocumentRecord(
        id=doc.id.hex,
        case_id=str(doc.case_id),
        filename=doc.filename,
        storage_path=doc.gcs_path,
        mime=doc.mime,
        kind=doc.file_kind or "",
        size_bytes=doc.size_bytes or 0,
        sha256=doc.sha256 or "",
        created_at=doc.created_at,
        delete_after=doc.delete_after,
        pages=[]
        if purged
        else [
            PageText(
                page=t.page,
                text=t.text,
                paragraph=t.paragraph,
                has_text_layer=t.has_text_layer,
            )
            for t in texts
        ],
        text_status=doc.text_status or "ok",  # type: ignore[arg-type]
        text_status_reason=doc.text_status_reason,
        redaction_counts=dict(doc.redaction_counts or {}),
        page_count=doc.pages,
        purged=purged,
        purged_at=doc.deleted_at,
        category=doc.kind,
        uploaded_by=str(doc.uploaded_by) if doc.uploaded_by else None,
    )


class PostgresDocumentRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def add(self, record: DocumentRecord) -> None:
        doc_id, case_id = _uuid(record.id), _uuid(record.case_id)
        if doc_id is None or case_id is None:
            raise ValueError("document and case ids must be UUIDs")
        async with self._sm() as session, session.begin():
            doc = Document(
                id=doc_id,
                case_id=case_id,
                kind=record.category,
                filename=record.filename,
                mime=record.mime,
                gcs_path=record.storage_path,
                size_bytes=record.size_bytes,
                sha256=record.sha256,
                pages=record.page_count,
                file_kind=record.kind,
                text_status=record.text_status,
                text_status_reason=record.text_status_reason,
                redaction_counts=dict(record.redaction_counts),
                uploaded_by=_uuid(record.uploaded_by) if record.uploaded_by else None,
                created_at=record.created_at,
                delete_after=record.delete_after,
            )
            session.add(doc)
            await session.flush()
            session.add_all(
                ExtractedText(
                    document_id=doc_id,
                    case_id=case_id,
                    page=page.page,
                    paragraph=page.paragraph,
                    position=position,
                    has_text_layer=page.has_text_layer,
                    text=page.text,
                    # Confidential document text is deleted on the upload's schedule.
                    delete_after=record.delete_after,
                )
                for position, page in enumerate(record.pages)
            )
            try:
                await session.flush()
            except IntegrityError as exc:  # pragma: no cover - same transaction as above
                raise ValueError("could not store the document's text") from exc

    async def get(self, document_id: str) -> DocumentRecord | None:
        doc_id = _uuid(document_id)
        if doc_id is None:
            return None
        async with self._sm() as session:
            doc = await session.get(Document, doc_id)
            if doc is None:
                return None
            return _record(doc, await self._texts(session, doc_id))

    async def list_for_case(self, case_id: str) -> list[DocumentRecord]:
        cid = _uuid(case_id)
        if cid is None:
            return []
        async with self._sm() as session:
            docs = (
                await session.execute(
                    select(Document).where(Document.case_id == cid).order_by(Document.created_at)
                )
            ).scalars()
            return [_record(d, await self._texts(session, d.id)) for d in list(docs)]

    async def list_expired(self, now: datetime) -> list[DocumentRecord]:
        async with self._sm() as session:
            docs = (
                await session.execute(
                    select(Document)
                    .where(Document.deleted_at.is_(None), Document.delete_after <= now)
                    .order_by(Document.delete_after)
                )
            ).scalars()
            # The text is about to go; callers only need the metadata.
            return [_record(d, []) for d in list(docs)]

    async def mark_purged(
        self, document_id: str, at: datetime, *, storage: dict[str, Any] | None = None
    ) -> None:
        doc_id = _uuid(document_id)
        if doc_id is None:
            raise KeyError(document_id)
        async with self._sm() as session, session.begin():
            doc = (
                await session.execute(
                    select(Document).where(Document.id == doc_id).with_for_update()
                )
            ).scalar_one_or_none()
            if doc is None:
                raise KeyError(document_id)
            if doc.deleted_at is not None:
                return  # already purged (by this service or the worker's sweep)
            text_ids = [
                str(t)
                for t in (
                    await session.execute(
                        delete(ExtractedText)
                        .where(ExtractedText.document_id == doc_id)
                        .returning(ExtractedText.id)
                    )
                ).scalars()
            ]
            workspace_id = (
                await session.execute(select(Case.workspace_id).where(Case.id == doc.case_id))
            ).scalar_one_or_none()
            record = DeletionRecord(
                workspace_id=workspace_id,
                case_id=doc.case_id,
                object_type="document",
                object_ids=[str(doc.id)],
                object_count=1,
                gcs_path=doc.gcs_path,
                deleted_at=at,
                detail={
                    "filename": doc.filename,
                    "delete_after": doc.delete_after.isoformat(),
                    "extracted_text_ids": text_ids,
                    "storage": storage,
                },
            )
            session.add(record)
            await session.flush()
            doc.deleted_at = at
            doc.deletion_record_id = record.id

    @staticmethod
    async def _texts(session: AsyncSession, doc_id: uuid.UUID) -> list[ExtractedText]:
        rows = await session.execute(
            select(ExtractedText)
            .where(ExtractedText.document_id == doc_id)
            .order_by(ExtractedText.position, ExtractedText.created_at)
        )
        return list(rows.scalars())
