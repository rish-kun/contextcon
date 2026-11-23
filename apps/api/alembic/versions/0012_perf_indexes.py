"""Indexes for foreign keys read by case pages: deletion records, a case's thesis and
shortlist item

- `deletion_records.case_id`: every `GET /cases/{id}` reads the case's deletion records
  (retention notices); the table only grows, as the purge job appends to it.
- `cases.thesis_id`, `cases.candidate_id`: foreign keys with `ON DELETE SET NULL`, so
  deleting a thesis or a shortlist item scanned every case; also used to find the case
  opened from a shortlist item.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-23 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = (
    ("ix_deletion_records_case_id", "deletion_records", "case_id"),
    ("ix_cases_thesis_id", "cases", "thesis_id"),
    ("ix_cases_candidate_id", "cases", "candidate_id"),
)


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
