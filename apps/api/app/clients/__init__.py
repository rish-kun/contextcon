"""External API clients (Crustdata, Anthropic) with call recording and caching."""

from app.clients.base import (
    CallOperation,
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
)
from app.clients.llm import LLMClient, LLMError, LLMRefusal, LLMTruncated, ModelPrice
from app.clients.ratelimit import SlidingWindowRateLimiter
from app.clients.sanitize import sanitize_response, strip_contact_fields

__all__ = [
    "CallOperation",
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
    "sanitize_response",
    "strip_contact_fields",
]
