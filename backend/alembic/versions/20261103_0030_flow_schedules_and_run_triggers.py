"""flow_schedules and flow_runs.trigger / schedule_id (ADR 0031)

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-03 12:53:52.792766
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flow_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("flow_id", sa.Uuid(), nullable=False),
        sa.Column("cadence", sa.String(length=8), nullable=False),
        sa.Column("at_time", sa.String(length=5), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("paused_reason", sa.String(length=16), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cadence IN ('hourly', 'daily', 'weekly')",
            name=op.f("ck_flow_schedules_cadence"),
        ),
        sa.CheckConstraint(
            "paused_reason IN ('failures', 'inactive')",
            name=op.f("ck_flow_schedules_paused_reason"),
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_flow_schedules_weekday")
        ),
        sa.ForeignKeyConstraint(
            ["flow_id"],
            ["flows.id"],
            name=op.f("fk_flow_schedules_flow_id_flows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_postings.id"],
            name=op.f("fk_flow_schedules_job_id_job_postings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flow_schedules_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_flow_schedules_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_schedules")),
    )
    op.create_index(
        "ix_flow_schedules_due",
        "flow_schedules",
        ["next_run_at"],
        unique=False,
        postgresql_where=sa.text("enabled AND paused_reason IS NULL"),
    )
    op.create_index(
        "ix_flow_schedules_flow_id", "flow_schedules", ["flow_id"], unique=False
    )
    op.create_index(
        "ix_flow_schedules_org_id", "flow_schedules", ["org_id"], unique=False
    )
    op.add_column(
        "flow_runs",
        sa.Column(
            "trigger", sa.String(length=16), server_default="manual", nullable=False
        ),
    )
    op.add_column("flow_runs", sa.Column("schedule_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f("ck_flow_runs_trigger"), "flow_runs", "trigger IN ('manual', 'schedule')"
    )
    op.create_index(
        "ix_flow_runs_schedule_id_created_at",
        "flow_runs",
        ["schedule_id", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_flow_runs_schedule_id_flow_schedules"),
        "flow_runs",
        "flow_schedules",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_flow_runs_schedule_id_created_at", table_name="flow_runs")
    op.drop_constraint(
        op.f("fk_flow_runs_schedule_id_flow_schedules"), "flow_runs", type_="foreignkey"
    )
    op.drop_constraint(op.f("ck_flow_runs_trigger"), "flow_runs", type_="check")
    op.drop_column("flow_runs", "schedule_id")
    op.drop_column("flow_runs", "trigger")
    op.drop_index("ix_flow_schedules_org_id", table_name="flow_schedules")
    op.drop_index("ix_flow_schedules_flow_id", table_name="flow_schedules")
    op.drop_index(
        "ix_flow_schedules_due",
        table_name="flow_schedules",
        postgresql_where=sa.text("enabled AND paused_reason IS NULL"),
    )
    op.drop_table("flow_schedules")
