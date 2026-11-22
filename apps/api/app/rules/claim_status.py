"""Claim status: a declarative rule table (``policy.COMPONENT_RULES``) applied
component by component, then combined with a fixed precedence.

Precedence (first that applies wins):
  1. not_checked             the check did not run (always with a reason)
  2. contradicted            some component is contradicted by the decisive sources
  3. conflicting_evidence    the decisive sources disagree on some component
  4. supported               every component is matched by adequate evidence
  5. partially_corroborated  some components matched, the rest unsettled
  6. cannot_verify           nothing adequate settles any component
"""

from __future__ import annotations

from collections import defaultdict

from app.domain.enums import ClaimCategory, ClaimStatus, ComponentState, SourceReliability
from app.domain.types import (
    CheckOutcome,
    Claim,
    ClaimCheck,
    ComponentFinding,
    EvidenceRef,
    ExtractedFact,
)
from app.rules import policy
from app.rules.compare import Relation, compare, contains_phrase
from app.rules.validation import screen_fact

_STATUS_LABEL = {
    ClaimStatus.SUPPORTED: "Supported",
    ClaimStatus.CONTRADICTED: "Contradicted",
    ClaimStatus.PARTIALLY_CORROBORATED: "Partially corroborated",
    ClaimStatus.CONFLICTING_EVIDENCE: "Conflicting evidence",
    ClaimStatus.CANNOT_VERIFY: "Cannot verify",
    ClaimStatus.NOT_CHECKED: "Not checked",
}

ANALYST_RETRY_REASONS = frozenset({"budget_exhausted", "source_error"})


def status_label(status: ClaimStatus) -> str:
    return _STATUS_LABEL[status]


def _check_of(component: str, claim: Claim) -> ClaimCategory:
    rule = policy.COMPONENT_RULES.get(component)
    return rule.check if rule else claim.category


def document_for(component: str, claim: Claim) -> str:
    rule = policy.COMPONENT_RULES.get(component)
    if rule is None:
        return policy.CATEGORY_DOCUMENTS[claim.category]
    if rule.check is ClaimCategory.DATED_EVENT and rule.document == policy.DOC_EVENT:
        event = next((c.value for c in claim.components if c.name == "event"), claim.text)
        if any(contains_phrase(event, w) for w in policy.FACILITY_WORDS):
            return policy.DOC_FACILITY
    return rule.document


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def _effective_class(facts: list[ExtractedFact]) -> SourceReliability:
    """Copies of one origin are only as authoritative as the weakest copy."""
    return max(
        (f.evidence.source.reliability for f in facts),
        key=lambda r: (policy.AUTHORITY_RANK[r], r.value),
    )


def _ref(fact: ExtractedFact, role: str, note: str = "") -> EvidenceRef:
    src = fact.evidence.source
    return EvidenceRef(
        fact_id=fact.id,
        evidence_id=fact.evidence.id,
        component=fact.component,
        value=fact.value,
        source_label=src.label,
        reliability=src.reliability,
        origin=src.origin,
        as_of=fact.evidence.as_of,
        role=role,
        note=note,
    )


def _not_checked(check: ClaimCheck) -> CheckOutcome:
    claim = check.claim
    reason = check.not_run_reason
    detail = f" ({check.not_run_detail})" if check.not_run_detail else ""
    docs = _dedupe([document_for(c.name, claim) for c in claim.components]) or [
        policy.CATEGORY_DOCUMENTS[claim.category]
    ]
    return CheckOutcome(
        claim_id=claim.id,
        category=claim.category,
        status=ClaimStatus.NOT_CHECKED,
        reason=f"Not checked: {reason.value.replace('_', ' ')}{detail}.",
        settle_with=docs,
        components=[
            ComponentFinding(
                component=c.name,
                check=_check_of(c.name, claim),
                state=ComponentState.NOT_CHECKED,
                note="check not run",
            )
            for c in claim.components
        ],
        not_checked_reason=reason,
        analyst_retry=reason.value in ANALYST_RETRY_REASONS,
    )


def decide_claim_status(check: ClaimCheck) -> CheckOutcome:
    """Decide one claim's status from its facts. Pure and order-independent."""
    if not check.ran:
        return _not_checked(check)

    claim = check.claim
    claimed = {c.name: c.value for c in claim.components}
    refs: list[EvidenceRef] = []

    # 1. Screen: identity guard and span validation. Rejected facts are kept
    #    for the audit trail but take no further part.
    valid: list[ExtractedFact] = []
    for fact in sorted(check.facts, key=lambda f: f.id):
        result = screen_fact(fact, claim.entity_ids)
        if result.valid:
            valid.append(fact)
        else:
            refs.append(_ref(fact, "rejected", result.reason))

    findings: list[ComponentFinding] = []
    notes: list[str] = []
    claim_component_names = set(claimed)

    for comp in claim.components:
        rule = policy.COMPONENT_RULES.get(comp.name)
        check_cat = _check_of(comp.name, claim)
        relevant = [f for f in valid if f.component == comp.name]
        if rule is None:
            for f in relevant:
                refs.append(_ref(f, "not_adequate", "no rule for this component"))
            findings.append(
                ComponentFinding(
                    component=comp.name,
                    check=check_cat,
                    state=ComponentState.UNSETTLED,
                    note="no source class is adequate for this question",
                )
            )
            notes.append(f"{comp.name}: no source class is adequate for this question.")
            continue

        # 2. Group by origin so syndicated copies count once.
        by_origin: dict[str, list[ExtractedFact]] = defaultdict(list)
        for f in relevant:
            by_origin[f.evidence.source.origin].append(f)

        decisive: list[tuple[int, Relation, str, list[ExtractedFact]]] = []
        for origin in sorted(by_origin):
            group = by_origin[origin]
            eff = _effective_class(group)
            if eff not in rule.adequate:
                caveat = rule.caveats.get(eff, "")
                for f in group:
                    refs.append(_ref(f, "not_adequate", caveat))
                values = ", ".join(sorted({str(f.value) for f in group}))
                line = (
                    f"{comp.name}: {group[0].evidence.source.label} ({eff.value}) gives "
                    f"{values}, which is not adequate for this question"
                )
                notes.append(line + (f". {caveat}." if caveat else "."))
                continue
            relations = {
                compare(
                    rule.kind,
                    comp.value,
                    comp.op,
                    f.value,
                    fact_as_of=f.evidence.as_of,
                    claim_context=claimed,
                )
                for f in group
            }
            decided = relations - {"insufficient"}
            if len(decided) == 1:
                rel = decided.pop()
                decisive.append((policy.AUTHORITY_RANK[eff], rel, origin, group))
            else:
                note = "copies of one origin disagree" if len(decided) > 1 else ""
                for f in group:
                    refs.append(_ref(f, "undecided", note))

        silent = _silent_sources(check, rule, comp.name, by_origin)

        if not decisive:
            findings.append(
                ComponentFinding(
                    component=comp.name,
                    check=check_cat,
                    state=ComponentState.UNSETTLED,
                    note="no adequate evidence settles it",
                )
            )
            if silent:
                notes.append(f"{comp.name}: {', '.join(silent)} was read and does not state it.")
            elif not relevant:
                notes.append(f"{comp.name}: no adequate source was found.")
            continue

        best = min(rank for rank, _, _, _ in decisive)
        top = [d for d in decisive if d[0] == best]
        lower = [d for d in decisive if d[0] != best]
        top_relations = {rel for _, rel, _, _ in top}
        if top_relations == {"match"}:
            state = ComponentState.MATCHED
        elif top_relations == {"conflict"}:
            state = ComponentState.CONTRADICTED
        else:
            state = ComponentState.CONFLICTING

        decisive_ids: list[str] = []
        for _, rel, _, group in top:
            for f in group:
                decisive_ids.append(f.evidence.id)
                refs.append(_ref(f, "decisive", rel))
        for _, rel, _, group in lower:
            overridden = rel not in top_relations or state is ComponentState.CONFLICTING
            for f in group:
                refs.append(
                    _ref(
                        f,
                        "undecided",
                        "outranked by a more authoritative source" if overridden else rel,
                    )
                )
        origins = len(top)
        summary = {
            ComponentState.MATCHED: "matched",
            ComponentState.CONTRADICTED: "contradicted",
            ComponentState.CONFLICTING: "sources disagree",
        }[state]
        labels = ", ".join(sorted({g[0].evidence.source.label for _, _, _, g in top}))
        note = f"{summary} by {labels} ({origins} independent origin{'s' if origins != 1 else ''})"
        findings.append(
            ComponentFinding(
                component=comp.name,
                check=check_cat,
                state=state,
                decisive_evidence_ids=_dedupe(decisive_ids),
                note=note,
            )
        )
        notes.append(f"{comp.name}: {note}.")

    # 3. Related facts: same check, component not in the claim (for example a
    #    registered charge next to a "no debt" claim). Reported, never decisive.
    claim_checks = {f.check for f in findings}
    for fact in valid:
        if fact.component in claim_component_names:
            continue
        rule = policy.COMPONENT_RULES.get(fact.component)
        if rule is None or rule.check not in claim_checks:
            continue
        caveat = rule.related_caveat
        refs.append(_ref(fact, "related", caveat))
        line = (
            f"Related: {fact.evidence.source.label} ({fact.evidence.source.reliability.value}) "
            f"records {fact.component} = {fact.value}"
        )
        notes.append(line + (f". {caveat}." if caveat else ", which does not settle this claim."))

    status = _combine([f.state for f in findings])
    unsettled_docs = [
        document_for(f.component, claim) for f in findings if f.state is not ComponentState.MATCHED
    ]
    if status is ClaimStatus.SUPPORTED:
        settle: list[str] = []
    else:
        settle = _dedupe(unsettled_docs) or [policy.CATEGORY_DOCUMENTS[claim.category]]

    headline = status_label(status)
    if not claim.components:
        notes.append("The claim has no checkable components.")
    reason = " ".join([f"{headline}."] + notes)
    if settle:
        reason += f" Would settle it: {'; '.join(settle)}."

    return CheckOutcome(
        claim_id=claim.id,
        category=claim.category,
        status=status,
        reason=reason,
        settle_with=settle,
        components=findings,
        evidence=refs,
    )


def _silent_sources(
    check: ClaimCheck,
    rule: policy.ComponentRule,
    component: str,
    by_origin: dict[str, list[ExtractedFact]],
) -> list[str]:
    """Adequate sources that were read but yielded nothing for this component."""
    spoke = {f.evidence.source.id for group in by_origin.values() for f in group}
    return sorted(
        {
            s.label
            for s in check.sources_read
            if s.reliability in rule.adequate and s.id not in spoke
        }
    )


def _combine(states: list[ComponentState]) -> ClaimStatus:
    if not states:
        return ClaimStatus.CANNOT_VERIFY
    if ComponentState.CONTRADICTED in states:
        return ClaimStatus.CONTRADICTED
    if ComponentState.CONFLICTING in states:
        return ClaimStatus.CONFLICTING_EVIDENCE
    if all(s is ComponentState.MATCHED for s in states):
        return ClaimStatus.SUPPORTED
    if ComponentState.MATCHED in states:
        return ClaimStatus.PARTIALLY_CORROBORATED
    return ClaimStatus.CANNOT_VERIFY


def decide_all(checks: list[ClaimCheck]) -> list[CheckOutcome]:
    return [decide_claim_status(c) for c in checks]
