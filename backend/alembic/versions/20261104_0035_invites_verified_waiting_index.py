"""email invite ledger, users.email_verified, index for waiting runs (review of ADR 0032)

Revision ID: 0035
Revises: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_invites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_invites")),
    )
    op.create_index(
        "ix_email_invites_user_id_created_at",
        "email_invites",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_email_invites_email_hash_created_at",
        "email_invites",
        ["email_hash", "created_at"],
    )
    op.create_index("ix_email_invites_created_at", "email_invites", ["created_at"])
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_flow_runs_waiting_wake_at",
        "flow_runs",
        ["wake_at"],
        postgresql_where=sa.text("status = 'waiting'"),
    )


def downgrade() -> None:
    op.drop_index("ix_flow_runs_waiting_wake_at", table_name="flow_runs")
    op.drop_column("users", "email_verified")
    op.drop_table("email_invites")
