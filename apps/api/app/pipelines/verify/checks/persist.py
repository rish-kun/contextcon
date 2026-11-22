"""Writing a decided check: a `claim_checks` row, its evidence links, and the inputs.

`claim_checks` is append-only (the newest row per claim is current). Each row links
to every fact's evidence row with the fact's component as the link's `relation`, and
to a `read` marker for each source that was read but yielded no fact, so the evaluate
reader (`app.pipelines.evaluate.inputs`) rebuilds the same `ClaimCheck`. The role each
fact played (`decisive`, `not_adequate`, ...) is in the stored outcome.

The rule inputs are returned as metadata for the step output (`Step.output["checks"]`,
reachable through `claim_checks.step_id`), so the outcome can be reproduced: the
same inputs under the same policy version give the same status. The claim's own
text and component values, and values from seller documents, are not copied there;
they are referenced by id, so the retention purge that scrubs claims and evidence
also covers what the check was about.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Claim, ClaimCheckEvidence
from app.db.models import ClaimCheck as ClaimCheckRow
from app.domain.enums import ClaimStatus
from app.domain.types import CheckOutcome, ClaimCheck
from app.pipelines.verify.checks.sources import READ_MARKER
from app.rules import policy
from app.rules.policy import POLICY_VERSION


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None  # not a stored row (unit fixtures only)


def adequate_source_reached(check: ClaimCheck) -> bool:
    """Was a source class adequate for any of the claim's components reached and read?"""
    adequate: set[Any] = set()
    for comp in check.claim.components:
        rule = policy.COMPONENT_RULES.get(comp.name)
        if rule is not None:
            adequate |= set(rule.adequate)
    reached = {s.reliability for s in check.sources_read}
    reached |= {f.evidence.source.reliability for f in check.facts}
    return bool(adequate & reached)


def substantive_result(outcome: CheckOutcome, adequate: bool) -> str | None:
    """What the evidence said, apart from whether it was adequate (spec §6.3 step 6)."""
    return {
        ClaimStatus.SUPPORTED: "supports",
        ClaimStatus.CONTRADICTED: "conflicts",
        ClaimStatus.CONFLICTING_EVIDENCE: "conflicts",
        ClaimStatus.PARTIALLY_CORROBORATED: "partial",
        ClaimStatus.CANNOT_VERIFY: "silent" if adequate else None,
        ClaimStatus.NOT_CHECKED: None,
    }[outcome.status]


_CONFIDENTIAL_CLASSES = {"seller_document", "seller_statement"}


def reproducible_inputs(check: ClaimCheck) -> dict[str, Any]:
    """The rule inputs without confidential content.

    The claim's text and component values are referenced by claim id (the claims row
    carries `delete_after` and is scrubbed by the purge). Values from seller documents
    are referenced by evidence id for the same reason. Public evidence (registry,
    news, provider fields) is kept whole so the decision can be replayed.
    """
    data = check.model_dump(mode="json")
    claim = data["claim"]
    claim["text"] = None
    claim["components"] = [{"name": c["name"], "op": c["op"]} for c in claim["components"]]
    for fact in data["facts"]:
        if fact["evidence"]["source"]["reliability"] in _CONFIDENTIAL_CLASSES:
            fact["value"] = None
            fact["evidence"]["quote"] = None
            fact["evidence"]["field_value"] = None
    return data


def stored_outcome(outcome: CheckOutcome) -> dict[str, Any]:
    data = outcome.model_dump(mode="json")
    for ref in data["evidence"]:
        if ref["reliability"] in _CONFIDENTIAL_CLASSES:
            ref["value"] = None
    return data


async def persist_outcome(
    session: AsyncSession,
    *,
    claim: Claim,
    check: ClaimCheck,
    outcome: CheckOutcome,
    run_id: uuid.UUID | None = None,
    step_id: uuid.UUID | None = None,
    read_markers: dict[str, uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Append the check row with its evidence links (flushes). Returns step metadata."""
    row = ClaimCheckRow(
        claim_id=claim.id,
        case_id=claim.case_id,
        run_id=run_id,
        step_id=step_id,
        status=outcome.status.value,
        reason=outcome.reason,
        what_would_settle="; ".join(outcome.settle_with) or None,
        policy_version=POLICY_VERSION,
    )
    links: dict[uuid.UUID, str] = {}
    spoke: set[str] = set()
    for fact in check.facts:
        evidence_id = _as_uuid(fact.evidence.id)
        if evidence_id is not None:
            links.setdefault(evidence_id, fact.component)
            spoke.add(fact.evidence.source.id)
    for source_id, marker_id in (read_markers or {}).items():
        if source_id not in spoke and marker_id not in links:
            links[marker_id] = READ_MARKER
    row.evidence_links = [
        ClaimCheckEvidence(evidence_id=eid, relation=role) for eid, role in links.items()
    ]
    session.add(row)
    await session.flush()
    adequate = adequate_source_reached(check)
    return {
        "claim_check_id": str(row.id),
        "status": outcome.status.value,
        "not_checked_reason": outcome.not_checked_reason.value
        if outcome.not_checked_reason
        else None,
        "not_checked_detail": check.not_run_detail,
        "adequate_source_reached": adequate
        if outcome.status is not ClaimStatus.NOT_CHECKED
        else None,
        "substantive_result": substantive_result(outcome, adequate),
        "policy_version": POLICY_VERSION,
        "inputs": reproducible_inputs(check),
        "outcome": stored_outcome(outcome),
    }
