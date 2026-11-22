"""run_activities: the live activity stream of a run

One row per thing a run did that the live run view and the run log show (a status
line, a call, a page read, a model read, a finding, a notice), numbered per run by
`seq`. `payload` holds the `ActivityOut` envelope. Public data only.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_activities",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_activities_run_id_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["steps.id"],
            name=op.f("fk_run_activities_step_id_steps"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_run_activities_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_activities")),
        # Also the (run_id, seq) index every stream and page query uses.
        sa.UniqueConstraint("run_id", "seq", name=op.f("uq_run_activities_run_id")),
    )
    op.create_index(
        op.f("ix_run_activities_workspace_id"), "run_activities", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_run_activities_workspace_id"), table_name="run_activities")
    op.drop_table("run_activities")
