"""The claim ledger: the `claims` section of `GET /cases/{id}` (`list[ClaimOut]`).

Each claim shows its current status (the newest `claim_checks` row), the evidence
that check looked at, and the full history. A claim with no check yet is shown as
`not_checked` ("the check has not run"), never as a clean result.

Per-check metadata that has no column of its own (why a check did not run,
evidence adequacy, the substantive result) is read from the output of the step
that wrote the check (`Step.output["checks"][<claim id>]`).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.claims import (
    ClaimCheckOut,
    ClaimOrigin,
    ClaimOut,
    NotCheckedReason,
    StatedInOut,
    SubstantiveResult,
)
from app.api.schemas.common import (
    ClaimCategory,
    ClaimStatus,
    EntityAttachment,
    EvidenceOut,
    SourceClass,
    SourceRef,
)
from app.db.models import (
    Case,
    Claim,
    ClaimCheck,
    ClaimCheckEvidence,
    Document,
    Evidence,
    Source,
    Step,
    User,
)
from app.pipelines.verify.checks.sources import READ_MARKER, reliability_of
from app.pipelines.verify.claims.components import intake_meta, public_components

NOT_RUN_YET = "Not checked yet: the check has not run."

_REASON_TO_API: dict[str, NotCheckedReason] = {
    "budget_exhausted": NotCheckedReason.budget_reached,
    "source_error": NotCheckedReason.step_failed,
    "source_unavailable": NotCheckedReason.source_unavailable,
    "no_source_in_scope": NotCheckedReason.source_unavailable,
    "identity_unresolved": NotCheckedReason.identity_unresolved,
}
_REASON_TEXT = re.compile(r"^Not checked: ([a-z ]+?)[ .(]")


def api_not_checked_reason(
    domain_value: str | None, reason_text: str = ""
) -> NotCheckedReason | None:
    if domain_value:
        return _REASON_TO_API.get(domain_value)
    m = _REASON_TEXT.match(reason_text or "")
    if m:
        return _REASON_TO_API.get(m.group(1).strip().replace(" ", "_"))
    return None


def api_source_class(source_class: str) -> SourceClass:
    """The contract's `SourceClass` equals the rules' `SourceReliability`."""
    return SourceClass(reliability_of(source_class).value)


def _normalised_text(claim: Claim) -> str:
    comps = public_components(claim.components)
    if not comps:
        return claim.original_text
    return " · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in comps.items())


def evidence_out(row: Evidence, source: Source, case: Case) -> EvidenceOut:
    request = source.request or {}
    deleted = row.scrubbed_at is not None
    company_id = str(case.crustdata_company_id or "")
    on_company = bool(company_id) and row.entity_ref.rsplit(":", 1)[-1] == company_id
    entity = request.get("entity_name") or (case.company_name if on_company else row.entity_ref)
    return EvidenceOut(
        evidence_id=str(row.id),
        source=SourceRef(
            source_id=str(source.id),
            provider=source.provider,
            label=source.title or source.endpoint_or_url,
            url_or_endpoint=source.endpoint_or_url,
            retrieved_at=source.retrieved_at,
            source_class=api_source_class(source.source_class),
            origin_id=request.get("origin_key"),
        ),
        quote=None if deleted else row.span,
        page=row.page,
        field_path=row.field_path,
        value=None if deleted else row.value,
        as_of=row.as_of,
        attached_to=EntityAttachment(
            entity_name=str(entity),
            matched_on=list(request.get("matched_on") or ["crustdata_company_id"]),
            identity_confidence=row.identity_confidence,
        ),
        deleted=deleted,
    )


def _meta(outputs: dict[uuid.UUID, dict[str, Any]], check: ClaimCheck) -> dict[str, Any]:
    if check.step_id is None:
        return {}
    return ((outputs.get(check.step_id) or {}).get("checks") or {}).get(str(check.claim_id)) or {}


async def build_claims_section(
    session: AsyncSession, case: Case, *, claim_ids: list[uuid.UUID] | None = None
) -> list[ClaimOut]:
    """Every claim of the case, ledger order (oldest first). The caller has already
    authorised `case` for the signed-in user's workspace."""
    claims = list(
        (
            await session.execute(
                select(Claim).where(Claim.case_id == case.id).order_by(Claim.created_at, Claim.id)
            )
        ).scalars()
    )
    if not claims:
        return []
    checks_by_claim: dict[uuid.UUID, list[ClaimCheck]] = defaultdict(list)
    for check in (
        await session.execute(
            select(ClaimCheck)
            .where(ClaimCheck.case_id == case.id)
            .order_by(ClaimCheck.created_at, ClaimCheck.id)
        )
    ).scalars():
        checks_by_claim[check.claim_id].append(check)

    step_ids = {c.step_id for cs in checks_by_claim.values() for c in cs if c.step_id}
    outputs: dict[uuid.UUID, dict[str, Any]] = {}
    if step_ids:
        rows = await session.execute(select(Step.id, Step.output).where(Step.id.in_(step_ids)))
        outputs = {r.id: r.output or {} for r in rows}

    latest_ids = [cs[-1].id for cs in checks_by_claim.values() if cs]
    links: dict[uuid.UUID, list[tuple[Evidence, Source]]] = defaultdict(list)
    link_ids: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if checks_by_claim:
        all_ids = [c.id for cs in checks_by_claim.values() for c in cs]
        for link in (
            await session.execute(
                select(ClaimCheckEvidence).where(ClaimCheckEvidence.claim_check_id.in_(all_ids))
            )
        ).scalars():
            link_ids[link.claim_check_id].append(link.evidence_id)
    if latest_ids:
        rows = await session.execute(
            select(ClaimCheckEvidence.claim_check_id, Evidence, Source)
            .join(Evidence, Evidence.id == ClaimCheckEvidence.evidence_id)
            .join(Source, Source.id == Evidence.source_id)
            .where(
                ClaimCheckEvidence.claim_check_id.in_(latest_ids),
                ClaimCheckEvidence.relation != READ_MARKER,
            )
            .order_by(Evidence.created_at, Evidence.id)
        )
        for check_id, ev, src in rows.all():
            links[check_id].append((ev, src))

    doc_ids = {c.document_id for c in claims if c.document_id}
    docs: dict[uuid.UUID, Document] = {}
    if doc_ids:
        docs = {
            d.id: d
            for d in (
                await session.execute(select(Document).where(Document.id.in_(doc_ids)))
            ).scalars()
        }
    user_ids = {c.created_by for c in claims if c.created_by}
    users: dict[uuid.UUID, str] = {}
    if user_ids:
        rows = await session.execute(
            select(User.id, User.display_name).where(User.id.in_(user_ids))
        )
        users = {r.id: r.display_name for r in rows}

    wanted = set(claim_ids) if claim_ids is not None else None
    out: list[ClaimOut] = []
    for number, claim in enumerate(claims, start=1):
        if wanted is not None and claim.id not in wanted:
            continue
        history = checks_by_claim.get(claim.id, [])
        current = history[-1] if history else None
        meta = _meta(outputs, current) if current else {}
        doc = docs.get(claim.document_id) if claim.document_id else None
        intake = intake_meta(claim.components)
        if current is None:
            status, reason = ClaimStatus.not_checked, NOT_RUN_YET
            nc_reason = None
        else:
            status, reason = ClaimStatus(current.status), current.reason
            nc_reason = (
                api_not_checked_reason(meta.get("not_checked_reason"), current.reason)
                if status is ClaimStatus.not_checked
                else None
            )
        substantive = meta.get("substantive_result")
        out.append(
            ClaimOut(
                id=str(claim.id),
                number=number,
                original_text=claim.original_text,
                normalised_text=_normalised_text(claim),
                category=ClaimCategory(claim.category),
                components=public_components(claim.components),
                material=claim.material,
                origin=ClaimOrigin.typed if claim.origin == "typed" else ClaimOrigin.document,
                stated_in=StatedInOut(
                    document_id=str(claim.document_id) if claim.document_id else None,
                    filename=doc.filename if doc else None,
                    page=claim.page,
                    quote=claim.quote,
                    typed_by_name=users.get(claim.created_by) if claim.created_by else None,
                    typed_at=claim.created_at if claim.origin == "typed" else None,
                ),
                status=status,
                reason=reason,
                not_checked_reason=nc_reason,
                adequate_source_reached=meta.get("adequate_source_reached"),
                substantive_result=SubstantiveResult(substantive) if substantive else None,
                settle_with=current.what_would_settle if current else None,
                evidence=[evidence_out(ev, src, case) for ev, src in links.get(current.id, [])]
                if current
                else [],
                history=[
                    ClaimCheckOut(
                        id=str(c.id),
                        run_id=str(c.run_id) if c.run_id else None,
                        status=ClaimStatus(c.status),
                        reason=c.reason,
                        not_checked_reason=api_not_checked_reason(
                            _meta(outputs, c).get("not_checked_reason"), c.reason
                        )
                        if c.status == "not_checked"
                        else None,
                        settle_with=c.what_would_settle,
                        evidence_ids=[str(e) for e in link_ids.get(c.id, [])],
                        created_at=c.created_at,
                    )
                    for c in history
                ],
            )
        )
        if intake.get("status") and current is None:
            out[-1] = out[-1].model_copy(update={"reason": intake.get("reason") or NOT_RUN_YET})
    return out
