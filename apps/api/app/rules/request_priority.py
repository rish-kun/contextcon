"""Blocker-first order for the request list, from a DecisionFlip analysis.

Pure, like the rest of ``app.rules``. ``build_request_list`` still decides *what* is
requested (one document per open question, deduplicated); this module only decides the
order and the label, so a missing analysis changes nothing.

Order (``rank``, lower first):

0. documents in the analysis's ``minimum_evidence`` set;
1. other documents that settle a decision blocker;
2. documents that settle a disqualifier risk;
3. everything else (non-blocking);
4. documents whose only open items are checks to re-run on our side.

Ties break by the document's estimated effort (``policy.DOCUMENT_EFFORT``, low first),
then by the order ``build_request_list`` gave.

Criteria and financial items carry DecisionFlip's ``conditional_action``. The seller
sees it without the internal parts (the "Hypothetically, ... gives Prioritise" branch,
claim ids and the "Obtain ..." instruction), so the email states both outcomes and
never suggests that a document makes the company qualify.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from app.domain.enums import EffortLevel, ItemKind, PriorityReason
from app.domain.types import DecisionFlipAnalysis, UnresolvedItem
from app.rules import policy

NEEDED_HEADING = "Needed to complete our screening"
ALSO_HELPFUL_HEADING = "Also helpful"

RANK_MINIMUM_EVIDENCE = 0
RANK_BLOCKER = 1
RANK_RISK = 2
RANK_NON_BLOCKING = 3
RANK_ANALYST_RETRY = 4

_EFFORT_RANK = {EffortLevel.LOW: 0, EffortLevel.MEDIUM: 1, EffortLevel.HIGH: 2}


@dataclass(frozen=True)
class Priority:
    rank: int
    reason: PriorityReason
    effort: EffortLevel
    # Seller-facing conditional sentences (both outcomes) for the items it settles.
    conditions: tuple[str, ...] = ()

    @property
    def needed(self) -> bool:
        """Listed under "Needed to complete our screening" (a decision blocker)."""
        return self.reason is PriorityReason.DECISION_BLOCKER


UNPRIORITISED = Priority(RANK_NON_BLOCKING, PriorityReason.NON_BLOCKING, EffortLevel.MEDIUM)


def group_label(reason: PriorityReason) -> str:
    return NEEDED_HEADING if reason is PriorityReason.DECISION_BLOCKER else ALSO_HELPFUL_HEADING


def document_effort(document: str) -> EffortLevel:
    return policy.DOCUMENT_EFFORT.get(document, EffortLevel.MEDIUM)


_HYPOTHETICAL = re.compile(r"\s*Hypothetically,.*$", re.S)
_OBTAIN = re.compile(r"^Obtain [^.]*\.\s*")


def seller_condition(conditional_action: str, claim_id: str | None = None) -> str:
    """DecisionFlip's conditional wording, fit for the seller: both outcomes, no
    internal disposition, no claim id, no instruction to the analyst."""
    text = _HYPOTHETICAL.sub("", conditional_action).strip()
    text = _OBTAIN.sub("", text).strip()
    if claim_id:
        text = text.replace(f"claim {claim_id}", "the claim")
    return text


def _matches(item: UnresolvedItem, document: str, claim_ids: set[str]) -> bool:
    """A claim item is settled (in part) by every document the request list linked it
    to; any other item by the documents it names."""
    if item.kind is ItemKind.CLAIM:
        return item.claim_id is not None and item.claim_id in claim_ids
    return document in item.settle_with


def item_priority(
    document: str, claim_ids: Iterable[str], analysis: DecisionFlipAnalysis | None
) -> Priority:
    """Where one requested document goes. Without an analysis, nothing moves."""
    if analysis is None:
        return UNPRIORITISED
    effort = document_effort(document)
    ids = set(claim_ids)
    matched = [i for i in analysis.items if _matches(i, document, ids)]
    conditions = tuple(
        dict.fromkeys(
            seller_condition(i.conditional_action, i.claim_id)
            for i in matched
            if i.conditional_action
        )
    )
    minimum = analysis.minimum_evidence
    if minimum is not None and document in {d.document for d in minimum.documents}:
        rank, reason = RANK_MINIMUM_EVIDENCE, PriorityReason.DECISION_BLOCKER
    elif any(i.decision_blocker for i in matched):
        rank, reason = RANK_BLOCKER, PriorityReason.DECISION_BLOCKER
    elif any(i.disqualifier_risk for i in matched):
        rank, reason = RANK_RISK, PriorityReason.DISQUALIFIER_RISK
    elif matched and all(i.analyst_retry for i in matched):
        rank, reason = RANK_ANALYST_RETRY, PriorityReason.ANALYST_RETRY
    else:
        rank, reason = RANK_NON_BLOCKING, PriorityReason.NON_BLOCKING
    return Priority(rank, reason, effort, conditions)


def prioritise[T](
    items: Sequence[T],
    key: Callable[[T], tuple[str, Iterable[str]]],
    analysis: DecisionFlipAnalysis | None,
) -> list[tuple[T, Priority]]:
    """``items`` (each giving ``(document, claim_ids)`` through ``key``) in blocker-first
    order, each with its priority. Stable: without an analysis the order is unchanged."""
    ranked = [(item, item_priority(*key(item), analysis)) for item in items]
    if analysis is None:
        return ranked
    order = sorted(
        range(len(ranked)),
        key=lambda n: (ranked[n][1].rank, _EFFORT_RANK[ranked[n][1].effort], n),
    )
    return [ranked[n] for n in order]
