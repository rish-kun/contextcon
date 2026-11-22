import importlib

import pytest

from app.db import enums


def test_values_match_the_prd() -> None:
    assert {s.value for s in enums.ClaimStatus} == {
        "supported",
        "contradicted",
        "partially_corroborated",
        "conflicting_evidence",
        "cannot_verify",
        "not_checked",
    }
    assert {d.value for d in enums.Disposition} == {
        "prioritise",
        "investigate_further",
        "deprioritise",
        "cannot_assess",
    }
    assert {s.value for s in enums.SendStatus} == {
        "pending",
        "sent",
        "suppressed_test_mode",
        "failed",
        "unknown",
    }


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ("ClaimStatus", "ClaimStatus"),
        ("Disposition", "Disposition"),
        ("CriterionKind", "CriterionKind"),
        ("CriterionResult", "TriState"),
        ("StepState", "StepState"),
    ],
)
def test_matches_shared_domain_vocabulary_when_present(ours: str, theirs: str) -> None:
    try:
        domain = importlib.import_module("app.domain.enums")
    except ModuleNotFoundError:
        pytest.skip("app.domain not merged yet")
    if not hasattr(domain, theirs):
        pytest.skip(f"app.domain has no {theirs}")
    assert {m.value for m in getattr(enums, ours)} == {m.value for m in getattr(domain, theirs)}
