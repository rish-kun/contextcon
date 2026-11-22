"""Document upload and signed download URLs. Stubs until CP-20 (recheck: CP-24).

The upload body is declared in OpenAPI by hand instead of with `UploadFile`/`Form`
parameters, so this module does not need `python-multipart` at import time. CP-20 parses
it with `await request.form()` once CP-01 adds that dependency.
"""

from fastapi import Request, status

from app.api import fixtures
from app.api._base import fixture_or_501, make_router, not_found
from app.api.schemas.documents import DocumentKind, DocumentOut, DocumentUrlOut

router = make_router(tags=["documents"])

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
async def upload_document(case_id: str, request: Request) -> DocumentOut:
    """Upload a seller document. A `seller_response` starts a recheck run."""

    def build() -> DocumentOut:
        if fixtures.case_out(case_id) is None:
            not_found("Case")
        return fixtures.uploaded_document(DocumentKind.seller_response)

    return fixture_or_501("CP-20", build)


@router.get("/documents/{document_id}/url", response_model=DocumentUrlOut)
def get_document_url(document_id: str) -> DocumentUrlOut:
    """A short-lived, case-scoped signed URL for the original file."""

    def build() -> DocumentUrlOut:
        if document_id not in {d.id for d in fixtures.documents()}:
            not_found("Document")
        return fixtures.document_url(document_id)

    return fixture_or_501("CP-20", build)
