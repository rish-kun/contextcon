"""Business profile → investor search spec (comparable-company criteria + funding sought)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.extraction.criteria import Criterion, CriterionDraft, DroppedItem, finalize_criteria
from app.extraction.llm import StructuredLlm, run_structured
from app.extraction.prompts import INVESTOR_SPEC, PROMPT_VERSION
from app.extraction.spans import normalize, span_in

Instrument = Literal["equity", "debt", "convertible", "grant", "unspecified"]


class BusinessProfile(BaseModel):
    sector: str
    location: str
    stage: str = ""
    size: str = ""
    funding_sought: str = ""
    description: str = ""

    def as_text(self) -> str:
        rows = [
            ("Sector", self.sector),
            ("Location", self.location),
            ("Stage", self.stage),
            ("Size", self.size),
            ("Funding sought", self.funding_sought),
            ("Description", self.description),
        ]
        return "\n".join(f"{k}: {v.strip()}" for k, v in rows if v and v.strip())


class FundingSoughtDraft(BaseModel):
    instrument: Instrument
    round_type: str | None = None
    amount_usd: float | None = None
    quote: str | None = None


class InvestorSpecDraft(BaseModel):
    comparable_criteria: list[CriterionDraft]
    activity_query: str
    funding_sought: FundingSoughtDraft


class FundingSought(BaseModel):
    instrument: Instrument
    round_type: str | None = None
    amount_usd: float | None = None
    quote: str | None = None
    needs_value_resolution: bool = False


class InvestorSearchSpec(BaseModel):
    comparable_criteria: list[Criterion]
    activity_query: str
    funding_sought: FundingSought
    dropped: list[DroppedItem] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    calls: list[Any] = Field(default_factory=list, exclude=True)


def _snake(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


_USD = re.compile(r"\$|\busd\b|\bus\s?dollars?\b|\bdollars?\b", re.IGNORECASE)
_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|mn|million|b|bn|billion)?\b", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6}
_SCALE.update({"b": 1e9, "bn": 1e9, "billion": 1e9})


def amount_supported(amount_usd: float, quote: str) -> bool:
    """True when the quote states this amount in US dollars (e.g. "$2M", "USD 2,000,000")."""
    if not _USD.search(quote):
        return False
    for number, unit in _NUMBER.findall(quote):
        value = float(number.replace(",", "")) * _SCALE.get(unit.lower(), 1.0)
        if abs(value - amount_usd) <= max(1.0, amount_usd * 1e-6):
            return True
    return False


def finalize_funding(draft: FundingSoughtDraft, source_text: str) -> FundingSought:
    """Keep the funding fields only when the profile text supports them."""
    if not draft.quote or not span_in(draft.quote, source_text):
        return FundingSought(instrument="unspecified")
    round_type = _snake(draft.round_type) if draft.round_type else None
    if round_type:
        words = re.sub(r"[^a-z0-9]+", " ", normalize(source_text))
        if f" {round_type.replace('_', ' ')} " not in f" {words} ":
            round_type = None  # the profile does not name this round
    amount = draft.amount_usd
    if amount is not None and not amount_supported(amount, draft.quote):
        amount = None
    return FundingSought(
        instrument=draft.instrument,
        round_type=round_type or None,
        amount_usd=amount,
        quote=draft.quote,
        needs_value_resolution=bool(round_type),
    )


async def extract_investor_spec(llm: StructuredLlm, profile: BusinessProfile) -> InvestorSearchSpec:
    text = profile.as_text()
    if not text:
        raise ValueError("business profile is empty")
    draft, record = await run_structured(
        llm,
        INVESTOR_SPEC.system,
        f"Business description:\n<business>\n{text}\n</business>",
        InvestorSpecDraft,
    )
    criteria, dropped = finalize_criteria(draft.comparable_criteria, text)
    return InvestorSearchSpec(
        comparable_criteria=criteria,
        activity_query=draft.activity_query.strip() or profile.sector,
        funding_sought=finalize_funding(draft.funding_sought, text),
        dropped=dropped,
        calls=[record] if record is not None else [],
    )
