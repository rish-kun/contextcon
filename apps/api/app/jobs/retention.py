"""Retention for confidential JSON that steps and assessments keep (spec §7,
"retention covers derivatives").

Approach: **separately expirable records, linked from the snapshot**. Document-derived
content that a step output or an assessment snapshot would otherwise copy inline goes
into a `confidential_payloads` row with its own `delete_after`; the snapshot keeps
only a reference. The purge job (`app.jobs.purge`) deletes expired payload rows and
writes a deletion record; the snapshot itself is untouched, which matters because
assessment versions are immutable (no UPDATE, and DELETE only on an explicit
retention path). Scrubbing snapshots in place was rejected for that reason.

- **Step outputs:** a handler whose output carries confidential text calls
  `ctx.keep_output_confidential()`. The worker stores the whole output in a payload
  and leaves `{"_confidential": true}` on the step (`steps.confidential_output_id`
  links them). Dependents read it through `ctx.dependencies[key]["output"]` as usual
  until it expires; afterwards they see `{"_retention_expired": true}`.
- **Assessment snapshots:** store the confidential part with
  `store_confidential(..., assessment_version_id=version.id)` and put
  `confidential_ref(payload_id)` in the version's JSON instead of the text. Read it
  back with `load_confidential` (None once expired or purged).

`delete_after` defaults to the earlier of now + `UPLOAD_RETENTION_DAYS` and the case's
next pending document deletion. Expired payloads are never returned, even before the
purge job runs.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.adapters import confidential_delete_after_sql, retention_deadline
from app.db.models import ConfidentialPayload

REF_KEY = "$confidential_payload"
EXPIRED_OUTPUT: dict[str, Any] = {"_retention_expired": True}
CONFIDENTIAL_MARKER: dict[str, Any] = {"_confidential": True}


def default_delete_after() -> datetime:
    """now + UPLOAD_RETENTION_DAYS (the case-aware default is applied when stored)."""
    return retention_deadline()


def confidential_ref(payload_id: uuid.UUID) -> dict[str, str]:
    return {REF_KEY: str(payload_id)}


def ref_id(value: Any) -> uuid.UUID | None:
    if isinstance(value, dict) and isinstance(value.get(REF_KEY), str):
        try:
            return uuid.UUID(value[REF_KEY])
        except ValueError:
            return None
    return None


async def store_confidential(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    case_id: uuid.UUID,
    kind: str,
    payload: Any,
    delete_after: datetime | None = None,
    run_id: uuid.UUID | None = None,
    assessment_version_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a payload in `session` (flushes, does not commit). Returns its id."""
    row = ConfidentialPayload(
        workspace_id=workspace_id,
        case_id=case_id,
        kind=kind,
        payload=payload,
        run_id=run_id,
        assessment_version_id=assessment_version_id,
        delete_after=delete_after or confidential_delete_after_sql(case_id),
    )
    session.add(row)
    await session.flush()
    return row.id


def _live() -> Any:
    return ConfidentialPayload.delete_after > func.now()


async def load_confidential(
    session: AsyncSession, payload_id: uuid.UUID, *, case_id: uuid.UUID | None = None
) -> Any | None:
    """The payload, or None when it expired, was purged, or belongs to another case."""
    stmt = select(ConfidentialPayload.payload).where(ConfidentialPayload.id == payload_id, _live())
    if case_id is not None:
        stmt = stmt.where(ConfidentialPayload.case_id == case_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def payloads_for_assessment(
    session: AsyncSession, assessment_version_id: uuid.UUID
) -> dict[str, Any]:
    """Live payloads linked to one assessment version, by kind."""
    rows = await session.execute(
        select(ConfidentialPayload.kind, ConfidentialPayload.payload).where(
            ConfidentialPayload.assessment_version_id == assessment_version_id,
            _live(),
        )
    )
    return {kind: payload for kind, payload in rows.all()}


async def payloads_for_assessments(
    session: AsyncSession, assessment_version_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """`payloads_for_assessment` for many versions in one query: {version id: {kind: payload}}."""
    out: dict[uuid.UUID, dict[str, Any]] = {}
    if not assessment_version_ids:
        return out
    rows = await session.execute(
        select(
            ConfidentialPayload.assessment_version_id,
            ConfidentialPayload.kind,
            ConfidentialPayload.payload,
        ).where(
            ConfidentialPayload.assessment_version_id.in_(assessment_version_ids),
            _live(),
        )
    )
    for version_id, kind, payload in rows.all():
        out.setdefault(version_id, {})[kind] = payload
    return out
