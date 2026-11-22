"""Opt-in live test: extract criteria from the PRD's sample thesis with the real model.

Skipped unless DEALPROOF_LIVE_TESTS=1. Uses `LLMClient.from_settings()`; the key
comes from settings and is never printed. One structured call, a few cents at most.
Run with `-s` to see the extracted criteria.
"""

import json
import os

import pytest

from app.clients.llm import LLMClient
from app.extraction.criteria import extract_criteria
from app.settings import Settings

LIVE = os.environ.get("DEALPROOF_LIVE_TESTS") == "1"

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not LIVE, reason="set DEALPROOF_LIVE_TESTS=1 to run live tests"),
]

PRD_THESIS = (
    "privately held Indian warehousing and supply-chain software companies that serve "
    "enterprise customers and show recent expansion"
)


async def test_live_criteria_from_prd_thesis() -> None:
    settings = Settings()
    if not settings.anthropic_api_key.get_secret_value():
        pytest.skip("ANTHROPIC_API_KEY not set")
    client = LLMClient.from_settings(settings)
    try:
        out = await extract_criteria(client, PRD_THESIS)
    finally:
        await client.aclose()

    print("\nactivity_query:", out.activity_query)
    for c in out.criteria:
        print(json.dumps(c.model_dump(), ensure_ascii=False))
    for d in out.dropped:
        print("dropped:", d.model_dump())
    record = out.calls[0]
    print(
        "call:",
        {
            k: getattr(record, k, None)
            for k in ("model", "input_tokens", "output_tokens", "cost_usd", "status", "from_cache")
        },
    )

    assert len(out.criteria) >= 3
    assert any(c.kind == "must" for c in out.criteria)
    dims = {c.dimension for c in out.criteria}
    assert {"geography", "ownership", "customer_type"} <= dims
    # Every kept criterion is anchored in the thesis text.
    assert all(c.thesis_quote.lower().strip(" .\"'") in PRD_THESIS.lower() for c in out.criteria)
    # Nothing the thesis does not state.
    assert "founded_year" not in dims and "funding_stage" not in dims
    assert out.activity_query
