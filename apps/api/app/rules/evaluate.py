"""Evaluate: five separate judgments and the screening disposition.

The judgments are never blended into one score. ``assess`` is the single entry
point that turns case inputs into an immutable ``AssessmentVersion``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from datetime import timedelta

from app.domain.enums import (
    ClaimCategory,
    ClaimStatus,
    CompanyType,
    ComponentState,
    CriterionKind,
    CriterionOperator,
    CriterionResult,
    Disposition,
    IdentityStatus,
    SourceReliability,
    ValueKind,
)
from app.domain.types import (
    AssessmentInputs,
    AssessmentVersion,
    BusinessAssessment,
    BusinessInputs,
    CheckOutcome,
    CheckSufficiency,
    Claim,
    Criterion,
    CriterionEvaluation,
    DispositionDecision,
    Evidence,
    EvidenceSufficiency,
    ExtractedFact,
    FinancialAssessment,
    FinancialFigure,
    FinancialInputs,
    Judgments,
    OpportunityFit,
    ReportedFigure,
    Signal,
)
from app.rules import financials as fin
from app.rules import policy
from app.rules.claim_status import combine_states, decide_claim_status, document_for, status_label
from app.rules.company_type import classify_company, required_checks
from app.rules.compare import normalize_text, same_number
from app.rules.fit import assess_case_candidate, fit_from_evaluations, must_have_failures
from app.rules.requests import build_request_list
from app.rules.validation import screen_fact

_BLOCKING_REQUIRED = frozenset(
    {ClaimStatus.CONTRADICTED, ClaimStatus.CONFLICTING_EVIDENCE, ClaimStatus.NOT_CHECKED}
)


# --- Evidence sufficiency ------------------------------------------------------


def _check_result(states: list[ComponentState]) -> ClaimStatus:
    """Same precedence as a compound claim: conflicting before contradicted."""
    if states and all(s is ComponentState.NOT_CHECKED for s in states):
        return ClaimStatus.NOT_CHECKED
    return combine_states(states)


def evidence_sufficiency(
    company_type: CompanyType,
    outcomes: list[CheckOutcome],
    claims: dict[str, Claim] | None = None,
) -> EvidenceSufficiency:
    """Share of required checks that adequate evidence settled (supported or
    contradicted). Adequacy and the substantive result are recorded separately."""
    claims = claims or {}
    by_check: dict[ClaimCategory, list[tuple[CheckOutcome, str, ComponentState]]] = defaultdict(
        list
    )
    for o in outcomes:
        for f in o.components:
            by_check[f.check].append((o, f.component, f.state))

    checks: list[CheckSufficiency] = []
    gaps: list[str] = []
    for check in required_checks(company_type):
        entries = by_check.get(check, [])
        label = check.value.replace("_", " ")
        if not entries:
            doc = policy.CATEGORY_DOCUMENTS[check]
            gap = f"{label}: not claimed and not checked"
            checks.append(
                CheckSufficiency(
                    check=check,
                    adequate=False,
                    result=None,
                    gap=gap,
                    settle_with=[doc],
                    covered_in_v1=check in policy.V1_COVERED_CHECKS,
                )
            )
            gaps.append(gap)
            continue
        states = [s for _, _, s in entries]
        adequate = all(s in (ComponentState.MATCHED, ComponentState.CONTRADICTED) for s in states)
        result = _check_result(states)
        claim_ids = list(dict.fromkeys(o.claim_id for o, _, _ in entries))
        settle: list[str] = []
        if not adequate:
            for o, comp, s in entries:
                if s in (ComponentState.MATCHED, ComponentState.CONTRADICTED):
                    continue
                claim = claims.get(o.claim_id)
                doc = (
                    document_for(comp, claim)
                    if claim
                    else (
                        policy.COMPONENT_RULES[comp].document
                        if comp in policy.COMPONENT_RULES
                        else policy.CATEGORY_DOCUMENTS[check]
                    )
                )
                if doc not in settle:
                    settle.append(doc)
        gap = None if adequate else f"{label}: {status_label(result)}"
        if gap:
            gaps.append(gap)
        checks.append(
            CheckSufficiency(
                check=check,
                adequate=adequate,
                result=result,
                claim_ids=claim_ids,
                gap=gap,
                settle_with=settle,
                covered_in_v1=check in policy.V1_COVERED_CHECKS,
            )
        )
    settled = sum(1 for c in checks if c.adequate)
    pct = round(100 * settled / len(checks)) if checks else 0
    return EvidenceSufficiency(company_type=company_type, pct=pct, checks=checks, gaps=gaps)


# --- Business assessment (signals) --------------------------------------------

BUSINESS_NOTE = (
    "Observed operating signals, not confirmed results. Headcount and hiring come from "
    "professional profiles and job listings; they are never treated as revenue."
)


def business_assessment(inputs: BusinessInputs) -> BusinessAssessment:
    signals: list[Signal] = []
    series = sorted(inputs.headcount_series, key=lambda p: (p.date, p.evidence_id))
    if series:
        latest = series[-1]
        signals.append(
            Signal(
                label="Headcount estimate (professional profiles)",
                value=int(latest.value),
                as_of=latest.date,
                evidence_ids=[latest.evidence_id],
            )
        )
        earlier = [p for p in series if p.date <= latest.date - timedelta(days=330)]
        if earlier and earlier[-1].value > 0:
            base = earlier[-1]
            change = round(100 * (latest.value - base.value) / base.value, 1)
            signals.append(
                Signal(
                    label=f"Headcount change since {base.date.isoformat()} (estimate)",
                    value=f"{change:+.1f}%",
                    as_of=latest.date,
                    evidence_ids=[base.evidence_id, latest.evidence_id],
                )
            )
    if inputs.open_roles is not None and inputs.open_roles.value is not None:
        signals.append(
            Signal(
                label="Open roles (hiring activity)",
                value=inputs.open_roles.value,
                as_of=inputs.open_roles.as_of,
                evidence_ids=[e for e in [inputs.open_roles.evidence_id] if e],
            )
        )
    if inputs.locations:
        signals.append(
            Signal(
                label="Locations on record",
                value=sorted({str(loc.value) for loc in inputs.locations}),
                evidence_ids=sorted({x.evidence_id for x in inputs.locations if x.evidence_id}),
            )
        )
    for e in sorted(inputs.events, key=lambda e: (e.date, e.label, e.evidence_id)):
        signals.append(
            Signal(
                label=f"Dated event: {e.label}",
                value=e.date.isoformat(),
                as_of=e.date,
                evidence_ids=[e.evidence_id],
            )
        )
    return BusinessAssessment(signals=signals, note=BUSINESS_NOTE)


# --- Financial assessment ------------------------------------------------------

NOT_ASSESSED = "Not assessed: no reliable financial inputs (audited statements or registry filings)"
NOT_FOUND = "No public financials found"
NO_VALUATION = "No valuation, forecast or fair value is implied"

# Order figures are listed in, after the period.
_FIGURE_ORDER = ("revenue", "ebitda", "profit", "net_worth", "revenue_band", "revenue_growth_pct")
# Preferred record when two sources state the same figure for the same period.
_BASIS_RANK = {"audited": 0, "filing": 1, "registry": 2, "company_results": 3}
_EXCHANGES = {"nseindia.com": "NSE", "bseindia.com": "BSE"}


def _host(url: str | None) -> str:
    if not url:
        return ""
    host = url.split("://", 1)[-1].split("/", 1)[0].lower()
    return host.removeprefix("www.")


def _exchange(url: str | None) -> str | None:
    host = _host(url)
    return next((n for h, n in _EXCHANGES.items() if host == h or host.endswith("." + h)), None)


def _basis(src_reliability: SourceReliability, url: str | None, listed: bool) -> str | None:
    R = SourceReliability
    if src_reliability is R.AUDITED_STATEMENT:
        return "audited"
    if _exchange(url) or (src_reliability is R.REGISTRY and "mca.gov.in" in _host(url)):
        return "filing"
    if src_reliability in (R.REGISTRY, R.REGISTRY_MIRROR):
        return "registry"
    if src_reliability is R.COMPANY_ANNOUNCEMENT and listed:
        # A listed company must publish its results on its own site; the same
        # figures it filed with the exchange.
        return "company_results"
    return None


def _source_short(fig: FinancialFigure, url: str | None) -> str:
    exchange = _exchange(url)
    if exchange:
        return f"{exchange} filing"
    if fig.basis == "filing":
        return "MCA filing"
    if fig.basis == "registry":
        return f"registry filing via {_host(url)}" if url else "registry filing"
    if fig.basis == "audited":
        return "audited statements"
    return f"results on {_host(url)}" if url else "company results"


def _figure(
    fact: ExtractedFact,
    reported: ReportedFigure | None,
    entity_ids: list[str],
    listed: bool,
) -> tuple[FinancialFigure, str | None] | None:
    rule = policy.COMPONENT_RULES.get(fact.component)
    if rule is None or rule.check is not ClaimCategory.FINANCIALS:
        return None
    src = fact.evidence.source
    basis = _basis(src.reliability, src.url, listed)
    if basis is None:
        return None
    if not screen_fact(fact, entity_ids).valid:
        return None
    quote = fact.evidence.quote
    if reported is not None:
        period = (
            fin.Period(reported.period, reported.period_end, reported.period_months or 0)
            if reported.period and reported.period_end
            else None
        )
        amount = (
            fin.Amount(reported.amount, reported.currency, reported.unit)
            if reported.amount is not None
            else None
        )
    else:
        period = fin.parse_period(quote)
        amount = fin.parse_amount(str(fact.value))
        stated = fin.parse_amount(quote)
        if (
            amount is not None
            and stated is not None
            and amount.unit is None
            and same_number(amount.value, stated.value)
        ):
            amount = stated  # the quote gives the unit and currency of a bare value
    if rule.kind is not ValueKind.MONEY:
        amount = None
    fig = FinancialFigure(
        component=fact.component,
        value=fact.value,
        as_of=fact.evidence.as_of,
        evidence_id=fact.evidence.id,
        source_label=src.label,
        period=period.label if period else None,
        period_end=period.end if period else None,
        period_months=period.months if period else None,
        amount=amount.value if amount else None,
        currency=amount.currency if amount else None,
        unit=amount.unit if amount else None,
        display=fin.display_amount(amount) if amount else str(fact.value),
        basis=basis,
        quote=quote,
    )
    return fig, src.url


def _same_length_before(
    figs: list[FinancialFigure], head: FinancialFigure, *, year_ago: bool
) -> FinancialFigure | None:
    if head.period_end is None or head.period_months is None:
        return None
    end, months = fin.prior_period(
        fin.Period(head.period or "", head.period_end, head.period_months), year_ago=year_ago
    )
    return next(
        (
            f
            for f in figs
            if f.component == head.component
            and f.period_end == end
            and f.period_months == months
            and f.amount is not None
            and f.currency == head.currency
        ),
        None,
    )


def _conclusion(figs: list[FinancialFigure], urls: dict[str, str | None]) -> tuple[str, str | None]:
    """One bounded sentence on the latest reported period: the headline figure,
    growth against the comparable earlier period, and margins in the same period."""
    dated = [f for f in figs if f.period_end is not None]
    revenue = [f for f in dated if f.component == "revenue" and f.amount is not None]
    pool = revenue or [f for f in dated if f.amount is not None] or dated or figs
    head = max(
        pool, key=lambda f: (f.period_end or dt.date.min, -_BASIS_RANK.get(f.basis or "", 9))
    )
    noun = {"revenue": "revenue", "profit": "profit", "ebitda": "EBITDA", "net_worth": "net worth"}
    what = noun.get(head.component, head.component.replace("_", " "))
    text = f"Reported {what} {head.display}"
    if head.period:
        text += f" in {head.period}"
    parts: list[str] = []
    if head.amount is not None:
        for year_ago in (True, False):
            prior = _same_length_before(figs, head, year_ago=year_ago)
            if prior is not None and prior.amount is not None:
                change = fin.pct_change(head.amount, prior.amount)
                if change is not None:
                    parts.append(
                        f"{fin.signed_pct(change)} YoY"
                        if year_ago
                        else f"{fin.signed_pct(change)} vs {prior.period}"
                    )
                    break
    if head.component == "revenue" and head.amount:
        for comp, label in (("ebitda", "EBITDA margin"), ("profit", "profit margin")):
            other = next(
                (
                    f
                    for f in figs
                    if f.component == comp
                    and f.period_end == head.period_end
                    and f.amount is not None
                    and f.currency == head.currency
                ),
                None,
            )
            if other is not None and other.amount is not None:
                parts.append(f"{label} {round(other.amount / head.amount * 100, 1):g}%")
    if parts:
        text += ", " + ", ".join(parts)
    text += f" ({_source_short(head, urls.get(head.evidence_id))})"
    return text + ". Reported figures only; " + NO_VALUATION.lower() + ".", head.period


def _would_need(listed: bool) -> list[str]:
    if listed:
        return ["The latest results filing on the stock exchange", policy.DOC_FINANCIALS]
    return [policy.DOC_FINANCIALS, "The latest annual filing with the company registry"]


def _usd(v: float | None) -> str | None:
    return fin.display_amount(fin.Amount(v, "USD", None)) if v is not None else None


def financial_assessment(
    facts: list[ExtractedFact],
    entity_ids: list[str] | None = None,
    financials: FinancialInputs | None = None,
) -> FinancialAssessment:
    """What reliable public inputs show, under stated assumptions (design §6.4).

    1. Reported figures: audited statements, exchange or registry filings, or a listed
       company's own results page, bound to the company (``entity_ids``) on a
       corroborating identifier with their quotes verified (the same screen claims
       use). Reported with their period, growth against the same-length earlier
       period, margins in the same period and a bounded conclusion.
    2. Otherwise a data provider's revenue range, labelled "Indicative (estimate)".
    3. Otherwise, once the public search ran, "No public financials found" with what
       was searched and what would settle it.
    Headcount and hiring never enter here, and nothing here is a valuation."""
    fx = financials or FinancialInputs()
    ids = list(entity_ids or [])
    listed = fx.listing == "listed"
    found: dict[tuple, tuple[FinancialFigure, str | None]] = {}
    candidates = [(f, None) for f in sorted(facts, key=lambda f: f.id)] + [
        (r.fact, r) for r in sorted(fx.figures, key=lambda r: r.fact.id)
    ]
    for fact, reported in candidates:
        got = _figure(fact, reported, ids, listed)
        if got is None:
            continue
        fig = got[0]
        key = (fig.component, fig.period, fig.amount if fig.amount is not None else str(fig.value))
        held = found.get(key)
        if held is None or _BASIS_RANK.get(fig.basis or "", 9) < _BASIS_RANK.get(
            held[0].basis or "", 9
        ):
            found[key] = got
    searched = list(fx.searched or [])
    would_need = _would_need(listed)
    if found:
        figs = sorted(
            (g[0] for g in found.values()),
            key=lambda f: (
                -(f.period_end or dt.date.min).toordinal(),
                _FIGURE_ORDER.index(f.component) if f.component in _FIGURE_ORDER else 99,
                f.evidence_id,
            ),
        )
        urls = {g[0].evidence_id: g[1] for g in found.values()}
        conclusion, period = _conclusion(figs, urls)
        bases = {f.basis for f in figs}
        assumptions = ["Figures are taken as reported in the cited documents, without adjustment"]
        if any(f.period_months == 3 for f in figs):
            assumptions.append("Quarterly results are limited-review figures, not audited")
        if "registry" in bases:
            assumptions.append(
                "Registry-mirror pages copy the filings made with the registry and may lag "
                "the latest year"
            )
        if "company_results" in bases:
            assumptions.append(
                "Results as the listed company published them on its own site; the exchange "
                "filing itself was not read"
            )
        assumptions += [
            "Amounts are in the unit the source states (1 crore = 10 million, 1 lakh = 100,000)",
            "Growth compares periods of the same length, on the basis (consolidated or "
            "standalone) the quote states",
            NO_VALUATION,
        ]
        return FinancialAssessment(
            assessed=True,
            state="assessed",
            reason=f"Based on {len(figs)} reported figure(s) from public filings or results",
            figures=figs,
            assumptions=assumptions,
            period=period,
            conclusion=conclusion,
            searched=searched,
        )
    estimates = [e for e in fx.estimates if e.lower_usd is not None or e.upper_usd is not None]
    if estimates:
        est = max(estimates, key=lambda e: (e.as_of or dt.date.min, e.evidence_id))
        low, high = _usd(est.lower_usd), _usd(est.upper_usd)
        span = f"{low}–{high}" if low and high else f"at least {low}" if low else f"up to {high}"
        when = f", as of {est.as_of.isoformat()}" if est.as_of else ""
        return FinancialAssessment(
            assessed=False,
            state="indicative",
            reason=(
                f"Indicative (estimate): annual revenue {span} from a data provider's model"
                f"{when}. Not a reported figure."
            ),
            figures=[
                FinancialFigure(
                    component="revenue_estimate",
                    value=span,
                    as_of=est.as_of,
                    evidence_id=est.evidence_id,
                    source_label=est.source_label,
                    display=span,
                    currency="USD",
                    basis="estimate",
                )
            ],
            assumptions=[
                "A modelled range from a data provider, not reported or audited figures",
                NO_VALUATION,
            ],
            searched=searched,
            would_need=would_need,
        )
    if fx.searched is not None:
        where = "; ".join(searched) if searched else "no public lookup could be made"
        return FinancialAssessment(
            assessed=False,
            state="not_found",
            reason=f"{NOT_FOUND} — searched: {where}",
            searched=searched,
            would_need=would_need,
        )
    return FinancialAssessment(
        assessed=False, state="not_assessed", reason=NOT_ASSESSED, would_need=would_need
    )


# --- Disposition -----------------------------------------------------------------


_CONTRADICTED_STATUSES = frozenset({ClaimStatus.CONTRADICTED, ClaimStatus.CONFLICTING_EVIDENCE})
_UNVERIFIED_STATUSES = frozenset(
    {ClaimStatus.CANNOT_VERIFY, ClaimStatus.PARTIALLY_CORROBORATED, ClaimStatus.NOT_CHECKED}
)


def _blocks_prioritise(key: str) -> bool:
    return policy.DISPOSITION_RULES[key].outcome is Disposition.INVESTIGATE_FURTHER


def _material_blocking(covered_required: set[ClaimCategory]) -> dict[ClaimStatus, bool]:
    """Which material claim statuses block Prioritise, from the disposition table.
    A contradicted or conflicting material claim blocks wherever it sits; an
    unverified one blocks outside the v1-covered required checks (inside them the
    required-check rule already applies)."""
    out: dict[ClaimStatus, bool] = {}
    if _blocks_prioritise("contradicted_optional_claim"):
        out.update(dict.fromkeys(_CONTRADICTED_STATUSES, True))
    if _blocks_prioritise("unverified_optional_claim"):
        out.update(dict.fromkeys(_UNVERIFIED_STATUSES, False))
    return out


def _complete(c: CheckSufficiency) -> bool:
    return c.adequate and c.result is ClaimStatus.SUPPORTED


def decide_disposition(
    identity_status: IdentityStatus,
    fit: OpportunityFit,
    sufficiency: EvidenceSufficiency,
    must_failures: list[str],
    *,
    outcomes: list[CheckOutcome] | None = None,
    claims: dict[str, Claim] | None = None,
) -> DispositionDecision:
    """Predicates in fixed precedence; the first that holds decides.

    1. cannot_assess        identity not confirmed, or too little of the thesis assessable
    2. deprioritise         a must-have verifiably failed, or poor fit on verified evidence
    3. prioritise           strong fit, every v1-covered required check complete, and no
                            material claim contradicted or conflicting anywhere
    4. investigate_further  everything else (attractive, evidence incomplete)

    Missing evidence never reaches rule 2: unknowns never fail a criterion,
    disputed criteria are unknown, estimate-based and stale results are
    excluded from the poor-fit test, and claim statuses do not feed it at all.
    Pass ``outcomes`` (and ``claims`` for materiality) so the whole ledger is
    considered, not only the required checks.
    """
    if identity_status is not IdentityStatus.CONFIRMED:
        return DispositionDecision(
            disposition=Disposition.CANNOT_ASSESS,
            rule="identity_uncertain",
            reasons=[
                f"Identity is {identity_status.value}: records cannot be attached to the "
                "company safely"
            ],
        )
    if fit.fit is None or fit.assessable_pct < policy.CANNOT_ASSESS_MAX_ASSESSABLE:
        return DispositionDecision(
            disposition=Disposition.CANNOT_ASSESS,
            rule="essential_information_missing",
            reasons=[
                f"Only {fit.assessable_pct}% of the criteria can be assessed "
                f"(minimum {policy.CANNOT_ASSESS_MAX_ASSESSABLE}%)"
            ],
        )
    if must_failures:
        return DispositionDecision(
            disposition=Disposition.DEPRIORITISE,
            rule="requirement_failed",
            reasons=list(must_failures),
        )
    if (
        fit.verified_fit is not None
        and fit.verified_fit < policy.DEPRIORITISE_MAX_FIT
        and fit.verified_assessable_pct >= policy.DEPRIORITISE_MIN_ASSESSABLE
    ):
        return DispositionDecision(
            disposition=Disposition.DEPRIORITISE,
            rule="poor_fit_on_good_evidence",
            reasons=[
                f"Verified fit {fit.verified_fit} is below {policy.DEPRIORITISE_MAX_FIT} with "
                f"{fit.verified_assessable_pct}% of the criteria verified"
            ],
        )

    claims = claims or {}
    blocking = [
        c for c in sufficiency.checks if c.result is not None and c.result in _BLOCKING_REQUIRED
    ]
    # Every required check v1 covers must be complete. An absent check
    # (result None) or a skipped one is a gap, never a pass.
    incomplete = [
        c
        for c in sufficiency.checks
        if c.check in policy.V1_COVERED_CHECKS and not _complete(c) and c not in blocking
    ]
    covered_required = {c.check for c in sufficiency.checks if c.check in policy.V1_COVERED_CHECKS}
    statuses = _material_blocking(covered_required)
    material = [
        o
        for o in outcomes or []
        if o.status in statuses
        and (statuses[o.status] or o.category not in covered_required)
        and (claims.get(o.claim_id) is None or claims[o.claim_id].material)
    ]
    unverified_musts = (
        [
            e
            for e in fit.evaluations
            if e.kind is CriterionKind.MUST and e.result is CriterionResult.UNKNOWN
        ]
        if _blocks_prioritise("unverified_mandatory_criterion")
        else []
    )
    strong = fit.fit >= policy.PRIORITISE_MIN_FIT
    if strong and not incomplete and not blocking and not material and not unverified_musts:
        return DispositionDecision(
            disposition=Disposition.PRIORITISE,
            rule="strong_fit_checks_satisfied",
            reasons=[
                fit.label,
                "Every required check within what v1 covers is settled by adequate evidence "
                f"({sufficiency.pct}% of all required checks)",
            ],
        )

    reasons = [fit.label]
    if not strong:
        reasons.append(f"Fit is below {policy.PRIORITISE_MIN_FIT}")
    for c in incomplete:
        label = c.check.value.replace("_", " ")
        state = "not claimed and not checked" if c.result is None else status_label(c.result)
        reasons.append(f"Required check {label}: {state}")
    for c in blocking:
        label = c.check.value.replace("_", " ")
        reasons.append(f"Required check {label}: {status_label(c.result)}")
    for o in material:
        reasons.append(f"Material claim {o.claim_id}: {status_label(o.status)}")
    for e in unverified_musts:
        reasons.append(f"Must-have criterion {e.criterion_id}: not verified")
    return DispositionDecision(
        disposition=Disposition.INVESTIGATE_FURTHER,
        rule="evidence_incomplete",
        reasons=reasons,
    )


def must_have_failure_reasons(
    criteria: list[Criterion], evaluations: list[CriterionEvaluation]
) -> list[str]:
    """The exclusion reasons ``assess_case_candidate`` gives, in the same words."""
    labels = {c.id: c.label for c in criteria}
    return [
        f"Must-have failed: {labels[e.criterion_id]} ({e.reason})"
        for e in must_have_failures(evaluations)
    ]


def _single_required_value(c: Criterion) -> object | None:
    """The one value a criterion requires, when it requires exactly one."""
    if c.operator is CriterionOperator.IS_TRUE:
        return True
    if c.operator is CriterionOperator.EQ:
        return c.value
    if c.operator in (CriterionOperator.IN, CriterionOperator.CONTAINS_ANY):
        values = c.value if isinstance(c.value, list | tuple) else [c.value]
        return values[0] if len(values) == 1 else None
    return None


def _same_value(claimed: object, required: object) -> bool:
    if isinstance(required, bool) or isinstance(claimed, bool):
        return str(claimed).strip().lower() == str(required).strip().lower()
    return normalize_text(str(claimed)) == normalize_text(str(required))


def contradicted_must_haves(
    criteria: list[Criterion],
    evaluations: list[CriterionEvaluation],
    outcomes: list[CheckOutcome],
    claims: dict[str, Claim],
) -> list[str]:
    """Verified must-have failures that come from claim checks (POLICY.md §5).

    A Contradicted claim whose component maps to a must-have's dimension
    (``policy.COMPONENT_CRITERION_DIMENSIONS``) is a verified failure of that
    must-have when the claimed value is exactly the one the criterion requires.
    Needs the claims (for their component values); a must-have that already
    failed is not counted twice."""
    if policy.DISPOSITION_RULES["verified_mandatory_failure"].outcome is not (
        Disposition.DEPRIORITISE
    ):
        return []
    failed = {e.criterion_id for e in must_have_failures(evaluations)}
    musts = [
        c for c in criteria if c.kind is CriterionKind.MUST and c.dimension and c.id not in failed
    ]
    reasons: list[str] = []
    seen: set[str] = set()
    for o in outcomes:
        claim = claims.get(o.claim_id)
        if o.status is not ClaimStatus.CONTRADICTED or claim is None:
            continue
        claimed = {c.name: c for c in claim.components}
        for f in o.components:
            dimension = policy.COMPONENT_CRITERION_DIMENSIONS.get(f.component)
            component = claimed.get(f.component)
            if f.state is not ComponentState.CONTRADICTED or not dimension or component is None:
                continue
            if component.op != "eq":
                continue
            for c in musts:
                required = _single_required_value(c)
                if (
                    c.dimension == dimension
                    and c.id not in seen
                    and required is not None
                    and _same_value(component.value, required)
                ):
                    seen.add(c.id)
                    reasons.append(
                        f"Must-have failed: {c.label} (claim {o.claim_id} contradicted "
                        f"on {f.component.replace('_', ' ')})"
                    )
    return reasons


def redecide(
    *,
    identity_status: IdentityStatus,
    company_type: CompanyType,
    outcomes: list[CheckOutcome],
    evaluations: list[CriterionEvaluation],
    criteria: list[Criterion],
    claims: dict[str, Claim],
) -> tuple[OpportunityFit, EvidenceSufficiency, DispositionDecision]:
    """Fit, evidence sufficiency and the disposition from already-decided claim
    outcomes and criterion evaluations. ``assess`` calls it with the real values
    and DecisionFlip with some of them forced, so a hypothetical and a real
    disposition always come from the same rules. ``criteria`` supplies weights
    and labels."""
    fit = fit_from_evaluations(criteria, evaluations)
    sufficiency = evidence_sufficiency(company_type, outcomes, claims)
    decision = decide_disposition(
        identity_status,
        fit,
        sufficiency,
        must_have_failure_reasons(criteria, evaluations)
        + contradicted_must_haves(criteria, evaluations, outcomes, claims),
        outcomes=outcomes,
        claims=claims,
    )
    return fit, sufficiency, decision


# --- Versioned assessment -------------------------------------------------------


def inputs_hash(inputs: AssessmentInputs) -> str:
    """sha256 of the canonical inputs and policy version. The version number is
    left out, so re-running unchanged inputs gives the same hash."""
    data = inputs.model_dump(mode="json", exclude={"version"})
    payload = {"policy_version": policy.POLICY_VERSION, "inputs": data}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _evidence_index(inputs: AssessmentInputs) -> list[Evidence]:
    seen: dict[str, Evidence] = {}
    for e in inputs.evidence:
        seen.setdefault(e.id, e)
    for c in inputs.claim_checks:
        for f in c.facts:
            seen.setdefault(f.evidence.id, f.evidence)
    for f in inputs.financial_facts:
        seen.setdefault(f.evidence.id, f.evidence)
    for r in inputs.financials.figures:
        seen.setdefault(r.fact.evidence.id, r.fact.evidence)
    return [seen[k] for k in sorted(seen)]


def assess(inputs: AssessmentInputs) -> AssessmentVersion:
    """Case inputs → one immutable assessment version. Same inputs, same output.

    Claims, fit and the financial assessment all use the same screened
    evidence: every fact and field passes the identity guard for the
    confirmed company before it can count.
    """
    outcomes = [decide_claim_status(c) for c in inputs.claim_checks]
    claims = {c.claim.id: c.claim for c in inputs.claim_checks}
    evidence = _evidence_index(inputs)
    disputed = sorted(
        {
            eid
            for o in outcomes
            for f in o.components
            if f.state is ComponentState.CONFLICTING
            for eid in f.decisive_evidence_ids
        }
    )
    candidate = assess_case_candidate(
        inputs.criteria,
        inputs.company,
        today=inputs.today,
        evidence=evidence,
        disputed_evidence_ids=disputed,
    )
    ctype = classify_company(
        inputs.profile.founded_year,
        inputs.profile.headcount,
        inputs.profile.funding_stage,
        inputs.today,
    )
    _, sufficiency, decision = redecide(
        identity_status=inputs.identity_status,
        company_type=ctype.company_type,
        outcomes=outcomes,
        evaluations=candidate.fit.evaluations,
        criteria=inputs.criteria,
        claims=claims,
    )
    business = business_assessment(inputs.business)
    financial = financial_assessment(
        [f for c in inputs.claim_checks for f in c.facts] + list(inputs.financial_facts),
        [inputs.company.entity_id],
        inputs.financials,
    )
    requests = build_request_list(
        outcomes,
        claims,
        inputs.identity_status,
        financial,
        financials_required=ClaimCategory.FINANCIALS in required_checks(ctype.company_type),
    )
    return AssessmentVersion(
        case_id=inputs.case_id,
        version=inputs.version,
        policy_version=policy.POLICY_VERSION,
        inputs_hash=inputs_hash(inputs),
        company_type=ctype,
        candidate=candidate,
        outcomes=outcomes,
        judgments=Judgments(
            opportunity_fit=candidate.fit,
            evidence_sufficiency=sufficiency,
            business=business,
            financial=financial,
            disposition=decision,
        ),
        disposition=decision.disposition,
        requests=requests,
    )
