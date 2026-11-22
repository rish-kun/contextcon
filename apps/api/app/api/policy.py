"""Scoring policy route: the rules' weights, thresholds and tables, plus POLICY.md.

Served from `app.rules.policy` itself, so the page always shows the policy the rules
run on. Public: it holds no case data.
"""

from functools import cache
from pathlib import Path

from app.api._base import make_router
from app.api.schemas.policy import (
    AdequateSourcesOut,
    BudgetsOut,
    DispositionRuleOut,
    PolicyOut,
    PolicyThresholdsOut,
    PolicyWeightsOut,
    RequiredChecksOut,
    SettleWithOut,
)
from app.domain.enums import CompanyType, CriterionKind
from app.rules import policy
from app.settings import get_settings

router = make_router(tags=["policy"])

POLICY_MD = Path(policy.__file__).with_name("POLICY.md")

DISPOSITION_RULES = [
    (
        "cannot_assess",
        "Identity is not confirmed, or fewer than "
        f"{policy.CANNOT_ASSESS_MAX_ASSESSABLE}% of the criteria can be assessed "
        "(including no strategy criteria yet). Identity uncertainty overrides every other "
        "signal.",
    ),
    (
        "deprioritise",
        "A must-have criterion verifiably failed on a sourced value that is not an estimate, "
        f"or verified fit is below {policy.DEPRIORITISE_MAX_FIT} with at least "
        f"{policy.DEPRIORITISE_MIN_ASSESSABLE}% of the criteria verified. Missing evidence "
        "alone never leads here.",
    ),
    (
        "prioritise",
        f"Fit is at least {policy.PRIORITISE_MIN_FIT}, at least "
        f"{policy.PRIORITISE_MIN_SUFFICIENCY}% of required checks are settled by adequate "
        "evidence, and no required check is contradicted, conflicting or not checked.",
    ),
    ("investigate_further", "Everything else: attractive, but important evidence is incomplete."),
]

COMPANY_TYPE_RULE = (
    f"Startup if founded within {policy.STARTUP_MAX_AGE_YEARS} years, unless it has more than "
    f"{policy.STARTUP_MAX_HEADCOUNT} people and is not at a venture stage "
    f"({', '.join(sorted(policy.STARTUP_STAGES))}). Older companies are established. With no "
    f"founding year, a company is established only when it has more than "
    f"{policy.STARTUP_MAX_HEADCOUNT} people and is not at a venture stage."
)
INVESTOR_RANKING_RULE = (
    "Only dated rounds with a named investor count. Score = sum of "
    f"0.5^(years since round / {policy.INVESTOR_RECENCY_HALF_LIFE_YEARS:g}) over comparable "
    f"rounds in the last {policy.INVESTOR_LOOKBACK_YEARS} years; ties break by count, then by "
    "latest date. Ranking describes past activity, not intent."
)
COMPARABLES_RULE = (
    "Peers share the top industry and headquarters country and have a headcount between half "
    "and twice the company's. With fewer than two such peers, the case says no fair "
    "comparison was found instead of using looser peers."
)


@cache
def policy_markdown() -> str:
    return POLICY_MD.read_text(encoding="utf-8")


def policy_out() -> PolicyOut:
    settings = get_settings()
    return PolicyOut(
        policy_version=policy.POLICY_VERSION,
        weights=PolicyWeightsOut(
            must=policy.CRITERION_WEIGHTS[CriterionKind.MUST],
            preference=policy.CRITERION_WEIGHTS[CriterionKind.PREFERENCE],
        ),
        fit_formula="fit = round(100 × Σ weight(pass) / Σ weight(pass or fail)); "
        "unavailable when nothing is assessable",
        assessable_formula="assessable % = round(100 × count(pass or fail) / count(all))",
        thresholds=PolicyThresholdsOut(
            prioritise_fit_min=policy.PRIORITISE_MIN_FIT,
            prioritise_sufficiency_min=policy.PRIORITISE_MIN_SUFFICIENCY,
            deprioritise_fit_below=policy.DEPRIORITISE_MAX_FIT,
            deprioritise_assessable_min=policy.DEPRIORITISE_MIN_ASSESSABLE,
            cannot_assess_assessable_below=policy.CANNOT_ASSESS_MAX_ASSESSABLE,
        ),
        disposition_rules=[
            DispositionRuleOut(order=i, disposition=d, rule=r)
            for i, (d, r) in enumerate(DISPOSITION_RULES, start=1)
        ],
        required_checks=RequiredChecksOut(
            startup=[c.value for c in policy.REQUIRED_CHECKS[CompanyType.STARTUP]],
            established=[c.value for c in policy.REQUIRED_CHECKS[CompanyType.ESTABLISHED]],
        ),
        adequate_sources=[
            AdequateSourcesOut(
                category=rule.check.value,
                component=name,
                source_classes=sorted(r.value for r in rule.adequate),
            )
            for name, rule in policy.COMPONENT_RULES.items()
        ],
        settle_with=[
            SettleWithOut(category=c.value, document=doc)
            for c, doc in policy.CATEGORY_DOCUMENTS.items()
        ],
        company_type_rule=COMPANY_TYPE_RULE,
        investor_ranking_rule=INVESTOR_RANKING_RULE,
        comparables_rule=COMPARABLES_RULE,
        budgets=BudgetsOut(
            case_credits=settings.case_credit_budget,
            discover_credits=settings.discover_credit_budget,
            investor_credits=settings.investor_credit_budget,
        ),
        markdown=policy_markdown(),
    )


@router.get("/policy", response_model=PolicyOut)
def get_policy() -> PolicyOut:
    """Weights, thresholds, adequacy table, required checks and the policy version."""
    return policy_out()
