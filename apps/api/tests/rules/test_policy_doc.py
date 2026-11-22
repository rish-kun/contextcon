from pathlib import Path

from app.rules import POLICY_VERSION, policy

DOC = (Path(__file__).parents[2] / "app" / "rules" / "POLICY.md").read_text()


def test_policy_doc_matches_version_and_table():
    assert POLICY_VERSION in DOC
    for component in policy.COMPONENT_RULES:
        assert f"`{component}`" in DOC


def test_policy_doc_states_the_thresholds():
    for text in (
        f"Fit at least {policy.PRIORITISE_MIN_FIT}",
        f"at least {policy.PRIORITISE_MIN_SUFFICIENCY}% of required checks",
        f"fit below {policy.DEPRIORITISE_MAX_FIT}",
        f"at least {policy.DEPRIORITISE_MIN_ASSESSABLE}% of criteria verified",
        f"less than {policy.CANNOT_ASSESS_MAX_ASSESSABLE}% of criteria assessable",
        "must-have counts 2 and a preference counts 1",
    ):
        assert text in DOC, text
