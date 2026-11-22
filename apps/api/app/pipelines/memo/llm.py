"""The drafting model for memo prose, built per step so calls are cached and metered.

Without an Anthropic key the memo uses the deterministic restatement of its facts, so a
case still gets a complete, cited memo. Tests replace `make_llm`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.jobs import StepContext
from app.settings import get_settings

log = logging.getLogger(__name__)


def _default_llm(ctx: StepContext) -> Any:
    if not get_settings().anthropic_api_key.get_secret_value():
        return None
    from app.clients.llm import LLMClient

    return LLMClient.from_settings(recorder=ctx.recorder, cache=ctx.cache)


make_llm: Callable[[StepContext], Any] = _default_llm


def memo_llm(ctx: StepContext) -> Any:
    try:
        return make_llm(ctx)
    except Exception:  # noqa: BLE001 - no model means the deterministic memo
        log.exception("memo: no drafting model available")
        return None


def memo_section_builder():  # noqa: ANN201
    from app.pipelines.memo.drafting import build_memo_document

    return build_memo_document
