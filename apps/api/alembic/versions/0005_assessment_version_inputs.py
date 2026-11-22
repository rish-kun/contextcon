"""assessment versions record which documents and evidence they rest on

- trigger_document_ids: the uploaded documents that caused this version (a seller
  response, or documents whose evidence first appears in it). The UI no longer has to
  match filenames in the trigger text, where two files with one name collide.
- document_ids / evidence_ids: every document and evidence row the version consumed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("trigger_document_ids", "document_ids", "evidence_ids")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column(
            "assessment_versions",
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column("assessment_versions", name)
