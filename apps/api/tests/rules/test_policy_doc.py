from pathlib import Path

from app.domain import SourceReliability
from app.rules import POLICY_VERSION, policy

DOC = (Path(__file__).parents[2] / "app" / "rules" / "POLICY.md").read_text()


def _row(component: str) -> str:
    return next(line for line in DOC.splitlines() if line.startswith(f"| `{component}` |"))


def test_policy_doc_matches_version_and_table():
    assert f"Policy version: **{POLICY_VERSION}**" in DOC
    for component in policy.COMPONENT_RULES:
        assert f"`{component}`" in DOC


def test_policy_doc_table_rows_match_the_rule_table():
    seller = SourceReliability.SELLER_DOCUMENT
    for name, rule in policy.COMPONENT_RULES.items():
        cells = [c.strip() for c in _row(name).strip("|").split("|")]
        assert cells[1] == rule.check.value.replace("_", " "), name
        assert cells[2] == ", ".join(sorted(c.value for c in rule.adequate)), name
        docs = rule.document_types.get(seller)
        if seller not in rule.adequate:
            assert cells[3] == "none", name
        elif docs is None:
            assert cells[3] == "any", name
        else:
            expected = ", ".join(sorted(d.value for d in docs))
            if seller in rule.needs_date:
                expected += " (dated)"
            assert cells[3] == expected, name
        assert cells[4] == rule.document + ("" if rule.seller_resolvable else " (analyst)"), name


def test_policy_doc_lists_the_corroborating_identifiers():
    for identifier in policy.CORROBORATING_IDENTIFIERS:
        assert f"`{identifier}`" in DOC, identifier


def test_policy_doc_names_the_v1_covered_checks():
    section = DOC[DOC.index("**What v1 covers.**") :]
    for check in policy.V1_COVERED_CHECKS:
        assert check.value.replace("_", " ").split()[0] in section, check


def test_policy_doc_states_the_thresholds():
    for text in (
        f"Fit at least {policy.PRIORITISE_MIN_FIT}",
        f"fit below {policy.DEPRIORITISE_MAX_FIT}",
        f"at least {policy.DEPRIORITISE_MIN_ASSESSABLE}% of criteria verified",
        f"less than {policy.CANNOT_ASSESS_MAX_ASSESSABLE}% of criteria assessable",
        "must-have counts 2 and a preference counts 1",
        f"more than {policy.FIELD_STALE_AFTER_DAYS} days old",
        "every required check that v1 covers Supported",
        "no material claim anywhere in the ledger contradicted or conflicting",
    ):
        assert text in DOC, text


def test_policy_doc_states_the_disposition_table_and_mapping():
    section = DOC[DOC.index("## 5. Screening disposition") : DOC.index("## 6. Requests")]
    for row in policy.DISPOSITION_TABLE:
        assert f"| {row.situation} |" in section, row.key
    for component in policy.COMPONENT_CRITERION_DIMENSIONS:
        assert f"`{component}`" in section, component


def test_policy_doc_explains_decision_flip():
    section = DOC[DOC.index("## 9. DecisionFlip") :]
    assert "Minimum set of checks required to change the screening outcome" in section
    assert "never described as the cheapest" in section
