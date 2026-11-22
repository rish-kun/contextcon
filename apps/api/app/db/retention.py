"""Explicit retention paths for rows the database otherwise keeps forever.

`assessment_versions`, `message_revisions` and `approvals` reject UPDATE always and
DELETE unless the transaction opts in here. Only a deliberate retention job (for
example, deleting a whole case under a retention schedule) may call this, and it must
record what it deleted in `deletion_records`.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RETENTION_DELETE_SETTING = "dealproof.retention_delete"


async def allow_retention_delete(session: AsyncSession) -> None:
    """Allow deleting immutable rows until the current transaction ends."""
    await session.execute(text(f"SET LOCAL {RETENTION_DELETE_SETTING} = 'on'"))
