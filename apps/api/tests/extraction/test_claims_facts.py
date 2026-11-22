import asyncio

from app.extraction.claims import PageText, batch_pages, extract_claims, render_batch
from app.extraction.facts import ClaimRef, extract_facts
from app.extraction.spans import normalize, span_in
from tests.extraction.fakes import FakeLlm

PAGES = [
    PageText(page=1, text="Acme Warehousing Pvt Ltd\nIncorporated in 2014, based in Pune."),
    PageText(page=2, text="We employ 250 people across 6 sites.\nWe have no debt."),
    PageText(page=3, text="We opened a new facility in October 2026 in Chakan."),
]


def run(coro):
    return asyncio.run(coro)


def claim(assertion, category, quote, page, **components):
    return {
        "assertion": assertion,
        "category": category,
        "components": [{"name": k, "value": v} for k, v in components.items()],
        "quote": quote,
        "page": page,
    }


def test_span_normalisation():
    assert span_in("“Incorporated  in 2014”", "incorporated in 2014, based in Pune")
    assert span_in("based in Pune.", "Incorporated in 2014, based in Pune")
    assert span_in("supply–chain", "supply-chain software")
    assert not span_in("incorporated in 2015", "Incorporated in 2014")
    assert not span_in("in", "Incorporated in 2014")  # too short to anchor anything
    assert not span_in(None, "anything")
    assert normalize("A  B") == "a b"


def test_claims_keep_verbatim_quotes_and_fix_page_numbers():
    llm = FakeLlm(
        structured=[
            {
                "claims": [
                    claim(
                        "Incorporated in 2014, based in Pune",
                        "identity_incorporation",
                        "Incorporated in 2014, based in Pune",
                        1,
                        year="2014",
                        city="Pune",
                    ),
                    # Model gives the wrong page; the quote is on page 2.
                    claim(
                        "We employ 250 people", "team_size", "We employ 250 people", 3, count="250"
                    ),
                    claim("We have no debt", "debt_security", "We have no debt.", 2),
                    claim(
                        "We opened a new facility in October 2026",
                        "dated_event",
                        "opened a new facility in October 2026",
                        3,
                        date="2026-10",
                        stage="operating",
                    ),
                    # Invented: not in the document.
                    claim(
                        "We raised growth funding in 2025",
                        "funding",
                        "We raised growth funding in 2025",
                        2,
                        year="2025",
                    ),
                    # Duplicate of the first claim.
                    claim(
                        "Incorporated in 2014, based in Pune.",
                        "identity_incorporation",
                        "Incorporated in 2014",
                        1,
                    ),
                ]
            }
        ]
    )
    out = run(extract_claims(llm, PAGES))

    assert [c.text for c in out.claims] == [
        "Incorporated in 2014, based in Pune",
        "We employ 250 people",
        "We have no debt",
        "We opened a new facility in October 2026",
    ]
    assert [c.page for c in out.claims] == [1, 2, 2, 3]
    assert out.claims[0].components == {"year": "2014", "city": "Pune"}
    assert [d.label for d in out.dropped] == ["We raised growth funding in 2025"]
    assert "=== PAGE 2 ===" in llm.calls[0].user


def test_claims_from_plain_string_have_no_page():
    llm = FakeLlm(structured=[{"claims": [claim("Based in Pune", "location", "based in Pune", 4)]}])
    out = run(extract_claims(llm, "Acme is based in Pune."))
    assert out.claims[0].page is None
    assert "=== PAGE" not in llm.calls[0].user


def test_long_documents_are_batched_without_truncation():
    pages = [PageText(page=n, text=f"page {n} " + "x" * 90) for n in range(1, 8)]
    batches = batch_pages(pages, max_chars=250)
    assert len(batches) > 1
    assert [p.page for b in batches for p in b] == list(range(1, 8))
    huge = PageText(page=9, text="\n".join(["word " * 30] * 20))
    pieces = batch_pages([huge], max_chars=400)
    assert sum(len(p.text) for b in pieces for p in b) >= len(huge.text) - 20
    assert all(len(p.text) <= 400 for b in pieces for p in b)
    assert render_batch(pieces[0]).startswith("=== PAGE 9 ===")


def test_one_call_per_batch():
    pages = [PageText(page=n, text="y" * 300) for n in range(1, 4)]
    llm = FakeLlm(structured=[{"claims": []}] * 3)
    run(extract_claims(llm, pages, max_chars=300))
    assert len(llm.calls) == 3


EVIDENCE = (
    "Pune, 14 March 2026 - Acme Warehousing Pvt Ltd today announced plans for a new "
    "fulfilment centre in Chakan, expected to begin operations in early 2027."
)
FACILITY = ClaimRef(
    id="c5",
    text="We opened a new facility in October 2026",
    category="dated_event",
    components={"date": "2026-10", "stage": "operating"},
)


def test_facts_require_verbatim_spans():
    llm = FakeLlm(
        structured=[
            {
                "speaks_to_claim": True,
                "entity_name": "Acme Warehousing Pvt Ltd",
                "effective_date": "2026-03-14",
                "effective_date_span": "14 March 2026",
                "facts": [
                    {
                        "name": "stage",
                        "value": "planned",
                        "span": "announced plans for a new fulfilment centre in Chakan",
                    },
                    {
                        "name": "expected_start",
                        "value": "2027",
                        "span": "expected to begin operations in early 2027",
                    },
                    # Not in the evidence: dropped.
                    {"name": "stage", "value": "operating", "span": "the centre is now operating"},
                    # Year not in its own span: dropped.
                    {"name": "year", "value": "2025", "span": "fulfilment centre in Chakan"},
                ],
            }
        ]
    )
    out = run(extract_facts(llm, FACILITY, EVIDENCE, source_label="news"))
    assert out.claim_id == "c5"
    assert out.speaks_to_claim is True
    assert [(f.name, f.value) for f in out.facts] == [
        ("stage", "planned"),
        ("expected_start", "2027"),
    ]
    assert len(out.dropped) == 2
    assert out.entity_name == "Acme Warehousing Pvt Ltd"
    assert out.effective_date == "2026-03-14"
    assert "We opened a new facility" in llm.calls[0].user


def test_facts_without_surviving_spans_mean_silent_and_bad_entity_or_date_cleared():
    llm = FakeLlm(
        structured=[
            {
                "speaks_to_claim": True,
                "entity_name": "Acme Logistics Ltd",  # not the name in the evidence
                "effective_date": "October 2026",  # not ISO
                "effective_date_span": "14 March 2026",
                "facts": [{"name": "stage", "value": "operating", "span": "opened in October"}],
            }
        ]
    )
    out = run(extract_facts(llm, FACILITY, EVIDENCE))
    assert out.speaks_to_claim is False
    assert out.facts == []
    assert out.entity_name is None
    assert out.effective_date is None and out.effective_date_span is None


def test_effective_date_year_must_be_in_its_span():
    llm = FakeLlm(
        structured=[
            {
                "speaks_to_claim": False,
                "effective_date": "2025-03-14",
                "effective_date_span": "14 March 2026",
                "facts": [],
            }
        ]
    )
    assert run(extract_facts(llm, FACILITY, EVIDENCE)).effective_date is None
