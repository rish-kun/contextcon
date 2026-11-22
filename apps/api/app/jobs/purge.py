"""Retention purge: delete confidential documents and everything derived from them once
`delete_after` passes, and keep a dated record of each deletion.

- documents: the stored object is deleted through `ObjectDeleter` (the GCS adapter is
  built elsewhere), then the row is stamped `deleted_at` and linked to its deletion
  record. The row stays so the case can show "deleted on <date>". The document's
  extracted text goes with it.
- extracted_texts, confidential api_cache rows: deleted.
- confidential_payloads (confidential step outputs and assessment-snapshot excerpts,
  see `app.jobs.retention`): deleted; the step or assessment version that referred to
  one stays and resolves to "deleted under the retention schedule".
- evidence spans, document claims, document sources: content scrubbed, row kept, so
  claim histories and assessment versions still resolve.

Run by the worker every `PURGE_INTERVAL_SECONDS`, or once via
`uv run python -m app.jobs.purge`.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    ApiCache,
    Case,
    Claim,
    ConfidentialPayload,
    DeletionRecord,
    Document,
    Evidence,
    ExtractedText,
    Source,
)

log = logging.getLogger(__name__)

SCRUBBED_CLAIM_TEXT = "[deleted: retention period ended]"


class ObjectDeleter(Protocol):
    async def delete(self, path: str) -> Any:
        """Delete one stored object. Must succeed if the object is already gone."""


class StorageDeleter:
    """Adapts `app.documents.storage.DocumentStorage` (GCS or local; sync) to
    `ObjectDeleter`, keeping what the backend reported for the deletion record."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    async def delete(self, path: str) -> dict[str, Any]:
        record = await asyncio.to_thread(self.storage.delete, path)
        return {
            "backend": getattr(record, "backend", None),
            "existed": getattr(record, "existed", None),
        }


def default_object_deleter() -> ObjectDeleter | None:
    """GCS when `GCS_BUCKET` is set, else local disk (see `storage_from_settings`)."""
    try:
        from app.documents.storage import storage_from_settings
        from app.settings import get_settings

        return StorageDeleter(storage_from_settings(get_settings()))
    except Exception:  # noqa: BLE001 - purge still handles derived rows without it
        log.exception("purge: no object storage available; documents will wait")
        return None


@dataclass
class PurgeReport:
    documents: int = 0
    documents_failed: int = 0
    documents_waiting_for_deleter: int = 0
    extracted_texts: int = 0
    cache_rows: int = 0
    confidential_payloads: int = 0
    evidence_scrubbed: int = 0
    claims_scrubbed: int = 0
    sources_scrubbed: int = 0

    @property
    def total(self) -> int:
        return sum(getattr(self, f.name) for f in fields(self))


async def _workspaces(session: AsyncSession, case_ids: Iterable[Any]) -> dict[Any, Any]:
    ids = {c for c in case_ids if c is not None}
    if not ids:
        return {}
    rows = await session.execute(select(Case.id, Case.workspace_id).where(Case.id.in_(ids)))
    return dict(rows.all())


async def _record_by_case(
    session: AsyncSession, object_type: str, rows: list[tuple[uuid.UUID, uuid.UUID | None]]
) -> None:
    """One deletion record per case for a batch of (object_id, case_id) rows."""
    by_case: dict[uuid.UUID | None, list[str]] = defaultdict(list)
    for object_id, case_id in rows:
        by_case[case_id].append(str(object_id))
    workspaces = await _workspaces(session, by_case)
    for case_id, ids in by_case.items():
        session.add(
            DeletionRecord(
                workspace_id=workspaces.get(case_id),
                case_id=case_id,
                object_type=object_type,
                object_ids=ids,
                object_count=len(ids),
            )
        )


async def _purge_documents(
    sessionmaker: async_sessionmaker[AsyncSession],
    deleter: ObjectDeleter | None,
    now: datetime,
    report: PurgeReport,
    batch: int,
) -> None:
    failed: list[uuid.UUID] = []
    for _ in range(batch):
        async with sessionmaker() as session:
            doc = (
                await session.execute(
                    select(Document)
                    .where(
                        Document.deleted_at.is_(None),
                        Document.delete_after <= now,
                        Document.id.not_in(failed),
                    )
                    .order_by(Document.delete_after)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if doc is None:
                return
            if deleter is None:
                waiting = await session.execute(
                    select(Document.id).where(
                        Document.deleted_at.is_(None), Document.delete_after <= now
                    )
                )
                report.documents_waiting_for_deleter = len(waiting.all())
                log.warning(
                    "purge: %d expired documents wait for an object deleter",
                    report.documents_waiting_for_deleter,
                )
                return
            try:
                storage_result = await deleter.delete(doc.gcs_path)
            except Exception:  # noqa: BLE001 - retried on the next sweep
                log.exception("purge: could not delete object for document %s", doc.id)
                report.documents_failed += 1
                failed.append(doc.id)
                await session.rollback()
                continue
            texts = (
                await session.execute(
                    delete(ExtractedText)
                    .where(ExtractedText.document_id == doc.id)
                    .returning(ExtractedText.id)
                )
            ).scalars()
            text_ids = [str(t) for t in texts]
            workspace_id = (await _workspaces(session, [doc.case_id])).get(doc.case_id)
            record = DeletionRecord(
                workspace_id=workspace_id,
                case_id=doc.case_id,
                object_type="document",
                object_ids=[str(doc.id)],
                object_count=1,
                gcs_path=doc.gcs_path,
                detail={
                    "filename": doc.filename,
                    "delete_after": doc.delete_after.isoformat(),
                    "extracted_text_ids": text_ids,
                    "storage": storage_result if isinstance(storage_result, dict) else None,
                },
            )
            session.add(record)
            await session.flush()
            doc.deleted_at = now
            doc.deletion_record_id = record.id
            await session.commit()
            report.documents += 1
            report.extracted_texts += len(text_ids)


async def purge_expired(
    sessionmaker: async_sessionmaker[AsyncSession],
    deleter: ObjectDeleter | None,
    *,
    now: datetime | None = None,
    batch: int = 100,
) -> PurgeReport:
    now = now or datetime.now(UTC)
    report = PurgeReport()
    await _purge_documents(sessionmaker, deleter, now, report, batch)

    async with sessionmaker() as session:
        rows = (
            await session.execute(
                delete(ExtractedText)
                .where(ExtractedText.delete_after <= now)
                .returning(ExtractedText.id, ExtractedText.case_id)
            )
        ).all()
        await _record_by_case(session, "extracted_text", [tuple(r) for r in rows])
        report.extracted_texts += len(rows)

        rows = (
            await session.execute(
                delete(ApiCache)
                .where(ApiCache.confidential.is_(True), ApiCache.delete_after <= now)
                .returning(ApiCache.id, ApiCache.case_id)
            )
        ).all()
        await _record_by_case(session, "api_cache", [tuple(r) for r in rows])
        report.cache_rows = len(rows)

        # Steps pointing at a payload lose the link (ON DELETE SET NULL) and keep their
        # `{"_confidential": true}` marker, which readers show as expired.
        rows = (
            await session.execute(
                delete(ConfidentialPayload)
                .where(ConfidentialPayload.delete_after <= now)
                .returning(ConfidentialPayload.id, ConfidentialPayload.case_id)
            )
        ).all()
        await _record_by_case(session, "confidential_payload", [tuple(r) for r in rows])
        report.confidential_payloads = len(rows)

        rows = (
            await session.execute(
                update(Evidence)
                .where(Evidence.delete_after <= now, Evidence.scrubbed_at.is_(None))
                .values(span=None, value=None, scrubbed_at=now)
                .returning(Evidence.id, Evidence.case_id)
            )
        ).all()
        await _record_by_case(session, "evidence_span", [tuple(r) for r in rows])
        report.evidence_scrubbed = len(rows)

        rows = (
            await session.execute(
                update(Claim)
                .where(Claim.delete_after <= now, Claim.scrubbed_at.is_(None))
                .values(
                    original_text=SCRUBBED_CLAIM_TEXT, quote=None, components={}, scrubbed_at=now
                )
                .returning(Claim.id, Claim.case_id)
            )
        ).all()
        await _record_by_case(session, "claim_text", [tuple(r) for r in rows])
        report.claims_scrubbed = len(rows)

        rows = (
            await session.execute(
                update(Source)
                .where(Source.delete_after <= now)
                .values(title=None, request={}, delete_after=None)
                .returning(Source.id, Source.case_id)
            )
        ).all()
        await _record_by_case(session, "source_detail", [tuple(r) for r in rows])
        report.sources_scrubbed = len(rows)

        await session.commit()
    return report


async def _main() -> None:
    from app.db.session import dispose_engine, get_sessionmaker

    try:
        report = await purge_expired(get_sessionmaker(), default_object_deleter())
        print(report)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
