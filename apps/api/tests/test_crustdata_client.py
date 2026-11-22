import json
from collections.abc import Callable

import httpx2
import pytest

from app.clients.base import InMemoryCache, InMemoryRecorder
from app.clients.crustdata import (
    DEFAULT_RATE_LIMITS,
    SHARED_RATE_LIMITER,
    CrustdataClient,
    CrustdataCreditsError,
    CrustdataError,
    CrustdataPlanError,
    SemanticSearchUnavailable,
    failed_urls,
    leadership_filters,
    strip_contact_fields,
)
from app.clients.crustdata_models import WebPage
from app.clients.ratelimit import SlidingWindowRateLimiter

pytestmark = pytest.mark.anyio

IDENTIFY_BODY = [
    {
        "matched_on": "stripe.com",
        "match_type": "domain",
        "matches": [
            {
                "confidence_score": 1.0,
                "company_data": {
                    "crustdata_company_id": 631394,
                    "basic_info": {
                        "crustdata_company_id": 631394,
                        "name": "Stripe",
                        "primary_domain": "stripe.com",
                        "year_founded": 2010,
                    },
                },
            }
        ],
    }
]

Handler = Callable[[httpx2.Request], httpx2.Response]


class Harness:
    def __init__(
        self,
        handler: Handler,
        *,
        cache: bool = False,
        max_retries: int = 3,
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self.requests: list[httpx2.Request] = []
        self.sleeps: list[float] = []
        self.recorder = InMemoryRecorder()
        self.cache = InMemoryCache() if cache else None

        def capture(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return handler(request)

        async def fake_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        self.client = CrustdataClient(
            "test-key",
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(capture)),
            recorder=self.recorder,
            cache=self.cache,
            max_retries=max_retries,
            rate_limiter=rate_limiter or SlidingWindowRateLimiter({}),
            sleep=fake_sleep,
        )

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


def ok(payload: object, credits: str | None = "0.2", request_id: str = "req-1") -> httpx2.Response:
    headers = {"x-request-id": request_id}
    if credits is not None:
        headers["x-credits-used"] = credits
    return httpx2.Response(200, json=payload, headers=headers)


def sequence(*responses: httpx2.Response | Exception) -> Handler:
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


async def test_identify_request_shape_auth_and_record() -> None:
    h = Harness(lambda request: ok(IDENTIFY_BODY))
    results, record = await h.client.identify_company(domains=["stripe.com"])

    request = h.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.crustdata.com/company/identify"
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["x-api-version"] == "2025-11-01"
    assert h.body() == {"domains": ["stripe.com"]}

    match = results[0].matches[0]
    assert match.company_data.crustdata_company_id == 631394
    assert match.company_data.basic_info.name == "Stripe"
    assert match.company_data.basic_info.year_founded == 2010

    assert record.status == "succeeded"
    assert record.endpoint == "/company/identify"
    assert record.http_status == 200
    assert record.credits_used == pytest.approx(0.2)
    assert record.usage_known is True
    assert record.provider_request_id == "req-1"
    assert record.attempts == 1
    assert record.started_at <= record.finished_at

    statuses = [(r.call_id, r.status) for r in h.recorder.records]
    assert [s for _, s in statuses] == ["started", "succeeded"]
    assert statuses[0][0] == statuses[1][0]
    assert h.recorder.records[0].finished_at is None


async def test_identify_requires_exactly_one_identifier_type() -> None:
    h = Harness(lambda request: ok(IDENTIFY_BODY))
    with pytest.raises(ValueError):
        await h.client.identify_company(domains=["a.com"], names=["A"])
    with pytest.raises(ValueError):
        await h.client.identify_company()
    assert h.requests == []


async def test_retries_429_and_5xx_then_succeeds() -> None:
    h = Harness(
        sequence(
            httpx2.Response(429, headers={"retry-after": "2"}),
            httpx2.Response(
                500,
                json={"error": {"type": "internal_error", "message": "x"}},
                headers={"x-credits-used": "0"},
            ),
            ok(IDENTIFY_BODY, credits="0.2", request_id="req-3"),
        )
    )
    _, record = await h.client.identify_company(domains=["stripe.com"])
    assert len(h.requests) == 3
    assert record.attempts == 3
    assert h.sleeps[0] == 2.0  # honours Retry-After
    assert 0 < h.sleeps[1] <= h.client.backoff_max
    assert record.status == "succeeded"
    # 429 is refused before the API (no charge); 500 reported 0; success 0.2.
    assert record.credits_used == pytest.approx(0.2)
    assert record.usage_known is True
    assert record.provider_request_id == "req-3"


async def test_rate_limit_reset_header_sets_delay() -> None:
    h = Harness(
        sequence(
            httpx2.Response(429, headers={"x-ratelimit-reset": "7"}),
            ok(IDENTIFY_BODY),
        )
    )
    await h.client.identify_company(domains=["stripe.com"])
    assert h.sleeps == [7.0]


async def test_gives_up_after_max_retries() -> None:
    h = Harness(
        lambda request: httpx2.Response(
            503, json={"error": {"type": "internal_error", "message": "busy"}}
        ),
        max_retries=2,
    )
    with pytest.raises(CrustdataError) as info:
        await h.client.identify_company(domains=["stripe.com"])
    assert info.value.status == 503
    assert len(h.requests) == 3
    record = info.value.record
    assert record.status == "failed"
    assert record.attempts == 3
    assert record.credits_used is None and record.usage_known is False
    assert h.recorder.final()[0].status == "failed"


async def test_client_error_is_not_retried() -> None:
    h = Harness(
        lambda request: httpx2.Response(
            400,
            json={"error": {"type": "invalid_request", "message": "Invalid fields"}},
            headers={"x-credits-used": "0", "x-request-id": "req-bad"},
        )
    )
    with pytest.raises(CrustdataError) as info:
        await h.client.enrich_company(1)
    assert len(h.requests) == 1
    assert info.value.status == 400
    assert info.value.error_type == "invalid_request"
    assert "Invalid fields" in str(info.value)
    assert info.value.record.credits_used == 0
    assert info.value.record.usage_known is True
    assert info.value.record.provider_request_id == "req-bad"


async def test_missing_credits_header_marks_usage_unknown() -> None:
    h = Harness(lambda request: ok(IDENTIFY_BODY, credits=None))
    _, record = await h.client.identify_company(domains=["stripe.com"])
    assert record.credits_used is None
    assert record.usage_known is False


async def test_timeout_then_success_marks_usage_unknown() -> None:
    h = Harness(sequence(httpx2.ReadTimeout("slow"), ok(IDENTIFY_BODY)))
    _, record = await h.client.identify_company(domains=["stripe.com"])
    assert record.status == "succeeded"
    assert record.attempts == 2
    assert record.credits_used is None
    assert record.usage_known is False


async def test_connect_error_is_known_free() -> None:
    h = Harness(sequence(httpx2.ConnectError("down"), ok(IDENTIFY_BODY, credits="0.2")))
    _, record = await h.client.identify_company(domains=["stripe.com"])
    assert record.credits_used == pytest.approx(0.2)
    assert record.usage_known is True


async def test_person_search_strips_contact_fields_and_caches_stripped() -> None:
    payload = {
        "profiles": [
            {
                "crustdata_person_id": 9,
                "basic_profile": {"name": "A. Founder", "current_title": "CEO"},
                "contact": {
                    "has_business_email": True,
                    "business_emails": ["a@example.com"],
                    "personal_emails": ["a@gmail.com"],
                    "phone_numbers": ["+91 99999 99999"],
                },
                "experience": {
                    "employment_details": {
                        "current": [
                            {
                                "name": "Acme",
                                "crustdata_company_id": 42,
                                "title": "CEO",
                                "start_date": "2014-01-01",
                                "business_email": "a@acme.com",
                                "business_email_verified": True,
                            }
                        ],
                        "past": [{"name": "Old Co", "title": "COO", "end_date": "2013-12-01"}],
                    }
                },
            }
        ],
        "next_cursor": None,
        "total_count": 1,
    }
    h = Harness(lambda request: ok(payload), cache=True)
    result, _ = await h.client.search_company_leadership(42)

    profile = result.profiles[0]
    dumped = json.dumps(profile.model_dump())
    for secret in ("a@example.com", "a@gmail.com", "99999", "a@acme.com"):
        assert secret not in dumped
    extra = profile.model_dump()
    assert extra["contact"] == {"has_business_email": True}
    current = profile.experience.employment_details.current[0]
    assert current.crustdata_company_id == 42
    assert current.start_date == "2014-01-01"
    assert profile.experience.employment_details.past[0].end_date == "2013-12-01"

    cached = json.dumps(await h.cache.get(h.recorder.records[0].cache_key))
    assert "a@example.com" not in cached and "99999" not in cached

    body = h.body()
    assert "contact" not in body["fields"]
    assert body["filters"] == leadership_filters(42)


async def test_enrich_strips_company_contact_fields_and_parses_profile() -> None:
    payload = [
        {
            "matched_on": "42",
            "match_type": "crustdata_company_id",
            "matches": [
                {
                    "confidence_score": 1,
                    "company_data": {
                        "crustdata_company_id": 42,
                        "basic_info": {"name": "Acme", "year_founded": 2014},
                        "headcount": {
                            "total": 120,
                            "timeseries": [{"date": "2026-01-01", "employee_count": 100}],
                        },
                        "funding": {
                            "contact_email": "ir@acme.com",
                            "phone_number": "+91 12345",
                            "milestones": [
                                {
                                    "round_type": "series_a",
                                    "date": "2025-03-01",
                                    "investors": ["Fund One"],
                                }
                            ],
                        },
                        "locations": {"headquarters": "Pune, India"},
                        "people": {"founders": [{"basic_profile": {"name": "A"}, "email": "x"}]},
                    },
                }
            ],
        }
    ]
    h = Harness(lambda request: ok(payload, credits="2"))
    results, record = await h.client.enrich_company(42)

    assert h.body()["crustdata_company_ids"] == [42]
    assert "funding" in h.body()["fields"] and "headcount" in h.body()["fields"]
    company = results[0].matches[0].company_data
    assert company.headcount.timeseries[0].employee_count == 100
    assert company.funding.milestones[0].investors == ["Fund One"]
    assert company.locations.headquarters == "Pune, India"
    dumped = json.dumps(company.model_dump())
    assert "ir@acme.com" not in dumped and "12345" not in dumped
    assert '"email"' not in dumped
    assert record.credits_used == 2


async def test_cache_hit_skips_network() -> None:
    h = Harness(lambda request: ok(IDENTIFY_BODY), cache=True)
    first, first_record = await h.client.identify_company(domains=["stripe.com"])
    second, second_record = await h.client.identify_company(domains=["stripe.com"])

    assert len(h.requests) == 1
    assert second == first
    assert second_record.status == "cache_hit"
    assert second_record.from_cache is True
    assert second_record.credits_used == 0
    assert second_record.provider_request_id == "req-1"
    assert second_record.cache_key == first_record.cache_key
    assert [r.status for r in h.recorder.records] == ["started", "succeeded", "cache_hit"]

    await h.client.identify_company(domains=["other.com"])
    assert len(h.requests) == 2


async def test_failures_are_not_cached() -> None:
    h = Harness(
        sequence(
            httpx2.Response(400, json={"error": {"type": "invalid_request", "message": "x"}}),
            ok(IDENTIFY_BODY),
        ),
        cache=True,
    )
    with pytest.raises(CrustdataError):
        await h.client.identify_company(domains=["stripe.com"])
    _, record = await h.client.identify_company(domains=["stripe.com"])
    assert record.status == "succeeded"
    assert len(h.requests) == 2


async def test_company_search_modes() -> None:
    h = Harness(lambda request: ok({"companies": [], "next_cursor": None}, credits="0"))
    filters = {"field": "locations.country", "type": "=", "value": "IND"}
    await h.client.search_companies(filters=filters, query="warehousing software", limit=10)
    assert h.body() == {
        "limit": 10,
        "filters": filters,
        "search": {"query": "warehousing software", "mode": "hybrid"},
    }
    await h.client.search_companies(
        filters=filters, sorts=[{"field": "headcount.total", "order": "desc"}], cursor="c1"
    )
    assert h.body()["sorts"] == [{"field": "headcount.total", "order": "desc"}]
    assert h.body()["cursor"] == "c1"
    assert "search" not in h.body()

    with pytest.raises(ValueError):
        await h.client.search_companies()
    with pytest.raises(ValueError):
        await h.client.search_companies(query="x", sorts=[{"field": "a", "order": "asc"}])


def test_leadership_filters_match_on_company_id_per_tense() -> None:
    current_only = leadership_filters(42, ["founder", "ceo"], include_past=False)
    assert current_only["op"] == "and"
    company, titles = current_only["conditions"]
    assert company == {
        "field": "experience.employment_details.current.company_id",
        "type": "=",
        "value": 42,
    }
    assert [c["value"] for c in titles["conditions"]] == ["founder", "ceo"]
    assert all(
        c["field"] == "experience.employment_details.current.title" for c in titles["conditions"]
    )
    both = leadership_filters(42)
    assert both["op"] == "or"
    assert both["conditions"][1]["conditions"][0]["field"] == (
        "experience.employment_details.past.company_id"
    )


async def test_job_search_filters_by_company_id() -> None:
    h = Harness(lambda request: ok({"job_listings": [{"crustdata_job_id": 1}]}, credits="0.03"))
    result, _ = await h.client.search_jobs(42, limit=5)
    assert h.requests[0].url.path == "/job/search"
    assert h.body() == {
        "filters": {"field": "company.basic_info.company_id", "type": "=", "value": 42},
        "limit": 5,
    }
    assert result.job_listings[0].crustdata_job_id == 1

    extra = {"field": "job_details.title", "type": "[.]", "value": "warehouse"}
    await h.client.search_jobs(42, extra_conditions=[extra])
    assert h.body()["filters"]["op"] == "and"
    assert h.body()["filters"]["conditions"][1] == extra


async def test_web_search_and_fetch() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/web/search/live":
            return ok(
                {
                    "success": True,
                    "query": "acme",
                    "results": [{"source": "news", "title": "T", "url": "https://n.example/a"}],
                },
                credits="1",
            )
        return ok(
            [{"success": True, "url": "https://n.example/a", "title": "T", "content": "<p>"}],
            credits="1",
        )

    h = Harness(handler)
    search, record = await h.client.web_search(
        "acme expansion", sources=["news"], location="IN", start_date=1_700_000_000
    )
    assert h.body() == {
        "query": "acme expansion",
        "sources": ["news"],
        "location": "IN",
        "start_date": 1_700_000_000,
    }
    assert search.results[0].url == "https://n.example/a"
    assert record.credits_used == 1

    pages, _ = await h.client.fetch_pages(["https://n.example/a"])
    assert h.requests[-1].url.path == "/web/enrich/live"
    assert h.body() == {"urls": ["https://n.example/a"]}
    assert pages[0].title == "T"

    with pytest.raises(ValueError):
        await h.client.fetch_pages([f"https://x.example/{i}" for i in range(11)])
    with pytest.raises(ValueError):
        await h.client.web_search("x", page=2)


def test_strip_contact_fields_keeps_flags_and_other_data() -> None:
    data = {
        "name": "A",
        "emails": ["a@b.c"],
        "Phone": "1",
        "has_business_email": True,
        "nested": [{"mobile_number": "2", "title": "CEO"}],
    }
    assert strip_contact_fields(data) == {
        "name": "A",
        "has_business_email": True,
        "nested": [{"title": "CEO"}],
    }


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        CrustdataClient("")


def test_from_settings_lets_kwargs_override_settings() -> None:
    from app.settings import Settings

    settings = Settings(_env_file=None, crustdata_api_key="k", crustdata_max_retries=5)
    assert CrustdataClient.from_settings(settings).max_retries == 5
    assert CrustdataClient.from_settings(settings, max_retries=1).max_retries == 1


def nl_forbidden() -> httpx2.Response:
    return httpx2.Response(
        403,
        json={"error": {"type": "permission_error", "message": "semantic search not enabled"}},
        headers={"x-credits-used": "0"},
    )


async def test_semantic_search_403_raises_specific_error() -> None:
    h = Harness(lambda request: nl_forbidden())
    with pytest.raises(SemanticSearchUnavailable) as info:
        await h.client.search_companies(query="warehousing software")
    assert isinstance(info.value, CrustdataPlanError)
    assert info.value.status == 403
    assert len(h.requests) == 1


async def test_semantic_search_falls_back_to_filters_when_asked() -> None:
    h = Harness(
        sequence(
            nl_forbidden(),
            ok({"companies": [{"crustdata_company_id": 7}]}, credits="0.03"),
        )
    )
    filters = {"field": "locations.country", "type": "=", "value": "IND"}
    result, record = await h.client.search_companies(
        filters=filters, query="warehousing software", fallback_to_filters=True
    )
    assert "search" in h.body(0)
    assert h.body(1) == {"limit": 20, "filters": filters}
    assert result.natural_language is False
    assert result.companies[0].crustdata_company_id == 7
    assert record.status == "succeeded"
    # Both calls reach the recorder: the refused NL attempt and the filter search.
    assert [r.status for r in h.recorder.final()] == ["failed", "succeeded"]

    h2 = Harness(lambda request: ok({"companies": []}, credits="0"))
    result, _ = await h2.client.search_companies(query="x")
    assert result.natural_language is True


async def test_semantic_fallback_needs_filters() -> None:
    h = Harness(lambda request: nl_forbidden())
    with pytest.raises(SemanticSearchUnavailable):
        await h.client.search_companies(query="x", fallback_to_filters=True)


async def test_plan_and_credit_errors() -> None:
    h = Harness(
        sequence(
            httpx2.Response(403, json={"error": {"type": "permission_error", "message": "no"}}),
            httpx2.Response(402, json={"error": {"type": "insufficient_credits", "message": "0"}}),
        )
    )
    with pytest.raises(CrustdataPlanError) as plan:
        await h.client.enrich_company(1)
    assert not isinstance(plan.value, SemanticSearchUnavailable)
    with pytest.raises(CrustdataCreditsError):
        await h.client.enrich_company(1)


async def test_enrich_accepts_up_to_25_ids() -> None:
    h = Harness(lambda request: ok([], credits="0"))
    await h.client.enrich_company(list(range(1, 26)))
    assert len(h.body()["crustdata_company_ids"]) == 25
    with pytest.raises(ValueError):
        await h.client.enrich_company(list(range(26)))
    with pytest.raises(ValueError):
        await h.client.enrich_company([])


def test_failed_urls_correlates_null_entries() -> None:
    requested = ["https://a.example/1", "https://b.example/2", "https://c.example/3"]
    pages = [
        WebPage(success=True, url="https://a.example/1", content="<p>"),
        WebPage(success=False, url=None),
        WebPage(success=True, url="https://c.example/3", content="<p>"),
    ]
    assert failed_urls(requested, pages) == ["https://b.example/2"]


async def test_each_attempt_waits_for_the_endpoint_rate_limit() -> None:
    now = [0.0]
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    limiter = SlidingWindowRateLimiter(
        {"/company/identify": 2}, clock=lambda: now[0], sleep=fake_sleep
    )
    h = Harness(
        sequence(
            httpx2.Response(500, headers={"x-credits-used": "0"}),
            ok(IDENTIFY_BODY),
            ok(IDENTIFY_BODY),
        ),
        rate_limiter=limiter,
    )
    await h.client.identify_company(domains=["a.com"])  # two attempts use the quota
    assert waits == []
    await h.client.identify_company(domains=["b.com"])  # third request waits for the window
    assert waits == [60.0]


def test_default_limits_follow_crustdata_defaults() -> None:
    assert DEFAULT_RATE_LIMITS["/company/enrich"] == 15
    assert DEFAULT_RATE_LIMITS["/web/search/live"] == 10
    assert DEFAULT_RATE_LIMITS["/web/enrich/live"] == 10
    assert DEFAULT_RATE_LIMITS["/company/identify"] == 30
    assert CrustdataClient("k").rate_limiter is SHARED_RATE_LIMITER
