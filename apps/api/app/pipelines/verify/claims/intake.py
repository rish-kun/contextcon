"""Claim intake (CP-20): uploaded seller documents and typed claims become claims.

Upload (in the request):
    `IngestionService` validates size and type, extracts text per page, regex-redacts
    it and stores the original under `cases/<case>/<doc>/<filename>` (GCS when
    `GCS_BUCKET` is set, local disk otherwise). This module then writes the
    `documents` row and one `extracted_texts` row per page, each with `delete_after`.

Extraction (a run step, `verify.claims.extract`):
    LLM PII pass over the regex-redacted pages, then `extract_claims` (quotes checked
    verbatim), then components named per `COMPONENT_RULES`. Each claim keeps the
    seller's assertion, category, components, quote and page, and carries the
    document's `delete_after`. A document without a text layer yields one claim per
    affected document marked `not_checked`, with the reason.

Typed claims (in the request):
    PII regex, `extract_claims` on the single sentence for the category, components
    as above, quote = the sentence itself, origin `typed`.

Every claim then gets a `verify.checks.claim:<id>` step (CP-21).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ClaimOrigin, RunKind
from app.db.models import Case, Claim, Document, ExtractedText, Run, Step
from app.documents import IncomingFile, IngestionService, IngestResult
from app.documents.extract import NO_TEXT_LAYER_REASON
from app.documents.redact import merge_counts
from app.documents.repository import DocumentRecord
from app.documents.storage import DocumentStorage, compute_delete_after
from app.domain.enums import NotCheckedReason
from app.domain.types import Claim as DomainClaim
from app.domain.types import ClaimCheck
from app.extraction import PageText, extract_claims, redact_document
from app.extraction.llm import LlmOutputError, StructuredLlm
from app.extraction.pii import regex_redact, regex_redact_fn
from app.jobs import StepSpec, append_steps, create_run
from app.jobs.activity import doc_kind
from app.pipelines.verify.claims.components import (
    ClaimToNormalise,
    NormalisedComponents,
    normalise_components,
    to_jsonb,
)
from app.rules import decide_claim_status

EXTRACT_HANDLER = "verify.claims.extract"
CHECK_HANDLER = "verify.checks.claim"
EXTRACT_PREFIX = "claims.extract:"
CHECK_PREFIX = "checks.claim:"
OWN_HANDLERS = frozenset({EXTRACT_HANDLER, CHECK_HANDLER})
# Steps that run after the checks (they wait for them), so a check never defers
# behind them: `evaluate.assess` and the request list built from its version.
DOWNSTREAM_HANDLERS = frozenset({"evaluate.assess", "act.request_list"})


class _CaptureRepository:
    """`DocumentRepository` for one ingest call: keeps the record so the caller can
    write it to Postgres (the service API is sync, the database is async)."""

    def __init__(self) -> None:
        self.record: DocumentRecord | None = None

    def add(self, record: DocumentRecord) -> None:
        self.record = record

    def get(self, document_id: str) -> DocumentRecord | None:
        return self.record if self.record and self.record.id == document_id else None

    def list_for_case(self, case_id: str) -> list[DocumentRecord]:
        return [self.record] if self.record and self.record.case_id == case_id else []

    def list_expired(self, now: datetime) -> list[DocumentRecord]:
        return []

    def mark_purged(self, document_id: str, at: datetime) -> None:
        return None


@dataclass
class _PageLogRedactor:
    """The regex redactor, keeping each page's counts (the service only sums them)."""

    logs: list[dict[str, int]] = field(default_factory=list)

    def __call__(self, text: str) -> tuple[str, dict[str, int]]:
        redacted, log = regex_redact_fn(text)
        self.logs.append(log)
        return redacted, log


@dataclass(frozen=True)
class StoredUpload:
    document: Document
    result: IngestResult


async def store_upload(
    session: AsyncSession,
    *,
    case: Case,
    file: IncomingFile,
    kind: str,
    storage: DocumentStorage,
    retention_days: int,
    max_upload_mb: int,
    uploaded_by: uuid.UUID | None = None,
    clock: Callable[[], datetime] | None = None,
) -> StoredUpload:
    """Validate, extract, regex-redact and store one upload; write its rows (flushes).

    Raises `UploadRejected` (with an HTTP status) for size, type or parse problems.
    """
    capture = _CaptureRepository()
    redactor = _PageLogRedactor()
    service = IngestionService(
        storage=storage,
        repository=capture,
        redactor=redactor,
        retention_days=retention_days,
        max_upload_mb=max_upload_mb,
        clock=clock,
    )
    result = await asyncio.to_thread(service.ingest, str(case.id), file)
    try:
        document = Document(
            id=uuid.UUID(hex=result.document_id),
            case_id=case.id,
            kind=kind,
            filename=result.filename,
            mime=result.mime,
            gcs_path=result.storage_path,
            size_bytes=capture.record.size_bytes if capture.record else len(file.data),
            sha256=capture.record.sha256 if capture.record else None,
            pages=capture.record.page_count if capture.record else None,
            uploaded_by=uploaded_by,
            delete_after=result.delete_after,
        )
        session.add(document)
        for page, log in zip(result.pages, redactor.logs, strict=False):
            if not page.text.strip():
                continue
            session.add(
                ExtractedText(
                    document_id=document.id,
                    case_id=case.id,
                    page=page.page,
                    text=page.text,
                    redaction_counts=log,
                    delete_after=result.delete_after,
                )
            )
        await session.flush()
    except BaseException:
        await asyncio.to_thread(storage.delete, result.storage_path)
        raise
    return StoredUpload(document=document, result=result)


# --- Claims from a document ---------------------------------------------------


async def _document_pages(session: AsyncSession, document_id: uuid.UUID) -> list[ExtractedText]:
    rows = await session.execute(
        select(ExtractedText)
        .where(ExtractedText.document_id == document_id)
        .order_by(ExtractedText.page.nulls_first(), ExtractedText.created_at)
    )
    return list(rows.scalars())


def _not_checked_claim_text(filename: str, pages: list[int] | None) -> str:
    if pages:
        listed = ", ".join(str(p) for p in pages)
        return f"Claims on pages {listed} of {filename} (no text layer)"
    return f"Claims in {filename} (no text layer)"


async def _unreadable_claim(
    session: AsyncSession,
    *,
    document: Document,
    status: str,
    reason: str,
    pages: list[int] | None,
    run_id: uuid.UUID | None,
    step_id: uuid.UUID | None,
) -> tuple[Claim, dict[str, Any]]:
    """A ledger row for text that could not be read, checked as `not_checked`."""
    from app.pipelines.verify.checks.persist import persist_outcome

    claim = Claim(
        case_id=document.case_id,
        original_text=_not_checked_claim_text(document.filename, pages),
        origin=ClaimOrigin.DECK,
        document_id=document.id,
        page=pages[0] if pages else None,
        quote=None,
        category="other",
        components=to_jsonb([], intake={"status": status, "reason": reason, "pages": pages}),
        delete_after=document.delete_after,
    )
    session.add(claim)
    await session.flush()
    check = ClaimCheck(
        claim=DomainClaim(
            id=str(claim.id), text=claim.original_text, category="other", components=[]
        ),
        ran=False,
        not_run_reason=NotCheckedReason.SOURCE_UNAVAILABLE,
        not_run_detail=reason.rstrip("."),
    )
    outcome = decide_claim_status(check)
    meta = await persist_outcome(
        session, claim=claim, check=check, outcome=outcome, run_id=run_id, step_id=step_id
    )
    return claim, meta


@dataclass
class DocumentIntake:
    claims: list[Claim]
    checked: dict[str, dict[str, Any]]  # claim id -> persisted check metadata
    dropped: int = 0
    redaction_counts: dict[str, int] = field(default_factory=dict)


async def extract_document_claims(
    session: AsyncSession,
    *,
    document: Document,
    llm: StructuredLlm,
    text_status: str = "ok",
    text_reason: str | None = None,
    pages_without_text: list[int] | None = None,
    run_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
) -> DocumentIntake:
    """Turn one stored document into claims (flushes, does not commit)."""
    checked: dict[str, dict[str, Any]] = {}
    if text_status != "ok":
        reason = text_reason or NO_TEXT_LAYER_REASON
        claim, meta = await _unreadable_claim(
            session,
            document=document,
            status=text_status,
            reason=reason,
            pages=None,
            run_id=run_id,
            step_id=step_id,
        )
        checked[str(claim.id)] = meta
        return DocumentIntake(claims=[claim], checked=checked)

    rows = await _document_pages(session, document.id)
    pages = [PageText(page=r.page, text=r.text) for r in rows]
    redaction = await redact_document(pages, llm)
    for row, page in zip(rows, redaction.pages, strict=True):
        if page.text != row.text:
            row.text = page.text  # the stored text is the fully redacted text
    # LLM-pass counts are per document; they are kept on the first page's row.
    llm_kinds = {k: v for k, v in redaction.counts.items() if k.startswith("llm:")}
    if llm_kinds and rows:
        rows[0].redaction_counts = merge_counts(rows[0].redaction_counts or {}, llm_kinds)

    extraction = await extract_claims(llm, redaction.pages, document_label=document.filename)
    normalised = await _normalise(
        llm,
        [
            ClaimToNormalise(text=c.text, category=c.category, raw_components=c.components)
            for c in extraction.claims
        ],
    )
    claims: list[Claim] = []
    for draft, comps in zip(extraction.claims, normalised, strict=True):
        claim = Claim(
            case_id=document.case_id,
            original_text=draft.text,
            origin=ClaimOrigin.DECK,
            document_id=document.id,
            page=draft.page,
            quote=draft.quote,
            category=draft.category,
            components=to_jsonb(comps.components, raw=draft.components),
            delete_after=document.delete_after,
        )
        session.add(claim)
        claims.append(claim)
    await session.flush()

    if pages_without_text:
        claim, meta = await _unreadable_claim(
            session,
            document=document,
            status="no_text_layer",
            reason=NO_TEXT_LAYER_REASON,
            pages=pages_without_text,
            run_id=run_id,
            step_id=step_id,
        )
        claims.append(claim)
        checked[str(claim.id)] = meta
    return DocumentIntake(
        claims=claims,
        checked=checked,
        dropped=len(extraction.dropped),
        redaction_counts=redaction.counts,
    )


async def _normalise(
    llm: StructuredLlm | None, items: list[ClaimToNormalise]
) -> list[NormalisedComponents]:
    try:
        return await normalise_components(llm, items)
    except (LlmOutputError, RuntimeError):
        return await normalise_components(None, items)


# --- Typed claims ---------------------------------------------------------------


async def add_typed_claim(
    session: AsyncSession,
    *,
    case: Case,
    text: str,
    llm: StructuredLlm,
    retention_days: int,
    created_by: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Claim:
    """Store a claim typed by an analyst (flushes). The LLM gives category and parts."""
    sentence = regex_redact(" ".join(text.split())).text
    extraction = await extract_claims(llm, sentence, document_label="typed claim")
    category = extraction.claims[0].category if extraction.claims else "other"
    raw: dict[str, str] = {}
    for c in extraction.claims:
        for k, v in c.components.items():
            raw.setdefault(k, v)
    [comps] = await _normalise(
        llm, [ClaimToNormalise(text=sentence, category=category, raw_components=raw)]
    )
    claim = Claim(
        case_id=case.id,
        original_text=sentence,
        origin=ClaimOrigin.TYPED,
        quote=sentence,
        page=None,
        category=category,
        components=to_jsonb(comps.components, raw=raw),
        created_by=created_by,
        delete_after=compute_delete_after(now or datetime.now(UTC), retention_days),
    )
    session.add(claim)
    await session.flush()
    return claim


# --- Scheduling -------------------------------------------------------------------


async def verify_run_for_case(
    session: AsyncSession, case: Case, *, created_by: uuid.UUID | None = None
) -> Run:
    """The case's latest verify run (reopened by `append_steps` if finished), or a new one."""
    run = (
        await session.execute(
            select(Run)
            .where(Run.case_id == case.id, Run.kind == RunKind.VERIFY)
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is not None:
        return run
    return await create_run(
        session,
        workspace_id=case.workspace_id,
        kind=RunKind.VERIFY,
        case_id=case.id,
        steps=[],
        created_by=created_by,
    )


async def _run_steps(session: AsyncSession, run_id: uuid.UUID) -> list[Step]:
    rows = await session.execute(select(Step).where(Step.run_id == run_id).order_by(Step.position))
    return list(rows.scalars())


async def schedule_document_extraction(
    session: AsyncSession, *, case: Case, stored: StoredUpload, created_by: uuid.UUID | None = None
) -> Run:
    run = await verify_run_for_case(session, case, created_by=created_by)
    result = stored.result
    await append_steps(
        session,
        run.id,
        [
            StepSpec(
                key=f"{EXTRACT_PREFIX}{stored.document.id}",
                handler=EXTRACT_HANDLER,
                label=f"Read claims from the uploaded {doc_kind(stored.document.file_kind)}",
                input={
                    "document_id": str(stored.document.id),
                    "text_status": result.text_status,
                    "text_reason": result.text_status_reason,
                    "pages_without_text": list(result.pages_without_text),
                },
                uses_budget=False,
            )
        ],
    )
    return run


def check_step_key(claim_id: uuid.UUID | str) -> str:
    return f"{CHECK_PREFIX}{claim_id}"


async def schedule_claim_checks(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    claims: list[Claim],
    after: list[str] | None = None,
    document_ids: list[uuid.UUID | str] | None = None,
    evaluate: bool = True,
) -> list[Step]:
    """Append one check step per claim to a run (flushes), then the closing
    `evaluate.assess` → `act.request_list` (`app.pipelines.verify.tail`).

    The assessment step (spec: "evaluate.assess runs last in verify and recheck runs")
    waits for every check and tolerates failed ones, so every batch of new claims ends
    in an assessment version and a request list. A batch added while that step is still
    pending joins it instead of adding another. `document_ids` are the uploads that
    caused the batch; they are recorded on the new version as its trigger documents.

    Each check waits for the run's other steps that exist now (identity, profile,
    registry, people from CP-19, document extraction) and for the previous check, so
    checks run one at a time and share cached provider responses instead of paying
    twice. They tolerate failed dependencies (a failed profile step becomes
    "source unavailable" in the ledger) and do their own budget accounting
    (`uses_budget=False`), so every claim always gets a ledger row.
    """
    existing = await _run_steps(session, run_id)
    used = {s.key for s in existing}
    # Never the closing evaluate / request list: they wait for the checks, not after.
    prior = [
        s.key
        for s in existing
        if s.handler != CHECK_HANDLER and s.handler not in DOWNSTREAM_HANDLERS
    ]
    last_check = next((s.key for s in reversed(existing) if s.handler == CHECK_HANDLER), None)
    specs: list[StepSpec] = []
    for claim in claims:
        key = check_step_key(claim.id)
        n = 1
        while key in used:  # a re-check (e.g. after an identity pick) gets a new step
            n += 1
            key = f"{check_step_key(claim.id)}@{n}"
        used.add(key)
        deps = [*prior, *(after or [])]
        if last_check:
            deps.append(last_check)
        specs.append(
            StepSpec(
                key=key,
                handler=CHECK_HANDLER,
                label=f"Check claim: {claim.category.replace('_', ' ')}",
                input={"claim_id": str(claim.id)},
                depends_on=list(dict.fromkeys(d for d in deps if d != key)),
                uses_budget=False,
                tolerate_failed_deps=True,
            )
        )
        last_check = key
    created = await append_steps(session, run_id, specs)
    if evaluate and created:
        # Imported here: the evaluate package imports the memo builders, which import
        # the claim ledger from this package.
        from app.pipelines.verify.tail import ensure_assessment_tail

        created += await ensure_assessment_tail(
            session, run_id=run_id, document_ids=document_ids or []
        )
    return created


async def schedule_case_checks(
    session: AsyncSession, *, case: Case, run_id: uuid.UUID
) -> list[Step]:
    """Re-check every readable claim of the case in `run_id` (flushes).

    Call after something changes what the checks can see, such as a manual identity
    pick or a fresh verify run; the new rows supersede the old ones in the ledger.
    Claims whose text could not be read are left as they are.
    """
    rows = await session.execute(
        select(Claim).where(Claim.case_id == case.id).order_by(Claim.created_at, Claim.id)
    )
    claims = [c for c in rows.scalars() if not (c.components or {}).get("intake")]
    if not claims:
        return []
    return await schedule_claim_checks(session, run_id=run_id, claims=claims)
