"""Opt-in live smoke tests: one cheap real call per client.

Skipped unless DEALPROOF_LIVE_TESTS=1 (or RUN_LIVE_SMOKE=1, the plan's name).
Keys come from settings (env / repo .env) and are never printed.

- Crustdata: one company identify (0.2 credits per matched identifier per the docs).
- Anthropic: one tiny structured extraction on the configured model.
"""

import os

import pytest
from pydantic import BaseModel

from app.clients.crustdata import CrustdataClient
from app.clients.llm import LLMClient
from app.settings import Settings

LIVE = "1" in (os.environ.get("DEALPROOF_LIVE_TESTS"), os.environ.get("RUN_LIVE_SMOKE"))

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not LIVE, reason="set DEALPROOF_LIVE_TESTS=1 to run live smoke tests"),
]


def _summary(record) -> dict:
    return record.model_dump(
        include={
            "endpoint",
            "status",
            "http_status",
            "attempts",
            "provider_request_id",
            "credits_used",
            "model",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "usage_known",
        }
    )


async def test_crustdata_identify_live() -> None:
    settings = Settings()
    if not settings.crustdata_api_key.get_secret_value():
        pytest.skip("CRUSTDATA_API_KEY not set")
    async with CrustdataClient.from_settings(settings, max_retries=1) as client:
        results, record = await client.identify_company(domains=["stripe.com"])
    print("crustdata identify:", _summary(record))
    assert record.status == "succeeded"
    assert record.http_status == 200
    top = results[0].matches[0].company_data
    print("  top match:", top.crustdata_company_id, top.basic_info and top.basic_info.name)
    assert top.crustdata_company_id


class CityFact(BaseModel):
    city: str | None


async def test_anthropic_extract_live() -> None:
    settings = Settings()
    if not settings.anthropic_api_key.get_secret_value():
        pytest.skip("ANTHROPIC_API_KEY not set")
    client = LLMClient.from_settings(settings)
    try:
        fact, record = await client.extract_structured(
            "Extract the city the text names. Use null if none.",
            "The company is based in Pune.",
            CityFact,
            max_tokens=1024,
        )
    finally:
        await client.aclose()
    print("anthropic extract:", _summary(record), "->", fact.model_dump())
    assert record.status == "succeeded"
    assert fact.city and "pune" in fact.city.lower()
