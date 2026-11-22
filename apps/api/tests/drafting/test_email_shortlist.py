import asyncio

import pytest

from app.drafting.seller_email import (
    RequestItem,
    SellerEmailRequest,
    draft_seller_email,
    fallback_email,
    parse_email,
    validate_email,
)
from app.drafting.shortlist import CriterionResult, draft_shortlist_why, fallback_why
from tests.extraction.fakes import FakeLlm

REQUEST = SellerEmailRequest(
    company_name="Acme Warehousing",
    recipient_name="Ms Rao",
    sender_name="Priya Shah",
    sender_organisation="Northline Logistics",
    items=[
        RequestItem(
            id="r1",
            document="Dated payroll summary",
            reason="team size",
            questions=['"We employ 250 people"'],
        ),
        RequestItem(
            id="r2",
            document="Lender statements",
            reason="debt position",
            questions=['"We have no debt"'],
        ),
    ],
)

GOOD = """Subject: Documents for our review of Acme Warehousing

Dear Ms Rao,

Thank you for your time so far. To complete our first-pass review, could you share:

1. Dated payroll summary
   This would help us confirm the statement "We employ 250 people".
2. Lender statements
   This would help us confirm the statement "We have no debt".

If any of these are not available, please let us know.

Best regards,
Priya Shah
Northline Logistics"""


def test_good_email_passes():
    assert validate_email(GOOD, REQUEST) == []
    subject, body = parse_email(GOOD)
    assert subject == "Documents for our review of Acme Warehousing"
    assert body.startswith("Dear Ms Rao")


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (lambda t: t.replace("Subject: ", "Re: "), "Subject"),
        (lambda t: t.replace("Lender statements", "Bank letters"), "Lender statements"),
        (lambda t: t + "\nWe guarantee a quick decision.", "guarantee"),
        (lambda t: t + "\nThis request shall remain confidential.", "shall"),
        (lambda t: t + "\nWe will invest once these arrive.", "we will invest"),
        (lambda t: t + "\nUpload here: https://example.com/upload", "link"),
        (lambda t: t + "\nCall me on +91 98765 43210.", "phone"),
        (lambda t: t.replace("Priya Shah", "[Your name]"), "placeholder"),
    ],
)
def test_bad_emails_rejected(mutate, problem):
    issues = validate_email(mutate(GOOD), REQUEST)
    assert any(problem in i for i in issues), issues


def test_draft_seller_email_falls_back_to_template():
    llm = FakeLlm(drafts=["Hi, send everything. We guarantee a deal.", "Still no subject"])
    out = asyncio.run(draft_seller_email(llm, REQUEST))
    assert out.used_fallback and len(out.rejected_attempts) == 2
    subject, body = fallback_email(REQUEST)
    assert (out.subject, out.body) == (subject, body)
    assert validate_email(f"Subject: {out.subject}\n\n{out.body}", REQUEST) == []
    assert "Dated payroll summary" in llm.calls[0].user


def test_draft_seller_email_uses_valid_draft():
    out = asyncio.run(draft_seller_email(FakeLlm(drafts=[GOOD]), REQUEST))
    assert not out.used_fallback and out.subject.startswith("Documents for")


def test_empty_request_list_is_an_error():
    with pytest.raises(ValueError):
        asyncio.run(draft_seller_email(FakeLlm(), REQUEST.model_copy(update={"items": []})))


RESULTS = [
    CriterionResult(
        id="C1", label="Headquartered in India", kind="must", result="pass", detail="HQ Pune, India"
    ),
    CriterionResult(id="C2", label="Privately held", kind="must", result="pass"),
    CriterionResult(id="C3", label="Serves enterprise customers", kind="must", result="unknown"),
    CriterionResult(id="C4", label="Recent expansion", kind="preference", result="fail"),
]


def test_shortlist_why_valid_draft():
    text = (
        "Acme Warehousing is headquartered in Pune, India and privately held [C1][C2]. "
        "Whether it serves enterprise customers is unknown [C3]. "
        "It does not show recent expansion [C4]."
    )
    out = asyncio.run(draft_shortlist_why(FakeLlm(drafts=[text]), "Acme Warehousing", RESULTS))
    assert not out.used_fallback
    assert out.citations_used == ["C1", "C2", "C3", "C4"]


def test_shortlist_why_rejects_judgement_and_uncited_text():
    llm = FakeLlm(
        drafts=[
            "Acme is the best target and we recommend it [C1].",
            "Acme fits the thesis well. It is in India [C1].",
        ]
    )
    out = asyncio.run(draft_shortlist_why(llm, "Acme Warehousing", RESULTS))
    assert out.used_fallback
    assert any("judgement" in i for i in out.rejected_attempts[0])
    assert out.text == fallback_why(RESULTS)
    assert out.text == (
        "Meets: Headquartered in India; Privately held [C1][C2]. "
        "Does not meet: Recent expansion [C4]. "
        "Not yet known: Serves enterprise customers [C3]."
    )


# --- Blocker-first groups -----------------------------------------------------------

CONDITION = (
    "If the verified figures match the claim, it is supported; otherwise it is contradicted."
)
GROUPED = SellerEmailRequest(
    company_name="Acme Warehousing",
    items=[
        RequestItem(
            id="r1",
            document="Dated payroll summary",
            reason="team size",
            questions=['"We employ 250 people": cannot verify.'],
            needed=True,
        ),
        RequestItem(
            id="r2",
            document="Audited financial statements",
            reason=f"Settles financials (cannot verify). {CONDITION}",
            questions=['"Revenue was 40 crore": cannot verify.'],
            conditions=[CONDITION],
        ),
        RequestItem(id="r3", document="Lender statements", reason="debt position"),
    ],
)


def test_fallback_lists_needed_documents_first_under_their_heading():
    subject, body = fallback_email(GROUPED)
    needed = body.index("Needed to complete our screening:")
    also = body.index("Also helpful:")
    assert needed < body.index("1. Dated payroll summary") < also
    assert also < body.index("2. Audited financial statements") < body.index("3. Lender")
    assert CONDITION in body  # both outcomes, for the financial item
    assert "help us check" in body and "cannot verify.." not in body
    assert validate_email(f"Subject: {subject}\n\n{body}", GROUPED) == []


def test_without_needed_documents_there_are_no_headings():
    _, body = fallback_email(REQUEST)
    assert "Needed to complete" not in body and "Also helpful:" not in body


def test_grouped_drafts_must_keep_the_headings_and_the_order():
    _, body = fallback_email(GROUPED)
    good = f"Subject: Documents\n\n{body}"
    assert validate_email(good, GROUPED) == []
    no_heading = good.replace("Needed to complete our screening:", "Documents:")
    assert any("Needed to complete" in i for i in validate_email(no_heading, GROUPED))
    swapped = good.replace("1. Dated payroll summary", "1. Placeholder").replace(
        "3. Lender statements", "3. Lender statements\n4. Dated payroll summary"
    )
    issues = validate_email(swapped, GROUPED)
    assert any('"Dated payroll summary" must be under' in i for i in issues), issues


def test_wording_that_implies_qualifying_or_a_disposition_is_rejected():
    _, body = fallback_email(GROUPED)
    good = f"Subject: Documents\n\n{body}"
    for extra, problem in [
        ("Sending these will help you qualify.", "qualif"),
        ("With these we can prioritise the company.", "prioriti"),
        ("Otherwise we would deprioritise it.", "deprioriti"),
    ]:
        issues = validate_email(good + "\n" + extra, GROUPED)
        assert any(problem in i for i in issues), (extra, issues)


def test_llm_payload_carries_groups_and_either_way_sentences():
    llm = FakeLlm(drafts=["no subject"] * 2)
    out = asyncio.run(draft_seller_email(llm, GROUPED))
    assert out.used_fallback  # nothing is sent either way: this is a draft to approve
    user = llm.calls[0].user
    assert '"headings": true' in user
    assert '"group": "Needed to complete our screening"' in user
    assert CONDITION in user
