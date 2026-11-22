"""org_profiles, org_research, signup status, workspace credit allowance, row origin

- `org_profiles`: one per workspace, the organisation and its goal (acquire / raise /
  both), with per-field provenance (record or stated) and the trimmed own-company
  record (design E §4.1, simplified; design I B0).
- `org_research`: one row per auto-research attempt (design I §4.1), linking the
  parent `org_research` run and the Discover / investor child runs it launches.
- `users.status`: `pending` for signups not yet enabled (signup test mode).
- `workspaces.credit_allowance`: total credit ceiling for self-serve workspaces.
- `theses.origin`, `investor_runs.origin`: `user` or `auto_research`.
- `runs.kind` gains `org_research`.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-22 12:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = "kind IN ('discover', 'investor_discover', 'verify', 'evaluate', 'recheck')"
NEW_KINDS = (
    "kind IN ('discover', 'investor_discover', 'verify', 'evaluate', 'recheck', 'org_research')"
)
ORG_TYPES = "org_type IN ('acquirer', 'investor', 'business', 'adviser')"
GOALS = "goal IN ('acquire', 'raise', 'both')"
BANDS = "deal_size_band IN ('under_0_5m', '0_5m_2m', '2m_10m', '10m_50m', 'over_50m')"


def _ts(name: str, *, nullable: bool = True, default: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("credit_allowance", sa.Numeric(14, 4), nullable=True))
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
    )
    op.create_check_constraint(op.f("ck_users_status"), "users", "status IN ('active', 'pending')")
    for table in ("theses", "investor_runs"):
        op.add_column(
            table,
            sa.Column("origin", sa.String(length=32), server_default="user", nullable=False),
        )
        op.create_check_constraint(
            op.f(f"ck_{table}_origin"), table, "origin IN ('user', 'auto_research')"
        )
    op.drop_constraint(op.f("ck_runs_kind"), "runs", type_="check")
    op.create_check_constraint(op.f("ck_runs_kind"), "runs", NEW_KINDS)

    op.create_table(
        "org_profiles",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("org_type", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("website_domain", sa.String(length=253), nullable=True),
        sa.Column("crustdata_company_id", sa.BigInteger(), nullable=True),
        sa.Column("sector", sa.String(length=300), nullable=True),
        sa.Column("hq", sa.String(length=200), nullable=True),
        sa.Column("hq_country", sa.String(length=100), nullable=True),
        sa.Column("size_band", sa.String(length=16), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("goal", sa.String(length=16), nullable=True),
        sa.Column("deal_size_band", sa.String(length=16), nullable=True),
        sa.Column("what_we_want", sa.Text(), nullable=True),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("record_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _ts("record_retrieved_at"),
        sa.Column("record_source_id", sa.Uuid(), nullable=True),
        sa.Column("pending_autofill", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _ts("updated_at", nullable=False, default=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        _ts("created_at", nullable=False, default=True),
        sa.CheckConstraint(
            f"org_type IS NULL OR {ORG_TYPES}", name=op.f("ck_org_profiles_org_type")
        ),
        sa.CheckConstraint(f"goal IS NULL OR {GOALS}", name=op.f("ck_org_profiles_goal")),
        sa.CheckConstraint(
            f"deal_size_band IS NULL OR {BANDS}", name=op.f("ck_org_profiles_deal_size_band")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_org_profiles_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_source_id"],
            ["sources.id"],
            name=op.f("fk_org_profiles_record_source_id_sources"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_org_profiles_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_profiles")),
        sa.UniqueConstraint("workspace_id", name=op.f("uq_org_profiles_workspace_id")),
    )

    op.create_table(
        "org_research",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("market", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("derivation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("thesis_id", sa.Uuid(), nullable=True),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=True),
        sa.Column("investor_run_id", sa.Uuid(), nullable=True),
        sa.Column("research_run_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("budget_credits", sa.Numeric(14, 4), nullable=False),
        _ts("finished_at"),
        sa.Column("id", sa.Uuid(), nullable=False),
        _ts("created_at", nullable=False, default=True),
        sa.CheckConstraint(
            "mode IN ('acquire', 'raise', 'both')", name=op.f("ck_org_research_mode")
        ),
        sa.CheckConstraint(
            "trigger IN ('onboarding', 'manual', 'retry', 'seed')",
            name=op.f("ck_org_research_trigger"),
        ),
        sa.CheckConstraint(
            "status IN ('deriving', 'searching', 'finishing', 'ready', 'partial', 'failed')",
            name=op.f("ck_org_research_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_org_research_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_org_research_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thesis_id"],
            ["theses.id"],
            name=op.f("fk_org_research_thesis_id_theses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"],
            ["discovery_runs.id"],
            name=op.f("fk_org_research_discovery_run_id_discovery_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["investor_run_id"],
            ["investor_runs.id"],
            name=op.f("fk_org_research_investor_run_id_investor_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["runs.id"],
            name=op.f("fk_org_research_research_run_id_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_research")),
    )
    op.create_index(
        op.f("ix_org_research_workspace_id"), "org_research", ["workspace_id"], unique=False
    )
    op.create_index(
        "ix_org_research_workspace_created",
        "org_research",
        ["workspace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_org_research_workspace_created", table_name="org_research")
    op.drop_index(op.f("ix_org_research_workspace_id"), table_name="org_research")
    op.drop_table("org_research")
    op.drop_table("org_profiles")
    op.execute("DELETE FROM runs WHERE kind = 'org_research'")
    op.drop_constraint(op.f("ck_runs_kind"), "runs", type_="check")
    op.create_check_constraint(op.f("ck_runs_kind"), "runs", OLD_KINDS)
    for table in ("investor_runs", "theses"):
        op.drop_constraint(op.f(f"ck_{table}_origin"), table, type_="check")
        op.drop_column(table, "origin")
    op.drop_constraint(op.f("ck_users_status"), "users", type_="check")
    op.drop_column("users", "status")
    op.drop_column("workspaces", "credit_allowance")
