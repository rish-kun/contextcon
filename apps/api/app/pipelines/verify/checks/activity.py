"""Claim-scoped live activity for the claim checks (the Claims tab's per-claim progress).

Every event here carries `ref: {type: "claim", id}` (from the `activity_topic` the check
step opens) and names the claim only by its category. Facts are announced with their
source and as-of date; a snippet only when the source is a public web page or a
Crustdata record, never a seller document and never a person's name. All functions
are fire-and-forget: they use the step's emitter (`current_emitter`) and never raise.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.activity import activity_topic, current_topic
from app.db.models import ClaimCheck, Step
from app.domain.types import ExtractedFact
from app.jobs.activity import (
    Subject,
    clean_domain,
    current_emitter,
    render,
    snippet,
    source_ref,
)

log = logging.getLogger(__name__)

_CONFIDENTIAL = {"seller_document", "seller_statement"}
_NO_SNIPPET_COMPONENTS = {"person_name"}


def _claim() -> tuple[str | None, str | None]:
    topic = current_topic()
    ref = topic.get("ref") or {}
    return (ref.get("id") if ref.get("type") == "claim" else None), topic.get("category")


def reading(source: Any) -> Any:
    """`activity_topic` for a model read of one stored source (a `sources` row): what
    kind of text it is and, for a web page, its domain. Never the text itself."""
    source_class = str(getattr(source, "source_class", "") or "")
    url = str(getattr(source, "endpoint_or_url", "") or "")
    if source_class in _CONFIDENTIAL:
        return activity_topic(reading="document")
    if url.startswith("http"):
        return activity_topic(reading="web_page", domain=clean_domain(url))
    return activity_topic(reading="record")


async def status(key: str, **slots: Any) -> None:
    try:
        label = render(key, **slots)
    except Exception:  # noqa: BLE001
        log.warning("activity: bad check status %s", key, exc_info=True)
        return
    await current_emitter().status(label)


def fact_source(fact: ExtractedFact) -> dict[str, Any]:
    src = fact.evidence.source
    reliability = str(getattr(src.reliability, "value", src.reliability))
    if reliability in _CONFIDENTIAL:
        return source_ref("seller_document", title="Seller document")
    if src.url and src.url.startswith("http"):
        return source_ref(
            "web_page",
            url=src.url,
            title=src.label,
            source_class=reliability,
            as_of=fact.evidence.as_of,
        )
    return source_ref(
        "crustdata_record",
        title=src.label,
        source_class=reliability,
        as_of=fact.evidence.as_of,
    )


def fact_snippet(fact: ExtractedFact) -> str | None:
    src = fact.evidence.source
    reliability = str(getattr(src.reliability, "value", src.reliability))
    if reliability in _CONFIDENTIAL or fact.component in _NO_SNIPPET_COMPONENTS:
        return None
    if fact.evidence.quote:
        return snippet(fact.evidence.quote)
    if fact.evidence.field_path:
        return snippet(f"{fact.evidence.field_path}: {fact.evidence.field_value}")
    return None


async def fact_found(fact: ExtractedFact) -> None:
    """One accepted fact for the claim being checked, with its source and as-of date."""
    claim_id, category = _claim()
    emitter = current_emitter()
    if claim_id is None or category is None or not emitter.enabled:
        return
    try:
        count = emitter.bump(f"facts:{claim_id}")
        source = fact_source(fact)
        label = render("finding.fact_found", category=category)
        item = {
            "id": claim_id,
            "stage": "checking",
            "category": category,
            "evidence_count": count,
            "snippet": fact_snippet(fact),
        }
    except Exception:  # noqa: BLE001
        log.warning("activity: could not describe a fact", exc_info=True)
        return
    await emitter.finding(label, subject=Subject.CLAIM, items=[item], source=source)


async def claim_counts(
    session: AsyncSession, run_id: uuid.UUID, handler: str, *, current: str | None = None
) -> dict[str, int]:
    """This run's claims by stage after this event: every claim with a check step,
    settled once it has a ledger row from this run, `current` being checked."""
    claim_ids = {
        str(v)
        for v in (
            await session.execute(
                select(Step.input["claim_id"].astext).where(
                    Step.run_id == run_id, Step.handler == handler
                )
            )
        ).scalars()
        if v
    }
    rows = (
        await session.execute(
            select(ClaimCheck.claim_id, ClaimCheck.status).where(ClaimCheck.run_id == run_id)
        )
    ).all()
    done = {str(c): status for c, status in rows}
    not_checked = sum(1 for s in done.values() if s == "not_checked")
    checking = int(current is not None and current not in done)
    return {
        "queued": max(0, len(claim_ids - set(done)) - checking),
        "checking": checking,
        "settled": len(done) - not_checked,
        "not_checked": not_checked,
    }


async def checking(counts: dict[str, int]) -> None:
    claim_id, category = _claim()
    if claim_id is None or category is None:
        return
    await current_emitter().finding(
        render("finding.claim_checking", category=category),
        subject=Subject.CLAIM,
        items=[{"id": claim_id, "stage": "checking", "category": category}],
        counts=counts,
    )


async def settled(meta: dict[str, Any], counts: dict[str, int]) -> None:
    """The claim's status, with the decisive public source and the rule's gap line."""
    claim_id, category = _claim()
    emitter = current_emitter()
    if claim_id is None or category is None or not emitter.enabled:
        return
    try:
        status_value = str(meta.get("status"))
        outcome = meta.get("outcome") or {}
        evidence = [e for e in outcome.get("evidence") or [] if e.get("role") != "rejected"]
        decisive = next((e for e in evidence if e.get("role") == "decisive"), None)
        facts = {f.get("id"): f for f in (meta.get("inputs") or {}).get("facts") or []}
        source = snip = None
        fact = facts.get(decisive.get("fact_id")) if decisive else None
        if fact is not None:
            try:
                parsed = ExtractedFact.model_validate(fact)
                source, snip = fact_source(parsed), fact_snippet(parsed)
            except Exception:  # noqa: BLE001 - redacted seller facts do not re-validate
                source = source_ref("seller_document", title="Seller document")
        not_checked = status_value == "not_checked"
        settle_with = [str(s) for s in outcome.get("settle_with") or []]
        item = {
            "id": claim_id,
            "stage": "not_checked" if not_checked else "settled",
            "category": category,
            "status": status_value,
            "previous_status": None,
            "evidence_count": len(evidence),
            "snippet": snip,
            "gap": snippet("Needs: " + "; ".join(settle_with[:2])) if settle_with else None,
        }
        label = (
            render("finding.claim_not_checked")
            if not_checked
            else render("finding.claim_settled", status=status_value)
        )
        detail = render("finding.category", category=category)
    except Exception:  # noqa: BLE001
        log.warning("activity: could not describe a settled claim", exc_info=True)
        return
    await emitter.finding(
        label, subject=Subject.CLAIM, items=[item], counts=counts, detail=detail, source=source
    )
