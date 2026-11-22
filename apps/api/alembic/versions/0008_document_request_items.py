"""document_request_items: which request items a seller response answers

A seller response upload names the request items it answers
(`answers_request_item_ids`). The links drive the recheck run (the claims behind those
items are checked again) and show on the case's documents.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22 23:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_request_items",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("request_item_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_request_items_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["request_item_id"],
            ["request_items.id"],
            name=op.f("fk_document_request_items_request_item_id_request_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "document_id", "request_item_id", name=op.f("pk_document_request_items")
        ),
    )
    op.create_index(
        op.f("ix_document_request_items_request_item_id"),
        "document_request_items",
        ["request_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_document_request_items_request_item_id"), table_name="document_request_items"
    )
    op.drop_table("document_request_items")
