"""radar consent log + pause state (ADR 0024)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
        sa.CheckConstraint("scope IN ('radar')", name=op.f("ck_consents_scope")),
        sa.CheckConstraint(
            "event IN ('granted', 'withdrawn')", name=op.f("ck_consents_event")
        ),
        sa.CheckConstraint(
            "source IN ('ui', 'email_link')", name=op.f("ck_consents_source")
        ),
    )
    op.create_index(
        "ix_consents_org_id_scope_at", "consents", ["org_id", "scope", "at"]
    )
    op.add_column("radar_searches", sa.Column("paused_reason", sa.String()))
    op.add_column("radar_searches", sa.Column("paused_at", sa.DateTime(timezone=True)))
    op.add_column(
        "radar_searches",
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_check_constraint(
        op.f("ck_radar_searches_paused_reason"),
        "radar_searches",
        "paused_reason IN ('consent', 'inactive', 'failures')",
    )
    op.add_column("users", sa.Column("radar_notice_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "radar_notice_at")
    op.drop_constraint(
        op.f("ck_radar_searches_paused_reason"), "radar_searches", type_="check"
    )
    op.drop_column("radar_searches", "consecutive_failures")
    op.drop_column("radar_searches", "paused_at")
    op.drop_column("radar_searches", "paused_reason")
    op.drop_index("ix_consents_org_id_scope_at", "consents")
    op.drop_table("consents")
