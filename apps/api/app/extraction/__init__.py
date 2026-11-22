"""LLM extraction: the model extracts, code verifies, rules decide.

Every function here takes an LLM client that satisfies `StructuredLlm`
(`app/clients/llm.py`), sends no sampling parameters, and keeps only output
whose quotes or spans are found verbatim in the input text.
"""

from app.extraction.claims import Claim, ClaimsExtraction, PageText, extract_claims
from app.extraction.criteria import CriteriaExtraction, Criterion, extract_criteria
from app.extraction.facts import ClaimRef, EvidenceFacts, Fact, extract_facts
from app.extraction.investors import BusinessProfile, InvestorSearchSpec, extract_investor_spec
from app.extraction.llm import DraftingLlm, LlmOutputError, StructuredLlm
from app.extraction.pii import DocumentRedaction, redact_document, regex_redact
from app.extraction.prompts import PROMPT_VERSION
from app.extraction.spans import span_in

__all__ = [
    "PROMPT_VERSION",
    "BusinessProfile",
    "Claim",
    "ClaimRef",
    "ClaimsExtraction",
    "CriteriaExtraction",
    "Criterion",
    "DocumentRedaction",
    "DraftingLlm",
    "EvidenceFacts",
    "Fact",
    "InvestorSearchSpec",
    "LlmOutputError",
    "PageText",
    "StructuredLlm",
    "extract_claims",
    "extract_criteria",
    "extract_facts",
    "extract_investor_spec",
    "redact_document",
    "regex_redact",
    "span_in",
]
