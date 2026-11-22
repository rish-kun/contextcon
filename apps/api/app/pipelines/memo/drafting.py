"""Drafted memo prose, stored with the assessment version it describes.

The model may only restate *accepted facts*: sourced profile fields of the confirmed
company and the thesis criteria they meet. Every sentence must carry a citation id
(`F1`, `F2`, …) that maps to one evidence row; `app.drafting.check_citations` rejects
uncited sentences, unknown ids and invented numbers, and after one retry the section
falls back to a deterministic restatement. Nothing uncited is ever stored.

Only public records are drafted from. Seller documents are confidential and deleted on
a schedule, while assessment versions are immutable, so prose built from them could
outlive the retention period. Claims appear in the memo as structured lines that
resolve their text at read time instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Case, Evidence, Source
from app.domain.enums import CriterionResult, IdentityStatus
from app.domain.types import AssessmentInputs, AssessmentVersion, FieldFact
from app.drafting import AcceptedFact, MemoSection, MemoSectionRequest, draft_memo_section
from app.drafting.citations import require_citations
from app.drafting.memo import fact_sources, fallback_section
from app.pipelines.evaluate.inputs import UNASSESSABLE_FIELD
from app.pipelines.evaluate.present import uuids

log = logging.getLogger(__name__)

PUBLIC_EXCLUDED_CLASSES = frozenset({"seller_document", "seller_statement"})

FIELD_LABELS: dict[str, str] = {
    "locations.country": "Country on record",
    "locations.headquarters": "Headquarters on record",
    "basic_info.year_founded": "Year founded",
    "basic_info.industries": "Industries",
    "basic_info.company_type": "Ownership type",
    "taxonomy.categories": "Business categories",
    "headcount.total": "Headcount estimate from professional profiles (not a payroll count)",
    "headcount.growth_percent.12m": "Headcount change over 12 months (estimate)",
    "hiring.openings_count": "Open roles (hiring signal)",
    "funding.last_round_type": "Latest funding round type",
    "funding.total_investment_usd": "Total funding recorded (USD)",
}

SECTIONS = {
    "relevance": (
        "Why this company is relevant",
        "Say which thesis criteria the confirmed company meets, citing each fact.",
    ),
    "profile": (
        "Public profile",
        "Summarise the company's public profile. Keep estimates labelled as estimates.",
    ),
}


def _value_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def field_label(path: str) -> str:
    return FIELD_LABELS.get(path, path.replace("_", " ").replace(".", " › "))


async def _public_evidence(session: AsyncSession, case: Case, ids: list[str]) -> dict[str, Source]:
    """Evidence id → source, for evidence that is public, unpurged and in this case."""
    wanted = uuids(ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(Evidence, Source)
        .join(Source, Source.id == Evidence.source_id)
        .where(Evidence.id.in_(wanted), Evidence.case_id == case.id)
    )
    return {
        str(e.id): s
        for e, s in rows.all()
        if e.scrubbed_at is None
        and s.document_id is None
        and s.provider != "upload"
        and s.source_class not in PUBLIC_EXCLUDED_CLASSES
    }


class FactBook:
    """Accepted facts with stable citation ids, in the order they are first cited."""

    def __init__(self) -> None:
        self.evidence_of: dict[str, str] = {}

    def add(self, statement: str, evidence_id: str, src: Source, fact: FieldFact) -> AcceptedFact:
        cid = f"F{len(self.evidence_of) + 1}"
        self.evidence_of[cid] = evidence_id
        return AcceptedFact(
            citation_id=cid,
            statement=statement,
            source_label=src.title or src.publisher or src.provider,
            as_of=fact.as_of.isoformat() if fact.as_of else None,
        )


async def accepted_facts(
    session: AsyncSession, case: Case, inputs: AssessmentInputs, a: AssessmentVersion
) -> tuple[FactBook, dict[str, list[AcceptedFact]]]:
    book = FactBook()
    if inputs.identity_status is not IdentityStatus.CONFIRMED:
        return book, {}
    fields = inputs.company.fields
    public = await _public_evidence(
        session, case, [f.evidence_id for f in fields.values() if f.evidence_id]
    )
    labels = {c.id: c for c in inputs.criteria}
    relevance: list[AcceptedFact] = []
    for e in a.candidate.fit.evaluations:
        crit = labels.get(e.criterion_id)
        if e.result is not CriterionResult.PASS or crit is None or crit.field == UNASSESSABLE_FIELD:
            continue
        fact = fields.get(crit.field)
        if fact is None or fact.evidence_id not in public:
            continue
        estimate = " (an estimate)" if fact.is_estimate else ""
        relevance.append(
            book.add(
                f'Meets the thesis criterion "{crit.label}": {field_label(crit.field)} is '
                f"{_value_text(fact.value)}{estimate}.",
                fact.evidence_id,
                public[fact.evidence_id],
                fact,
            )
        )
    profile: list[AcceptedFact] = []
    for path, fact in sorted(fields.items()):
        if fact.evidence_id not in public or fact.value in (None, "", []):
            continue
        profile.append(
            book.add(
                f"{field_label(path)}: {_value_text(fact.value)}.",
                fact.evidence_id,
                public[fact.evidence_id],
                fact,
            )
        )
    return book, {"relevance": relevance, "profile": profile}


async def _draft(llm: Any, key: str, facts: list[AcceptedFact]) -> MemoSection:
    heading, guidance = SECTIONS[key]
    request = MemoSectionRequest(section=heading, facts=facts, guidance=guidance)
    if llm is not None:
        try:
            return await draft_memo_section(llm, request)
        except Exception:  # noqa: BLE001 - a provider failure must not block the assessment
            log.exception("memo: drafting %s failed; using the deterministic restatement", key)
    text = fallback_section(facts)
    report = require_citations(text, fact_sources(facts))
    return MemoSection(
        section=heading, text=text, citations_used=report.citations_used, used_fallback=True
    )


async def build_memo_document(
    session: AsyncSession, case: Case, inputs: AssessmentInputs, a: AssessmentVersion, llm: Any
) -> dict:
    """The `memo` entry of an assessment version's stored document."""
    book, facts = await accepted_facts(session, case, inputs, a)
    drafted: dict[str, dict] = {}
    for key, section_facts in facts.items():
        if not section_facts:
            continue
        section = await _draft(llm, key, section_facts)
        # Re-check before storing: uncited prose never reaches the database.
        require_citations(section.text, fact_sources(section_facts))
        drafted[key] = {
            "text": section.text,
            "used_fallback": section.used_fallback,
            "citations_used": section.citations_used,
            "rejected_attempts": len(section.rejected_attempts),
            "prompt_version": section.prompt_version,
        }
    used = {c for d in drafted.values() for c in d["citations_used"]}
    return {
        "memo": {
            "drafted": drafted,
            "citations": {c: e for c, e in book.evidence_of.items() if c in used},
        }
    }
