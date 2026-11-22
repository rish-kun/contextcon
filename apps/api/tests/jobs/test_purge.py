import pytest
from sqlalchemy import select

from app.db.adapters import DbCache
from app.db.ledger import CostContext
from app.db.models import (
    ApiCache,
    Claim,
    DeletionRecord,
    Document,
    Evidence,
    ExtractedText,
    Source,
)
from app.jobs.purge import SCRUBBED_CLAIM_TEXT, purge_expired
from tests.db.factories import days, tenant

pytestmark = pytest.mark.asyncio


class FakeStorage:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.deleted: list[str] = []
        self.fail = fail or set()

    async def delete(self, path: str) -> None:
        if path in self.fail:
            raise OSError("gcs unavailable")
        self.deleted.append(path)


async def _seed(session, sm, t, *, expired: bool):
    when = days(-1) if expired else days(30)
    doc = Document(
        case_id=t.case.id,
        filename="deck.pdf",
        mime="application/pdf",
        gcs_path=f"cases/{t.case.id}/{'old' if expired else 'new'}/deck.pdf",
        delete_after=when,
    )
    session.add(doc)
    await session.flush()
    session.add(
        ExtractedText(
            document_id=doc.id,
            case_id=t.case.id,
            page=1,
            text="We employ 250 people",
            delete_after=when,
        )
    )
    src = Source(
        workspace_id=t.workspace.id,
        case_id=t.case.id,
        document_id=doc.id,
        provider="upload",
        endpoint_or_url=doc.gcs_path,
        source_class="seller_document",
        title="Seller deck",
        delete_after=when,
    )
    session.add(src)
    await session.flush()
    ev = Evidence(
        source_id=src.id,
        case_id=t.case.id,
        entity_ref="company",
        span="250 people",
        origin_key=f"doc:{doc.id}:p1",
        delete_after=when,
    )
    claim = Claim(
        case_id=t.case.id,
        original_text="We employ 250 people",
        origin="deck",
        category="team_size",
        quote="250 people",
        document_id=doc.id,
        delete_after=when,
    )
    session.add_all([ev, claim])
    await session.commit()
    cache = DbCache(
        sm, CostContext(t.workspace.id, case_id=t.case.id), confidential=True, delete_after=when
    )
    await cache.set(f"llm:claims:{doc.id}", {"claims": ["250"]})
    return doc, ev, claim, src


async def test_purge_deletes_expired_documents_and_derivatives(session, sm) -> None:
    t = await tenant(session)
    old_doc, old_ev, old_claim, old_src = await _seed(session, sm, t, expired=True)
    new_doc, *_ = await _seed(session, sm, t, expired=False)
    storage = FakeStorage()

    report = await purge_expired(sm, storage)

    assert storage.deleted == [old_doc.gcs_path]
    assert (report.documents, report.extracted_texts, report.cache_rows) == (1, 1, 1)
    assert (report.evidence_scrubbed, report.claims_scrubbed, report.sources_scrubbed) == (1, 1, 1)
    async with sm() as s:
        old = await s.get(Document, old_doc.id)
        assert old.deleted_at is not None and old.deletion_record_id is not None
        record = await s.get(DeletionRecord, old.deletion_record_id)
        assert record.object_type == "document" and record.gcs_path == old_doc.gcs_path
        assert record.deleted_at is not None and "250" not in str(record.detail)
        assert (await s.get(Document, new_doc.id)).deleted_at is None
        texts = (await s.execute(select(ExtractedText.document_id))).scalars().all()
        assert texts == [new_doc.id]
        assert len((await s.execute(select(ApiCache))).all()) == 1
        ev = await s.get(Evidence, old_ev.id)
        assert ev.span is None and ev.scrubbed_at is not None
        claim = await s.get(Claim, old_claim.id)
        assert claim.original_text == SCRUBBED_CLAIM_TEXT and claim.quote is None
        assert (await s.get(Source, old_src.id)).title is None
        kinds = {r.object_type for r in (await s.execute(select(DeletionRecord))).scalars()}
        assert kinds == {"document", "api_cache", "evidence_span", "claim_text", "source_detail"}

    again = await purge_expired(sm, storage)
    assert again.total == 0  # idempotent


async def test_failed_object_delete_is_retried_later(session, sm) -> None:
    t = await tenant(session)
    doc, *_ = await _seed(session, sm, t, expired=True)
    report = await purge_expired(sm, FakeStorage(fail={doc.gcs_path}))
    assert (report.documents, report.documents_failed) == (0, 1)
    async with sm() as s:
        assert (await s.get(Document, doc.id)).deleted_at is None
        doc_records = await s.execute(
            select(DeletionRecord).where(DeletionRecord.object_type == "document")
        )
        assert doc_records.first() is None
    retry = await purge_expired(sm, FakeStorage())
    assert retry.documents == 1


async def test_without_a_deleter_documents_wait(session, sm) -> None:
    t = await tenant(session)
    doc, *_ = await _seed(session, sm, t, expired=True)
    report = await purge_expired(sm, None)
    assert report.documents == 0 and report.documents_waiting_for_deleter == 1
    assert report.extracted_texts == 1  # derivatives still go on schedule


async def test_storage_deleter_adapts_document_storage(session, sm, tmp_path) -> None:
    from app.documents.storage import LocalStorage
    from app.jobs.purge import StorageDeleter

    t = await tenant(session)
    doc, *_ = await _seed(session, sm, t, expired=True)
    storage = LocalStorage(tmp_path)
    storage.put(doc.gcs_path, b"%PDF-1.7 fixture", "application/pdf", days(-1))
    report = await purge_expired(sm, StorageDeleter(storage))
    assert report.documents == 1
    async with sm() as s:
        record = (
            await s.execute(select(DeletionRecord).where(DeletionRecord.object_type == "document"))
        ).scalar_one()
    assert record.detail["storage"] == {"backend": "local", "existed": True}
    assert not (tmp_path / doc.gcs_path).exists()
