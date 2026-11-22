"""PII minimisation for uploaded document text.

Two passes, regex first:

1. Deterministic regex redaction: `app.documents.redact.regex_redactor`
   (emails, phone numbers, PAN, Aadhaar, IFSC, bank accounts) plus Indian
   landline numbers. It runs before the text is stored and before any LLM
   call, so the model never sees what the regex catches.
2. An LLM pass over the regex-redacted text that flags personal details
   regex cannot recognise (home addresses, salaries of named people, dates of
   birth, other ID numbers). Each flagged span is removed only where it is
   found in the text.

Redacted spans become "[redacted:<kind>]". Logs hold counts by kind only,
never values.

Two ways to use it:
- `await redact_document(pages, llm)` does both passes and returns the pages.
- For `app.documents.service`, which takes a sync `RedactorFn`: run
  `items, calls = await find_personal_details(llm, pages)` on the
  regex-cleaned pages, then pass
  `chain_redactors(regex_redact_fn, span_redactor(items))` as the redactor.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.documents.redact import RedactorFn, chain_redactors, regex_redactor
from app.extraction.claims import DEFAULT_MAX_CHARS, PageText, as_pages, batch_pages, render_batch
from app.extraction.llm import StructuredLlm, run_structured
from app.extraction.prompts import PII, PROMPT_VERSION

# Indian landlines such as 020-2765 4321 or (022) 2345 6789; the shared regex
# redactor covers mobiles and +country numbers but not these.
_LANDLINE = re.compile(r"(?<![\w\d])\(?0\d{2,4}\)?[\s\-]\d{3,4}[\s\-]?\d{4}(?!\d)")


def _landline_redactor(text: str) -> tuple[str, dict[str, int]]:
    text, n = _LANDLINE.subn("[redacted:phone]", text)
    return text, ({"phone": n} if n else {})


regex_redact_fn: RedactorFn = chain_redactors(regex_redactor, _landline_redactor)

LlmPiiKind = Literal[
    "personal_phone",
    "personal_email",
    "home_address",
    "id_number",
    "individual_salary",
    "date_of_birth",
    "other_personal",
]

MIN_LLM_SPAN = 4
MAX_LLM_SPAN = 300


class PiiSpanDraft(BaseModel):
    kind: LlmPiiKind
    span: str


class PiiDraft(BaseModel):
    items: list[PiiSpanDraft] = Field(default_factory=list)


class RedactionResult(BaseModel):
    text: str
    counts: dict[str, int] = Field(default_factory=dict)


class DocumentRedaction(BaseModel):
    pages: list[PageText]
    # Counts by kind only. Never values. Regex kinds are bare ("email"); LLM
    # kinds are prefixed ("llm:home_address"). "llm:unmatched" counts flagged
    # spans that could not be located in the text and so were not removed.
    counts: dict[str, int] = Field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


def regex_redact(text: str) -> RedactionResult:
    text, counts = regex_redact_fn(text)
    return RedactionResult(text=text, counts=counts)


def _flexible_pattern(span: str) -> re.Pattern[str]:
    """Match `span` with any run of whitespace between its tokens."""
    tokens = [re.escape(t) for t in span.split()]
    return re.compile(r"\s+".join(tokens))


def _usable(item: PiiSpanDraft) -> bool:
    span = item.span.strip()
    return MIN_LLM_SPAN <= len(span) <= MAX_LLM_SPAN and "[redacted:" not in span


def span_redactor(items: list[PiiSpanDraft]) -> RedactorFn:
    """A sync redactor that removes the LLM-flagged spans (for `chain_redactors`).

    Its log counts hits only, as "llm:<kind>". Spans too short or too long to
    act on safely are ignored.
    """
    # Longest first, so a full address is removed before a fragment of it.
    ordered = sorted((i for i in items if _usable(i)), key=lambda i: len(i.span), reverse=True)
    patterns = [(i.kind, _flexible_pattern(i.span.strip())) for i in ordered]

    def redact(text: str) -> tuple[str, dict[str, int]]:
        counts: Counter[str] = Counter()
        for kind, pattern in patterns:
            text, n = pattern.subn(f"[redacted:{kind}]", text)
            counts[f"llm:{kind}"] += n
        return text, {k: v for k, v in counts.items() if v}

    return redact


async def find_personal_details(
    llm: StructuredLlm,
    document: str | list[PageText] | list[dict],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[list[PiiSpanDraft], list[Any]]:
    """Ask the model for personal details in ALREADY regex-redacted text."""
    flagged: list[PiiSpanDraft] = []
    calls: list[Any] = []
    pages = [p for p in as_pages(document) if p.text.strip()]
    for batch in batch_pages(pages, max_chars):
        draft, record = await run_structured(
            llm, PII.system, f"<text>\n{render_batch(batch)}\n</text>", PiiDraft
        )
        if record is not None:
            calls.append(record)
        flagged.extend(draft.items)
    return flagged, calls


def _unmatched(items: list[PiiSpanDraft], pages: list[PageText]) -> int:
    """Flagged spans that were unusable or found on no page (so nothing was removed)."""
    return sum(
        1
        for i in items
        if not _usable(i)
        or not any(_flexible_pattern(i.span.strip()).search(p.text) for p in pages)
    )


async def redact_document(
    document: str | list[PageText] | list[dict],
    llm: StructuredLlm | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> DocumentRedaction:
    """Regex-redact every page, then (if `llm` is given) apply the LLM pass."""
    counts: Counter[str] = Counter()
    pages: list[PageText] = []
    for page in as_pages(document):
        text, log = regex_redact_fn(page.text)
        counts.update(log)
        pages.append(PageText(page=page.page, text=text))

    calls: list[Any] = []
    if llm is not None:
        flagged, calls = await find_personal_details(llm, pages, max_chars=max_chars)
        if flagged:
            counts["llm:unmatched"] += _unmatched(flagged, pages)
            redact = span_redactor(flagged)
            redacted: list[PageText] = []
            for page in pages:
                text, log = redact(page.text)
                counts.update(log)
                redacted.append(PageText(page=page.page, text=text))
            pages = redacted

    return DocumentRedaction(
        pages=pages, counts={k: v for k, v in counts.items() if v}, calls=calls
    )
