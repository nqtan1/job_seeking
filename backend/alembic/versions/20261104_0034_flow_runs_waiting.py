"""flow_runs_waiting: a run can park on a wait step (ADR 0032)

Revision ID: 0034
Revises: 0033
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_OLD = "status IN ('queued', 'running', 'done', 'failed', 'cancelled')"
RUN_NEW = "status IN ('queued', 'running', 'waiting', 'done', 'failed', 'cancelled')"
STEP_OLD = "status IN ('pending', 'running', 'done', 'failed', 'skipped')"
STEP_NEW = "status IN ('pending', 'running', 'waiting', 'done', 'failed', 'skipped')"


def _swap(table: str, new: str) -> None:
    name = op.f(f"ck_{table}_status")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, new)


def upgrade() -> None:
    op.add_column(
        "flow_runs", sa.Column("wake_at", sa.DateTime(timezone=True), nullable=True)
    )
    _swap("flow_runs", RUN_NEW)
    _swap("flow_run_steps", STEP_NEW)


def downgrade() -> None:
    op.execute(
        "UPDATE flow_runs SET status = 'failed', error_code = 'wake_lost', finished_at = now() "
        "WHERE status = 'waiting'"
    )
    op.execute(
        "UPDATE flow_run_steps SET status = 'failed', error_code = 'wake_lost' "
        "WHERE status = 'waiting'"
    )
    _swap("flow_run_steps", STEP_OLD)
    _swap("flow_runs", RUN_OLD)
    op.drop_column("flow_runs", "wake_at")
