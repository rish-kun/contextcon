"""Async Crustdata REST client.

Verified against Crustdata's docs (API version 2025-11-01):

- Base URL ``https://api.crustdata.com``.
- Auth: ``authorization: Bearer <key>`` plus the required ``x-api-version: 2025-11-01``.
- Cost: every priced endpoint returns ``X-Credits-Used`` (also on error responses).
  429s from rate limiting are refused before reaching the API and carry no header.
- ``X-Request-Id`` identifies the request (``GET /account/usage/events/{id}`` explains
  a charge).
- Rate limits: 429 carries ``Retry-After`` or ``X-RateLimit-Reset`` (seconds).

Only synchronous endpoints are used; batch endpoints are not on this plan.

Every response is reduced to an allowlist of the fields DealProof reads, with emails
and phone numbers redacted from free text, before it is returned or cached
(`app.clients.sanitize`). DealProof never collects personal contact details.

Every HTTP dispatch is recorded separately (see `app.clients.base`), and a dispatch
whose cost is ambiguous is never retried automatically.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NoReturn

import httpx2
from pydantic import ValidationError

from app.clients import activity
from app.clients.base import (
    CallOperation,
    CallRecord,
    CallRecorder,
    ResponseCache,
    make_cache_key,
    safe_error_code,
    stable_hash,
)
from app.clients.crustdata_models import (
    CompanySearchResult,
    EnrichResult,
    IdentifyResult,
    JobSearchResult,
    PersonSearchResult,
    WebPage,
    WebSearchResult,
)
from app.clients.ratelimit import SlidingWindowRateLimiter
from app.clients.sanitize import sanitize_response, strip_contact_fields  # noqa: F401 (re-export)
from app.settings import Settings, get_settings

PROVIDER = "crustdata"

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

# Endpoint paths (all POST).
COMPANY_IDENTIFY = "/company/identify"
COMPANY_SEARCH = "/company/search"
COMPANY_ENRICH = "/company/enrich"
PERSON_SEARCH = "/person/search"
JOB_SEARCH = "/job/search"
WEB_SEARCH_LIVE = "/web/search/live"
WEB_FETCH_LIVE = "/web/enrich/live"

# Crustdata's default per-endpoint limits (requests per minute, per API key).
DEFAULT_RATE_LIMITS: dict[str, int] = {
    COMPANY_IDENTIFY: 30,
    COMPANY_SEARCH: 30,
    PERSON_SEARCH: 30,
    JOB_SEARCH: 30,
    COMPANY_ENRICH: 15,
    WEB_SEARCH_LIVE: 10,
    WEB_FETCH_LIVE: 10,
}

# Shared by every client in the process (the limits are per API key, not per client).
SHARED_RATE_LIMITER = SlidingWindowRateLimiter(DEFAULT_RATE_LIMITS)

MAX_ENRICH_IDS = 25
MAX_FETCH_URLS = 10

# Enrich groups DealProof needs for a company profile. Enrich bills per returned
# match (2 credits), not per group, except `technographics`, which is left out.
DEFAULT_ENRICH_FIELDS: tuple[str, ...] = (
    "basic_info",
    "headcount",
    "funding",
    "locations",
    "hiring",
    "taxonomy",
    "people",
    "news",
    # Estimated revenue bounds and public-market data (stock symbols, IPO date, fiscal
    # year end): the estimate is indicative only, the market data marks a listed company.
    "revenue",
    "metadata",
    "updated_at",
)

# Person search: no `contact` group (it is never needed and must not be stored).
DEFAULT_PERSON_FIELDS: tuple[str, ...] = (
    "crustdata_person_id",
    "basic_profile",
    "experience",
    "education",
    "social_handles",
)

LEADERSHIP_TITLE_KEYWORDS: tuple[str, ...] = (
    "founder",
    "co-founder",
    "ceo",
    "chief",
    "cto",
    "cfo",
    "coo",
    "managing director",
    "director",
    "president",
    "vp",
    "vice president",
    "head",
    "partner",
)


def parse_credits(headers: httpx2.Headers) -> float | None:
    raw = headers.get("x-credits-used")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class CrustdataError(Exception):
    """A Crustdata call that failed after retries (or with a non-retryable status)."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None,
        error_type: str | None,
        record: CallRecord,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type
        self.record = record


class CrustdataPlanError(CrustdataError):
    """403: the endpoint or a requested field is not on this account's plan."""


class SemanticSearchUnavailable(CrustdataPlanError):
    """403 on company search with ``search``: natural-language mode is not enabled."""


class CrustdataCreditsError(CrustdataError):
    """402: the account is out of credits."""


class CrustdataResponseInvalid(CrustdataError):
    """A paid response that does not fit the typed model.

    The call was still recorded with its usage and the (sanitised) response cached, so
    nothing paid for is lost: `raw` holds the payload, and the same request through
    `CrustdataClient.post` (or a retry) replays it from the cache for free."""

    def __init__(self, message: str, *, record: CallRecord, raw: Any) -> None:
        super().__init__(
            message, status=record.http_status, error_type="invalid_response", record=record
        )
        self.raw = raw


def _typed[M](endpoint: str, parse: Callable[[Any], M], data: Any, record: CallRecord) -> M:
    try:
        return parse(data)
    except (ValidationError, TypeError, ValueError):
        raise CrustdataResponseInvalid(
            _message(endpoint, record.http_status, "invalid_response", record.provider_request_id),
            record=record,
            raw=data,
        ) from None


def _error_class(status: int | None, *, natural_language: bool) -> type[CrustdataError]:
    if status == 402:
        return CrustdataCreditsError
    if status == 403:
        return SemanticSearchUnavailable if natural_language else CrustdataPlanError
    return CrustdataError


class CrustdataClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.crustdata.com",
        api_version: str = "2025-11-01",
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_max: float = 30.0,
        recorder: CallRecorder | None = None,
        cache: ResponseCache | None = None,
        http_client: httpx2.AsyncClient | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("Crustdata API key is empty; set CRUSTDATA_API_KEY.")
        self._headers = {
            "authorization": f"Bearer {api_key}",
            "x-api-version": api_version,
            "content-type": "application/json",
            "accept": "application/json",
        }
        self._owns_http = http_client is None
        self._http = http_client or httpx2.AsyncClient()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.recorder = recorder
        self.cache = cache
        self.rate_limiter = rate_limiter or SHARED_RATE_LIMITER
        self._sleep = sleep

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kwargs: Any) -> CrustdataClient:
        s = settings or get_settings()
        options: dict[str, Any] = {
            "base_url": s.crustdata_base_url,
            "api_version": s.crustdata_api_version,
            "timeout": s.crustdata_timeout_seconds,
            "max_retries": s.crustdata_max_retries,
        }
        return cls(s.crustdata_api_key.get_secret_value(), **{**options, **kwargs})

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> CrustdataClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # --- Companies -------------------------------------------------------------

    async def identify_company(
        self,
        *,
        domains: Sequence[str] | None = None,
        names: Sequence[str] | None = None,
        crustdata_company_ids: Sequence[int] | None = None,
        professional_network_profile_urls: Sequence[str] | None = None,
        exact_match: bool | None = None,
    ) -> tuple[list[IdentifyResult], CallRecord]:
        """Resolve a company to Crustdata ids. One identifier type per call.

        Priced at 0.2 credits per identifier that matches (unmatched ones are free).
        """
        identifiers = {
            "domains": domains,
            "names": names,
            "crustdata_company_ids": crustdata_company_ids,
            "professional_network_profile_urls": professional_network_profile_urls,
        }
        given = {k: list(v) for k, v in identifiers.items() if v}
        if len(given) != 1:
            raise ValueError("identify_company takes exactly one identifier type.")
        body: dict[str, Any] = dict(given)
        if exact_match is not None:
            body["exact_match"] = exact_match
        data, record = await self._post(COMPANY_IDENTIFY, body)
        parse = lambda d: [IdentifyResult.model_validate(item) for item in d or []]  # noqa: E731
        return _typed(COMPANY_IDENTIFY, parse, data, record), record

    async def search_companies(
        self,
        *,
        filters: dict[str, Any] | None = None,
        query: str | None = None,
        mode: str = "hybrid",
        limit: int = 20,
        cursor: str | None = None,
        sorts: Sequence[dict[str, str]] | None = None,
        fields: Sequence[str] | None = None,
        fallback_to_filters: bool = False,
    ) -> tuple[CompanySearchResult, CallRecord]:
        """Company search with structured filters, a natural-language query, or both.

        With ``query`` the results are relevance-ranked (``mode`` = hybrid | lexical |
        semantic, at most 100 per page) and ``filters`` act as hard constraints;
        ``sorts`` are rejected in that mode.

        Natural-language mode is enabled per account. When it is not, the API answers
        403 and this raises `SemanticSearchUnavailable`, unless ``fallback_to_filters``
        is set and ``filters`` were given: then the same search runs on the filters
        alone and the result has ``natural_language=False``. The failed attempt is
        still reported to the recorder as its own call.
        """
        if filters is None and not query:
            raise ValueError("search_companies needs filters, a query, or both.")
        if query and sorts:
            raise ValueError("sorts are not supported with natural-language search.")
        body: dict[str, Any] = {"limit": limit}
        if filters is not None:
            body["filters"] = filters
        if query:
            body["search"] = {"query": query, "mode": mode}
        if cursor:
            body["cursor"] = cursor
        if sorts:
            body["sorts"] = list(sorts)
        if fields:
            body["fields"] = list(fields)
        try:
            data, record = await self._post(COMPANY_SEARCH, body)
        except SemanticSearchUnavailable:
            if not (fallback_to_filters and filters is not None):
                raise
            body.pop("search")
            data, record = await self._post(COMPANY_SEARCH, body)
        result = _typed(
            COMPANY_SEARCH, lambda d: CompanySearchResult.model_validate(d or {}), data, record
        )
        result.natural_language = "search" in body
        return result, record

    async def enrich_company(
        self,
        crustdata_company_ids: int | Sequence[int],
        *,
        fields: Sequence[str] = DEFAULT_ENRICH_FIELDS,
    ) -> tuple[list[EnrichResult], CallRecord]:
        """Full profile by Crustdata id: funding rounds and investors, headcount and
        its time series, locations, founded year, description, key people.

        2 credits per returned match. Enrich by id (from identify) to avoid paying
        for several fuzzy matches.
        """
        ids = (
            [crustdata_company_ids]
            if isinstance(crustdata_company_ids, int)
            else list(crustdata_company_ids)
        )
        if not 1 <= len(ids) <= MAX_ENRICH_IDS:
            raise ValueError(f"enrich_company takes between 1 and {MAX_ENRICH_IDS} company ids.")
        body = {"crustdata_company_ids": ids, "fields": list(fields)}
        data, record = await self._post(COMPANY_ENRICH, body)
        parse = lambda d: [EnrichResult.model_validate(item) for item in d or []]  # noqa: E731
        return _typed(COMPANY_ENRICH, parse, data, record), record

    # --- People ----------------------------------------------------------------

    async def search_people(
        self,
        filters: dict[str, Any],
        *,
        limit: int = 25,
        cursor: str | None = None,
        sorts: Sequence[dict[str, str]] | None = None,
        fields: Sequence[str] = DEFAULT_PERSON_FIELDS,
    ) -> tuple[PersonSearchResult, CallRecord]:
        body: dict[str, Any] = {"filters": filters, "limit": limit, "fields": list(fields)}
        if cursor:
            body["cursor"] = cursor
        if sorts:
            body["sorts"] = list(sorts)
        data, record = await self._post(PERSON_SEARCH, body)
        parse = lambda d: PersonSearchResult.model_validate(d or {})  # noqa: E731
        return _typed(PERSON_SEARCH, parse, data, record), record

    async def search_company_leadership(
        self,
        crustdata_company_id: int,
        *,
        title_keywords: Sequence[str] = LEADERSHIP_TITLE_KEYWORDS,
        include_past: bool = True,
        limit: int = 25,
        cursor: str | None = None,
        fields: Sequence[str] = DEFAULT_PERSON_FIELDS,
    ) -> tuple[PersonSearchResult, CallRecord]:
        """People currently (and optionally previously) at a company id in leadership
        titles, with full career history and dates. Matches on company id, never name.
        """
        return await self.search_people(
            leadership_filters(crustdata_company_id, title_keywords, include_past=include_past),
            limit=limit,
            cursor=cursor,
            fields=fields,
        )

    # --- Jobs ------------------------------------------------------------------

    async def search_jobs(
        self,
        crustdata_company_id: int,
        *,
        limit: int = 50,
        cursor: str | None = None,
        extra_conditions: Sequence[dict[str, Any]] = (),
        sorts: Sequence[dict[str, str]] | None = None,
        fields: Sequence[str] | None = None,
    ) -> tuple[JobSearchResult, CallRecord]:
        """Job postings for one company id (~0.03 credits per result)."""
        company_condition = {
            "field": "company.basic_info.company_id",
            "type": "=",
            "value": crustdata_company_id,
        }
        filters: dict[str, Any] = (
            {"op": "and", "conditions": [company_condition, *extra_conditions]}
            if extra_conditions
            else company_condition
        )
        body: dict[str, Any] = {"filters": filters, "limit": limit}
        if cursor:
            body["cursor"] = cursor
        if sorts:
            body["sorts"] = list(sorts)
        if fields:
            body["fields"] = list(fields)
        data, record = await self._post(JOB_SEARCH, body)
        parse = lambda d: JobSearchResult.model_validate(d or {})  # noqa: E731
        return _typed(JOB_SEARCH, parse, data, record), record

    # --- Web -------------------------------------------------------------------

    async def web_search(
        self,
        query: str,
        *,
        sources: Sequence[str] | None = None,
        location: str | None = None,
        site: str | None = None,
        start_date: int | None = None,
        end_date: int | None = None,
        page: int = 1,
    ) -> tuple[WebSearchResult, CallRecord]:
        """Live web/news search. 1 credit per page. Dates are Unix seconds."""
        if page > 1 and (not sources or len(sources) != 1):
            raise ValueError("page > 1 needs exactly one source.")
        body: dict[str, Any] = {"query": query}
        optional = {
            "sources": list(sources) if sources else None,
            "location": location,
            "site": site,
            "start_date": start_date,
            "end_date": end_date,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        if page != 1:
            body["page"] = page
        data, record = await self._post(WEB_SEARCH_LIVE, body)
        parse = lambda d: WebSearchResult.model_validate(d or {})  # noqa: E731
        return _typed(WEB_SEARCH_LIVE, parse, data, record), record

    async def fetch_pages(
        self, urls: Sequence[str], *, human_mode: bool = False
    ) -> tuple[list[WebPage], CallRecord]:
        """Live fetch of up to 10 pages (title + HTML content). 1 credit per page.

        Pages that could not be fetched come back with ``url: null``; use
        `failed_urls` to find which requested URLs they were.
        """
        url_list = list(urls)
        if not 1 <= len(url_list) <= MAX_FETCH_URLS:
            raise ValueError(f"fetch_pages takes between 1 and {MAX_FETCH_URLS} URLs.")
        body: dict[str, Any] = {"urls": url_list}
        if human_mode:
            body["human_mode"] = True
        data, record = await self._post(WEB_FETCH_LIVE, body)
        parse = lambda d: [WebPage.model_validate(item) for item in d or []]  # noqa: E731
        return _typed(WEB_FETCH_LIVE, parse, data, record), record

    # --- Transport ---------------------------------------------------------------

    def _retry_delay(self, attempt: int, response: httpx2.Response | None) -> float:
        if response is not None:
            for header in ("retry-after", "x-ratelimit-reset"):
                raw = response.headers.get(header)
                if raw is None:
                    continue
                try:
                    return min(max(float(raw), 0.0), self.backoff_max)
                except ValueError:
                    continue
        delay = self.backoff_base * (2**attempt)
        return min(delay + random.uniform(0, self.backoff_base), self.backoff_max)

    async def post(self, endpoint: str, body: dict[str, Any]) -> tuple[Any, CallRecord]:
        """The sanitised JSON of one request, without a typed model.

        Same cache key, recorder, retries and field allowlist as the typed methods
        (``enrich_company`` builds ``{"crustdata_company_ids": [...], "fields": [...]}``
        for `COMPANY_ENRICH`), so a typed call and a raw call share one paid response."""
        return await self._post(endpoint, body)

    async def _post(self, endpoint: str, body: dict[str, Any]) -> tuple[Any, CallRecord]:
        """`_operation`, reported to the recorder's live activity hook when it returns
        (a success, a cache hit, or a final failure)."""
        if not callable(getattr(self.recorder, "activity", None)):
            return await self._operation(endpoint, body)
        started = time.monotonic()
        try:
            data, record = await self._operation(endpoint, body)
        except CrustdataError as exc:
            await self._report(endpoint, body, None, exc.record, started, ok=False)
            raise
        await self._report(endpoint, body, data, record, started, ok=True)
        return data, record

    async def _report(
        self,
        endpoint: str,
        body: dict[str, Any],
        data: Any,
        record: CallRecord,
        started: float,
        *,
        ok: bool,
    ) -> None:
        report = activity.CallReport(
            provider=PROVIDER,
            endpoint=endpoint,
            ok=ok,
            from_cache=record.from_cache,
            attempts=record.attempts,
            duration_ms=int((time.monotonic() - started) * 1000),
            credits=record.credits_used,
            error=record.error,
            body=body,
            data=data,
        )
        await activity.emit(self.recorder, report)

    async def _operation(self, endpoint: str, body: dict[str, Any]) -> tuple[Any, CallRecord]:
        """One operation: cache lookup, then dispatches until success or give-up.

        Each dispatch is recorded on its own. A dispatch is retried only when its cost
        is known: a connect failure (never reached the API), a 429 (refused before
        billing), or a 5xx that carried ``X-Credits-Used``. A read timeout, a dropped
        connection or a 5xx without the header may have been billed, so the call fails
        there with that dispatch's cost unknown rather than paying again blindly.
        """
        key = make_cache_key(PROVIDER, endpoint, body)
        estimate = estimate_credits(endpoint, body)
        async with CallOperation(
            self.recorder,
            self.cache,
            provider=PROVIDER,
            endpoint=endpoint,
            cache_key=key,
            params_hash=stable_hash(body),
        ) as op:
            cached = await op.lookup()
            if cached is not None:
                record = await op.cache_hit(
                    http_status=cached.get("http_status"),
                    provider_request_id=cached.get("provider_request_id"),
                    credits_used=0.0,
                )
                return cached["body"], record

            url = f"{self._base_url}{endpoint}"
            attempt = 0
            while True:
                await self.rate_limiter.acquire(endpoint)
                record = op.new_record(credits_estimate=estimate)
                await op.start(record)
                try:
                    response = await self._http.post(
                        url, json=body, headers=self._headers, timeout=self._timeout
                    )
                except httpx2.TransportError as exc:
                    never_sent = isinstance(exc, httpx2.ConnectError | httpx2.ConnectTimeout)
                    code = "timeout" if isinstance(exc, httpx2.TimeoutException) else None
                    record.status = "failed"
                    record.error = code or "network_error"
                    record.credits_used = 0.0 if never_sent else None
                    record.usage_known = never_sent
                    await op.finish(record)
                    if never_sent and attempt < self.max_retries:
                        await self._sleep(self._retry_delay(attempt, None))
                        attempt += 1
                        continue
                    raise CrustdataError(
                        _message(endpoint, None, record.error, None),
                        status=None,
                        error_type=record.error,
                        record=record,
                    ) from None

                status = response.status_code
                record.http_status = status
                record.provider_request_id = response.headers.get("x-request-id")
                credits = parse_credits(response.headers)
                if status == 429:
                    # Refused by the rate limiter before reaching the API: not billed.
                    record.credits_used, record.usage_known = 0.0, True
                else:
                    record.credits_used, record.usage_known = credits, credits is not None

                if status in RETRYABLE_STATUSES:
                    record.status = "failed"
                    record.error = _error_code(response)
                    await op.finish(record)
                    if record.usage_known and attempt < self.max_retries:
                        await self._sleep(self._retry_delay(attempt, response))
                        attempt += 1
                        continue
                    self._raise(endpoint, body, record, status)

                if status >= 400:
                    record.status = "failed"
                    record.error = _error_code(response)
                    await op.finish(record)
                    self._raise(endpoint, body, record, status)

                try:
                    data = sanitize_response(endpoint, response.json())
                except ValueError:
                    # The credits header already arrived: the dispatch is billed and
                    # its cost known even though the body is unusable.
                    record.status = "failed"
                    record.error = "decode_error"
                    await op.finish(record)
                    raise CrustdataError(
                        _message(endpoint, status, "decode_error", record.provider_request_id),
                        status=status,
                        error_type="decode_error",
                        record=record,
                    ) from None
                record.status = "succeeded"
                await op.finish(
                    record,
                    cache_value={
                        "body": data,
                        "http_status": status,
                        "provider_request_id": record.provider_request_id,
                    },
                )
                return data, record

    def _raise(
        self, endpoint: str, body: dict[str, Any], record: CallRecord, status: int
    ) -> NoReturn:
        error_class = _error_class(status, natural_language="search" in body)
        raise error_class(
            _message(endpoint, status, record.error, record.provider_request_id),
            status=status,
            error_type=record.error,
            record=record,
        )


def failed_urls(requested: Sequence[str], pages: Sequence[WebPage]) -> list[str]:
    """Requested URLs with no successful page in a `fetch_pages` result."""
    fetched = {page.url for page in pages if page.success and page.url}
    return [url for url in requested if url not in fetched]


def leadership_filters(
    crustdata_company_id: int,
    title_keywords: Sequence[str] = LEADERSHIP_TITLE_KEYWORDS,
    *,
    include_past: bool = True,
) -> dict[str, Any]:
    """Person-search filter: a leadership title held at this company id.

    Each tense (current / past) is its own group so the company id and the title
    are checked on that tense's positions.
    """
    if not title_keywords:
        raise ValueError("title_keywords must not be empty.")

    def tense(name: str) -> dict[str, Any]:
        prefix = f"experience.employment_details.{name}"
        return {
            "op": "and",
            "conditions": [
                {"field": f"{prefix}.company_id", "type": "=", "value": crustdata_company_id},
                {
                    "op": "or",
                    "conditions": [
                        {"field": f"{prefix}.title", "type": "(.)", "value": keyword}
                        for keyword in title_keywords
                    ],
                },
            ],
        }

    if not include_past:
        return tense("current")
    return {"op": "or", "conditions": [tense("current"), tense("past")]}


def _error_code(response: httpx2.Response) -> str:
    """The allowlisted ``error.type`` of an error response; never its message."""
    try:
        payload = response.json()
    except ValueError:
        return "http_error"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return safe_error_code(error.get("type")) or "http_error"
    return "http_error"


def _message(endpoint: str, status: int | None, code: str | None, request_id: str | None) -> str:
    parts = [f"crustdata {endpoint}", f"HTTP {status}" if status else "no response"]
    if code:
        parts.append(code)
    if request_id:
        parts.append(f"request_id={request_id}")
    return " ".join(parts)


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 1


def estimate_credits(endpoint: str, body: dict[str, Any]) -> float:
    """Upper bound on what one dispatch can cost, reserved against the budget first.

    From Crustdata's published prices (see the v1 plan, "External APIs"); the actual
    charge comes from ``X-Credits-Used`` and settles the reservation.
    """
    if endpoint == COMPANY_IDENTIFY:
        ids = next((v for k, v in body.items() if k != "exact_match"), [])
        return 0.2 * _count(ids)
    if endpoint == COMPANY_ENRICH:
        return 2.0 * _count(body.get("crustdata_company_ids", []))
    if endpoint in (WEB_SEARCH_LIVE,):
        return 1.0
    if endpoint == WEB_FETCH_LIVE:
        return 1.0 * _count(body.get("urls", []))
    limit = int(body.get("limit") or 1)
    if endpoint == COMPANY_SEARCH:
        groups = set(body.get("fields") or ("taxonomy", "funding", "headcount", "hiring"))
        per_side = 0.1 * ("taxonomy" in groups) + 0.2 * len(
            groups & {"funding", "headcount", "hiring"}
        )
        filters = str(body.get("filters") or "")
        filter_side = 0.1 * ("taxonomy." in filters) + 0.2 * sum(
            f"{g}." in filters for g in ("funding", "headcount", "hiring")
        )
        return round(limit * (0.03 + per_side + filter_side), 4)
    if endpoint == PERSON_SEARCH:
        groups = set(body.get("fields") or ("experience",))
        experience = ("experience" in groups) + ("experience." in str(body.get("filters") or ""))
        return round(limit * (0.03 + 0.1 * experience), 4)
    if endpoint == JOB_SEARCH:
        return round(limit * 0.03, 4)
    return 1.0
