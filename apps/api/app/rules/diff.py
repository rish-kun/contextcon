"""What changed between two assessment versions, and why.

Every change points at the evidence (or the claims and criteria) that caused it,
so new evidence changes the assessment in the open (PRD principle 9).
"""

from __future__ import annotations

from app.domain.types import (
    AssessmentDiff,
    AssessmentVersion,
    CheckOutcome,
    ClaimChange,
    DispositionChange,
    EvidenceRef,
    JudgmentChange,
)
from app.rules.claim_status import status_label

_DECIDING_ROLES = frozenset({"decisive", "not_adequate", "related", "undecided"})


def _evidence(o: CheckOutcome | None) -> dict[str, EvidenceRef]:
    if o is None:
        return {}
    return {r.evidence_id: r for r in o.evidence if r.role in _DECIDING_ROLES}


def _label(status) -> str:
    return status_label(status) if status is not None else "absent"


def _claim_changes(old: AssessmentVersion, new: AssessmentVersion) -> list[ClaimChange]:
    before = {o.claim_id: o for o in old.outcomes}
    after = {o.claim_id: o for o in new.outcomes}
    order = list(dict.fromkeys([*before, *after]))
    changes: list[ClaimChange] = []
    for cid in order:
        b, a = before.get(cid), after.get(cid)
        if b is not None and a is not None and b.status == a.status:
            continue
        eb, ea = _evidence(b), _evidence(a)
        added = sorted(set(ea) - set(eb))
        removed = sorted(set(eb) - set(ea))
        if added:
            cause = "new evidence: " + "; ".join(
                f"{ea[e].source_label} ({ea[e].reliability.value})" for e in added
            )
        elif removed:
            cause = "evidence no longer used: " + "; ".join(eb[e].source_label for e in removed)
        elif old.policy_version != new.policy_version:
            cause = f"policy changed from {old.policy_version} to {new.policy_version}"
        else:
            cause = a.reason if a is not None else "claim removed"
        changes.append(
            ClaimChange(
                claim_id=cid,
                before=b.status if b else None,
                after=a.status if a else None,
                evidence_added=added,
                evidence_removed=removed,
                reason=f"{_label(b.status if b else None)} → {_label(a.status if a else None)} "
                f"because of {cause}",
            )
        )
    return changes


def _claims_in_checks(changes: list[ClaimChange], new: AssessmentVersion, old: AssessmentVersion):
    changed = {c.claim_id for c in changes}
    out: dict[str, list[str]] = {}
    for v in (old, new):
        for chk in v.judgments.evidence_sufficiency.checks:
            ids = [cid for cid in chk.claim_ids if cid in changed]
            if ids:
                out.setdefault(chk.check.value, [])
                out[chk.check.value] = list(dict.fromkeys(out[chk.check.value] + ids))
    return out


def _evidence_of(changes: list[ClaimChange], claim_ids: list[str]) -> list[str]:
    ids: list[str] = []
    for c in changes:
        if c.claim_id in claim_ids:
            ids += c.evidence_added + c.evidence_removed
    return list(dict.fromkeys(ids))


def _judgment_changes(
    old: AssessmentVersion, new: AssessmentVersion, claim_changes: list[ClaimChange]
) -> list[JudgmentChange]:
    out: list[JudgmentChange] = []
    oj, nj = old.judgments, new.judgments

    # Opportunity fit: which criteria evaluations changed.
    of, nf = oj.opportunity_fit, nj.opportunity_fit
    before_eval = {e.criterion_id: e for e in of.evaluations}
    changed_criteria = [
        e
        for e in nf.evaluations
        if e.criterion_id not in before_eval or before_eval[e.criterion_id].result != e.result
    ]
    because_fit = [e.criterion_id for e in changed_criteria] + [
        ev for e in changed_criteria for ev in e.evidence_ids
    ]
    for field in ("fit", "assessable_pct"):
        b, a = getattr(of, field), getattr(nf, field)
        if b != a:
            out.append(
                JudgmentChange(
                    judgment="opportunity_fit",
                    field=field,
                    before=b,
                    after=a,
                    because=list(dict.fromkeys(because_fit)),
                    reason="criteria changed: "
                    + (
                        ", ".join(f"{e.criterion_id} → {e.result.value}" for e in changed_criteria)
                        or "none (weights or criteria list changed)"
                    ),
                )
            )

    # Evidence sufficiency: which required checks moved, and the claims behind them.
    os_, ns = oj.evidence_sufficiency, nj.evidence_sufficiency
    per_check = _claims_in_checks(claim_changes, new, old)
    if os_.pct != ns.pct:
        moved = sorted(per_check)
        claim_ids = list(dict.fromkeys(cid for k in moved for cid in per_check[k]))
        out.append(
            JudgmentChange(
                judgment="evidence_sufficiency",
                field="pct",
                before=os_.pct,
                after=ns.pct,
                because=claim_ids + _evidence_of(claim_changes, claim_ids),
                reason="required checks affected: " + (", ".join(moved) or "company type changed"),
            )
        )

    # Business signals.
    ob = {s.label: s for s in oj.business.signals}
    nb = {s.label: s for s in nj.business.signals}
    for label in sorted(set(ob) | set(nb)):
        b, a = ob.get(label), nb.get(label)
        if b is not None and a is not None and b.value == a.value:
            continue
        out.append(
            JudgmentChange(
                judgment="business",
                field=label,
                before=b.value if b else None,
                after=a.value if a else None,
                because=list(a.evidence_ids if a else b.evidence_ids),
                reason="signal "
                + ("added" if b is None else "removed" if a is None else "changed"),
            )
        )

    # Financial assessment.
    ofa, nfa = oj.financial, nj.financial
    if ofa.assessed != nfa.assessed or ofa.figures != nfa.figures:
        out.append(
            JudgmentChange(
                judgment="financial",
                field="assessed",
                before=ofa.assessed,
                after=nfa.assessed,
                because=[f.evidence_id for f in (nfa.figures or ofa.figures)],
                reason=nfa.reason,
            )
        )
    return out


def diff(old: AssessmentVersion, new: AssessmentVersion) -> AssessmentDiff:
    claim_changes = _claim_changes(old, new)
    judgment_changes = _judgment_changes(old, new, claim_changes)
    disposition_change = None
    if old.disposition != new.disposition:
        because = list(dict.fromkeys(cid for j in judgment_changes for cid in j.because)) or [
            c.claim_id for c in claim_changes
        ]
        disposition_change = DispositionChange(
            before=old.disposition,
            after=new.disposition,
            because=because,
            reason=f"{old.judgments.disposition.rule} → {new.judgments.disposition.rule}: "
            + "; ".join(new.judgments.disposition.reasons),
        )
    return AssessmentDiff(
        from_version=old.version,
        to_version=new.version,
        policy_changed=old.policy_version != new.policy_version,
        inputs_changed=old.inputs_hash != new.inputs_hash,
        claim_changes=claim_changes,
        judgment_changes=judgment_changes,
        disposition_change=disposition_change,
    )
