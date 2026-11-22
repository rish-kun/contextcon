from datetime import date, datetime

from app.domain import (
    ClaimStatus,
    Disposition,
    Evidence,
    ExtractedFact,
    Source,
    SourceReliability,
)
from app.rules.diff import diff
from app.rules.evaluate import assess
from tests.rules import prd_fixtures as prd
from tests.rules.test_evaluate import PRD_INPUTS

LEASE = Source(
    id="src-lease",
    provider="upload",
    label="Seller document: facility lease and occupancy certificate",
    retrieved_at=datetime(2026, 11, 25),
    reliability=SourceReliability.SELLER_DOCUMENT,
)
LEASE_QUOTE = (
    "Occupancy certificate issued 1 October 2026. The warehouse facility at Chakan "
    "commenced operations on 3 October 2026."
)


def lease_fact(id, component, value):
    ev = Evidence(
        id="ev-lease",
        source=LEASE,
        entity_id=prd.COMPANY,
        quote=LEASE_QUOTE,
        as_of=date(2026, 10, 3),
    )
    return ExtractedFact(id=id, evidence=ev, component=component, value=value)


def with_lease():
    facility = prd.FACILITY.model_copy(
        update={
            "facts": [
                *prd.FACILITY.facts,
                lease_fact("f-lease-date", "event_date", "2026-10-03"),
                lease_fact("f-lease-stage", "stage", "operating"),
            ]
        }
    )
    checks = [facility if c.claim.id == "c-facility" else c for c in prd.PRD_CHECKS]
    return PRD_INPUTS.model_copy(update={"version": 2, "claim_checks": checks})


def test_diff_reports_status_change_with_reason_pointing_at_evidence():
    v1, v2 = assess(PRD_INPUTS), assess(with_lease())
    d = diff(v1, v2)
    assert d.inputs_changed and not d.policy_changed
    assert (d.from_version, d.to_version) == (1, 2)
    [change] = d.claim_changes
    assert change.claim_id == "c-facility"
    assert (change.before, change.after) == (
        ClaimStatus.PARTIALLY_CORROBORATED,
        ClaimStatus.SUPPORTED,
    )
    assert change.evidence_added == ["ev-lease"]
    assert "Partially corroborated → Supported" in change.reason
    assert "facility lease" in change.reason


def test_disposition_change_points_at_causing_evidence():
    # A startup case where the payroll summary arrives and settles team size.
    from tests.rules.test_evaluate import _supported_startup_checks

    checks, _ = _supported_startup_checks()
    from app.domain import CompanyProfile

    profile = CompanyProfile(founded_year=2021, headcount=60, funding_stage="series_a")
    before = PRD_INPUTS.model_copy(
        update={"profile": profile, "claim_checks": [checks[0], prd.EMPLOYEES, *checks[2:]]}
    )
    after = before.model_copy(update={"version": 2, "claim_checks": checks})
    v1, v2 = assess(before), assess(after)
    assert v1.disposition is Disposition.INVESTIGATE_FURTHER
    assert v2.disposition is Disposition.PRIORITISE
    d = diff(v1, v2)
    assert [c.claim_id for c in d.claim_changes] == ["c-employees"]
    suff = next(j for j in d.judgment_changes if j.judgment == "evidence_sufficiency")
    assert (suff.before, suff.after) == (75, 100)
    assert "c-employees" in suff.because and "ev-pay" in suff.because
    assert d.disposition_change is not None
    assert d.disposition_change.before is Disposition.INVESTIGATE_FURTHER
    assert d.disposition_change.after is Disposition.PRIORITISE
    assert "ev-pay" in d.disposition_change.because
    assert d.disposition_change.reason.startswith("evidence_incomplete → strong_fit")


def test_identical_versions_have_empty_diff():
    v = assess(PRD_INPUTS)
    d = diff(v, assess(PRD_INPUTS))
    assert not d.inputs_changed
    assert d.claim_changes == [] and d.judgment_changes == [] and d.disposition_change is None


def test_diff_is_deterministic():
    v1, v2 = assess(PRD_INPUTS), assess(with_lease())
    assert diff(v1, v2) == diff(v1, v2)
    again = diff(assess(PRD_INPUTS), assess(with_lease()))
    assert diff(v1, v2).model_dump_json() == again.model_dump_json()
