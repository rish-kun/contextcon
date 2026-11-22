"""Document ingestion: validate → extract → redact → store → persist.

Only redacted text leaves this module. The original file goes to private storage
under ``cases/<case_id>/<doc_id>/<filename>`` and is deleted on schedule
(``delete_after = upload time + UPLOAD_RETENTION_DAYS``).

Extraction runs in a sandboxed subprocess (``app.documents.sandbox``) with page, output,
time and memory limits. The service works with a sync repository (``ingest``,
``download_url``, ``delete``, ``purge_expired``) or with an async one such as
``PostgresDocumentRepository`` (the ``*_async`` methods, which also accept a sync
repository).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

from app.documents.extract import (
    DEFAULT_LIMITS,
    ExtractionError,
    ExtractionLimits,
    ExtractionResult,
    ExtractionStatus,
    PageText,
    extract_text,
)
from app.documents.redact import RedactorFn, merge_counts, regex_redactor
from app.documents.repository import (
    AsyncDocumentRepository,
    DocumentRecord,
    DocumentRepository,
    as_async,
    is_async_repository,
)
from app.documents.sandbox import extract_text_isolated
from app.documents.storage import (
    DEFAULT_URL_TTL,
    DeletionRecord,
    DocumentStorage,
    case_prefix,
    compute_delete_after,
    object_path,
    storage_from_settings,
)
from app.documents.validation import (
    DEFAULT_MAX_UPLOAD_MB,
    FileKind,
    UploadRejected,
    validate_upload,
)

log = logging.getLogger(__name__)

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


class PurgeResult(list[DeletionRecord]):
    """Deletions done by a purge sweep. ``failed`` holds the ids of documents whose
    deletion raised; they stay unpurged and the next sweep tries them again."""

    def __init__(self) -> None:
        super().__init__()
        self.failed: list[str] = []


def _storage_detail(deletion: DeletionRecord) -> dict[str, Any]:
    return {"backend": deletion.backend, "existed": deletion.existed}


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
        repository: DocumentRepository | AsyncDocumentRepository,
        redactor: RedactorFn = regex_redactor,
        retention_days: int = 30,
        max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB,
        clock: Callable[[], datetime] | None = None,
        limits: ExtractionLimits = DEFAULT_LIMITS,
        isolate_extraction: bool = True,
    ) -> None:
        if retention_days <= 0:
            raise ValueError("retention_days must be positive")
        self.storage = storage
        self.repository = repository
        self.redactor = redactor
        self.retention_days = retention_days
        self.max_upload_bytes = max_upload_mb * 1024 * 1024
        self.limits = limits
        self.isolate_extraction = isolate_extraction
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        repository: DocumentRepository | AsyncDocumentRepository,
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

    # --- ingestion --------------------------------------------------------------------

    def ingest(
        self,
        case_id: str,
        file: IncomingFile,
        *,
        category: str = "seller_deck",
        uploaded_by: str | None = None,
    ) -> IngestResult:
        repo = self._sync_repo()
        record, result = self._prepare(case_id, file, category, uploaded_by)
        try:
            repo.add(record)
        except Exception:
            self.storage.delete(record.storage_path)  # don't leave an orphaned upload behind
            raise
        return result

    async def ingest_async(
        self,
        case_id: str,
        file: IncomingFile,
        *,
        category: str = "seller_deck",
        uploaded_by: str | None = None,
    ) -> IngestResult:
        """`ingest` for async repositories. Parsing and storage run off the event loop."""
        record, result = await asyncio.to_thread(
            self._prepare, case_id, file, category, uploaded_by
        )
        try:
            await as_async(self.repository).add(record)
        except Exception:
            await asyncio.to_thread(self.storage.delete, record.storage_path)
            raise
        return result

    def _extract(self, data: bytes, kind: FileKind) -> ExtractionResult:
        if self.isolate_extraction:
            return extract_text_isolated(data, kind, limits=self.limits)
        return extract_text(data, kind, limits=self.limits)

    def _prepare(
        self, case_id: str, file: IncomingFile, category: str, uploaded_by: str | None
    ) -> tuple[DocumentRecord, IngestResult]:
        upload = validate_upload(file.filename, file.data, max_bytes=self.max_upload_bytes)
        try:
            extraction = self._extract(file.data, upload.kind)
        except ExtractionError as exc:
            raise UploadRejected(str(exc), 422) from exc

        redacted: list[PageText] = []
        logs: list[dict[str, int]] = []
        for page in extraction.pages:
            text, log_ = self.redactor(page.text)
            logs.append(log_)
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
            category=category,
            uploaded_by=uploaded_by,
        )
        result = IngestResult(
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
        return record, result

    # --- downloads ----------------------------------------------------------------------

    def download_url(
        self,
        document_id: str,
        *,
        caller: Any,
        authorize: CaseAuthorizer,
        ttl: timedelta = DEFAULT_URL_TTL,
    ) -> str:
        """Short-lived signed URL, issued only if ``authorize(caller, case_id)`` is True."""
        record = self._sync_repo().get(document_id)
        return self._sign(record, document_id, caller, authorize, ttl)

    async def download_url_async(
        self,
        document_id: str,
        *,
        caller: Any,
        authorize: CaseAuthorizer,
        ttl: timedelta = DEFAULT_URL_TTL,
    ) -> str:
        record = await as_async(self.repository).get(document_id)
        return await asyncio.to_thread(self._sign, record, document_id, caller, authorize, ttl)

    def _sign(
        self,
        record: DocumentRecord | None,
        document_id: str,
        caller: Any,
        authorize: CaseAuthorizer,
        ttl: timedelta,
    ) -> str:
        if record is None or record.purged:
            raise DocumentNotFound(document_id)
        # Past its retention date the file is as good as deleted, even before the sweep.
        remaining = record.delete_after - self._clock()
        if remaining < timedelta(seconds=1):
            raise DocumentNotFound(document_id)
        if caller is None or not authorize(caller, record.case_id):
            raise DocumentAccessDenied(document_id)
        if not record.storage_path.startswith(case_prefix(record.case_id)):
            raise DocumentAccessDenied(document_id)
        # A link never outlives the document's retention date.
        return self.storage.signed_url(record.storage_path, min(ttl, remaining))

    # --- deletion and retention ---------------------------------------------------------

    def delete(self, document_id: str) -> DeletionRecord:
        repo = self._sync_repo()
        record = repo.get(document_id)
        if record is None:
            raise DocumentNotFound(document_id)
        deletion = self.storage.delete(record.storage_path)
        repo.mark_purged(document_id, deletion.deleted_at, storage=_storage_detail(deletion))
        return deletion

    async def delete_async(self, document_id: str) -> DeletionRecord:
        repo = as_async(self.repository)
        record = await repo.get(document_id)
        if record is None:
            raise DocumentNotFound(document_id)
        deletion = await asyncio.to_thread(self.storage.delete, record.storage_path)
        await repo.mark_purged(document_id, deletion.deleted_at, storage=_storage_detail(deletion))
        return deletion

    def purge_expired(self) -> PurgeResult:
        """Delete every document past ``delete_after``. Safe to run on a schedule.

        One failing document never stops the sweep: it is logged, left unpurged and
        listed in ``result.failed`` so the next run retries it."""
        result = PurgeResult()
        for record in self._sync_repo().list_expired(self._clock()):
            try:
                result.append(self.delete(record.id))
            except Exception:  # noqa: BLE001 - retried on the next sweep
                log.exception("purge: could not delete document %s", record.id)
                result.failed.append(record.id)
        return result

    async def purge_expired_async(self) -> PurgeResult:
        result = PurgeResult()
        for record in await as_async(self.repository).list_expired(self._clock()):
            try:
                result.append(await self.delete_async(record.id))
            except Exception:  # noqa: BLE001 - retried on the next sweep
                log.exception("purge: could not delete document %s", record.id)
                result.failed.append(record.id)
        return result

    def _sync_repo(self) -> DocumentRepository:
        if is_async_repository(self.repository):
            raise TypeError("this repository is async; use the *_async methods")
        return self.repository  # type: ignore[return-value]


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
