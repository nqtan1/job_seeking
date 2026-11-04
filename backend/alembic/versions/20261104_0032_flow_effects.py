"""flow_effects: at-most-once outside effects of a flow run (ADR 0032)

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flow_effects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flow_effects_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_flow_effects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["flow_runs.id"],
            name=op.f("fk_flow_effects_run_id_flow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_effects")),
        sa.UniqueConstraint(
            "run_id", "node_id", name=op.f("uq_flow_effects_run_id_node_id")
        ),
    )
    op.create_index("ix_flow_effects_org_id", "flow_effects", ["org_id"])
    op.create_index(
        "ix_flow_effects_user_id_kind_created_at",
        "flow_effects",
        ["user_id", "kind", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("flow_effects")
