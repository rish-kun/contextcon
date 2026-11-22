import asyncio

import pytest

from app.drafting.citations import (
    UncitedSentenceError,
    check_citations,
    cite_each_sentence,
    require_citations,
    split_sentences,
)
from app.drafting.memo import AcceptedFact, MemoSectionRequest, draft_memo_section
from tests.extraction.fakes import FakeLlm

SOURCES = {
    "F1": "Acme Warehousing Pvt. Ltd. was incorporated in Pune in 2014 (registry)",
    "F2": "Profile-based headcount estimate: 140 (estimate)",
    "F3": "A dated announcement describes a planned facility in Chakan",
}


def test_split_sentences_keeps_citations_and_abbreviations():
    text = (
        "Acme Warehousing Pvt. Ltd. was incorporated in 2014 [F1]. "
        "Its headcount estimate is 140. [F2]\n"
        "- A facility in Chakan is planned [F3]."
    )
    assert split_sentences(text) == [
        "Acme Warehousing Pvt. Ltd. was incorporated in 2014 [F1].",
        "Its headcount estimate is 140. [F2]",
        "A facility in Chakan is planned [F3].",
    ]


def test_validator_accepts_fully_cited_text():
    text = "Acme was incorporated in Pune in 2014 [F1]. The headcount estimate is 140 [F1, F2]."
    report = require_citations(text, SOURCES)
    assert report.ok
    assert report.citations_used == ["F1", "F2"]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("Acme was incorporated in 2014 [F1]. It is a strong business.", "no citation"),
        ("Acme was incorporated in 2014 [F9].", "unknown citation id F9"),
        ("Acme was incorporated in 2014 [F1] [see note].", "non-citation brackets"),
        ("Acme employs 250 people [F2].", "numbers not in cited facts: 250"),
        ("Acme opened in 2014 [F3].", "numbers not in cited facts: 2014"),
        ("", "text is empty"),
    ],
)
def test_validator_rejects(text, problem):
    report = check_citations(text, SOURCES)
    assert not report.ok
    assert any(problem in issue for issue in report.issues), report.issues
    with pytest.raises(UncitedSentenceError):
        require_citations(text, SOURCES)


def test_cite_each_sentence():
    out = cite_each_sentence("Raised growth funding in 2025. Lead investor named.", "F7")
    assert out == "Raised growth funding in 2025 [F7]. Lead investor named [F7]."


FACTS = [
    AcceptedFact(
        citation_id="F1", statement=SOURCES["F1"], source_label="MCA mirror", as_of="2014-06-02"
    ),
    AcceptedFact(citation_id="F2", statement=SOURCES["F2"]),
]


def test_memo_section_uses_valid_draft():
    llm = FakeLlm(
        drafts=[
            "Acme Warehousing was incorporated in Pune in 2014 [F1]. "
            "Its profile-based headcount estimate is 140 [F2]."
        ]
    )
    out = asyncio.run(draft_memo_section(llm, MemoSectionRequest(section="Identity", facts=FACTS)))
    assert not out.used_fallback
    assert out.citations_used == ["F1", "F2"]
    assert '"id": "F1"' in llm.calls[0].user


def test_memo_section_retries_with_issues_then_falls_back():
    llm = FakeLlm(
        drafts=[
            "Acme is a well-run company. It was incorporated in 2014 [F1].",
            "Acme has 250 staff [F2].",
        ]
    )
    out = asyncio.run(draft_memo_section(llm, MemoSectionRequest(section="Identity", facts=FACTS)))
    assert len(llm.calls) == 2
    assert "sentence has no citation" in llm.calls[1].user  # retry carries the complaints
    assert out.used_fallback
    assert len(out.rejected_attempts) == 2
    require_citations(out.text, {"F1": SOURCES["F1"], "F2": SOURCES["F2"]})
    assert out.text.startswith("Acme Warehousing Pvt. Ltd. was incorporated in Pune in 2014")


def test_memo_second_attempt_can_pass():
    llm = FakeLlm(drafts=["Uncited.", "Acme was incorporated in 2014 [F1]."])
    out = asyncio.run(draft_memo_section(llm, MemoSectionRequest(section="Identity", facts=FACTS)))
    assert not out.used_fallback and out.text == "Acme was incorporated in 2014 [F1]."


def test_memo_section_without_facts_is_empty_and_calls_nothing():
    llm = FakeLlm()
    out = asyncio.run(draft_memo_section(llm, MemoSectionRequest(section="Financials", facts=[])))
    assert out.text == "" and llm.calls == []


def test_accepted_fact_rejects_bad_ids():
    with pytest.raises(ValueError):
        AcceptedFact(citation_id="F 1", statement="x")
