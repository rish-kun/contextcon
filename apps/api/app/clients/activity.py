"""What the clients tell the live activity stream about each call they make.

After every Crustdata or Anthropic operation (a cache hit, a success or a final
failure) the client builds a `CallReport` and hands it to the recorder's optional
``activity`` hook. Inside a job step that hook is the step's `ActivityEmitter`
(`app.jobs.activity`), which turns the report into `call`, `source` and `model`
events: fixed counts per endpoint, labels from templates, sanitised URLs and titles.
The report itself is never stored; only what the emitter takes from it.

`activity_topic` lets a pipeline say, in public words, what the calls inside a block
are for (the claim a page is read for, the source class of a registry page, what a
model read is about), so the emitter can label them without seeing private text.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class CallReport:
    provider: str  # "crustdata" | "anthropic"
    endpoint: str  # the API path, e.g. "/company/enrich", or "messages.parse"
    ok: bool
    from_cache: bool
    attempts: int
    duration_ms: int | None
    credits: float | None = None
    usd: float | None = None
    error: str | None = None  # an allowlisted error code
    # Crustdata only: the request body and the sanitised response. Read by the emitter
    # for counts, highlights and page sources; never stored as they are.
    body: dict[str, Any] | None = None
    data: Any = None
    # Anthropic only: whether the prompt was built from public data.
    public: bool = True


_topic: ContextVar[dict[str, Any] | None] = ContextVar("activity_topic", default=None)

# Keys `activity_topic` accepts. Values are public words or ids only.
TOPIC_KEYS = frozenset(
    {
        "subject",  # the public company name a case run is about ("the company" before identity)
        "ref",  # {"type": "claim", "id": ...}: the row the calls are for
        "category",  # a claim category, e.g. "team_size"
        "source_class",  # reliability class of the pages read here, e.g. "registry"
        "reading",  # what a model read is reading: "web_page" | "record" | "document"
        "domain",  # the domain of the page a model read is reading
        "purpose",  # what a model call is for: "facts" | "claims" | "criteria" | ...
        "case_run",  # True in case runs: search queries and filters stay out of events
    }
)


def _merge(fields: dict[str, Any]) -> dict[str, Any]:
    unknown = set(fields) - TOPIC_KEYS
    if unknown:
        raise ValueError(f"unknown activity topic keys: {sorted(unknown)}")
    current = _topic.get() or {}
    return {**current, **{k: v for k, v in fields.items() if v is not None}}


@contextlib.contextmanager
def activity_topic(**fields: Any) -> Iterator[None]:
    """Describe the calls inside this block (see `TOPIC_KEYS`). Never pass document
    text, claim wording, filenames or model output."""
    token = _topic.set(_merge(fields))
    try:
        yield
    finally:
        _topic.reset(token)


def set_activity_topic(**fields: Any) -> Any:
    """Non-scoped `activity_topic`; returns the token for `reset_activity_topic`."""
    return _topic.set(_merge(fields))


def reset_activity_topic(token: Any) -> None:
    _topic.reset(token)


def current_topic() -> dict[str, Any]:
    return dict(_topic.get() or {})


async def emit(recorder: Any, report: CallReport) -> None:
    """Hand `report` to the recorder's ``activity`` hook, if any. Never raises: a lost
    activity line must not fail the call it describes."""
    hook = getattr(recorder, "activity", None)
    if not callable(hook):
        return
    try:
        await hook(report)
    except Exception:  # noqa: BLE001
        log.warning("activity: could not report a %s call", report.provider, exc_info=True)
