"""Run step `verify.claims.extract`: one uploaded document → claims → check steps."""

from __future__ import annotations

import uuid
from typing import Any

import app.pipelines.verify.checks.steps  # noqa: F401  (registers verify.checks.claim)
from app.clients.activity import activity_topic
from app.db.enums import RunKind
from app.db.models import Document
from app.jobs import StepContext, step_handler
from app.jobs.activity import NoticeCode, Subject, doc_kind, document_step_result, render
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
    # Never the filename: the document kind in words (§2.10 of the live-run design).
    await ctx.set_detail(render("status.reading_document", doc_kind=doc_kind(document.file_kind)))
    llm = client_factory().llm(ctx, delete_after=document.delete_after)
    try:
        with activity_topic(purpose="claims", reading="document"):
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
    rechecked = 0
    if ctx.run.kind == RunKind.RECHECK and ctx.run.case_id is not None:
        # A seller response: the new claims and the claims behind the answered request
        # items are checked in one batch, then evaluate and the request list follow.
        from app.pipelines.verify.claims.recheck import plan_recheck

        rechecked = await plan_recheck(
            ctx.session,
            run_id=ctx.run.id,
            case_id=ctx.run.case_id,
            plan=ctx.input.get("recheck") or {},
            new_claims=to_check,
            document_id=document.id,
            after=ctx.key,
        )
    elif to_check:
        await schedule_claim_checks(
            ctx.session, run_id=ctx.run.id, claims=to_check, document_ids=[document.id]
        )
    if to_check:
        # Ids and categories only: the client already has the claim text.
        await ctx.activity.findings(
            lambda _batch: render("finding.claims_queued", n=len(to_check)),
            subject=Subject.CLAIM,
            items=[{"id": str(c.id), "stage": "queued", "category": c.category} for c in to_check],
            counts={"queued": len(to_check), "checking": 0, "settled": 0,
                    "not_checked": len(intake.checked)},
        )  # fmt: skip
    elif not intake.claims:
        await ctx.activity.notice(NoticeCode.NOTHING_TO_CHECK)
    readable = len(intake.claims) - len(intake.checked)
    # Counts and the document kind only, never the filename.
    ctx.result = document_step_result(
        readable, doc_kind(document.file_kind), unreadable=bool(intake.checked)
    )
    ctx.log(f"dropped {intake.dropped} unquoted items; redactions {intake.redaction_counts}")
    return {
        "document_id": str(document.id),
        "claim_ids": [str(c.id) for c in intake.claims],
        "checks": intake.checked,
        "dropped": intake.dropped,
        "redaction_counts": intake.redaction_counts,
        "rechecked": rechecked,
    }
