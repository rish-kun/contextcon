"""Assessment snapshots that respect retention (design §7, "retention covers derivatives").

Assessment versions are immutable, so the purge job cannot scrub them. Anything in a
snapshot that can carry seller-derived text (claim status reasons with quoted values,
evidence values and source labels, request questions built from claim wording,
financial figures, the reasons in a claim's diff line) is therefore never written into
the version itself:

- the version's `judgments["assessment"]` and `diff_from_previous` hold a *skeleton*:
  statuses, ids, enums, scores and the public profile evaluation stay; confidential text
  is replaced by "Removed per retention on <date>" and values by null;
- the full snapshot and diff go into a `confidential_payloads` row
  (`app.jobs.retention`) linked to the version, which expires with the case's documents
  (or after `UPLOAD_RETENTION_DAYS`) and is deleted by the purge job.

Readers call `load_snapshot`: the full snapshot while the payload lives, the skeleton
afterwards (with `removed_on` set), so an old version still renders its statuses and
explains why its wording is gone. Versions written before this module have no
`confidential` entry and are read as they were stored.
"""

from __future__ import annotations

import copy
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.adapters import confidential_delete_after_sql
from app.db.models import AssessmentVersion as VersionRow
from app.domain.types import AssessmentDiff, AssessmentVersion
from app.jobs.retention import payloads_for_assessment, store_confidential

SNAPSHOT_KIND = "assessment_snapshot"


def removed_text(on: dt.date) -> str:
    return f"Removed per retention on {on.isoformat()}"


def redact_assessment(doc: dict[str, Any], placeholder: str) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    for o in out.get("outcomes", []):
        o["reason"] = placeholder
        for ev in o.get("evidence", []):
            ev["value"] = None
            ev["source_label"] = placeholder
            ev["note"] = ""
        for c in o.get("components", []):
            c["note"] = ""
    for q in (out.get("requests") or {}).get("questions", []):
        q["text"] = placeholder
    financial = (out.get("judgments") or {}).get("financial") or {}
    for f in financial.get("figures", []):
        f["value"] = None
        f["source_label"] = placeholder
    return out


def redact_diff(doc: dict[str, Any] | None, placeholder: str) -> dict[str, Any] | None:
    if doc is None:
        return None
    out = copy.deepcopy(doc)
    for c in out.get("claim_changes", []):
        c["reason"] = placeholder
    return out


@dataclass
class Snapshot:
    row: VersionRow
    assessment: AssessmentVersion
    diff: AssessmentDiff | None
    # Set once the confidential part has expired or been purged.
    removed_on: dt.date | None = None


def _retention(row: VersionRow) -> dict[str, Any] | None:
    meta = (row.judgments or {}).get("confidential")
    return meta if isinstance(meta, dict) else None


def skeleton(row: VersionRow) -> Snapshot:
    meta = _retention(row)
    removed_on = dt.date.fromisoformat(meta["removed_on"]) if meta else None
    diff = AssessmentDiff.model_validate(row.diff_from_previous) if row.diff_from_previous else None
    return Snapshot(
        row=row,
        assessment=AssessmentVersion.model_validate(row.judgments["assessment"]),
        diff=diff,
        removed_on=removed_on,
    )


async def load_snapshot(session: AsyncSession, row: VersionRow) -> Snapshot:
    snap = skeleton(row)
    if _retention(row) is None:
        return snap  # written before snapshots were split: stored as is
    payload = (await payloads_for_assessment(session, row.id)).get(SNAPSHOT_KIND)
    if not isinstance(payload, dict):
        return snap  # expired or purged: the skeleton, with removed_on
    full_diff = payload.get("diff")
    return Snapshot(
        row=row,
        assessment=AssessmentVersion.model_validate(payload["assessment"]),
        diff=AssessmentDiff.model_validate(full_diff) if full_diff else None,
    )


async def load_snapshots(session: AsyncSession, rows: list[VersionRow]) -> list[Snapshot]:
    return [await load_snapshot(session, r) for r in rows]


async def snapshot_deadline(session: AsyncSession, case_id: uuid.UUID) -> dt.datetime:
    """When this case's confidential derivatives expire (never after its documents)."""
    return await session.scalar(select(confidential_delete_after_sql(case_id)))


async def store_snapshot(
    session: AsyncSession,
    row: VersionRow,
    *,
    workspace_id: uuid.UUID,
    assessment: AssessmentVersion,
    diff: AssessmentDiff | None,
    delete_after: dt.datetime,
    run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await store_confidential(
        session,
        workspace_id=workspace_id,
        case_id=row.case_id,
        kind=SNAPSHOT_KIND,
        payload={
            "assessment": assessment.model_dump(mode="json"),
            "diff": diff.model_dump(mode="json") if diff else None,
        },
        delete_after=delete_after,
        run_id=run_id,
        assessment_version_id=row.id,
    )
