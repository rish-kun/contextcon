"""The consolidated seller request email.

One email for the whole request list. The model drafts; code checks that every
requested document is named, that nothing is promised, that there is no legal
language, links, contact details or placeholders. If the draft still fails
after one corrective retry, a plain deterministic template is used instead.
The analyst can edit either before approving.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.drafting._loop import draft_until_valid
from app.drafting.prompts import PROMPT_VERSION, SELLER_EMAIL
from app.extraction.llm import DraftingLlm
from app.extraction.spans import normalize


class RequestItem(BaseModel):
    id: str
    document: str  # e.g. "Dated payroll summary"
    reason: str = ""  # why it is needed, from the rules table
    questions: list[str] = Field(default_factory=list)  # the claims/questions it resolves


class SellerEmailRequest(BaseModel):
    company_name: str
    items: list[RequestItem]
    recipient_name: str | None = None
    sender_name: str | None = None
    sender_organisation: str | None = None


class SellerEmail(BaseModel):
    subject: str
    body: str
    used_fallback: bool = False
    rejected_attempts: list[list[str]] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


# Promises, commitments and legal phrasing a first-pass request must not carry.
BANNED_PHRASES: tuple[str, ...] = (
    "guarantee",
    "we promise",
    "we will invest",
    "we will proceed",
    "we commit",
    "commitment to invest",
    "term sheet",
    "valuation",
    "exclusivity",
    "binding",
    "hereby",
    "shall",
    "herein",
    "whereas",
    "indemn",
    "warrant",
    "without prejudice",
    "liability",
    "liabilities",
    "legal obligation",
    "confidentiality obligation",
)
# Phrases matched as word prefixes ("indemnify", "warranty"); the rest as whole words.
_PREFIX_PHRASES = frozenset({"guarantee", "indemn", "warrant"})
_URL = re.compile(r"https?://|www\.", re.I)
_EMAIL = re.compile(r"\b[\w.%+\-]+@[\w.\-]+\.[a-z]{2,}\b", re.I)
_PHONE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")
_PLACEHOLDER = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>")


def parse_email(text: str) -> tuple[str, str]:
    """Split "Subject: ...\\n\\nbody" into (subject, body). Subject is "" when missing."""
    lines = text.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        return subject, "\n".join(lines[1:]).strip()
    return "", "\n".join(lines).strip()


def _given_text(request: SellerEmailRequest) -> str:
    """Everything the caller supplied; a phrase that appears here is not the model's."""
    parts = [request.company_name, request.recipient_name or "", request.sender_name or ""]
    parts.append(request.sender_organisation or "")
    for item in request.items:
        parts.extend([item.document, item.reason, *item.questions])
    return normalize(" ".join(parts))


def validate_email(text: str, request: SellerEmailRequest) -> list[str]:
    subject, body = parse_email(text)
    issues: list[str] = []
    if not subject:
        issues.append('first line must be "Subject: ..."')
    if not body:
        issues.append("body is empty")
    norm_body = normalize(body)
    given = _given_text(request)
    for item in request.items:
        if normalize(item.document) not in norm_body:
            issues.append(f'document "{item.document}" is not named exactly')
    full = normalize(f"{subject}\n{body}")
    for phrase in BANNED_PHRASES:
        tail = "" if phrase in _PREFIX_PHRASES else r"\b"
        if re.search(rf"\b{re.escape(phrase)}{tail}", full) and phrase not in given:
            issues.append(f'contains "{phrase}" (no promises or legal language)')
    if _URL.search(body):
        issues.append("contains a link")
    if _EMAIL.search(body):
        issues.append("contains an email address")
    if any(normalize(m) not in given for m in _PHONE.findall(body)):
        issues.append("contains a phone number")
    if _PLACEHOLDER.search(body):
        issues.append("contains a placeholder or bracketed text")
    return issues


def fallback_email(request: SellerEmailRequest) -> tuple[str, str]:
    greeting = f"Dear {request.recipient_name}," if request.recipient_name else "Hello,"
    lines = [
        greeting,
        "",
        f"Thank you for your time so far. To complete our first-pass review of "
        f"{request.company_name}, could you share the following documents?",
        "",
    ]
    for n, item in enumerate(request.items, 1):
        lines.append(f"{n}. {item.document}")
        if item.questions:
            lines.append(f"   This would help us confirm: {'; '.join(item.questions)}.")
        elif item.reason:
            lines.append(f"   This would help us with: {item.reason}.")
    lines += ["", "If any of these are not available, a short note saying so is also helpful."]
    lines += ["", "Best regards,"]
    lines += [x for x in (request.sender_name, request.sender_organisation) if x]
    subject = f"Documents for our review of {request.company_name}"
    return subject, "\n".join(lines)


async def draft_seller_email(
    llm: DraftingLlm, request: SellerEmailRequest, *, max_attempts: int = 2
) -> SellerEmail:
    if not request.items:
        raise ValueError("request list is empty; there is nothing to ask for")
    payload = {
        "company": request.company_name,
        "recipient_name": request.recipient_name,
        "sender_name": request.sender_name,
        "sender_organisation": request.sender_organisation,
        "documents": [
            {"document": i.document, "why_needed": i.reason, "questions_it_resolves": i.questions}
            for i in request.items
        ],
    }
    user = "Request list:\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    attempts = await draft_until_valid(
        llm,
        SELLER_EMAIL.system,
        user,
        lambda text: validate_email(text, request),
        max_attempts=max_attempts,
    )
    if attempts.text is None:
        subject, body = fallback_email(request)
    else:
        subject, body = parse_email(attempts.text)
    return SellerEmail(
        subject=subject,
        body=body,
        used_fallback=attempts.text is None,
        rejected_attempts=attempts.issues,
        calls=attempts.calls,
    )
