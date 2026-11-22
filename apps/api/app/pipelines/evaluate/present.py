"""Stored assessment versions → the API contract (`AssessmentVersionOut`).

Every fact shown carries its source: evidence ids are resolved to `EvidenceOut` rows
with their source. An excerpt purged under retention comes back with `deleted=True`
and no quote, so an older version still explains itself instead of breaking.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.assessments import (
    AssessmentVersionOut,
    BusinessAssessmentOut,
    BusinessSignalOut,
    DiffLineOut,
    DispositionReasonOut,
    EvidenceSufficiencyOut,
    FinancialAssessmentOut,
    FinancialFigureOut,
    FitState,
    JudgmentsOut,
    OpportunityFitOut,
    ScreeningDispositionOut,
    SufficiencyItemOut,
)
from app.api.schemas.common import EstimateKind, EvidenceOut, FactStr, SourceClass, SourceRef
from app.api.schemas.theses import CriterionResultOut
from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Claim, Criterion, Evidence, Source
from app.domain.enums import CriterionKind
from app.domain.types import AssessmentDiff, AssessmentVersion, CheckSufficiency
from app.pipelines.evaluate.inputs import reliability_of
from app.pipelines.evaluate.service import stored_assessment
from app.rules import policy

NO_CRITERIA_NOTE = (
    "Fit unavailable: this case has no strategy criteria yet. Add them to get a fit score."
)
IDENTITY_NOTE = "No fit score while identity is unconfirmed."


def contract_class(value: str | None) -> SourceClass:
    """The contract's class equals the rule reliability (older plan names are mapped)."""
    return SourceClass(reliability_of(value).value)


def source_label(src: Source) -> str:
    return src.title or src.publisher or src.provider


def source_ref(src: Source) -> SourceRef:
    origin = (src.request or {}).get("origin_key") if isinstance(src.request, dict) else None
    return SourceRef(
        source_id=str(src.id),
        provider=src.provider,
        label=source_label(src),
        url_or_endpoint=src.endpoint_or_url,
        retrieved_at=src.retrieved_at,
        source_class=contract_class(src.source_class),
        origin_id=origin,
    )


def evidence_out(e: Evidence, src: Source) -> EvidenceOut:
    deleted = e.scrubbed_at is not None
    return EvidenceOut(
        evidence_id=str(e.id),
        source=source_ref(src),
        quote=None if deleted else e.span,
        page=e.page,
        field_path=e.field_path,
        value=None if deleted else e.value,
        as_of=e.as_of,
        deleted=deleted,
    )


def uuids(ids: Iterable[str]) -> list[uuid.UUID]:
    out = []
    for i in ids:
        try:
            out.append(uuid.UUID(str(i)))
        except ValueError:
            continue
    return out


@dataclass
class Lookups:
    """Rows a version refers to, loaded once per response."""

    evidence: dict[str, EvidenceOut] = field(default_factory=dict)
    claims: dict[str, str] = field(default_factory=dict)
    criteria: dict[str, str] = field(default_factory=dict)

    def chips(self, ids: Iterable[str]) -> list[EvidenceOut]:
        return [self.evidence[i] for i in dict.fromkeys(ids) if i in self.evidence]

    def fact(self, value: Any, ids: Iterable[str], **kw: Any) -> FactStr | None:
        for i in ids:
            ev = self.evidence.get(i)
            if ev is not None:
                text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
                return FactStr(value=text, source=ev.source, evidence_id=i, as_of=ev.as_of, **kw)
        return None


def _evidence_ids(a: AssessmentVersion, d: AssessmentDiff | None) -> set[str]:
    j = a.judgments
    ids = {i for e in j.opportunity_fit.evaluations for i in e.evidence_ids}
    ids |= {i for s in j.business.signals for i in s.evidence_ids}
    ids |= {f.evidence_id for f in j.financial.figures}
    ids |= {r.evidence_id for o in a.outcomes for r in o.evidence}
    if d is not None:
        ids |= {i for c in d.claim_changes for i in c.evidence_added + c.evidence_removed}
        ids |= {i for c in d.judgment_changes for i in c.because}
    return ids


async def load_lookups(
    session: AsyncSession, case_id: uuid.UUID, rows: list[VersionRow]
) -> Lookups:
    ev_ids: set[str] = set()
    for row in rows:
        d = (
            AssessmentDiff.model_validate(row.diff_from_previous)
            if row.diff_from_previous
            else None
        )
        ev_ids |= _evidence_ids(stored_assessment(row), d)
    lk = Lookups()
    wanted = uuids(ev_ids)
    if wanted:
        res = await session.execute(
            select(Evidence, Source)
            .join(Source, Source.id == Evidence.source_id)
            .where(Evidence.id.in_(wanted), Evidence.case_id == case_id)
        )
        lk.evidence = {str(e.id): evidence_out(e, s) for e, s in res.all()}
    claims = await session.execute(
        select(Claim.id, Claim.original_text).where(Claim.case_id == case_id)
    )
    lk.claims = {str(i): t for i, t in claims.all()}
    crit_ids = uuids(
        e.criterion_id
        for row in rows
        for e in stored_assessment(row).judgments.opportunity_fit.evaluations
    )
    if crit_ids:
        crit = await session.execute(
            select(Criterion.id, Criterion.label).where(Criterion.id.in_(crit_ids))
        )
        lk.criteria = {str(i): label for i, label in crit.all()}
    return lk


# --- Judgments -------------------------------------------------------------------------


def fit_state(a: AssessmentVersion) -> FitState:
    fit = a.judgments.opportunity_fit
    if a.judgments.disposition.rule == "identity_uncertain":
        return FitState.identity_unresolved
    if not fit.evaluations:
        return FitState.awaiting_strategy_criteria
    if fit.fit is None:
        return FitState.unavailable
    return FitState.scored


def opportunity_fit_out(a: AssessmentVersion, lk: Lookups) -> OpportunityFitOut:
    fit = a.judgments.opportunity_fit
    state = fit_state(a)
    note = {
        FitState.identity_unresolved: IDENTITY_NOTE,
        FitState.awaiting_strategy_criteria: NO_CRITERIA_NOTE,
    }.get(state, fit.label)
    return OpportunityFitOut(
        state=state,
        fit=fit.fit if state is FitState.scored else None,
        assessable_pct=fit.assessable_pct,
        note=note,
        criterion_results=[
            CriterionResultOut(
                criterion_id=e.criterion_id,
                label=lk.criteria.get(e.criterion_id, e.criterion_id),
                kind=e.kind.value,
                weight=policy.CRITERION_WEIGHTS[CriterionKind(e.kind)],
                state=e.result.value,
                reason=e.reason,
                evidence=lk.chips(e.evidence_ids),
            )
            for e in fit.evaluations
        ],
    )


def _sufficiency_item(c: CheckSufficiency) -> SufficiencyItemOut:
    return SufficiencyItemOut(
        category=c.check.value,
        status=c.result.value if c.result is not None else None,
        claim_ids=list(c.claim_ids),
        settle_with="; ".join(c.settle_with) or None,
        note=c.gap,
    )


def judgments_out(a: AssessmentVersion, lk: Lookups) -> JudgmentsOut:
    j = a.judgments
    s = j.evidence_sufficiency
    signals = []
    for sig in j.business.signals:
        fact = lk.fact(
            sig.value,
            sig.evidence_ids,
            is_estimate=True,
            estimate_kind=EstimateKind.signal,
            estimate_basis=j.business.note,
        )
        if fact is not None:  # a signal without a resolvable source is not shown
            signals.append(BusinessSignalOut(label=sig.label, fact=fact))
    figures = []
    for f in j.financial.figures:
        fact = lk.fact(f.value, [f.evidence_id])
        if fact is not None:
            figures.append(
                FinancialFigureOut(
                    label=f.component.replace("_", " "),
                    fact=fact,
                    assumption="; ".join(j.financial.assumptions) or None,
                )
            )
    return JudgmentsOut(
        opportunity_fit=opportunity_fit_out(a, lk),
        evidence_sufficiency=EvidenceSufficiencyOut(
            pct=s.pct,
            required_categories=[c.check.value for c in s.checks],
            settled=[_sufficiency_item(c) for c in s.checks if c.adequate],
            gaps=[_sufficiency_item(c) for c in s.checks if not c.adequate],
        ),
        business_assessment=BusinessAssessmentOut(
            assessed=bool(signals),
            reason=None if signals else "No operating signals on record",
            signals=signals,
        ),
        financial_assessment=FinancialAssessmentOut(
            assessed=j.financial.assessed and bool(figures),
            reason=None if (j.financial.assessed and figures) else j.financial.reason,
            would_need=[] if j.financial.assessed else [policy.DOC_FINANCIALS],
            figures=figures,
        ),
        screening_disposition=ScreeningDispositionOut(
            disposition=a.disposition.value,
            reasons=[DispositionReasonOut(text=r) for r in j.disposition.reasons],
        ),
    )


# --- Diff ------------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def diff_lines(d: AssessmentDiff, lk: Lookups) -> list[DiffLineOut]:
    lines: list[DiffLineOut] = []
    for c in d.claim_changes:
        lines.append(
            DiffLineOut(
                kind="claim",
                subject=lk.claims.get(c.claim_id, f"Claim {c.claim_id}"),
                subject_id=c.claim_id,
                before=c.before.value if c.before else None,
                after=c.after.value if c.after else "removed",
                because=c.reason,
                evidence=lk.chips(c.evidence_added + c.evidence_removed),
            )
        )
    for j in d.judgment_changes:
        lines.append(
            DiffLineOut(
                kind="judgment",
                subject=f"{j.judgment.replace('_', ' ')}: {j.field.replace('_', ' ')}",
                before=_text(j.before),
                after=_text(j.after) or "none",
                because=j.reason or "inputs changed",
                evidence=lk.chips(j.because),
            )
        )
    if d.disposition_change is not None:
        dc = d.disposition_change
        lines.append(
            DiffLineOut(
                kind="disposition",
                subject="Screening disposition",
                before=dc.before.value,
                after=dc.after.value,
                because=dc.reason,
            )
        )
    if not lines and d.policy_changed:
        lines.append(
            DiffLineOut(
                kind="judgment",
                subject="Scoring policy",
                after="updated",
                because="the scoring policy changed; no judgment moved",
            )
        )
    return lines


def version_out(row: VersionRow, lk: Lookups) -> AssessmentVersionOut:
    a = stored_assessment(row)
    d = AssessmentDiff.model_validate(row.diff_from_previous) if row.diff_from_previous else None
    return AssessmentVersionOut(
        id=str(row.id),
        version=row.version,
        created_at=row.created_at,
        policy_version=row.policy_version,
        inputs_hash=row.inputs_hash,
        trigger=row.trigger,
        company_type=a.company_type.company_type.value,
        judgments=judgments_out(a, lk),
        diff_from_previous=diff_lines(d, lk) if d is not None else None,
    )


async def list_versions_out(
    session: AsyncSession, case_id: uuid.UUID, rows: list[VersionRow]
) -> list[AssessmentVersionOut]:
    lk = await load_lookups(session, case_id, rows)
    return [version_out(r, lk) for r in rows]
