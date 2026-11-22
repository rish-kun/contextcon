"""DecisionFlip: which open items stand between a case and the next disposition.

Pure, like the rest of ``app.rules``: no I/O, no LLM, no clock. It re-runs the
real disposition rules (``evaluate.redecide``) with unresolved items forced to
a hypothetical state, so a simulated result and a real one always come from
the same code. Every output is marked ``hypothetical``. POLICY.md §9 explains
the method; docs/design/iterations/F-decisionflip.md is the design.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Literal

from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    ComponentState,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    Disposition,
    FlipSearch,
    FlipState,
    IdentityStatus,
    ItemClass,
    ItemKind,
    NextAction,
    NotCheckedReason,
)
from app.domain.types import (
    AssessmentInputs,
    AssessmentVersion,
    CheckOutcome,
    Claim,
    ComponentFinding,
    Criterion,
    CriterionEvaluation,
    DecisionFlipAnalysis,
    DispositionDecision,
    ItemOutcome,
    MinimalSet,
    NextBestAction,
    SettleDocument,
    UnresolvedItem,
)
from app.rules import policy
from app.rules.claim_status import document_for
from app.rules.company_type import required_checks
from app.rules.evaluate import assess, redecide
from app.rules.requests import seller_can_resolve

FLIP_VERSION = "decision-flip-1"

# Up to this many candidates every subset is tried (2**6 = 64 runs); above it a
# deletion greedy finds one irreducible set.
EXHAUSTIVE_MAX_ITEMS = 6

# An unknown criterion is settled by a sourced record about the company, which
# the analyst obtains (registry or data provider); no seller document maps to it.
CRITERION_DOCUMENT = "Sourced record for the criterion (registry filing or data provider)"

__all__ = [
    "CRITERION_DOCUMENT",
    "EXHAUSTIVE_MAX_ITEMS",
    "FLIP_VERSION",
    "DecisionFlipAnalysis",
    "FlipSearch",
    "FlipState",
    "ItemClass",
    "ItemKind",
    "ItemOutcome",
    "MinimalSet",
    "NextAction",
    "NextBestAction",
    "ReplayMismatch",
    "SettleDocument",
    "UnresolvedItem",
    "analyse",
    "analysis_key",
    "rank",
]


class ReplayMismatch(ValueError):
    """Replaying the stored version through the current rules did not give its
    stored disposition (for example a version made under an older policy)."""


# --- The ladder -----------------------------------------------------------------

_RANK = {
    Disposition.CANNOT_ASSESS: 0,
    Disposition.INVESTIGATE_FURTHER: 1,
    Disposition.PRIORITISE: 2,
}


def rank(disposition: Disposition) -> int:
    """Cannot assess 0 < Investigate further 1 < Prioritise 2. Deprioritise is off
    the ladder (-1): no simulated set ever "reaches" a rung through it."""
    return _RANK.get(disposition, -1)


# --- Reproducibility --------------------------------------------------------------


def analysis_key(inputs_hash: str, policy_version: str, materiality: Mapping[str, bool]) -> str:
    """sha256 of the canonical {inputs_hash, policy_version, flip_version, materiality}."""
    payload = {
        "inputs_hash": inputs_hash,
        "policy_version": policy_version,
        "flip_version": FLIP_VERSION,
        "materiality": dict(sorted(materiality.items())),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


# --- Normalised input ---------------------------------------------------------------


@dataclass(frozen=True)
class _Base:
    version: AssessmentVersion
    identity: IdentityStatus
    outcomes: list[CheckOutcome]
    evaluations: list[CriterionEvaluation]
    criteria: list[Criterion]
    claims: dict[str, Claim]


def _identity_from_version(v: AssessmentVersion) -> IdentityStatus:
    decision = v.judgments.disposition
    if decision.rule != "identity_uncertain":
        return IdentityStatus.CONFIRMED  # rule 1 fires first whenever identity is not confirmed
    for reason in decision.reasons:
        for status in IdentityStatus:
            if status is not IdentityStatus.CONFIRMED and reason.startswith(
                f"Identity is {status.value}"
            ):
                return status
    return IdentityStatus.UNRESOLVED


def _criteria_for_version(
    v: AssessmentVersion, given: Sequence[Criterion] | None
) -> list[Criterion]:
    """The criteria behind the version's evaluations. Missing ones are rebuilt from
    the version (labels from its exclusion reasons and unknown list, kind-default
    weights) so a retention skeleton can still be replayed."""
    by_id = {c.id: c for c in given or []}
    evaluations = v.candidate.fit.evaluations
    labels: dict[str, str] = {}
    fails = [
        e
        for e in evaluations
        if e.kind is CriterionKind.MUST and e.result is CriterionResult.FAIL and e.verified
    ]
    for e, reason in zip(fails, v.candidate.exclusion_reasons, strict=False):
        prefix, suffix = "Must-have failed: ", f" ({e.reason})"
        if reason.startswith(prefix) and reason.endswith(suffix):
            labels[e.criterion_id] = reason[len(prefix) : -len(suffix)]
    unknown = [e for e in evaluations if e.result is CriterionResult.UNKNOWN]
    for e, label in zip(unknown, v.candidate.unknown_criteria, strict=False):
        labels[e.criterion_id] = label
    out = list(by_id.values())
    for e in evaluations:
        if e.criterion_id not in by_id:
            out.append(
                Criterion(
                    id=e.criterion_id,
                    label=labels.get(e.criterion_id, e.criterion_id),
                    kind=e.kind,
                    field=e.criterion_id,
                    operator=CriterionOperator.EQ,
                )
            )
            by_id[e.criterion_id] = out[-1]
    return out


def _normalise(
    version: AssessmentInputs | AssessmentVersion | Mapping[str, Any],
    claims: Mapping[str, Claim] | None,
    criteria: Sequence[Criterion] | None,
    identity_status: IdentityStatus | None,
) -> _Base:
    if isinstance(version, AssessmentInputs):
        inputs = version
        v = assess(inputs)
        claims = {c.claim.id: c.claim for c in inputs.claim_checks} if claims is None else claims
        criteria = inputs.criteria if criteria is None else criteria
        identity_status = identity_status or inputs.identity_status
    elif isinstance(version, AssessmentVersion):
        v = version
    else:
        payload = version
        if "outcomes" not in payload and isinstance(payload.get("assessment"), Mapping):
            payload = payload["assessment"]
        v = AssessmentVersion.model_validate(payload)
    return _Base(
        version=v,
        identity=identity_status or _identity_from_version(v),
        outcomes=list(v.outcomes),
        evaluations=list(v.candidate.fit.evaluations),
        criteria=_criteria_for_version(v, criteria),
        claims=dict(claims or {}),
    )


# --- Unresolved items -------------------------------------------------------------

_KIND_ORDER = {
    ItemKind.IDENTITY: 0,
    ItemKind.CLAIM: 1,
    ItemKind.CHECK_GAP: 2,
    ItemKind.CRITERION: 3,
    ItemKind.FINANCIAL_INPUTS: 4,
}

Mode = Literal["supported", "contradicted"]


@dataclass(frozen=True)
class _Item:
    id: str
    kind: ItemKind
    current_state: str
    settle_with: tuple[str, ...]
    seller_resolvable: bool
    analyst_retry: bool = False
    claim_id: str | None = None
    criterion_id: str | None = None
    criterion_kind: CriterionKind | None = None
    check: ClaimCategory | None = None
    depends_on: tuple[str, ...] = ()
    can_contradict: bool = True
    no_op: bool = False  # forcing it changes no rule input (financial inputs)

    @property
    def sort_key(self) -> tuple[int, str]:
        return (_KIND_ORDER[self.kind], self.id)


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _component_document(component: str, category: ClaimCategory, claim: Claim | None) -> str:
    """The same mapping ``build_request_list`` uses."""
    if claim is not None:
        return document_for(component, claim)
    rule = policy.COMPONENT_RULES.get(component)
    return rule.document if rule is not None else policy.CATEGORY_DOCUMENTS[category]


def _claim_item(o: CheckOutcome, claim: Claim | None) -> _Item:
    open_findings = [f for f in o.components if f.state is not ComponentState.MATCHED]
    depends: tuple[str, ...] = ()
    if o.analyst_retry:
        docs: tuple[str, ...] = ()
        seller = False
    elif o.not_checked_reason is NotCheckedReason.IDENTITY_UNRESOLVED:
        docs, seller, depends = (policy.DOC_IDENTITY,), True, ("identity",)
    elif open_findings:
        docs = _dedupe(_component_document(f.component, o.category, claim) for f in open_findings)
        seller = all(seller_can_resolve(f.component) for f in open_findings)
    else:
        docs = _dedupe(o.settle_with) or (policy.CATEGORY_DOCUMENTS[o.category],)
        seller = True
    return _Item(
        id=f"claim:{o.claim_id}",
        kind=ItemKind.CLAIM,
        current_state=o.status.value,
        settle_with=docs,
        seller_resolvable=seller,
        analyst_retry=o.analyst_retry,
        claim_id=o.claim_id,
        check=o.category,
        depends_on=depends,
        can_contradict=o.status is not ClaimStatus.CONTRADICTED,
    )


def _gap_component(check: ClaimCategory) -> str:
    """A component of ``check`` for the synthetic outcome: the one whose document is
    the category's document, else the first by name, else the category itself."""
    names = sorted(n for n, r in policy.COMPONENT_RULES.items() if r.check is check)
    doc = policy.CATEGORY_DOCUMENTS[check]
    return next((n for n in names if policy.COMPONENT_RULES[n].document == doc), None) or (
        names[0] if names else check.value
    )


def _enumerate(base: _Base) -> list[_Item]:
    v = base.version
    items: list[_Item] = []
    if base.identity is not IdentityStatus.CONFIRMED:
        items.append(
            _Item(
                id="identity",
                kind=ItemKind.IDENTITY,
                current_state=base.identity.value,
                settle_with=(policy.DOC_IDENTITY,),
                seller_resolvable=True,
                can_contradict=False,
            )
        )
    for o in base.outcomes:
        if o.status is not ClaimStatus.SUPPORTED:
            items.append(_claim_item(o, base.claims.get(o.claim_id)))
    for c in v.judgments.evidence_sufficiency.checks:
        if c.result is None:
            component = _gap_component(c.check)
            items.append(
                _Item(
                    id=f"check:{c.check.value}",
                    kind=ItemKind.CHECK_GAP,
                    current_state="absent",
                    settle_with=(policy.CATEGORY_DOCUMENTS[c.check],),
                    seller_resolvable=seller_can_resolve(component),
                    check=c.check,
                )
            )
    for e in base.evaluations:
        if e.result is CriterionResult.UNKNOWN:
            items.append(
                _Item(
                    id=f"criterion:{e.criterion_id}",
                    kind=ItemKind.CRITERION,
                    current_state=CriterionResult.UNKNOWN.value,
                    settle_with=(CRITERION_DOCUMENT,),
                    seller_resolvable=False,
                    criterion_id=e.criterion_id,
                    criterion_kind=e.kind,
                )
            )
    financials_required = ClaimCategory.FINANCIALS in required_checks(v.company_type.company_type)
    if financials_required and not v.judgments.financial.assessed:
        items.append(
            _Item(
                id="financial_inputs",
                kind=ItemKind.FINANCIAL_INPUTS,
                current_state="not_assessed",
                settle_with=(policy.DOC_FINANCIAL_INPUTS,),
                seller_resolvable=True,
                can_contradict=False,
                no_op=True,
            )
        )
    return sorted(items, key=lambda i: i.sort_key)


# --- Forcing items and re-running the rules ------------------------------------------


def _force_outcome(o: CheckOutcome, mode: Mode) -> CheckOutcome:
    if mode == "supported":
        components = [f.model_copy(update={"state": ComponentState.MATCHED}) for f in o.components]
        status = ClaimStatus.SUPPORTED
    else:
        components = [
            f
            if f.state is ComponentState.MATCHED
            else f.model_copy(update={"state": ComponentState.CONTRADICTED})
            for f in o.components
        ]
        status = ClaimStatus.CONTRADICTED
    return o.model_copy(
        update={
            "status": status,
            "components": components,
            "not_checked_reason": None,
            "analyst_retry": False,
            "settle_with": [] if mode == "supported" else o.settle_with,
        }
    )


def _gap_outcome(item: _Item, mode: Mode) -> CheckOutcome:
    assert item.check is not None
    supported = mode == "supported"
    return CheckOutcome(
        claim_id=f"hyp:{item.check.value}",
        category=item.check,
        status=ClaimStatus.SUPPORTED if supported else ClaimStatus.CONTRADICTED,
        reason="Hypothetical",
        settle_with=[] if supported else list(item.settle_with),
        components=[
            ComponentFinding(
                component=_gap_component(item.check),
                check=item.check,
                state=ComponentState.MATCHED if supported else ComponentState.CONTRADICTED,
            )
        ],
    )


def _force_evaluation(e: CriterionEvaluation, mode: Mode) -> CriterionEvaluation:
    passed = mode == "supported"
    return e.model_copy(
        update={
            "result": CriterionResult.PASS if passed else CriterionResult.FAIL,
            "verified": True,
            "reason": "hypothetical pass" if passed else "hypothetical fail",
        }
    )


Forcing = frozenset[tuple[str, Mode]]


class _Runner:
    """Re-runs ``redecide`` with items forced; memoised, so ``evaluations`` counts
    distinct rule runs."""

    def __init__(self, base: _Base, items: list[_Item]) -> None:
        self.base = base
        self.items = {i.id: i for i in items}
        self.memo: dict[Forcing, DispositionDecision] = {}
        self.ctype = base.version.company_type.company_type

    def run(self, forcing: Mapping[str, Mode]) -> DispositionDecision:
        key: Forcing = frozenset(forcing.items())
        if key not in self.memo:
            self.memo[key] = self._decide(forcing)
        return self.memo[key]

    def _decide(self, forcing: Mapping[str, Mode]) -> DispositionDecision:
        b = self.base
        identity = (
            IdentityStatus.CONFIRMED if forcing.get("identity") == "supported" else b.identity
        )
        outcomes = []
        for o in b.outcomes:
            mode = forcing.get(f"claim:{o.claim_id}")
            outcomes.append(_force_outcome(o, mode) if mode else o)
        for item_id in sorted(forcing):
            item = self.items[item_id]
            if item.kind is ItemKind.CHECK_GAP:
                outcomes.append(_gap_outcome(item, forcing[item_id]))
        evaluations = []
        for e in b.evaluations:
            mode = forcing.get(f"criterion:{e.criterion_id}")
            evaluations.append(_force_evaluation(e, mode) if mode else e)
        _, _, decision = redecide(
            identity_status=identity,
            company_type=self.ctype,
            outcomes=outcomes,
            evaluations=evaluations,
            criteria=b.criteria,
            claims=b.claims,
        )
        return decision


def _outcome(decision: DispositionDecision, real: Disposition) -> ItemOutcome:
    return ItemOutcome(
        disposition=decision.disposition,
        rule=decision.rule,
        reasons=list(decision.reasons),
        changes_disposition=decision.disposition is not real,
    )


# --- Minimal sets -------------------------------------------------------------------


def _exhaustive(candidates: list[str], reaches: Callable[[tuple[str, ...]], bool]) -> list[tuple]:
    found: list[tuple[str, ...]] = []
    for size in range(len(candidates) + 1):
        for subset in combinations(candidates, size):
            if any(set(m) <= set(subset) for m in found):
                continue
            if reaches(subset):
                found.append(subset)
    return found


def _greedy(candidates: list[_Item], reaches: Callable[[tuple[str, ...]], bool]) -> tuple[str, ...]:
    """Deletion greedy: drop items in reverse priority order (analyst-only first,
    then most documents, then id) while the set still reaches. Repeated until no
    item can be dropped, so the result is irreducible."""
    order = sorted(candidates, key=lambda i: (i.seller_resolvable, -len(i.settle_with), i.id))
    chosen = [i.id for i in order]
    changed = True
    while changed:
        changed = False
        for item in order:
            if item.id not in chosen:
                continue
            trial = [x for x in chosen if x != item.id]
            if reaches(tuple(sorted(trial))):
                chosen = trial
                changed = True
    return tuple(sorted(chosen))


def _documents(ids: Sequence[str], items: Mapping[str, _Item]) -> list[SettleDocument]:
    docs: dict[str, list[str]] = {}
    seller: dict[str, bool] = {}
    for item_id in ids:
        item = items[item_id]
        for d in item.settle_with:
            docs.setdefault(d, []).append(item_id)
            seller[d] = seller.get(d, False) or item.seller_resolvable
    return [
        SettleDocument(document=d, item_ids=item_ids, seller_resolvable=seller[d])
        for d, item_ids in docs.items()
    ]


def _set_key(ids: Sequence[str], items: Mapping[str, _Item]) -> tuple:
    return (
        len(_documents(ids, items)),
        sum(1 for i in ids if not items[i].seller_resolvable),
        len(ids),
        tuple(sorted(ids)),
    )


# --- Next best action ----------------------------------------------------------------


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _next_best_action(
    state: FlipState,
    real: DispositionDecision,
    ceiling: DispositionDecision,
    chosen: MinimalSet | None,
    items: Mapping[str, _Item],
) -> NextBestAction:
    if state is FlipState.NO_BLOCKERS:
        return NextBestAction(
            action=NextAction.NONE, text="No open item stands in the way of Prioritise."
        )
    if state is FlipState.DISQUALIFIED:
        return NextBestAction(
            action=NextAction.REVIEW_DISQUALIFIER,
            text=f"Deprioritise rests on verified evidence: {'; '.join(real.reasons)}. "
            "No evidence request changes it.",
        )
    if state is FlipState.NOT_EVIDENCE_LIMITED or chosen is None:
        return NextBestAction(
            action=NextAction.NONE,
            text=f"More evidence will not change the disposition: {'; '.join(ceiling.reasons)}.",
        )
    ids = chosen.item_ids
    docs = [d.document for d in chosen.documents]
    in_set = [items[i] for i in ids]
    common = {"item_ids": list(ids), "documents": docs}
    if "identity" in ids:
        k = sum(1 for i in items.values() if "identity" in i.depends_on)
        return NextBestAction(
            action=NextAction.RESOLVE_IDENTITY,
            text=f"Confirm the legal entity first; {_n(k, 'check')} cannot run until then.",
            **common,
        )
    retries = [i for i in in_set if i.analyst_retry]
    if retries:
        return NextBestAction(
            action=NextAction.RERUN_CHECKS,
            text=f"Re-run {_n(len(retries), 'check')} that did not run. "
            "No seller document is needed for them.",
            **common,
        )
    if not any(i.seller_resolvable for i in in_set):
        return NextBestAction(
            action=NextAction.ANALYST_FOLLOW_UP,
            text=f"Follow up {_n(len(in_set), 'item')} the seller cannot resolve: "
            f"{'; '.join(docs)}.",
            **common,
        )
    d, k = len(docs), len(in_set)
    blockers = "the decision blocker" if k == 1 else f"the {k} decision blockers"
    return NextBestAction(
        action=NextAction.REQUEST_DOCUMENTS,
        text=f"Request {_n(d, 'document')} that settle{'s' if d == 1 else ''} {blockers}, "
        "rather than everything open.",
        **common,
    )


# --- Entry point ----------------------------------------------------------------------


def _worst(outcomes: Iterable[ItemOutcome]) -> ItemOutcome | None:
    best: ItemOutcome | None = None
    for o in outcomes:
        if best is None or rank(o.disposition) < rank(best.disposition):
            best = o
    return best


def analyse(
    version: AssessmentInputs | AssessmentVersion | Mapping[str, Any],
    *,
    claims: Mapping[str, Claim] | None = None,
    criteria: Sequence[Criterion] | None = None,
    identity_status: IdentityStatus | None = None,
) -> DecisionFlipAnalysis:
    """Analyse one assessment version.

    ``version`` is either the case inputs (assessed here with ``rules.assess``),
    an ``AssessmentVersion``, or a stored version payload: the
    ``AssessmentVersion`` JSON, or the stored ``judgments`` document that holds
    it under ``"assessment"`` (the retention skeleton works: it keeps every
    status and id).

    For a stored version, pass ``claims`` (materiality and settling documents;
    without them every claim counts as material, as in ``decide_disposition``)
    and ``criteria`` (custom weights; without them kind defaults are used).
    ``identity_status`` is read from the version when omitted. With
    ``AssessmentInputs`` all three come from the inputs.

    Raises ``ReplayMismatch`` when the current rules do not reproduce the
    version's stored disposition.
    """
    base = _normalise(version, claims, criteria, identity_status)
    v = base.version
    items = _enumerate(base)
    by_id = {i.id: i for i in items}
    runner = _Runner(base, items)

    real = runner.run({})
    stored = v.judgments.disposition
    if (real.disposition, real.rule, real.reasons) != (
        stored.disposition,
        stored.rule,
        stored.reasons,
    ):
        raise ReplayMismatch(
            f"Replaying version {v.version} gives {real.disposition.value} ({real.rule}), "
            f"stored {stored.disposition.value} ({stored.rule})"
        )
    current = real.disposition

    candidates = [i for i in items if not i.no_op]
    all_supported: dict[str, Mode] = {i.id: "supported" for i in candidates}
    ceiling = runner.run(all_supported)

    target: Disposition | None = None
    if current is Disposition.CANNOT_ASSESS and rank(ceiling.disposition) >= 1:
        target = Disposition.INVESTIGATE_FURTHER
    elif current is Disposition.INVESTIGATE_FURTHER and ceiling.disposition is (
        Disposition.PRIORITISE
    ):
        target = Disposition.PRIORITISE

    if target is not None:
        state = FlipState.HAS_BLOCKERS
    elif current is Disposition.PRIORITISE:
        state = FlipState.NO_BLOCKERS
    elif current is Disposition.DEPRIORITISE:
        state = FlipState.DISQUALIFIED
    else:
        state = FlipState.NOT_EVIDENCE_LIMITED

    def reaches(ids: Sequence[str]) -> bool:
        assert target is not None
        return rank(runner.run(dict.fromkeys(ids, "supported")).disposition) >= rank(target)

    # Minimal sets.
    search = FlipSearch.EXHAUSTIVE
    minimal: list[tuple[str, ...]] = []
    if target is not None:
        cand_ids = [i.id for i in candidates]
        if len(cand_ids) <= EXHAUSTIVE_MAX_ITEMS:
            minimal = _exhaustive(cand_ids, reaches)
        else:
            search = FlipSearch.GREEDY
            minimal = [_greedy(candidates, reaches)]
        minimal.sort(key=lambda ids: _set_key(ids, by_id))
    in_any_set = {i for ids in minimal for i in ids}

    # Per-item runs. A verified Deprioritise is not simulated away.
    out_items: list[UnresolvedItem] = []
    for item in items:
        if_supported = if_contradicted = None
        needed = locks = False
        if state is not FlipState.DISQUALIFIED:
            if_supported = _outcome(runner.run({item.id: "supported"}), current)
            if item.can_contradict:
                if_contradicted = _outcome(runner.run({item.id: "contradicted"}), current)
            if target is not None and not item.no_op:
                others = {k: m for k, m in all_supported.items() if k != item.id}
                needed = rank(runner.run(others).disposition) < rank(target)
                if item.can_contradict:
                    locks = rank(
                        runner.run({**others, item.id: "contradicted"}).disposition
                    ) < rank(target)
        blocker = target is not None and (item.id in in_any_set or needed)
        # POLICY.md §5: claim statuses never feed Deprioritise, so only an unknown
        # must-have whose verified fail would exclude the company is a risk.
        risk = (
            item.kind is ItemKind.CRITERION
            and item.criterion_kind is CriterionKind.MUST
            and if_contradicted is not None
            and if_contradicted.disposition is Disposition.DEPRIORITISE
        )
        flips = (
            target is not None
            and if_supported is not None
            and rank(if_supported.disposition) >= rank(target)
        )
        out_items.append(
            UnresolvedItem(
                id=item.id,
                kind=item.kind,
                claim_id=item.claim_id,
                criterion_id=item.criterion_id,
                check=item.check,
                current_state=item.current_state,
                classification=(
                    ItemClass.DECISION_BLOCKER
                    if blocker
                    else ItemClass.DISQUALIFIER_RISK
                    if risk
                    else ItemClass.NON_BLOCKING
                ),
                decision_blocker=blocker,
                disqualifier_risk=risk,
                required_in_every_path=needed,
                flips_alone=flips,
                locks_target=locks,
                seller_resolvable=item.seller_resolvable,
                analyst_retry=item.analyst_retry,
                depends_on=list(item.depends_on),
                settle_with=list(item.settle_with),
                if_supported=if_supported,
                if_contradicted=if_contradicted,
            )
        )

    sets = [
        MinimalSet(
            item_ids=list(ids),
            documents=_documents(ids, by_id),
            outcome=_outcome(runner.run(dict.fromkeys(ids, "supported")), current),
        )
        for ids in minimal
    ]
    chosen = sets[0] if sets else None
    worst = _worst(
        i.if_contradicted
        for i in out_items
        if i.if_contradicted is not None and (i.decision_blocker or i.disqualifier_risk)
    )
    materiality = {
        o.claim_id: (base.claims[o.claim_id].material if o.claim_id in base.claims else True)
        for o in base.outcomes
    }
    return DecisionFlipAnalysis(
        case_id=v.case_id,
        assessment_version=v.version,
        policy_version=v.policy_version,
        inputs_hash=v.inputs_hash,
        flip_version=FLIP_VERSION,
        analysis_key=analysis_key(v.inputs_hash, v.policy_version, materiality),
        state=state,
        current=current,
        current_rule=real.rule,
        current_reasons=list(real.reasons),
        target=target,
        ceiling=_outcome(ceiling, current),
        items=out_items,
        minimal_sets=sets,
        minimum_evidence=chosen,
        worst_if_contradicted=worst,
        next_best_action=_next_best_action(state, real, ceiling, chosen, by_id),
        search=search,
        greedy=search is FlipSearch.GREEDY,
        evaluations=len(runner.memo),
    )
