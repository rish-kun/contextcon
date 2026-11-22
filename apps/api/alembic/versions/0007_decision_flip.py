"""decision_flip_analyses: DecisionFlip beside each assessment version

One immutable row per (assessment version, analysis_key): which open items stand
between the case and the next disposition (`app.rules.decision_flip`). Like
`assessment_versions`, UPDATE and DELETE are rejected by trigger (DELETE only inside a
retention transaction), and every foreign key is RESTRICT. `(case_id, workspace_id)`
references the case, so a row cannot name a case from another workspace.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22 23:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "decision_flip_analyses"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_version_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_key", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("inputs_hash", sa.String(length=128), nullable=False),
        sa.Column("flip_version", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=32), nullable=True),
        sa.Column("blocker_count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_version_id"],
            ["assessment_versions.id"],
            name=op.f("fk_decision_flip_analyses_assessment_version_id_assessment_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "workspace_id"],
            ["cases.id", "cases.workspace_id"],
            name=op.f("fk_decision_flip_analyses_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_decision_flip_analyses_run_id_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_decision_flip_analyses_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_flip_analyses")),
        sa.UniqueConstraint(
            "assessment_version_id",
            "analysis_key",
            name=op.f("uq_decision_flip_analyses_assessment_version_id"),
        ),
    )
    op.create_index(op.f("ix_decision_flip_analyses_case_id"), TABLE, ["case_id"], unique=False)
    op.create_index(
        op.f("ix_decision_flip_analyses_workspace_id"), TABLE, ["workspace_id"], unique=False
    )
    # dealproof_forbid_update() (0001, retention-aware since 0003) rejects both.
    op.execute(
        f"CREATE TRIGGER {TABLE}_immutable BEFORE UPDATE ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION dealproof_forbid_update()"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_no_delete BEFORE DELETE ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION dealproof_forbid_update()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_delete ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_immutable ON {TABLE}")
    op.drop_index(op.f("ix_decision_flip_analyses_workspace_id"), table_name=TABLE)
    op.drop_index(op.f("ix_decision_flip_analyses_case_id"), table_name=TABLE)
    op.drop_table(TABLE)
