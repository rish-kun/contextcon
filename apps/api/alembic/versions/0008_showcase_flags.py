"""is_showcase on theses, cases and investor runs (investor searches)

The public read-only showcase (`/public/showcase/*`) serves only rows flagged here:
one real discovery thesis, one real verified case and one real investor search, run by
the real pipelines on public information. Nothing else is ever served without a session.
Flags are set by an operator, never by the API.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22 23:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("theses", "cases", "investor_runs")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("is_showcase", sa.Boolean(), server_default=sa.false(), nullable=False),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "is_showcase")
