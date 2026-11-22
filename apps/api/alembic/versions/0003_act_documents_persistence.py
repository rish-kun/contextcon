"""act + documents persistence: send generations and payloads, document text status,
immutable rows protected from DELETE

- send_attempts: `generation` (compare-and-set fence), `attempts`, `test_mode`, the exact
  dispatch `payload`, and dispatch/completion timestamps.
- documents / extracted_texts: what the ingestion service records about extraction
  (file kind, text status and reason, redaction counts, page/paragraph order).
- assessment_versions, message_revisions, approvals: the immutability trigger now also
  rejects DELETE, unless the transaction opted into a retention path with
  `SET LOCAL dealproof.retention_delete = 'on'` (see `app.db.retention`). Foreign keys
  that used to cascade or SET NULL into these rows become RESTRICT, so ordinary cleanup
  fails loudly instead of tripping the trigger halfway through.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = ("assessment_versions", "message_revisions", "approvals")

FORBID_CHANGE_FN = """
CREATE OR REPLACE FUNCTION dealproof_forbid_update() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND coalesce(current_setting('dealproof.retention_delete', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'rows in % are immutable; insert a new version instead', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

ORIGINAL_FN = """
CREATE OR REPLACE FUNCTION dealproof_forbid_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'rows in % are immutable; insert a new version instead', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

# (table, column, referred table, ondelete before this revision)
RESTRICTED_FKS = (
    ("assessment_versions", "case_id", "cases", "CASCADE"),
    ("assessment_versions", "created_by", "users", "SET NULL"),
    ("assessment_versions", "previous_version_id", "assessment_versions", "SET NULL"),
    ("assessment_versions", "run_id", "runs", "SET NULL"),
    ("message_revisions", "case_id", "cases", "CASCADE"),
    ("message_revisions", "created_by", "users", "SET NULL"),
    ("message_revisions", "request_list_id", "request_lists", "CASCADE"),
    ("approvals", "message_revision_id", "message_revisions", "CASCADE"),
    ("send_attempts", "message_revision_id", "message_revisions", "CASCADE"),
    ("send_attempts", "request_list_id", "request_lists", "CASCADE"),
)


def _replace_fk(table: str, column: str, referred: str, ondelete: str) -> None:
    name = op.f(f"fk_{table}_{column}_{referred}")
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(name, table, referred, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    op.add_column(
        "send_attempts",
        sa.Column("generation", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "send_attempts",
        sa.Column("attempts", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "send_attempts",
        sa.Column("test_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "send_attempts",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    for column in ("dispatched_at", "last_attempt_at", "completed_at"):
        op.add_column("send_attempts", sa.Column(column, sa.DateTime(timezone=True)))

    op.add_column("documents", sa.Column("file_kind", sa.String(length=16), nullable=True))
    op.add_column("documents", sa.Column("text_status", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("text_status_reason", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "redaction_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "extracted_texts",
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("extracted_texts", sa.Column("paragraph", sa.Integer(), nullable=True))
    op.add_column(
        "extracted_texts",
        sa.Column("has_text_layer", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    for table, column, referred, _ in RESTRICTED_FKS:
        _replace_fk(table, column, referred, "RESTRICT")

    op.execute(FORBID_CHANGE_FN)
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION dealproof_forbid_update()"
        )


def downgrade() -> None:
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.execute(ORIGINAL_FN)
    for table, column, referred, ondelete in RESTRICTED_FKS:
        _replace_fk(table, column, referred, ondelete)

    op.drop_column("extracted_texts", "has_text_layer")
    op.drop_column("extracted_texts", "paragraph")
    op.drop_column("extracted_texts", "position")
    op.drop_column("documents", "redaction_counts")
    op.drop_column("documents", "text_status_reason")
    op.drop_column("documents", "text_status")
    op.drop_column("documents", "file_kind")
    for column in (
        "completed_at",
        "last_attempt_at",
        "dispatched_at",
        "payload",
        "test_mode",
        "attempts",
        "generation",
    ):
        op.drop_column("send_attempts", column)
