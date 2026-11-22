"""Claim status: a declarative rule table (``policy.COMPONENT_RULES``) applied
component by component, then combined with a fixed precedence.

Precedence (first that applies wins, design §6.3):
  1. not_checked             the check did not run (always with a reason), or
                             the claim has no corroborated entity
  2. conflicting_evidence    adequate independent origins disagree on some component
  3. contradicted            adequate evidence conflicts with some component and
                             none supports it
  4. supported               every component is matched by adequate evidence
  5. partially_corroborated  some components matched, the rest unsettled
  6. cannot_verify           nothing adequate settles any component
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    ComponentState,
    NotCheckedReason,
    SourceReliability,
    ValueKind,
)
from app.domain.types import (
    CheckOutcome,
    Claim,
    ClaimCheck,
    ClaimComponent,
    ComponentFinding,
    EvidenceRef,
    ExtractedFact,
)
from app.rules import policy
from app.rules.compare import Relation, compare, contains_phrase, normalize_text
from app.rules.standards import standards_in
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


def _not_checked(
    check: ClaimCheck,
    reason: NotCheckedReason | None = None,
    detail: str | None = None,
    refs: list[EvidenceRef] | None = None,
) -> CheckOutcome:
    claim = check.claim
    reason = reason or check.not_run_reason
    detail = detail if detail is not None else check.not_run_detail
    detail_text = f" ({detail})" if detail else ""
    docs = _dedupe([document_for(c.name, claim) for c in claim.components]) or [
        policy.CATEGORY_DOCUMENTS[claim.category]
    ]
    return CheckOutcome(
        claim_id=claim.id,
        category=claim.category,
        status=ClaimStatus.NOT_CHECKED,
        reason=f"Not checked: {reason.value.replace('_', ' ')}{detail_text}.",
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
        evidence=refs or [],
        not_checked_reason=reason,
        analyst_retry=reason.value in ANALYST_RETRY_REASONS,
    )


def claimed_stage(text: str) -> str:
    """The stage a dated-event claim asserts when it has no stage component:
    "planned" for future wording, otherwise "operating" (it happened)."""
    tokens = normalize_text(text).split()
    future = ("will", "plan", "planned", "plans", "to open", "upcoming", "proposed", "expect")
    if any(_starts_cue(tokens, f) for f in future):
        return "planned"
    return "operating"


def _starts_cue(tokens: list[str], cue: str) -> bool:
    words = cue.split()
    for i in range(len(tokens) - len(words) + 1):
        if tokens[i : i + len(words) - 1] == words[:-1] and tokens[i + len(words) - 1].startswith(
            words[-1]
        ):
            return True
    return False


def today() -> date:
    """The date a present-tense claim ("is certified") is checked against."""
    return date.today()


def effective_components(claim: Claim) -> list[ClaimComponent]:
    """The components a claim is checked on. A dated-event claim always
    asserts whether the event happened, so a missing stage is added from its
    wording: an announcement alone can then never make it supported.

    A compliance claim asserts each standard it names and that the certificate
    is current: a `certification` naming several standards is checked once per
    standard, and `certificate_valid_until` (on or after today) is added, so an
    expired certificate contradicts the claim."""
    comps = list(claim.components)
    if claim.category is ClaimCategory.DATED_EVENT and not any(c.name == "stage" for c in comps):
        comps.append(ClaimComponent(name="stage", value=claimed_stage(claim.text)))
    if claim.category is ClaimCategory.COMPLIANCE:
        comps = _compliance_components(comps)
    return comps


def _compliance_components(comps: list[ClaimComponent]) -> list[ClaimComponent]:
    """One `certification` per standard, each with its own validity component scoped
    to that standard: a current ISO 9001 record says nothing about ISO 27001."""
    out: list[ClaimComponent] = []
    for c in comps:
        found = standards_in(c.value) if c.name == "certification" else []
        if len(found) > 1:
            out.extend(ClaimComponent(name=c.name, value=s.display) for s in found)
        else:
            out.append(c)
    if any(c.name == "certificate_valid_until" for c in out):
        return out  # the claim states its own validity date
    on = today().isoformat()
    for c in [c for c in out if c.name == "certification"]:
        out.append(
            ClaimComponent(name="certificate_valid_until", value=on, op="gte", scope=str(c.value))
        )
    return out


def _scoped(
    relevant: list[ExtractedFact], standard: str, valid: list[ExtractedFact]
) -> list[ExtractedFact]:
    """Validity facts from origins that also state `standard` (a certification fact
    from the same origin that names it). A validity date with no standard beside it
    settles nothing."""
    origins = {
        f.evidence.source.origin
        for f in valid
        if f.component == "certification"
        and compare(ValueKind.STANDARD, standard, "eq", f.value) == "match"
    }
    return [f for f in relevant if f.evidence.source.origin in origins]


def _origin_adequacy(
    rule: policy.ComponentRule, eff: SourceReliability, group: list[ExtractedFact]
) -> tuple[bool, str]:
    """Is this origin adequate for this question? (adequate, caveat)."""
    if eff not in rule.adequate:
        return False, rule.caveats.get(eff, "")
    allowed = rule.document_types.get(eff)
    if allowed is not None:
        types = {f.evidence.source.document_type for f in group}
        if not types <= allowed:
            have = ", ".join(sorted(t.value if t else "generic document" for t in types))
            need = ", ".join(sorted(t.value for t in allowed))
            return False, (
                f"A seller document of type {have} cannot settle this; it needs one of: {need}"
            )
    if eff in rule.needs_date and any(f.evidence.as_of is None for f in group):
        return False, "The document must be dated to settle this"
    return True, ""


def _values_disagree(kind, groups: list[list[ExtractedFact]]) -> bool:
    """Do these origins state values that conflict with each other?"""
    values = [g[0].value for g in groups]
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            if compare(kind, a, "eq", b) == "conflict":
                return True
    return False


def decide_claim_status(check: ClaimCheck) -> CheckOutcome:
    """Decide one claim's status from its facts. Pure and order-independent."""
    if not check.ran:
        return _not_checked(check)

    claim = check.claim
    components = effective_components(claim)
    claimed = {c.name: c.value for c in components}
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

    # A claim with no corroborated entity cannot accept any fact: the check
    # is identity-dependent and stays not checked (design §5.4).
    if not claim.entity_ids:
        return _not_checked(
            check,
            NotCheckedReason.IDENTITY_UNRESOLVED,
            "no corroborated entity to attach evidence to",
            refs,
        )

    findings: list[ComponentFinding] = []
    notes: list[str] = []
    claim_component_names = set(claimed)

    for comp in components:
        rule = policy.COMPONENT_RULES.get(comp.name)
        check_cat = _check_of(comp.name, claim)
        relevant = [f for f in valid if f.component == comp.name]
        if comp.scope is not None:
            relevant = _scoped(relevant, comp.scope, valid)
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

        decisive: list[tuple[Relation, str, list[ExtractedFact], SourceReliability]] = []
        for origin in sorted(by_origin):
            group = by_origin[origin]
            eff = _effective_class(group)
            adequate, caveat = _origin_adequacy(rule, eff, group)
            if not adequate:
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
                decisive.append((decided.pop(), origin, group, eff))
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

        # 3. Every adequate independent origin counts, whatever its tier: a
        #    registry and a registry mirror that disagree are conflicting
        #    evidence, never silently resolved by rank.
        relations = {rel for rel, _, _, _ in decisive}
        if relations == {"match"}:
            state = ComponentState.MATCHED
        elif "match" in relations:
            state = ComponentState.CONFLICTING
        elif _values_disagree(rule.kind, [g for _, _, g, _ in decisive]):
            state = ComponentState.CONFLICTING
        else:
            state = ComponentState.CONTRADICTED

        classes = sorted({eff for _, _, _, eff in decisive}, key=lambda r: r.value)
        announcement_only = classes == [SourceReliability.COMPANY_ANNOUNCEMENT]
        decisive_ids: list[str] = []
        for rel, _, group, eff in decisive:
            ref_note = rel
            if eff is SourceReliability.COMPANY_ANNOUNCEMENT:
                ref_note = f"{rel}; {policy.ANNOUNCEMENT_CAVEAT}"
            for f in group:
                decisive_ids.append(f.evidence.id)
                refs.append(_ref(f, "decisive", ref_note))
        origins = len(decisive)
        summary = {
            ComponentState.MATCHED: "matched",
            ComponentState.CONTRADICTED: "contradicted",
            ComponentState.CONFLICTING: "sources disagree",
        }[state]
        labels = ", ".join(sorted({g[0].evidence.source.label for _, _, g, _ in decisive}))
        note = f"{summary} by {labels} ({origins} independent origin{'s' if origins != 1 else ''})"
        if announcement_only and state is ComponentState.MATCHED:
            note += ": announced only, which shows it was announced, not that it happened"
        findings.append(
            ComponentFinding(
                component=comp.name,
                check=check_cat,
                state=state,
                decisive_evidence_ids=_dedupe(decisive_ids),
                note=note,
                provenance=classes,
                announcement_only=announcement_only,
            )
        )
        notes.append(f"{comp.name}: {note}.")

    # 4. Related facts: same check, component not in the claim (for example a
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
    capped = status is ClaimStatus.SUPPORTED and _self_statement_only(claim, findings)
    if capped:
        # The company's own page shows that it says so, not that the other party
        # (partner, certifier, registry) confirms it (policy.SELF_STATEMENT_CAPPED).
        status = ClaimStatus.PARTIALLY_CORROBORATED
        notes.append(f"{policy.SELF_STATEMENT_CAVEAT}.")
    unsettled_docs = [
        document_for(f.component, claim)
        for f in findings
        if f.state is not ComponentState.MATCHED or capped
    ]
    if status is ClaimStatus.SUPPORTED:
        settle: list[str] = []
    else:
        settle = _dedupe(unsettled_docs) or [policy.CATEGORY_DOCUMENTS[claim.category]]

    headline = status_label(status)
    if not components:
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


def _self_statement_only(claim: Claim, findings: list[ComponentFinding]) -> bool:
    if claim.category not in policy.SELF_STATEMENT_CAPPED:
        return False
    matched = [f for f in findings if f.state is ComponentState.MATCHED]
    return bool(matched) and all(f.announcement_only for f in matched)


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


def combine_states(states: list[ComponentState]) -> ClaimStatus:
    """Compound aggregation, first match wins: conflicting evidence before
    contradicted (design §6.3), then supported, partial, cannot verify."""
    if not states:
        return ClaimStatus.CANNOT_VERIFY
    if ComponentState.CONFLICTING in states:
        return ClaimStatus.CONFLICTING_EVIDENCE
    if ComponentState.CONTRADICTED in states:
        return ClaimStatus.CONTRADICTED
    if all(s is ComponentState.MATCHED for s in states):
        return ClaimStatus.SUPPORTED
    if ComponentState.MATCHED in states:
        return ClaimStatus.PARTIALLY_CORROBORATED
    return ClaimStatus.CANNOT_VERIFY


_combine = combine_states


def decide_all(checks: list[ClaimCheck]) -> list[CheckOutcome]:
    return [decide_claim_status(c) for c in checks]
