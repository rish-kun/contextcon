"""Persistence seam for documents.

Two shapes of the same interface:

- ``DocumentRepository`` (sync), with ``InMemoryDocumentRepository`` for dev and tests;
- ``AsyncDocumentRepository`` (async), implemented over Postgres by
  ``app.documents.pg_repository.PostgresDocumentRepository`` (the ``documents``,
  ``extracted_texts`` and ``deletion_records`` tables).

``as_async(repo)`` turns a sync repository into an async one, so the ingestion
service's async methods accept either.
"""

from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol

from app.documents.extract import ExtractionStatus, PageText


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    case_id: str
    filename: str  # sanitized
    storage_path: str
    mime: str
    kind: str  # FileKind value
    size_bytes: int
    sha256: str
    created_at: datetime
    delete_after: datetime
    pages: list[PageText]  # redacted text only; raw text is never persisted
    text_status: ExtractionStatus
    text_status_reason: str | None
    redaction_counts: dict[str, int] = field(default_factory=dict)
    page_count: int | None = None
    purged: bool = False
    purged_at: datetime | None = None
    category: str = "seller_deck"  # what the uploader said it is (API DocumentKind)
    uploaded_by: str | None = None  # user id


class DocumentRepository(Protocol):
    def add(self, record: DocumentRecord) -> None: ...

    def get(self, document_id: str) -> DocumentRecord | None: ...

    def list_for_case(self, case_id: str) -> list[DocumentRecord]: ...

    def list_expired(self, now: datetime) -> list[DocumentRecord]: ...

    def mark_purged(
        self, document_id: str, at: datetime, *, storage: dict[str, Any] | None = None
    ) -> None:
        """Drop the stored text and flag the document purged; keep the metadata row.
        ``storage`` is what the storage backend reported for the deleted object."""
        ...


class AsyncDocumentRepository(Protocol):
    async def add(self, record: DocumentRecord) -> None: ...

    async def get(self, document_id: str) -> DocumentRecord | None: ...

    async def list_for_case(self, case_id: str) -> list[DocumentRecord]: ...

    async def list_expired(self, now: datetime) -> list[DocumentRecord]: ...

    async def mark_purged(
        self, document_id: str, at: datetime, *, storage: dict[str, Any] | None = None
    ) -> None: ...


def is_async_repository(repo: object) -> bool:
    return inspect.iscoroutinefunction(getattr(repo, "add", None))


class AsyncRepositoryAdapter:
    """Async face of a sync repository (the in-memory one is fast and thread-safe, so
    its methods are called inline)."""

    def __init__(self, inner: DocumentRepository) -> None:
        self.inner = inner

    async def add(self, record: DocumentRecord) -> None:
        self.inner.add(record)

    async def get(self, document_id: str) -> DocumentRecord | None:
        return self.inner.get(document_id)

    async def list_for_case(self, case_id: str) -> list[DocumentRecord]:
        return self.inner.list_for_case(case_id)

    async def list_expired(self, now: datetime) -> list[DocumentRecord]:
        return self.inner.list_expired(now)

    async def mark_purged(
        self, document_id: str, at: datetime, *, storage: dict[str, Any] | None = None
    ) -> None:
        self.inner.mark_purged(document_id, at, storage=storage)


def as_async(repo: DocumentRepository | AsyncDocumentRepository) -> AsyncDocumentRepository:
    if is_async_repository(repo):
        return repo  # type: ignore[return-value]
    return AsyncRepositoryAdapter(repo)  # type: ignore[arg-type]


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._rows: dict[str, DocumentRecord] = {}
        self._lock = threading.Lock()

    def add(self, record: DocumentRecord) -> None:
        with self._lock:
            if record.id in self._rows:
                raise KeyError(f"document {record.id} already exists")
            self._rows[record.id] = record

    def get(self, document_id: str) -> DocumentRecord | None:
        return self._rows.get(document_id)

    def list_for_case(self, case_id: str) -> list[DocumentRecord]:
        return sorted(
            (r for r in self._rows.values() if r.case_id == case_id), key=lambda r: r.created_at
        )

    def list_expired(self, now: datetime) -> list[DocumentRecord]:
        return [r for r in self._rows.values() if not r.purged and r.delete_after <= now]

    def mark_purged(
        self, document_id: str, at: datetime, *, storage: dict[str, Any] | None = None
    ) -> None:
        with self._lock:
            row = self._rows[document_id]
            self._rows[document_id] = replace(row, pages=[], purged=True, purged_at=at)
