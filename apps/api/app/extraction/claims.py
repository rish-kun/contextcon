"""Seller document → atomic factual claims.

The document arrives as pages (already PII-redacted, see `pii.py`). Pages are
packed into batches of at most `max_chars`, each page introduced by a
"=== PAGE n ===" marker. A claim is kept only if its quote is found verbatim in
the batch, and its page number comes from where the quote is found, not from
what the model said.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.extraction.criteria import DroppedItem
from app.extraction.llm import StructuredLlm, run_structured
from app.extraction.prompts import CLAIMS, PROMPT_VERSION
from app.extraction.spans import normalize, span_in

ClaimCategory = Literal[
    "identity_incorporation",
    "location",
    "team_size",
    "leadership_history",
    "funding",
    "dated_event",
    "customer_partnership",
    "financials",
    "debt_security",
    "litigation",
    "other",
]

DEFAULT_MAX_CHARS = 40_000


class PageText(BaseModel):
    page: int | None = None
    text: str


class ComponentDraft(BaseModel):
    name: str
    value: str


class ClaimDraft(BaseModel):
    assertion: str
    category: ClaimCategory
    components: list[ComponentDraft] = Field(default_factory=list)
    quote: str
    page: int | None = None


class ClaimsDraft(BaseModel):
    claims: list[ClaimDraft]


class Claim(BaseModel):
    text: str
    category: ClaimCategory
    components: dict[str, str] = Field(default_factory=dict)
    quote: str
    page: int | None = None


class ClaimsExtraction(BaseModel):
    claims: list[Claim]
    dropped: list[DroppedItem] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


def as_pages(document: str | list[PageText] | list[dict]) -> list[PageText]:
    if isinstance(document, str):
        return [PageText(page=None, text=document)]
    return [p if isinstance(p, PageText) else PageText.model_validate(p) for p in document]


def _split_long(page: PageText, max_chars: int) -> list[PageText]:
    """Split one oversized page on paragraph (then line) boundaries; never truncate."""
    if len(page.text) <= max_chars:
        return [page]
    lines: list[str] = []
    for line in page.text.replace("\r\n", "\n").split("\n"):
        # A single enormous line is cut into max_chars pieces.
        lines.extend(line[i : i + max_chars] for i in range(0, max(len(line), 1), max_chars))
    parts: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return [PageText(page=page.page, text=t) for t in parts if t.strip()]


def batch_pages(pages: list[PageText], max_chars: int = DEFAULT_MAX_CHARS) -> list[list[PageText]]:
    batches: list[list[PageText]] = []
    current: list[PageText] = []
    size = 0
    for page in pages:
        for piece in _split_long(page, max_chars):
            if current and size + len(piece.text) > max_chars:
                batches.append(current)
                current, size = [], 0
            current.append(piece)
            size += len(piece.text)
    if current:
        batches.append(current)
    return batches


def render_batch(batch: list[PageText]) -> str:
    if all(p.page is None for p in batch):
        return "\n\n".join(p.text for p in batch)
    return "\n\n".join(f"=== PAGE {p.page} ===\n{p.text}" for p in batch)


def locate_page(quote: str, batch: list[PageText], claimed: int | None) -> tuple[bool, int | None]:
    """Find the page that holds `quote`, preferring the page the model named."""
    ordered = sorted(batch, key=lambda p: p.page != claimed)
    for page in ordered:
        if span_in(quote, page.text):
            return True, page.page
    return False, None


def finalize_claims(
    drafts: list[ClaimDraft], batch: list[PageText]
) -> tuple[list[Claim], list[DroppedItem]]:
    kept: list[Claim] = []
    dropped: list[DroppedItem] = []
    for d in drafts:
        found, page = locate_page(d.quote, batch, d.page)
        if not found:
            dropped.append(DroppedItem(label=d.assertion, reason="quote not found in document"))
            continue
        components = {
            c.name.strip().lower(): c.value.strip()
            for c in d.components
            if c.name.strip() and c.value.strip()
        }
        kept.append(
            Claim(
                text=d.assertion.strip(),
                category=d.category,
                components=components,
                quote=d.quote.strip(),
                page=page,
            )
        )
    return kept, dropped


def dedupe_claims(claims: list[Claim]) -> list[Claim]:
    seen: set[str] = set()
    out: list[Claim] = []
    for c in claims:
        key = normalize(c.text).rstrip(".")
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


async def extract_claims(
    llm: StructuredLlm,
    document: str | list[PageText] | list[dict],
    *,
    document_label: str = "seller document",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> ClaimsExtraction:
    """Extract claims from already-redacted document text (a string or a list of pages)."""
    pages = [p for p in as_pages(document) if p.text.strip()]
    claims: list[Claim] = []
    dropped: list[DroppedItem] = []
    calls: list[Any] = []
    for batch in batch_pages(pages, max_chars):
        user = f"Document: {document_label}\n<document>\n{render_batch(batch)}\n</document>"
        draft, record = await run_structured(llm, CLAIMS.system, user, ClaimsDraft)
        if record is not None:
            calls.append(record)
        kept, lost = finalize_claims(draft.claims, batch)
        claims.extend(kept)
        dropped.extend(lost)
    return ClaimsExtraction(claims=dedupe_claims(claims), dropped=dropped, calls=calls)
