"""lease tokens, per-dispatch attempts, credit budgets, owner/workspace FKs, payloads

- steps.lease_token: a fresh token per claim, required to renew, finish or dispatch.
- call_attempts: operation_key, dispatch_index, reserved_credits; status `unknown`.
- credit_budgets: one lockable row per budget owner, for atomic credit reservation.
- runs / call_attempts / cost_entries / credit_budgets: owner columns reference
  (id, workspace_id), so an owner from another workspace cannot be attached.
- confidential_payloads (+ steps.confidential_output_id): expiring storage for
  confidential step outputs and assessment snapshots.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNERS = (
    ("case_id", "cases"),
    ("discovery_run_id", "discovery_runs"),
    ("investor_run_id", "investor_runs"),
)
OWNED_TABLES = ("runs", "call_attempts", "cost_entries")


def _fk_name(table: str, column: str, referred: str) -> str:
    return op.f(f"fk_{table}_{column}_{referred}")


def upgrade() -> None:
    # Targets for the composite foreign keys.
    for _, owner in OWNERS:
        op.create_unique_constraint(op.f(f"uq_{owner}_id"), owner, ["id", "workspace_id"])

    # Owner columns now reference (id, workspace_id).
    for table in OWNED_TABLES:
        for column, owner in OWNERS:
            name = _fk_name(table, column, owner)
            op.drop_constraint(name, table, type_="foreignkey")
            op.create_foreign_key(
                name,
                table,
                owner,
                [column, "workspace_id"],
                ["id", "workspace_id"],
                ondelete="CASCADE",
            )

    op.create_table(
        "credit_budgets",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=True),
        sa.Column("investor_run_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "num_nonnulls(case_id, discovery_run_id, investor_run_id) = 1",
            name=op.f("ck_credit_budgets_one_owner"),
        ),
        *(
            sa.ForeignKeyConstraint(
                [column, "workspace_id"],
                [f"{owner}.id", f"{owner}.workspace_id"],
                name=_fk_name("credit_budgets", column, owner),
                ondelete="CASCADE",
            )
            for column, owner in OWNERS
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_credit_budgets_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_budgets")),
        sa.UniqueConstraint("case_id", name=op.f("uq_credit_budgets_case_id")),
        sa.UniqueConstraint("discovery_run_id", name=op.f("uq_credit_budgets_discovery_run_id")),
        sa.UniqueConstraint("investor_run_id", name=op.f("uq_credit_budgets_investor_run_id")),
    )
    op.create_index(
        op.f("ix_credit_budgets_workspace_id"), "credit_budgets", ["workspace_id"], unique=False
    )

    op.create_table(
        "confidential_payloads",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_version_id", sa.Uuid(), nullable=True),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
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
            name=op.f("fk_confidential_payloads_assessment_version_id_assessment_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_confidential_payloads_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_confidential_payloads_run_id_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_confidential_payloads_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confidential_payloads")),
    )
    op.create_index(
        op.f("ix_confidential_payloads_assessment_version_id"),
        "confidential_payloads",
        ["assessment_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_confidential_payloads_case_id"), "confidential_payloads", ["case_id"], unique=False
    )
    op.create_index(
        "ix_confidential_payloads_delete_after",
        "confidential_payloads",
        ["delete_after"],
        unique=False,
    )
    op.create_index(
        op.f("ix_confidential_payloads_workspace_id"),
        "confidential_payloads",
        ["workspace_id"],
        unique=False,
    )

    op.add_column("call_attempts", sa.Column("operation_key", sa.String(length=64), nullable=True))
    op.add_column(
        "call_attempts",
        sa.Column("dispatch_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "call_attempts",
        sa.Column(
            "reserved_credits",
            sa.Numeric(precision=14, scale=4),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("call_attempts", "dispatch_index", server_default=None)
    op.alter_column("call_attempts", "reserved_credits", server_default=None)
    op.create_index(
        op.f("ix_call_attempts_operation_key"), "call_attempts", ["operation_key"], unique=False
    )
    op.drop_constraint(op.f("ck_call_attempts_status"), "call_attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_call_attempts_status"),
        "call_attempts",
        "status IN ('started', 'succeeded', 'failed', 'cache_hit', 'unknown')",
    )

    op.add_column("steps", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.add_column("steps", sa.Column("confidential_output_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_steps_confidential_output_id_confidential_payloads"),
        "steps",
        "confidential_payloads",
        ["confidential_output_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_steps_confidential_output_id_confidential_payloads"), "steps", type_="foreignkey"
    )
    op.drop_column("steps", "confidential_output_id")
    op.drop_column("steps", "lease_token")

    op.execute("UPDATE call_attempts SET status = 'failed' WHERE status = 'unknown'")
    op.drop_constraint(op.f("ck_call_attempts_status"), "call_attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_call_attempts_status"),
        "call_attempts",
        "status IN ('started', 'succeeded', 'failed', 'cache_hit')",
    )
    op.drop_index(op.f("ix_call_attempts_operation_key"), table_name="call_attempts")
    op.drop_column("call_attempts", "reserved_credits")
    op.drop_column("call_attempts", "dispatch_index")
    op.drop_column("call_attempts", "operation_key")

    op.drop_table("confidential_payloads")
    op.drop_table("credit_budgets")

    for table in OWNED_TABLES:
        for column, owner in OWNERS:
            name = _fk_name(table, column, owner)
            op.drop_constraint(name, table, type_="foreignkey")
            op.create_foreign_key(name, table, owner, [column], ["id"], ondelete="CASCADE")

    for _, owner in OWNERS:
        op.drop_constraint(op.f(f"uq_{owner}_id"), owner, type_="unique")
