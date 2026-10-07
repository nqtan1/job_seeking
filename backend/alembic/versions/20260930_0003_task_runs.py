"""task_runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="queued", nullable=False
        ),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("result_ref", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'done', 'failed')", name=op.f("ck_task_runs_status")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_task_runs_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_runs")),
    )
    op.create_index(
        "ix_task_runs_org_id_created_at",
        "task_runs",
        ["org_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_task_runs_org_id_created_at", table_name="task_runs")
    op.drop_table("task_runs")
