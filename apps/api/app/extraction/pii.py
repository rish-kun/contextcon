"""PII minimisation for uploaded document text.

Two passes, regex first:

1. Deterministic regex redaction of emails, phone numbers, PAN, Aadhaar, IFSC
   and bank account numbers. This runs before the text is stored and before
   any LLM call, so the model never sees what the regex catches.
2. An optional LLM pass over the regex-redacted text that flags personal
   details regex cannot recognise (home addresses, salaries of named people,
   dates of birth, other ID numbers). Each flagged span is removed only where
   it is found in the text.

Redacted spans become "[redacted:<kind>]". The redaction log holds counts by
kind only, never the values.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.extraction.claims import DEFAULT_MAX_CHARS, PageText, as_pages, batch_pages, render_batch
from app.extraction.llm import StructuredLlm, run_structured
from app.extraction.prompts import PII, PROMPT_VERSION

# Order matters: more specific patterns run first so a PAN is not eaten by a
# looser pattern, and account numbers are matched only next to an account cue.
_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("pan", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("ifsc", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    (
        "bank_account",
        re.compile(
            r"(?i)\b(?:a/c|acct|account)(?:\s*(?:no\.?|number|#))?\s*[:\-]?\s*\d[\d\s\-]{7,20}\d\b"
        ),
    ),
    ("aadhaar", re.compile(r"(?<![\d+])[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}(?![\d])")),
    (
        "phone",
        re.compile(r"(?<![\w+])(?:\+91[\s\-]?|0091[\s\-]?|0)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)"),
    ),
    (
        "phone",
        re.compile(
            r"(?<![\w])\+\d{1,3}[\s\-]?(?:\(\d{1,4}\)[\s\-]?)?\d{2,4}(?:[\s\-]?\d{2,4}){2,4}"
        ),
    ),
    # Indian landlines such as 020-2765 4321 or (022) 2345 6789.
    ("phone", re.compile(r"(?<![\w\d])\(?0\d{2,4}\)?[\s\-]\d{3,4}[\s\-]?\d{4}(?![\d])")),
]

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
    counts: Counter[str] = Counter()
    for kind, pattern in _REGEXES:

        def _sub(_m: re.Match[str], kind: str = kind) -> str:
            counts[kind] += 1
            return f"[redacted:{kind}]"

        text = pattern.sub(_sub, text)
    return RedactionResult(text=text, counts=dict(counts))


def _flexible_pattern(span: str) -> re.Pattern[str]:
    """Match `span` with any run of whitespace between its tokens."""
    tokens = [re.escape(t) for t in span.split()]
    return re.compile(r"\s+".join(tokens))


def _usable(item: PiiSpanDraft) -> bool:
    span = item.span.strip()
    return MIN_LLM_SPAN <= len(span) <= MAX_LLM_SPAN and "[redacted:" not in span


def apply_spans(
    pages: list[PageText], items: list[PiiSpanDraft]
) -> tuple[list[PageText], Counter[str]]:
    """Remove each flagged span wherever it occurs; count hits by kind, and misses."""
    counts: Counter[str] = Counter()
    # Longest first, so a full address is removed before a fragment of it.
    ordered = sorted((i for i in items if _usable(i)), key=lambda i: len(i.span), reverse=True)
    counts["llm:unmatched"] += len(items) - len(ordered)
    texts = [p.text for p in pages]
    for item in ordered:
        pattern = _flexible_pattern(item.span.strip())
        hits = 0
        for n, text in enumerate(texts):
            texts[n], found = pattern.subn(f"[redacted:{item.kind}]", text)
            hits += found
        counts[f"llm:{item.kind}" if hits else "llm:unmatched"] += hits or 1
    out = [PageText(page=p.page, text=t) for p, t in zip(pages, texts, strict=True)]
    return out, counts


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
        result = regex_redact(page.text)
        counts.update(result.counts)
        pages.append(PageText(page=page.page, text=result.text))

    calls: list[Any] = []
    if llm is not None:
        flagged: list[PiiSpanDraft] = []
        for batch in batch_pages([p for p in pages if p.text.strip()], max_chars):
            draft, record = await run_structured(
                llm, PII.system, f"<text>\n{render_batch(batch)}\n</text>", PiiDraft
            )
            if record is not None:
                calls.append(record)
            flagged.extend(draft.items)
        if flagged:
            pages, llm_counts = apply_spans(pages, flagged)
            counts.update(llm_counts)

    return DocumentRedaction(
        pages=pages, counts={k: v for k, v in counts.items() if v}, calls=calls
    )
