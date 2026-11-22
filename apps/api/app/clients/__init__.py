"""External API clients (Crustdata, Anthropic) with call recording and caching."""

from app.clients.base import (
    CallRecord,
    CallRecorder,
    InMemoryCache,
    InMemoryRecorder,
    ResponseCache,
)
from app.clients.crustdata import (
    CrustdataClient,
    CrustdataCreditsError,
    CrustdataError,
    CrustdataPlanError,
    SemanticSearchUnavailable,
    failed_urls,
    strip_contact_fields,
)
from app.clients.llm import LLMClient, LLMError, LLMRefusal, LLMTruncated, ModelPrice
from app.clients.ratelimit import SlidingWindowRateLimiter

__all__ = [
    "CallRecord",
    "CallRecorder",
    "CrustdataClient",
    "CrustdataCreditsError",
    "CrustdataError",
    "CrustdataPlanError",
    "InMemoryCache",
    "InMemoryRecorder",
    "LLMClient",
    "LLMError",
    "LLMRefusal",
    "LLMTruncated",
    "ModelPrice",
    "ResponseCache",
    "SemanticSearchUnavailable",
    "SlidingWindowRateLimiter",
    "failed_urls",
    "strip_contact_fields",
]
