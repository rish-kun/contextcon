"""Document upload (CP-20) and signed download URLs. Recheck on seller responses: CP-24.

A `seller_response` names the request items it answers (`answers_request_item_ids`,
checked against the case's request lists, 422 otherwise). The links are stored and a
`recheck` run starts: claims from the new document, re-checks of the claims behind
the answered items, a new assessment version naming the upload, a new request list.

The upload body is declared in OpenAPI by hand and parsed with `await request.form()`.
An upload is validated (size, then type by extension and content), its text extracted
and regex-redacted, and the original stored privately under
`cases/<case>/<document>/<filename>` with a retention date. Claim extraction runs as a
step of the case's verify run, and each claim then gets its own check step.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from starlette.datastructures import UploadFile

from app.api import fixtures
from app.api._base import fixtures_enabled, make_router, not_found
from app.api.schemas.documents import DocumentKind, DocumentOut, DocumentUrlOut
from app.auth.deps import AuthorizedCaseId, CurrentUser, load_case, parse_id
from app.db import repo
from app.db.session import get_sessionmaker
from app.documents import DocumentStorage, IncomingFile, UploadRejected, storage_from_settings
from app.documents.storage import DEFAULT_URL_TTL
from app.documents.validation import DEFAULT_MAX_UPLOAD_MB
from app.jobs import events
from app.pipelines.verify.claims.intake import schedule_document_extraction, store_upload
from app.pipelines.verify.claims.recheck import (
    UnknownRequestItems,
    answered_items,
    link_answers,
    schedule_recheck,
)
from app.settings import get_settings

router = make_router(tags=["documents"])

# Multipart framing on top of the file itself.
_MULTIPART_OVERHEAD = 1024 * 1024

UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file", "kind"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "PDF, PPTX or DOCX, at most MAX_UPLOAD_MB (25).",
                        },
                        "kind": {"type": "string", "enum": [k.value for k in DocumentKind]},
                        "answers_request_item_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Request items this seller response answers.",
                        },
                    },
                }
            }
        },
    }
}


def document_storage() -> DocumentStorage:
    """GCS when `GCS_BUCKET` is set, local disk otherwise."""
    return storage_from_settings(get_settings())


def max_upload_mb() -> int:
    return int(getattr(get_settings(), "max_upload_mb", DEFAULT_MAX_UPLOAD_MB))


async def _read_upload(request: Request, limit: int) -> tuple[UploadFile, str, list[str]]:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + _MULTIPART_OVERHEAD:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than {limit // 2**20} MB."
        )
    try:
        form = await request.form(max_files=1, max_fields=50)
    except Exception as exc:  # malformed multipart, too many parts
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Send the file as multipart form data."
        ) from exc
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A file is required.")
    kind = form.get("kind") or DocumentKind.seller_deck.value
    if not isinstance(kind, str) or kind not in DocumentKind.__members__:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown document kind.")
    answers = [
        a for a in form.getlist("answers_request_item_ids") if isinstance(a, str) and a.strip()
    ]
    return upload, kind, answers


@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=UPLOAD_BODY,
    responses={
        413: {"description": "File larger than MAX_UPLOAD_MB."},
        415: {"description": "Unsupported file type."},
    },
)
async def upload_document(
    case_id: AuthorizedCaseId,
    request: Request,
    user: CurrentUser,
    storage: Annotated[DocumentStorage, Depends(document_storage)],
    limit_mb: Annotated[int, Depends(max_upload_mb)],
) -> DocumentOut:
    """Upload a seller document. A `seller_response` starts a recheck run."""
    if fixtures_enabled():  # `authorize_case` has already checked the fixture case id
        return fixtures.uploaded_document(DocumentKind.seller_response)

    limit = limit_mb * 1024 * 1024
    upload, kind, answers = await _read_upload(request, limit)
    try:
        data = await upload.read(limit + 1)
    finally:
        await upload.close()
    settings = get_settings()
    now = datetime.now(UTC)
    async with get_sessionmaker()() as db:
        case = await load_case(db, user.workspace_id, case_id)
        answered: list = []
        if answers:
            if kind != DocumentKind.seller_response.value:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Only a seller response answers request items.",
                )
            try:
                answered = await answered_items(db, case, answers)
            except UnknownRequestItems as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        try:
            stored = await store_upload(
                db,
                case=case,
                file=IncomingFile(upload.filename, data, upload.content_type),
                kind=kind,
                storage=storage,
                retention_days=settings.upload_retention_days,
                max_upload_mb=limit_mb,
                uploaded_by=user.id,
                clock=lambda: now,
            )
        except UploadRejected as exc:
            raise HTTPException(exc.status_code, exc.reason) from None
        if kind == DocumentKind.seller_response.value:  # CP-24: recheck the case
            await link_answers(db, stored.document.id, answered)
            run = await schedule_recheck(
                db, case=case, stored=stored, answered=answered, created_by=user.id
            )
        else:
            run = await schedule_document_extraction(
                db, case=case, stored=stored, created_by=user.id
            )
        await db.commit()
        run_out: Any = await events.load_run_out(db, user.workspace_id, run.id)
        doc = stored.document
        return DocumentOut(
            id=str(doc.id),
            case_id=str(case.id),
            kind=DocumentKind(kind),
            filename=doc.filename,
            mime=doc.mime,
            size_bytes=doc.size_bytes or len(data),
            pages=doc.pages,
            uploaded_at=now,
            uploaded_by_name=user.display_name,
            delete_after=doc.delete_after,
            purged=False,
            redaction_counts=stored.result.redaction_log,
            answers_request_item_ids=[str(i) for i in answered],
            claims_extracted=0,
            run=run_out,
        )


@router.get("/documents/{document_id}/url", response_model=DocumentUrlOut)
async def get_document_url(
    document_id: str,
    user: CurrentUser,
    storage: Annotated[DocumentStorage, Depends(document_storage)],
) -> DocumentUrlOut:
    """A short-lived, case-scoped signed URL for the original file."""
    if fixtures_enabled():
        if document_id not in {d.id for d in fixtures.documents()}:
            not_found("Document")
        return fixtures.document_url(document_id)
    doc_id = parse_id(document_id, "Document")
    async with get_sessionmaker()() as db:
        try:
            doc = await repo.get_document(db, user.workspace_id, doc_id)
        except repo.NotFound:
            not_found("Document")
    if doc.deleted_at is not None or not doc.gcs_path.startswith(f"cases/{doc.case_id}/"):
        not_found("Document")
    expires_at = datetime.now(UTC) + DEFAULT_URL_TTL
    url = storage.signed_url(doc.gcs_path, DEFAULT_URL_TTL)
    return DocumentUrlOut(url=url, expires_at=expires_at)
