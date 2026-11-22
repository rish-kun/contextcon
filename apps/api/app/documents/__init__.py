"""Confidential document ingestion (PRD principle 8, spec §7).

Public API:

- ``IngestionService(...).ingest(case_id, IncomingFile)`` / ``ingest(...)`` →
  ``IngestResult{document_id, pages, redaction_log, delete_after, ...}``
- ``validate_upload``, ``sanitize_filename``, ``UploadRejected`` (carries an HTTP status)
- ``extract_text(data, kind)`` → ``ExtractionResult{pages, status, reason}``
- ``regex_redactor``, ``chain_redactors`` (plug an LLM redactor in after the regex pass)
- ``DocumentStorage`` with ``GCSStorage`` and ``LocalStorage``; ``storage_from_settings``
- ``DocumentRepository`` Protocol with ``InMemoryDocumentRepository``;
  ``AsyncDocumentRepository`` with ``as_async`` and, over Postgres,
  ``app.documents.pg_repository.PostgresDocumentRepository``
- ``ExtractionLimits`` and ``extract_text_isolated`` (sandboxed parsing)
"""

from app.documents.extract import (
    NO_TEXT_LAYER_REASON,
    ExtractionError,
    ExtractionLimits,
    ExtractionResult,
    PageText,
    extract_text,
)
from app.documents.redact import Redactor, RedactorFn, chain_redactors, regex_redactor
from app.documents.repository import (
    AsyncDocumentRepository,
    DocumentRecord,
    DocumentRepository,
    InMemoryDocumentRepository,
    as_async,
)
from app.documents.sandbox import extract_text_isolated
from app.documents.service import (
    CaseAuthorizer,
    DocumentAccessDenied,
    DocumentNotFound,
    IncomingFile,
    IngestionService,
    IngestResult,
    PurgeResult,
    ingest,
    read_limited,
)
from app.documents.storage import (
    DeletionRecord,
    DocumentStorage,
    GCSStorage,
    LocalStorage,
    StoredObject,
    compute_delete_after,
    object_path,
    storage_from_settings,
)
from app.documents.validation import (
    FileKind,
    UploadRejected,
    ValidatedUpload,
    sanitize_filename,
    validate_upload,
)

__all__ = [
    "NO_TEXT_LAYER_REASON",
    "AsyncDocumentRepository",
    "ExtractionLimits",
    "PurgeResult",
    "as_async",
    "extract_text_isolated",
    "CaseAuthorizer",
    "DeletionRecord",
    "DocumentAccessDenied",
    "DocumentNotFound",
    "DocumentRecord",
    "DocumentRepository",
    "DocumentStorage",
    "ExtractionError",
    "ExtractionResult",
    "FileKind",
    "GCSStorage",
    "InMemoryDocumentRepository",
    "IncomingFile",
    "IngestResult",
    "IngestionService",
    "LocalStorage",
    "PageText",
    "Redactor",
    "RedactorFn",
    "StoredObject",
    "UploadRejected",
    "ValidatedUpload",
    "chain_redactors",
    "compute_delete_after",
    "extract_text",
    "ingest",
    "object_path",
    "read_limited",
    "regex_redactor",
    "sanitize_filename",
    "storage_from_settings",
    "validate_upload",
]
