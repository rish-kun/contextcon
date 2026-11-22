import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.documents import (
    DocumentAccessDenied,
    DocumentNotFound,
    IncomingFile,
    IngestionService,
    InMemoryDocumentRepository,
    LocalStorage,
    UploadRejected,
    ingest,
    read_limited,
)
from app.settings import Settings
from tests.documents.conftest import make_pdf, make_scanned_pdf

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(tmp_path: Path, clock: Clock) -> IngestionService:
    return IngestionService(
        storage=LocalStorage(tmp_path / "uploads", clock=clock),
        repository=InMemoryDocumentRepository(),
        retention_days=30,
        clock=clock,
    )


def test_ingest_pdf_end_to_end(service: IngestionService, tmp_path: Path) -> None:
    pdf = make_pdf(["Based in Pune. Email cfo@northwind.example", "Call 9876543210"])
    result = service.ingest("case1", IncomingFile("../Pitch Deck.pdf", pdf))

    assert result.filename == "Pitch_Deck.pdf"
    assert result.storage_path == f"cases/case1/{result.document_id}/Pitch_Deck.pdf"
    assert result.delete_after == NOW + timedelta(days=30)
    assert result.text_status == "ok"
    assert result.redaction_log == {"email": 1, "phone": 1}
    assert [p["page"] for p in result.pages_as_dicts()] == [1, 2]
    joined = " ".join(p.text for p in result.pages)
    assert "cfo@northwind.example" not in joined and "9876543210" not in joined
    assert "Based in Pune." in joined

    # The original file is stored as uploaded; the persisted text is the redacted text.
    stored = tmp_path / "uploads" / result.storage_path
    assert stored.read_bytes() == pdf
    record = service.repository.get(result.document_id)
    assert record is not None
    assert record.pages == result.pages and record.redaction_counts == result.redaction_log
    assert record.page_count == 2 and record.kind == "pdf" and record.size_bytes == len(pdf)


def test_ingest_each_office_type(service, sample_pptx, sample_docx) -> None:
    pptx = service.ingest("case1", IncomingFile("deck.pptx", sample_pptx))
    assert [p.page for p in pptx.pages] == [1, 2, 3]
    docx = service.ingest("case1", IncomingFile("memo.docx", sample_docx))
    assert all(p.page is None for p in docx.pages)
    assert docx.redaction_log == {"email": 1}
    assert len(service.repository.list_for_case("case1")) == 2


def test_ingest_scanned_pdf_flags_no_text_layer(service) -> None:
    result = service.ingest("case1", IncomingFile("scan.pdf", make_scanned_pdf(2)))
    assert result.text_status == "no_text_layer"
    assert result.text_status_reason and "no text layer" in result.text_status_reason
    assert result.pages_without_text == [1, 2]
    assert service.repository.get(result.document_id).text_status == "no_text_layer"


def test_rejected_uploads_store_nothing(service, tmp_path: Path) -> None:
    with pytest.raises(UploadRejected) as exc:
        service.ingest("case1", IncomingFile("deck.pdf", b"PK\x03\x04fake"))
    assert exc.value.status_code == 415
    with pytest.raises(UploadRejected) as exc:
        service.ingest("case1", IncomingFile("deck.pdf", b"%PDF-1.4 broken"))
    assert exc.value.status_code == 422
    assert service.repository.list_for_case("case1") == []
    assert not (tmp_path / "uploads" / "cases").exists()


def test_max_upload_mb_is_configurable(tmp_path: Path) -> None:
    small = IngestionService(
        storage=LocalStorage(tmp_path),
        repository=InMemoryDocumentRepository(),
        max_upload_mb=1,
    )
    with pytest.raises(UploadRejected) as exc:
        small.ingest("case1", IncomingFile("notes.txt", b"a" * (1024 * 1024 + 1)))
    assert exc.value.status_code == 413


def test_read_limited_stops_early() -> None:
    assert read_limited(io.BytesIO(b"abc"), 3) == b"abc"
    with pytest.raises(UploadRejected) as exc:
        read_limited(io.BytesIO(b"abcd"), 3)
    assert exc.value.status_code == 413


def test_custom_redactor_is_used_for_every_page(service) -> None:
    calls: list[str] = []

    def redactor(text: str) -> tuple[str, dict[str, int]]:
        calls.append(text)
        return text.upper(), {"custom": 1}

    service.redactor = redactor
    result = service.ingest("case1", IncomingFile("deck.pdf", make_pdf(["one", "two"])))
    assert calls == ["one", "two"]
    assert [p.text for p in result.pages] == ["ONE", "TWO"]
    assert result.redaction_log == {"custom": 2}


def test_repository_failure_removes_stored_file(tmp_path: Path) -> None:
    class Broken(InMemoryDocumentRepository):
        def add(self, record):
            raise RuntimeError("db down")

    svc = IngestionService(storage=LocalStorage(tmp_path), repository=Broken())
    with pytest.raises(RuntimeError):
        svc.ingest("case1", IncomingFile("notes.txt", b"hello"))
    assert not (tmp_path / "cases").exists()


def test_download_url_only_for_authorized_callers(service) -> None:
    doc = service.ingest("case1", IncomingFile("notes.txt", b"hello"))

    def authorize(caller, case_id):
        return caller == "alice" and case_id == "case1"

    url = service.download_url(doc.document_id, caller="alice", authorize=authorize)
    assert doc.storage_path in url and "sig=" in url
    with pytest.raises(DocumentAccessDenied):
        service.download_url(doc.document_id, caller="mallory", authorize=authorize)
    with pytest.raises(DocumentAccessDenied):
        service.download_url(doc.document_id, caller=None, authorize=lambda *_: True)
    with pytest.raises(DocumentNotFound):
        service.download_url("missing", caller="alice", authorize=authorize)


def test_delete_returns_record_and_purges_text(service, tmp_path: Path) -> None:
    doc = service.ingest("case1", IncomingFile("notes.txt", b"hello"))
    record = service.delete(doc.document_id)
    assert record.existed and record.path == doc.storage_path and record.deleted_at == NOW

    row = service.repository.get(doc.document_id)
    assert row.purged and row.pages == [] and row.purged_at == NOW
    assert not (tmp_path / "uploads" / doc.storage_path).exists()
    with pytest.raises(DocumentNotFound):
        service.download_url(doc.document_id, caller="a", authorize=lambda *_: True)


def test_purge_expired_after_retention(service, clock: Clock) -> None:
    old = service.ingest("case1", IncomingFile("old.txt", b"old"))
    clock.now = NOW + timedelta(days=10)
    new = service.ingest("case1", IncomingFile("new.txt", b"new"))

    clock.now = NOW + timedelta(days=30)
    purged = service.purge_expired()
    assert [r.path for r in purged] == [old.storage_path]
    assert service.repository.get(new.document_id).purged is False
    assert service.purge_expired() == []


def test_functional_ingest_and_from_settings(tmp_path: Path) -> None:
    repo = InMemoryDocumentRepository()
    result = ingest(
        "case1",
        IncomingFile("notes.md", b"# Notes"),
        storage=LocalStorage(tmp_path),
        repository=repo,
        retention_days=7,
        clock=lambda: NOW,
    )
    assert result.delete_after == NOW + timedelta(days=7)
    assert repo.get(result.document_id) is not None

    settings = Settings(_env_file=None, gcs_bucket="", upload_retention_days=14)
    svc = IngestionService.from_settings(settings, repo, storage=LocalStorage(tmp_path))
    assert svc.retention_days == 14
    assert svc.max_upload_bytes == 25 * 1024 * 1024
