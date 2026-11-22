"""request_items.priority and priority_reason: blocker-first evidence requests

`act.request_list` orders a request list from the version's DecisionFlip analysis:
documents in its minimum evidence set first (priority 0), then other decision blockers
(1), disqualifier risks (2), non-blocking documents (3) and documents whose only open
items are checks to re-run on our side (4). `position` keeps the final order; these
columns say why. Rows written before this migration read as non-blocking, which is how
they were drafted.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-23 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = ("decision_blocker", "disqualifier_risk", "non_blocking", "analyst_retry")


def upgrade() -> None:
    op.add_column(
        "request_items",
        sa.Column("priority", sa.Integer(), server_default=sa.text("3"), nullable=False),
    )
    op.add_column(
        "request_items",
        sa.Column(
            "priority_reason",
            sa.String(length=32),
            server_default=sa.text("'non_blocking'"),
            nullable=False,
        ),
    )
    values = ", ".join(f"'{r}'" for r in REASONS)
    op.create_check_constraint(
        op.f("ck_request_items_priority_reason"),
        "request_items",
        f"priority_reason IN ({values})",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_request_items_priority_reason"), "request_items", type_="check")
    op.drop_column("request_items", "priority_reason")
    op.drop_column("request_items", "priority")
