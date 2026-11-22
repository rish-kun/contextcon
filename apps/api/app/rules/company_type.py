"""Company type by rule, and the PRD's criteria set for each type."""

from __future__ import annotations

import re
from datetime import date

from app.domain.enums import ClaimCategory, CompanyType
from app.domain.types import CompanyTypeDecision, EvaluationCriterion
from app.rules import policy


def _headcount_floor(headcount: int | str | None) -> int | None:
    """A number, or the lower bound of a band such as "201-500" or "10001+"."""
    if headcount is None or isinstance(headcount, bool):
        return None
    if isinstance(headcount, int):
        return headcount
    m = re.search(r"\d[\d,]*", str(headcount))
    return int(m.group().replace(",", "")) if m else None


def _stage(stage: str | None) -> str | None:
    if not stage:
        return None
    return re.sub(r"[^a-z0-9]+", "_", stage.casefold()).strip("_")


def classify_company(
    founded_year: int | None,
    headcount: int | str | None,
    funding_stage: str | None,
    today: date,
) -> CompanyTypeDecision:
    """startup vs established.

    Founded within STARTUP_MAX_AGE_YEARS: a startup unless it is both large
    (headcount above STARTUP_MAX_HEADCOUNT) and past the venture stages.
    Older: established. Founding year unknown: established only when large.
    """
    size = _headcount_floor(headcount)
    stage = _stage(funding_stage)
    large = size is not None and size > policy.STARTUP_MAX_HEADCOUNT
    venture = stage in policy.STARTUP_STAGES

    if founded_year is None:
        kind = CompanyType.ESTABLISHED if large and not venture else CompanyType.STARTUP
        reason = "founding year unknown; " + (
            f"headcount {size} is above {policy.STARTUP_MAX_HEADCOUNT}"
            if large
            else "not shown to be large"
        )
        return CompanyTypeDecision(company_type=kind, reason=reason)

    age = today.year - founded_year
    if age > policy.STARTUP_MAX_AGE_YEARS:
        return CompanyTypeDecision(
            company_type=CompanyType.ESTABLISHED,
            reason=f"founded {founded_year}, {age} years ago "
            f"(more than {policy.STARTUP_MAX_AGE_YEARS})",
        )
    if large and not venture:
        return CompanyTypeDecision(
            company_type=CompanyType.ESTABLISHED,
            reason=f"founded {founded_year} but headcount {size} is above "
            f"{policy.STARTUP_MAX_HEADCOUNT} and funding stage is {stage or 'unknown'}",
        )
    return CompanyTypeDecision(
        company_type=CompanyType.STARTUP,
        reason=f"founded {founded_year}, {age} years ago"
        + (f", at {stage} stage" if venture else ""),
    )


def criteria_for(company_type: CompanyType) -> list[EvaluationCriterion]:
    return [
        EvaluationCriterion(name=name, label=label, checks=checks)
        for name, label, checks in policy.EVALUATION_CRITERIA[company_type]
    ]


def required_checks(company_type: CompanyType) -> list[ClaimCategory]:
    return list(policy.REQUIRED_CHECKS[company_type])
