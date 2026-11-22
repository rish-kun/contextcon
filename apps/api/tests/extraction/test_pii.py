import asyncio

import pytest

from app.extraction.claims import PageText
from app.extraction.pii import redact_document, regex_redact


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Write to ravi.k@gmail.com today", "email"),
        ("Call +91 98765 43210 now", "phone"),
        ("Call +91-9876543210 now", "phone"),
        ("Mobile 9876543210", "phone"),
        ("Mobile 09876543210", "phone"),
        ("Office (020) 2765 4321", "phone"),
        ("Office 020-2765 4321", "phone"),
        ("US line +1 415 555 0134", "phone"),
        ("PAN ABCDE1234F on file", "pan"),
        ("Aadhaar 2345 6789 0123", "aadhaar"),
        ("Aadhaar 234567890123", "aadhaar"),
        ("IFSC HDFC0001234 branch", "ifsc"),
        ("Account no. 50100234567891 at HDFC", "bank_account"),
        ("a/c: 1234-5678-9012", "bank_account"),
    ],
)
def test_regex_redacts_each_kind(text, kind):
    out = regex_redact(text)
    assert f"[redacted:{kind}]" in out.text, out.text
    assert out.counts.get(kind) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Incorporated in 2014, based in Pune.",
        "We employ 250 people across 6 sites.",
        "Raised INR 120,000,000 in 2025.",
        "CIN U63030PN2014PTC151234 registered in Maharashtra.",
        "Revenue grew 35% in FY2025-26.",
        "Opened on 2026-10-01.",
    ],
)
def test_regex_leaves_business_facts_alone(text):
    out = regex_redact(text)
    assert out.text == text
    assert out.counts == {}


def test_redaction_log_has_counts_not_values():
    out = regex_redact("a@b.co and c@d.in, PAN ABCDE1234F")
    assert out.counts == {"email": 2, "pan": 1}
    assert "a@b.co" not in str(out.counts)


class PiiLlm:
    def __init__(self, items):
        self.items = items
        self.seen: list[str] = []

    async def extract_structured(self, system, user, schema):
        self.seen.append(user)
        return schema.model_validate({"items": self.items}), None


def test_llm_pass_runs_after_regex_and_removes_flagged_spans():
    pages = [
        PageText(page=1, text="Founder Ravi Kumar (ravi@gmail.com, +91 98765 43210)."),
        PageText(
            page=2,
            text="Ravi lives at 14 Lake View Road,\nKoregaon Park. His salary is INR 48 lakh.",
        ),
    ]
    llm = PiiLlm(
        [
            {"kind": "home_address", "span": "14 Lake View Road, Koregaon Park"},
            {"kind": "individual_salary", "span": "INR 48 lakh"},
            {"kind": "other_personal", "span": "not in the text at all"},
            {"kind": "other_personal", "span": "Ra"},  # too short to act on
        ]
    )
    out = asyncio.run(redact_document(pages, llm))

    # The model never saw what the regex removed.
    assert "ravi@gmail.com" not in llm.seen[0] and "98765" not in llm.seen[0]
    assert "[redacted:email]" in llm.seen[0]

    page2 = out.pages[1].text
    assert "Lake View" not in page2 and "48 lakh" not in page2
    assert "[redacted:home_address]" in page2  # matched across the line break
    assert out.pages[0].text.startswith("Founder Ravi Kumar")  # executive names stay
    assert out.counts == {
        "email": 1,
        "phone": 1,
        "llm:home_address": 1,
        "llm:individual_salary": 1,
        "llm:unmatched": 2,
    }


def test_regex_only_when_no_llm():
    out = asyncio.run(redact_document("Call 9876543210"))
    assert out.pages[0].text == "Call [redacted:phone]"
    assert out.calls == []
