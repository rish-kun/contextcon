"""The screening memo for one assessment version (`docs/content/memo-template.md`).

Two kinds of section content:
- drafted prose, stored with the version when it was created, restating only cited
  accepted facts (`app.pipelines.memo.drafting`);
- deterministic lines built here from the stored assessment, so the same version
  always renders the same memo. Claim wording and excerpts are resolved when read, so
  text deleted under retention shows as deleted (with its record) rather than living on
  in the memo.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.cases import (
    CaseMemoOut,
    ComparablesOut,
    EventOut,
    MemoCitationOut,
    MemoLineOut,
    MemoSectionOut,
    RiskItemOut,
)
from app.db.models import AssessmentVersion as VersionRow
from app.db.models import Evidence, Source
from app.domain.enums import ClaimStatus, CompanyType, CriterionResult, Disposition
from app.domain.types import AssessmentDiff, AssessmentVersion
from app.pipelines.evaluate.present import Lookups, evidence_out, fit_state, uuids
from app.pipelines.evaluate.snapshot import Snapshot
from app.pipelines.memo.records import Retention, deletion_out
from app.rules.claim_status import status_label

STATUS_ORDER = [
    ClaimStatus.SUPPORTED,
    ClaimStatus.PARTIALLY_CORROBORATED,
    ClaimStatus.CONFLICTING_EVIDENCE,
    ClaimStatus.CONTRADICTED,
    ClaimStatus.CANNOT_VERIFY,
    ClaimStatus.NOT_CHECKED,
]
DISPOSITION_LABELS = {
    Disposition.PRIORITISE: "Prioritise",
    Disposition.INVESTIGATE_FURTHER: "Investigate further",
    Disposition.DEPRIORITISE: "Deprioritise",
    Disposition.CANNOT_ASSESS: "Cannot assess",
}
NEXT_ACTIONS = {
    Disposition.PRIORITISE: "Move to formal due diligence, and confirm the remaining items "
    "in section 9 with the seller.",
    Disposition.INVESTIGATE_FURTHER: "Request the documents in section 9 from the seller, then "
    "re-run the assessment when they arrive.",
    Disposition.DEPRIORITISE: "Do not pursue under this thesis unless the failed requirement "
    "changes; keep the reasons on file.",
    Disposition.CANNOT_ASSESS: "Resolve what is blocking the assessment first (the company's "
    "identity, or strategy criteria for the fit score), then re-run it.",
}
LENS = {
    CompanyType.STARTUP: "Evaluated as an early-stage business on thesis fit, founder "
    "relevance, team development, and funding history.",
    CompanyType.ESTABLISHED: "Evaluated as an established business on strategic fit, "
    "identity, operating scale, financial performance, commercial position, and leadership "
    "continuity.",
}
SCOPE_NOTICE = (
    "First-pass screening before formal due diligence. Every finding rests on the dated "
    "sources recorded at the end of this memo."
)
FIT_CAVEAT = "Fit measures match to your criteria. It says nothing about returns."
CLAIMS_FOOTNOTE = (
    "Cannot verify is a finished screening result where available records cannot settle the "
    "question. Not checked indicates that a check did not run and is excluded from settled "
    "counts."
)
EVENTS_NONE = "No recent dated public events were returned on record for this confirmed entity."
EVENTS_PLANS = (
    "Company announcements describing planned launches or expansions are worded as plans "
    "unless independent records confirm execution."
)
COMPARABLES_NONE = (
    "DealProof does not substitute a weaker peer list when records do not support a fair "
    "comparison."
)
FINANCIAL_NONE = (
    "Public records for private companies do not provide complete current financial "
    "statements, and no audited statements were supplied for this case. DealProof does not "
    "fill missing financial inputs with guesses."
)
FINANCIAL_SCOPE = (
    "These figures are as reported in the cited documents under the stated assumptions. They "
    "are not a valuation, a verified fair value, or financial due diligence."
)
RISKS_NOTE = "Missing information is stated plainly and is not treated as negative performance."
RISKS_NONE = (
    "No material risks were identified within the sources checked. Refer to unknowns and any "
    "Not checked items below."
)
DECISION_NOTE = (
    "This disposition is produced by stated rules under Policy {policy} from the records "
    "attached to this case. It is a first-pass screening recommendation, not a prediction of "
    "returns, legal advice, or formal due diligence."
)
SOURCES_NOTE = (
    "Complete record of every source used in this case so all findings can be audited and "
    "reproduced."
)
NO_REQUEST = "No seller request is required at this stage."


@dataclass
class MemoContext:
    """Read-time material the memo resolves: wording, chips, live sections."""

    lookups: Lookups
    claim_numbers: dict[str, int]
    thesis_text: str | None = None
    company_name: str = ""
    events: list[EventOut] = field(default_factory=list)
    comparables: ComparablesOut | None = None
    retention: Retention = field(default_factory=Retention)
    retention_notice: str | None = None
    cost_line: str | None = None
    source_count: int = 0


def _claim_ref(ctx: MemoContext, claim_id: str) -> str:
    n = ctx.claim_numbers.get(claim_id)
    text = ctx.lookups.claims.get(claim_id, "")
    return f'Claim {n} ("{text}")' if n else f'"{text}"'


# --- Risks (also CaseDetail.risks) -------------------------------------------------


def risk_items(a: AssessmentVersion, ctx: MemoContext) -> list[RiskItemOut]:
    items: list[RiskItemOut] = []
    for o in a.outcomes:
        if o.status in (ClaimStatus.CONTRADICTED, ClaimStatus.CONFLICTING_EVIDENCE):
            items.append(
                RiskItemOut(
                    kind="risk",
                    text=f"{_claim_ref(ctx, o.claim_id)}: {status_label(o.status)}. {o.reason}",
                    claim_ids=[o.claim_id],
                )
            )
    for o in a.outcomes:
        if o.status is ClaimStatus.NOT_CHECKED:
            items.append(
                RiskItemOut(
                    kind="not_checked",
                    text=f"{_claim_ref(ctx, o.claim_id)}: Not checked. {o.reason}",
                    claim_ids=[o.claim_id],
                )
            )
    for c in a.judgments.evidence_sufficiency.checks:
        if c.gap:
            settle = f" Would settle it: {'; '.join(c.settle_with)}." if c.settle_with else ""
            items.append(
                RiskItemOut(kind="gap", text=f"{c.gap}.{settle}", claim_ids=list(c.claim_ids))
            )
    for s in a.judgments.business.signals:
        if "estimate" in s.label.casefold() or "signal" in s.label.casefold():
            items.append(
                RiskItemOut(
                    kind="estimate_used",
                    text=f"{s.label}: {s.value}. {a.judgments.business.note}",
                )
            )
    for assumption in a.judgments.financial.assumptions:
        items.append(RiskItemOut(kind="assumption", text=assumption))
    for label in a.candidate.unknown_criteria:
        items.append(RiskItemOut(kind="gap", text=f"Criterion unknown: {label}."))
    return items


# --- Sections --------------------------------------------------------------------


def _line(text: str, **kw) -> MemoLineOut:  # noqa: ANN003
    return MemoLineOut(text=text, **kw)


def _summary(a: AssessmentVersion, ctx: MemoContext) -> MemoSectionOut:
    j = a.judgments
    fit = j.opportunity_fit
    state = fit_state(a).value
    if state == "scored":
        fit_text = f"Opportunity fit: Fit {fit.fit} · {fit.assessable_pct}% of criteria assessable"
    else:
        fit_text = f"Opportunity fit: unavailable ({state.replace('_', ' ')})"
    checks = j.evidence_sufficiency.checks
    settled = sum(1 for c in checks if c.adequate)
    not_checked = [o for o in a.outcomes if o.status is ClaimStatus.NOT_CHECKED]
    lines = [
        _line(f"Screening disposition: {DISPOSITION_LABELS[a.disposition]}"),
        *[_line(f"Reason: {r}") for r in j.disposition.reasons],
        _line(fit_text),
        _line(
            f"Evidence sufficiency: {settled} of {len(checks)} checks settled · "
            f"{len(not_checked)} not checked"
        ),
    ]
    if not_checked:
        reasons = sorted(
            {(o.not_checked_reason or "unknown").replace("_", " ") for o in not_checked}
        )
        lines.append(
            _line(
                f"{len(not_checked)} checks were not run ({', '.join(reasons)}). Results are "
                "incomplete where marked Not checked.",
                kind="not_checked",
                claim_ids=[o.claim_id for o in not_checked],
            )
        )
    if ctx.cost_line:
        lines.append(_line(f"Case cost: {ctx.cost_line}"))
    return MemoSectionOut(
        key="summary", heading="Summary", lines=lines, notes=[FIT_CAVEAT, SCOPE_NOTICE]
    )


def _changes(row: VersionRow, d: AssessmentDiff, ctx: MemoContext) -> MemoSectionOut:
    lines = []
    for c in d.claim_changes:
        before = status_label(c.before) if c.before else "absent"
        after = status_label(c.after) if c.after else "removed"
        lines.append(
            _line(
                f"{_claim_ref(ctx, c.claim_id)}: {before} → {after}. Because: {c.reason}",
                claim_ids=[c.claim_id],
            )
        )
    for j in d.judgment_changes:
        lines.append(
            _line(f"{j.judgment.replace('_', ' ')} ({j.field}): {j.before} → {j.after}. {j.reason}")
        )
    if d.disposition_change is not None:
        dc = d.disposition_change
        lines.append(
            _line(
                f"Screening disposition: {DISPOSITION_LABELS[dc.before]} → "
                f"{DISPOSITION_LABELS[dc.after]}. Because: {dc.reason}"
            )
        )
    unchanged = len(ctx.claim_numbers) - len({c.claim_id for c in d.claim_changes})
    return MemoSectionOut(
        key="changes",
        heading=f"What changed since version {d.from_version}",
        lines=lines,
        notes=[
            f"Updated on {row.created_at.date().isoformat()} ({row.trigger}). Version "
            f"{d.from_version} remains archived and readable in full.",
            f"{max(unchanged, 0)} claims unchanged since version {d.from_version}.",
        ],
    )


def _drafted(stored: dict, key: str) -> tuple[str | None, bool]:
    entry = (stored.get("drafted") or {}).get(key)
    if not entry:
        return None, False
    return entry.get("text") or None, bool(entry.get("used_fallback"))


def _opportunity(a: AssessmentVersion, stored: dict, ctx: MemoContext) -> MemoSectionOut:
    text, fallback = _drafted(stored, "relevance")
    lines = [_line(f"Investment thesis: {ctx.thesis_text}")] if ctx.thesis_text else []
    groups = {r: [] for r in CriterionResult}
    for e in a.candidate.fit.evaluations:
        groups[e.result].append(ctx.lookups.criteria.get(e.criterion_id, e.criterion_id))
    for result, word in (
        (CriterionResult.PASS, "met"),
        (CriterionResult.FAIL, "not met"),
        (CriterionResult.UNKNOWN, "unknown"),
    ):
        names = groups[result]
        lines.append(_line(f"Criteria {word} ({len(names)}): {', '.join(names) or 'none'}"))
    notes = [LENS[a.company_type.company_type]]
    if not a.candidate.fit.evaluations:
        notes.insert(0, "No strategy criteria yet: fit is unavailable until they are added.")
    return MemoSectionOut(
        key="opportunity",
        number=1,
        heading="The opportunity",
        drafted_text=text,
        used_fallback=fallback,
        lines=lines,
        notes=notes,
    )


def _identity(a: AssessmentVersion, stored: dict, ctx: MemoContext) -> MemoSectionOut:
    if a.judgments.disposition.rule == "identity_uncertain":
        return MemoSectionOut(
            key="identity",
            number=2,
            heading="Identity and profile",
            lines=[
                _line(
                    "Identity unresolved. DealProof did not attach unconfirmed records. "
                    "Screening disposition remains Cannot assess until the entity is confirmed.",
                    kind="gap",
                )
            ],
        )
    text, fallback = _drafted(stored, "profile")
    lines = [_line("Identity confirmed.")]
    for s in a.judgments.business.signals:
        lines.append(_line(f"{s.label}: {s.value}", kind="signal"))
    return MemoSectionOut(
        key="identity",
        number=2,
        heading="Identity and profile",
        drafted_text=text,
        used_fallback=fallback,
        lines=lines,
        notes=[
            "Records in this case were attached using verified identifiers, not on a matching "
            "name alone.",
            "Operating signals and profile-based headcount estimates are indirect indicators. "
            "They are not payroll counts and are never treated as proof of revenue.",
        ],
    )


def _claims(a: AssessmentVersion, ctx: MemoContext) -> MemoSectionOut:
    counts = Counter(o.status for o in a.outcomes)
    summary = " · ".join(f"{counts.get(s, 0)} {status_label(s)}" for s in STATUS_ORDER)
    ordered = sorted(a.outcomes, key=lambda o: ctx.claim_numbers.get(o.claim_id, 10**6))
    lines = [_line(f"Summary: {summary}.")]
    for o in ordered:
        settle = "; ".join(o.settle_with) or "-"
        text = f"{_claim_ref(ctx, o.claim_id)}: {status_label(o.status)}. {o.reason}"
        if o.status is ClaimStatus.NOT_CHECKED:
            text += " No search was run for this claim."
        lines.append(
            _line(
                f"{text} What would settle it: {settle}.",
                claim_ids=[o.claim_id],
                kind="not_checked" if o.status is ClaimStatus.NOT_CHECKED else None,
            )
        )
    return MemoSectionOut(
        key="claims", number=3, heading="Claims", lines=lines, notes=[CLAIMS_FOOTNOTE]
    )


def _events(ctx: MemoContext) -> MemoSectionOut:
    events = sorted(ctx.events, key=lambda e: e.event_date, reverse=True)
    lines = [
        _line(f"{e.event_date.isoformat()}: {e.title} ({e.kind})", kind="event") for e in events
    ]
    return MemoSectionOut(
        key="events",
        number=4,
        heading="Recent events",
        lines=lines,
        notes=[EVENTS_PLANS] if lines else [EVENTS_NONE],
    )


def _comparables(ctx: MemoContext) -> MemoSectionOut:
    comp = ctx.comparables
    if comp is None or not comp.companies:
        reason = (comp.no_fair_comparison_reason if comp else None) or (
            "No comparison has been run for this case."
        )
        return MemoSectionOut(
            key="comparables",
            number=5,
            heading="Comparable companies",
            lines=[_line(f"No fair comparison found. {reason}")],
            notes=[COMPARABLES_NONE],
        )
    basis = comp.basis
    return MemoSectionOut(
        key="comparables",
        number=5,
        heading="Comparable companies",
        lines=[_line(f"{c.name}: {c.observation.value}") for c in comp.companies],
        notes=[
            f"Basis of comparison: {basis.industry or '?'}, {basis.country or '?'}, headcount "
            f"{basis.headcount_band or '?'}. Informational only: comparables are not scored."
        ],
    )


def _financial(a: AssessmentVersion) -> MemoSectionOut:
    f = a.judgments.financial
    if not f.assessed:
        return MemoSectionOut(
            key="financial",
            number=6,
            heading="Financial evaluation",
            lines=[
                _line("Not assessed · no reliable financial inputs.", kind="gap"),
                _line("Would need: Audited financial statements and current management accounts."),
            ],
            notes=[FINANCIAL_NONE],
        )
    lines = [
        _line(
            f"{x.component.replace('_', ' ')}: {x.value}"
            + (f" (as of {x.as_of.isoformat()})" if x.as_of else "")
            + f", {x.source_label}"
        )
        for x in f.figures
    ]
    lines += [_line(f"Assumption: {x}", kind="assumption") for x in f.assumptions]
    return MemoSectionOut(
        key="financial",
        number=6,
        heading="Financial evaluation",
        lines=lines,
        notes=[FINANCIAL_SCOPE],
    )


def _risks(items: list[RiskItemOut]) -> MemoSectionOut:
    lines = [_line(i.text, kind=i.kind, claim_ids=i.claim_ids) for i in items]
    if not any(i.kind in ("risk", "not_checked") for i in items):
        lines.insert(0, _line(RISKS_NONE))
    return MemoSectionOut(
        key="risks",
        number=7,
        heading="Risks, assumptions and unknowns",
        lines=lines,
        notes=[RISKS_NOTE],
    )


def _next_step(a: AssessmentVersion) -> MemoSectionOut:
    lines = [
        _line(f"Disposition: {DISPOSITION_LABELS[a.disposition]} (Policy {a.policy_version})"),
        *[_line(f"{i}. {r}") for i, r in enumerate(a.judgments.disposition.reasons, start=1)],
        _line(f"Recommended action: {NEXT_ACTIONS[a.disposition]}"),
    ]
    return MemoSectionOut(
        key="next_step",
        number=8,
        heading="Recommended next step",
        lines=lines,
        notes=[DECISION_NOTE.format(policy=a.policy_version)],
    )


def _requests(a: AssessmentVersion, ctx: MemoContext) -> MemoSectionOut:
    lines = []
    for i, item in enumerate(a.requests.documents, start=1):
        refs = ", ".join(_claim_ref(ctx, c) for c in item.claim_ids) or "open questions"
        lines.append(_line(f"{i}. {item.document} — settles {refs}", claim_ids=item.claim_ids))
    retries = [r for r in a.requests.analyst_retries]
    for r in retries:
        lines.append(
            _line(
                f"To re-run on our side (not sent to the seller): {_claim_ref(ctx, r.claim_id)} "
                f"({r.reason.value.replace('_', ' ')})",
                kind="not_checked",
                claim_ids=[r.claim_id],
            )
        )
    return MemoSectionOut(
        key="requests",
        number=9,
        heading="Information to request from the seller",
        lines=lines or [_line(NO_REQUEST)],
        notes=["The following documents would settle the open claims in this case."]
        if a.requests.documents
        else [],
    )


def _sources(ctx: MemoContext) -> MemoSectionOut:
    notes = [SOURCES_NOTE, f"{ctx.source_count} sources on record; see the source record."]
    if ctx.retention_notice:
        notes.append(f"Confidentiality: {ctx.retention_notice}")
    return MemoSectionOut(key="sources", number=10, heading="Sources", notes=notes)


# --- Citations -------------------------------------------------------------------


async def citations_out(
    session: AsyncSession, case_id: uuid.UUID, stored: dict, ret: Retention
) -> list[MemoCitationOut]:
    cites: dict[str, str] = stored.get("citations") or {}
    if not cites:
        return []
    rows = await session.execute(
        select(Evidence, Source)
        .join(Source, Source.id == Evidence.source_id)
        .where(Evidence.id.in_(uuids(cites.values())), Evidence.case_id == case_id)
    )
    found = {str(e.id): (e, s) for e, s in rows.all()}
    out = []
    for n, cid in enumerate(sorted(cites, key=lambda c: int(c[1:])), start=1):
        pair = found.get(cites[cid])
        ev = evidence_out(*pair) if pair else None
        record = ret.for_object(cites[cid])
        if record is None and pair is not None and pair[1].document_id is not None:
            record = ret.for_object(pair[1].document_id)
        deleted = ev is None or ev.deleted
        out.append(
            MemoCitationOut(
                id=cid,
                number=n,
                evidence=ev,
                deletion=deletion_out(record, cites[cid]) if (record and deleted) else None,
            )
        )
    return out


async def memo_out(session: AsyncSession, snap: Snapshot, ctx: MemoContext) -> CaseMemoOut:
    row, a, d = snap.row, snap.assessment, snap.diff
    stored = (row.judgments or {}).get("memo") or {}
    sections = [_summary(a, ctx)]
    if d is not None:
        sections.append(_changes(row, d, ctx))
    sections += [
        _opportunity(a, stored, ctx),
        _identity(a, stored, ctx),
        _claims(a, ctx),
        _events(ctx),
        _comparables(ctx),
        _financial(a),
        _risks(risk_items(a, ctx)),
        _next_step(a),
        _requests(a, ctx),
        _sources(ctx),
    ]
    return CaseMemoOut(
        assessment_version=row.version,
        assessment_version_id=str(row.id),
        policy_version=row.policy_version,
        generated_at=row.created_at,
        title=ctx.company_name,
        sections=sections,
        citations=await citations_out(session, row.case_id, stored, ctx.retention),
        retention_notice=ctx.retention_notice,
    )
