"""email recipients (confirmed by link) and the platform-wide suppression list (ADR 0032)

Revision ID: 0033
Revises: 0032
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("confirm_hash", sa.String(length=64), nullable=True),
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed')",
            name=op.f("ck_email_recipients_status"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_email_recipients_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_recipients_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_recipients")),
        sa.UniqueConstraint(
            "user_id", "email", name=op.f("uq_email_recipients_user_id_email")
        ),
        sa.UniqueConstraint(
            "unsubscribe_token", name=op.f("uq_email_recipients_unsubscribe_token")
        ),
    )
    op.create_index("ix_email_recipients_org_id", "email_recipients", ["org_id"])
    op.create_index(
        "ix_email_recipients_confirm_hash", "email_recipients", ["confirm_hash"]
    )
    op.create_table(
        "email_suppressions",
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("email_hash", name=op.f("pk_email_suppressions")),
    )


def downgrade() -> None:
    op.drop_table("email_suppressions")
    op.drop_table("email_recipients")
