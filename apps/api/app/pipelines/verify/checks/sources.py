"""Source and evidence rows for claim checks, and their domain (rules) views.

- `sources.source_class` holds a `SourceReliability` value (the rules' vocabulary).
- `sources.request` keeps the request parameters, plus `origin_key` (copies of one
  syndicated announcement share it, so they count as one origin) and, for records
  that could not be attached to the confirmed entity, `attached: false` with the
  reason. Unattached records are kept for the Sources tab and never get evidence.
- `evidence.origin_key` is the row's natural key within its source, so a re-run
  upserts instead of duplicating.
- One evidence row per fact: `value` is the fact's value and the claim-check link's
  `relation` is the component it speaks to (the convention the evaluate reader,
  `app.pipelines.evaluate.inputs`, relies on). A source that was read and said
  nothing gets one `read` row, linked with relation `read`.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Evidence as EvidenceRow
from app.db.models import Source as SourceRow
from app.domain.enums import SourceReliability
from app.domain.types import Evidence, Source

REGISTRY_CLASSES = frozenset({"registry", "registry_mirror", "registry_official"})
NEWS_CLASSES = frozenset({"news", "company_announcement"})

# API/plan vocabulary -> rules vocabulary, for rows written by other steps.
_CLASS_ALIASES: dict[str, SourceReliability] = {
    "registry_official": SourceReliability.REGISTRY,
    "funding_database": SourceReliability.DATA_PROVIDER,
    "professional_profile": SourceReliability.PROFESSIONAL_PROFILE_SIGNAL,
    "headcount_estimate": SourceReliability.PROFESSIONAL_PROFILE_SIGNAL,
    "data_provider_profile": SourceReliability.DATA_PROVIDER,
    "user_typed": SourceReliability.SELLER_STATEMENT,
}


def reliability_of(source_class: str) -> SourceReliability:
    if source_class in _CLASS_ALIASES:
        return _CLASS_ALIASES[source_class]
    return SourceReliability(source_class)


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlsplit(url if "//" in url else f"//{url}").hostname or "").lower()
    return host.removeprefix("www.") or None


def same_site(url: str | None, domain: str | None) -> bool:
    host, dom = host_of(url), host_of(domain)
    return bool(host and dom and (host == dom or host.endswith("." + dom)))


_TITLE_SUFFIX = re.compile(r"\s+[-|–—:]\s+[^-|–—:]{2,60}$")


def syndication_origin(title: str | None, url: str | None) -> str:
    """Copies of one announcement carry the same headline; they share this key."""
    if title:
        norm = _TITLE_SUFFIX.sub("", title.strip())
        norm = re.sub(r"[^a-z0-9]+", " ", norm.casefold()).strip()
        if len(norm) >= 12:
            return "title:" + hashlib.sha1(norm.encode()).hexdigest()[:16]
    return "url:" + (url or "")


def span_key(text: str) -> str:
    return "span:" + hashlib.sha1(" ".join(text.split()).encode()).hexdigest()[:20]


@dataclass(frozen=True)
class SourceSpec:
    provider: str  # "crustdata" | "web"
    endpoint_or_url: str
    reliability: SourceReliability
    label: str
    request: dict[str, Any] = field(default_factory=dict)
    publisher: str | None = None
    origin_key: str | None = None
    attached: bool = True
    unattached_reason: str | None = None


@dataclass
class EvidenceStore:
    """Finds or writes rows for one case (flushes, never commits)."""

    session: AsyncSession
    workspace_id: uuid.UUID
    case_id: uuid.UUID
    run_id: uuid.UUID | None = None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    _sources: dict[tuple[str, str, str, str], SourceRow] = field(default_factory=dict)

    async def source(self, spec: SourceSpec) -> SourceRow:
        key = (spec.provider, spec.endpoint_or_url, spec.reliability.value, spec.label)
        if key in self._sources:
            return self._sources[key]
        row = (
            (
                await self.session.execute(
                    select(SourceRow).where(
                        SourceRow.case_id == self.case_id,
                        SourceRow.provider == spec.provider,
                        SourceRow.endpoint_or_url == spec.endpoint_or_url,
                        SourceRow.source_class == spec.reliability.value,
                        SourceRow.title == spec.label,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            request = dict(spec.request)
            if spec.origin_key:
                request["origin_key"] = spec.origin_key
            if not spec.attached:
                request["attached"] = False
                request["unattached_reason"] = spec.unattached_reason
            row = SourceRow(
                workspace_id=self.workspace_id,
                case_id=self.case_id,
                run_id=self.run_id,
                provider=spec.provider,
                endpoint_or_url=spec.endpoint_or_url,
                request=request,
                source_class=spec.reliability.value,
                title=spec.label,
                publisher=spec.publisher,
                retrieved_at=self.now,
            )
            self.session.add(row)
            await self.session.flush()
        self._sources[key] = row
        return row

    async def evidence(
        self,
        source: SourceRow,
        *,
        entity_ref: str,
        component: str | None = None,
        span: str | None = None,
        field_path: str | None = None,
        value: Any = None,
        as_of: date | None = None,
        page: int | None = None,
        delete_after: datetime | None = None,
    ) -> EvidenceRow:
        if span:
            origin_key = span_key(span) + f":{entity_ref}"
        elif field_path:
            origin_key = f"field:{field_path}:{entity_ref}"
        else:
            raise ValueError("evidence needs a span or a field path")
        if component:
            origin_key += f":{component}"
        row = (
            await self.session.execute(
                select(EvidenceRow).where(
                    EvidenceRow.source_id == source.id, EvidenceRow.origin_key == origin_key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = EvidenceRow(
                source_id=source.id,
                case_id=self.case_id,
                entity_ref=entity_ref,
                field_path=field_path,
                span=span,
                value=value,
                as_of=as_of,
                page=page,
                origin_key=origin_key,
                delete_after=delete_after,
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def read_marker(self, source: SourceRow, *, entity_ref: str) -> EvidenceRow:
        """A row that records "this source was read" when it yielded no fact."""
        return await self.evidence(source, entity_ref=entity_ref, field_path=READ_MARKER)


READ_MARKER = "read"


def domain_source(row: SourceRow) -> Source:
    request = row.request or {}
    url = row.endpoint_or_url if row.provider == "web" else None
    return Source(
        id=str(row.id),
        provider=row.provider,
        label=row.title or row.endpoint_or_url,
        url=url,
        retrieved_at=row.retrieved_at or datetime(1970, 1, 1),
        reliability=reliability_of(row.source_class),
        origin_key=request.get("origin_key"),
    )


def domain_evidence(row: EvidenceRow, source: SourceRow) -> Evidence:
    return Evidence(
        id=str(row.id),
        source=domain_source(source),
        entity_id=row.entity_ref,
        quote=row.span,
        field_path=row.field_path,
        field_value=row.value,
        page=row.page,
        as_of=row.as_of,
    )
