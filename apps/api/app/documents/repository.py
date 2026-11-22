"""Persistence seam for documents.

The Postgres layer (``app/db/``) is being written separately and was not on main
when this module was built, so ingestion talks to this small Protocol. The DB
agent can implement ``DocumentRepository`` over the ``documents`` table; the
in-memory version serves dev and tests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol

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


class DocumentRepository(Protocol):
    def add(self, record: DocumentRecord) -> None: ...

    def get(self, document_id: str) -> DocumentRecord | None: ...

    def list_for_case(self, case_id: str) -> list[DocumentRecord]: ...

    def list_expired(self, now: datetime) -> list[DocumentRecord]: ...

    def mark_purged(self, document_id: str, at: datetime) -> None:
        """Drop the stored text and flag the document purged; keep the metadata row."""
        ...


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

    def mark_purged(self, document_id: str, at: datetime) -> None:
        with self._lock:
            row = self._rows[document_id]
            self._rows[document_id] = replace(row, pages=[], purged=True, purged_at=at)
