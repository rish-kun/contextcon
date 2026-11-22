"""Document ingestion: validate → extract → redact → store → persist.

Only redacted text leaves this module. The original file goes to private storage
under ``cases/<case_id>/<doc_id>/<filename>`` and is deleted on schedule
(``delete_after = upload time + UPLOAD_RETENTION_DAYS``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

from app.documents.extract import (
    ExtractionError,
    ExtractionStatus,
    PageText,
    extract_text,
)
from app.documents.redact import RedactorFn, merge_counts, regex_redactor
from app.documents.repository import DocumentRecord, DocumentRepository
from app.documents.storage import (
    DEFAULT_URL_TTL,
    DeletionRecord,
    DocumentStorage,
    case_prefix,
    compute_delete_after,
    object_path,
    storage_from_settings,
)
from app.documents.validation import DEFAULT_MAX_UPLOAD_MB, UploadRejected, validate_upload

# authorize(caller, case_id) -> True only if the caller may read that case.
CaseAuthorizer = Callable[[Any, str], bool]


class DocumentNotFound(LookupError):
    pass


class DocumentAccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class IncomingFile:
    filename: str | None
    data: bytes
    content_type: str | None = None  # client-declared; informational only, never trusted


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    pages: list[PageText]  # redacted
    redaction_log: dict[str, int]  # kind -> spans replaced, summed over pages
    delete_after: datetime
    filename: str
    storage_path: str
    mime: str
    text_status: ExtractionStatus
    text_status_reason: str | None = None
    pages_without_text: list[int] = field(default_factory=list)

    def pages_as_dicts(self) -> list[dict[str, Any]]:
        return [p.as_dict() for p in self.pages]


def read_limited(stream: BinaryIO, max_bytes: int) -> bytes:
    """Read a stream but stop (413) as soon as it exceeds ``max_bytes``."""
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadRejected(f"File is larger than {max_bytes // (1024 * 1024)} MB.", 413)
    return data


class IngestionService:
    def __init__(
        self,
        *,
        storage: DocumentStorage,
        repository: DocumentRepository,
        redactor: RedactorFn = regex_redactor,
        retention_days: int = 30,
        max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if retention_days <= 0:
            raise ValueError("retention_days must be positive")
        self.storage = storage
        self.repository = repository
        self.redactor = redactor
        self.retention_days = retention_days
        self.max_upload_bytes = max_upload_mb * 1024 * 1024
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        repository: DocumentRepository,
        *,
        redactor: RedactorFn = regex_redactor,
        storage: DocumentStorage | None = None,
    ) -> IngestionService:
        return cls(
            storage=storage or storage_from_settings(settings),
            repository=repository,
            redactor=redactor,
            retention_days=settings.upload_retention_days,
            max_upload_mb=getattr(settings, "max_upload_mb", DEFAULT_MAX_UPLOAD_MB),
        )

    def ingest(self, case_id: str, file: IncomingFile) -> IngestResult:
        upload = validate_upload(file.filename, file.data, max_bytes=self.max_upload_bytes)
        try:
            extraction = extract_text(file.data, upload.kind)
        except ExtractionError as exc:
            raise UploadRejected(str(exc), 422) from exc

        redacted: list[PageText] = []
        logs: list[dict[str, int]] = []
        for page in extraction.pages:
            text, log = self.redactor(page.text)
            logs.append(log)
            redacted.append(
                PageText(
                    page=page.page,
                    text=text,
                    paragraph=page.paragraph,
                    has_text_layer=page.has_text_layer,
                )
            )
        redaction_log = merge_counts(*logs)

        now = self._clock()
        delete_after = compute_delete_after(now, self.retention_days)
        document_id = uuid.uuid4().hex
        path = object_path(case_id, document_id, upload.filename)
        stored = self.storage.put(path, file.data, upload.mime, delete_after)

        record = DocumentRecord(
            id=document_id,
            case_id=case_id,
            filename=upload.filename,
            storage_path=path,
            mime=upload.mime,
            kind=upload.kind.value,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            created_at=now,
            delete_after=delete_after,
            pages=redacted,
            text_status=extraction.status,
            text_status_reason=extraction.reason,
            redaction_counts=redaction_log,
            page_count=extraction.page_count,
        )
        try:
            self.repository.add(record)
        except Exception:
            self.storage.delete(path)  # don't leave an orphaned upload behind
            raise

        return IngestResult(
            document_id=document_id,
            pages=redacted,
            redaction_log=redaction_log,
            delete_after=delete_after,
            filename=upload.filename,
            storage_path=path,
            mime=upload.mime,
            text_status=extraction.status,
            text_status_reason=extraction.reason,
            pages_without_text=list(extraction.pages_without_text),
        )

    def _live_record(self, document_id: str) -> DocumentRecord:
        record = self.repository.get(document_id)
        if record is None or record.purged:
            raise DocumentNotFound(document_id)
        return record

    def download_url(
        self,
        document_id: str,
        *,
        caller: Any,
        authorize: CaseAuthorizer,
        ttl: timedelta = DEFAULT_URL_TTL,
    ) -> str:
        """Short-lived signed URL, issued only if ``authorize(caller, case_id)`` is True."""
        record = self._live_record(document_id)
        if caller is None or not authorize(caller, record.case_id):
            raise DocumentAccessDenied(document_id)
        if not record.storage_path.startswith(case_prefix(record.case_id)):
            raise DocumentAccessDenied(document_id)
        return self.storage.signed_url(record.storage_path, ttl)

    def delete(self, document_id: str) -> DeletionRecord:
        record = self.repository.get(document_id)
        if record is None:
            raise DocumentNotFound(document_id)
        deletion = self.storage.delete(record.storage_path)
        self.repository.mark_purged(document_id, deletion.deleted_at)
        return deletion

    def purge_expired(self) -> list[DeletionRecord]:
        """Delete every document past ``delete_after``. Safe to run on a schedule."""
        now = self._clock()
        return [self.delete(r.id) for r in self.repository.list_expired(now)]


def ingest(
    case_id: str,
    file: IncomingFile,
    *,
    storage: DocumentStorage,
    repository: DocumentRepository,
    redactor: RedactorFn = regex_redactor,
    retention_days: int = 30,
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB,
    clock: Callable[[], datetime] | None = None,
) -> IngestResult:
    """Functional form of ``IngestionService.ingest``."""
    service = IngestionService(
        storage=storage,
        repository=repository,
        redactor=redactor,
        retention_days=retention_days,
        max_upload_mb=max_upload_mb,
        clock=clock,
    )
    return service.ingest(case_id, file)
