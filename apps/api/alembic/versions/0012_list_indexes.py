"""Indexes for the list pages: GET /cases and GET /runs

- `cases (workspace_id, created_at)`: a workspace's cases, newest first.
- `runs (workspace_id, updated_at)`: the latest runs.
- `runs (workspace_id, state, created_at)`: active runs, oldest first.
- `cost_entries (run_id, step_id)`: a page of runs' costs grouped by run and step.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-22 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = (
    ("ix_cases_workspace_created", "cases", ["workspace_id", "created_at"]),
    ("ix_runs_workspace_updated", "runs", ["workspace_id", "updated_at"]),
    ("ix_runs_workspace_state_created", "runs", ["workspace_id", "state", "created_at"]),
    ("ix_cost_entries_run_step", "cost_entries", ["run_id", "step_id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
