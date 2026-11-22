"""LLM drafting: seller request email, memo sections, shortlist explanations.

Drafts are validated in code. Memo and shortlist text must cite an id on
every sentence; anything that fails after one corrective retry is replaced by
a deterministic fallback, so uncited text never leaves this package.
"""

from app.drafting.citations import (
    CitationReport,
    UncitedSentenceError,
    check_citations,
    require_citations,
)
from app.drafting.memo import AcceptedFact, MemoSection, MemoSectionRequest, draft_memo_section
from app.drafting.prompts import PROMPT_VERSION
from app.drafting.seller_email import (
    RequestItem,
    SellerEmail,
    SellerEmailRequest,
    draft_seller_email,
)
from app.drafting.shortlist import CriterionResult, ShortlistWhy, draft_shortlist_why

__all__ = [
    "PROMPT_VERSION",
    "AcceptedFact",
    "CitationReport",
    "CriterionResult",
    "MemoSection",
    "MemoSectionRequest",
    "RequestItem",
    "SellerEmail",
    "SellerEmailRequest",
    "ShortlistWhy",
    "UncitedSentenceError",
    "check_citations",
    "draft_memo_section",
    "draft_seller_email",
    "draft_shortlist_why",
    "require_citations",
]
