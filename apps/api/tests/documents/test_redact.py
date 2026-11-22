import pytest

from app.documents.redact import chain_redactors, merge_counts, regex_redactor


def test_redacts_email_phone_pan_aadhaar() -> None:
    text = (
        "Write to founder@northwind.example or ops.team+deals@mail.co.in. "
        "Call +91 98765 43210, 9876543210 or 091-98765-43210. "
        "Aadhaar 2345 6789 0123 and 234567890123. PAN ABCDE1234F."
    )
    redacted, log = regex_redactor(text)
    assert "@" not in redacted
    assert "98765" not in redacted and "9876543210" not in redacted
    assert "2345 6789 0123" not in redacted and "234567890123" not in redacted
    assert "ABCDE1234F" not in redacted
    assert log == {"email": 2, "phone": 3, "aadhaar": 2, "pan": 1}
    assert "[redacted:email]" in redacted and "[redacted:pan]" in redacted


def test_redacts_bank_details_only_near_account_keyword() -> None:
    text = "Pay to A/c No: 50100123456789, IFSC HDFC0001234. Revenue was 120000000 in FY25."
    redacted, log = regex_redactor(text)
    assert "50100123456789" not in redacted
    assert "A/c No: [redacted:bank_account]" in redacted
    assert "HDFC0001234" not in redacted
    assert "120000000" in redacted
    assert log == {"bank_account": 1, "ifsc": 1}


def test_international_phone() -> None:
    redacted, log = regex_redactor("London office: +44 20 7946 0958.")
    assert redacted == "London office: [redacted:phone]."
    assert log == {"phone": 1}


@pytest.mark.parametrize(
    "text",
    [
        "Incorporated in 2014, based in Pune.",
        "We employ 250 people across 4 warehouses.",
        "Raised INR 1,20,00,000 in 2025; ARR 3.5 crore.",
        "CIN U63030MH2014PTC123456 is the registry id.",
        "Opened on 2026-10-01; order 1234-5678 shipped.",
    ],
)
def test_business_facts_are_untouched(text: str) -> None:
    redacted, log = regex_redactor(text)
    assert redacted == text
    assert log == {}


def test_chain_runs_in_order_and_sums_counts() -> None:
    seen: list[str] = []

    def fake_llm(text: str) -> tuple[str, dict[str, int]]:
        seen.append(text)
        return text.replace("Asha Rao", "[redacted:person]"), {"person": 1, "email": 0}

    redactor = chain_redactors(regex_redactor, fake_llm)
    redacted, log = redactor("Asha Rao, asha@fixture.test")
    # The LLM stage only ever sees regex-cleaned text.
    assert seen == ["Asha Rao, [redacted:email]"]
    assert redacted == "[redacted:person], [redacted:email]"
    assert log == {"email": 1, "person": 1}


def test_chain_requires_a_redactor() -> None:
    with pytest.raises(ValueError):
        chain_redactors()


def test_merge_counts() -> None:
    assert merge_counts({"email": 1}, {}, {"email": 2, "pan": 1}) == {"email": 3, "pan": 1}
