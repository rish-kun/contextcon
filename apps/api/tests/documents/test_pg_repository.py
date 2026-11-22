"""PostgresDocumentRepository with the ingestion service and the worker's purge job."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import DeletionRecord, Document, ExtractedText
from app.documents import IncomingFile, IngestionService, LocalStorage
from app.documents.pg_repository import PostgresDocumentRepository
from app.jobs.purge import StorageDeleter, purge_expired
from tests.db.factories import tenant
from tests.documents.conftest import make_pdf

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def _service(sm, root: Path, clock: Clock) -> IngestionService:
    return IngestionService(
        storage=LocalStorage(root, clock=clock),
        repository=PostgresDocumentRepository(sm),
        retention_days=30,
        clock=clock,
    )


async def test_ingest_persists_document_and_confidential_text(sm, session, tmp_path) -> None:
    t = await tenant(session)
    clock = Clock()
    svc = _service(sm, tmp_path, clock)
    pdf = make_pdf(["Write to cfo@northwind.example", "We employ 250 people."])
    result = await svc.ingest_async(
        str(t.case.id),
        IncomingFile("deck.pdf", pdf),
        category="seller_response",
        uploaded_by=str(t.user.id),
    )

    record = await svc.repository.get(result.document_id)
    assert [p.text for p in record.pages] == ["Write to [redacted:email]", "We employ 250 people."]
    assert [p.page for p in record.pages] == [1, 2]
    assert record.category == "seller_response" and record.kind == "pdf"
    assert record.redaction_counts == {"email": 1}
    assert record.uploaded_by == str(t.user.id)
    assert record.delete_after == NOW + timedelta(days=30)
    assert [r.id for r in await svc.repository.list_for_case(str(t.case.id))] == [record.id]

    texts = (await session.execute(select(ExtractedText))).scalars().all()
    assert len(texts) == 2
    assert all(x.delete_after == record.delete_after for x in texts)
    assert "cfo@" not in " ".join(x.text for x in texts)
    doc = (await session.execute(select(Document))).scalar_one()
    assert doc.gcs_path == result.storage_path and (tmp_path / doc.gcs_path).is_file()


async def test_service_purge_deletes_object_text_and_records_it(sm, session, tmp_path) -> None:
    t = await tenant(session)
    clock = Clock()
    svc = _service(sm, tmp_path, clock)
    doc = await svc.ingest_async(str(t.case.id), IncomingFile("deck.pdf", make_pdf(["x"])))

    clock.now = doc.delete_after - timedelta(seconds=1)
    assert await svc.purge_expired_async() == []
    clock.now = doc.delete_after
    purged = await svc.purge_expired_async()
    assert [r.path for r in purged] == [doc.storage_path] and purged.failed == []
    assert not (tmp_path / doc.storage_path).exists()

    record = await svc.repository.get(doc.document_id)
    assert record.purged and record.pages == [] and record.purged_at == doc.delete_after
    deletion = (await session.execute(select(DeletionRecord))).scalar_one()
    assert deletion.object_type == "document" and deletion.case_id == t.case.id
    assert deletion.detail["filename"] == "deck.pdf"
    assert deletion.detail["storage"] == {"backend": "local", "existed": True}
    assert (await session.execute(select(ExtractedText))).first() is None
    # Idempotent: a second purge finds nothing and writes no second record.
    await svc.repository.mark_purged(doc.document_id, clock.now)
    assert len((await session.execute(select(DeletionRecord))).all()) == 1


async def test_worker_purge_uses_real_storage_on_repository_documents(
    sm, session, tmp_path
) -> None:
    t = await tenant(session)
    clock = Clock()
    svc = _service(sm, tmp_path, clock)
    doc = await svc.ingest_async(str(t.case.id), IncomingFile("deck.pdf", make_pdf(["x"])))
    assert (tmp_path / doc.storage_path).is_file()

    deleter = StorageDeleter(LocalStorage(tmp_path))
    report = await purge_expired(sm, deleter, now=doc.delete_after + timedelta(seconds=1))
    assert report.documents == 1 and report.extracted_texts == 1

    assert not (tmp_path / doc.storage_path).exists()
    record = await svc.repository.get(doc.document_id)
    assert record.purged and record.pages == []
    assert await svc.repository.list_expired(doc.delete_after + timedelta(days=1)) == []
    deletion = (await session.execute(select(DeletionRecord))).scalar_one()
    assert deletion.detail["storage"] == {"backend": "local", "existed": True}
    with pytest.raises(Exception, match=doc.document_id):
        await svc.download_url_async(doc.document_id, caller="a", authorize=lambda *_: True)
