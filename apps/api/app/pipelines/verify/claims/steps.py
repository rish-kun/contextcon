"""Run step `verify.claims.extract`: one uploaded document → claims → check steps."""

from __future__ import annotations

import uuid
from typing import Any

import app.pipelines.verify.checks.steps  # noqa: F401  (registers verify.checks.claim)
from app.db.models import Document
from app.jobs import StepContext, step_handler
from app.pipelines.verify.checks.clients import client_factory, close_quietly
from app.pipelines.verify.claims.intake import (
    EXTRACT_HANDLER,
    extract_document_claims,
    schedule_claim_checks,
)


@step_handler(EXTRACT_HANDLER)
async def extract_claims_step(ctx: StepContext) -> dict[str, Any]:
    document = await ctx.session.get(Document, uuid.UUID(ctx.input["document_id"]))
    if document is None or document.case_id != ctx.run.case_id:
        raise LookupError("document not found for this case")
    await ctx.set_detail(f"Reading {document.filename}")
    llm = client_factory().llm(ctx, delete_after=document.delete_after)
    try:
        intake = await extract_document_claims(
            ctx.session,
            document=document,
            llm=llm,
            text_status=ctx.input.get("text_status") or "ok",
            text_reason=ctx.input.get("text_reason"),
            pages_without_text=ctx.input.get("pages_without_text") or None,
            run_id=ctx.run.id,
            step_id=ctx.step_id,
        )
    finally:
        await close_quietly(llm)
    to_check = [c for c in intake.claims if str(c.id) not in intake.checked]
    if to_check:
        await schedule_claim_checks(ctx.session, run_id=ctx.run.id, claims=to_check)
    readable = len(intake.claims) - len(intake.checked)
    ctx.result = f"{readable} claim{'s' if readable != 1 else ''} read from {document.filename}"
    if intake.checked:
        ctx.result += "; unreadable text marked not checked"
    ctx.log(f"dropped {intake.dropped} unquoted items; redactions {intake.redaction_counts}")
    return {
        "document_id": str(document.id),
        "claim_ids": [str(c.id) for c in intake.claims],
        "checks": intake.checked,
        "dropped": intake.dropped,
        "redaction_counts": intake.redaction_counts,
    }
