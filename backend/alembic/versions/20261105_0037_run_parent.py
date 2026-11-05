"""flow_runs.parent_run_id and trigger 'flow' (ADR 0034); seen_offers dropped, offers are remembered as saved Jobs (ADR 0035)

Revision ID: 0037
Revises: 0036
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _retire_tools() -> None:
    """Flows saved with the short-lived new_offer / new_offers blocks keep loading: the block
    becomes find_offers. Links that read fields it no longer has show up as problems in the
    editor, so such a flow is fixed by hand instead of failing to open."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, graph FROM flow_versions WHERE graph::text ~ 'new_offers?\"'"
        )
    ).all()
    for row_id, graph in rows:
        for node in graph.get("nodes", []):
            if node.get("tool") in ("new_offer", "new_offers"):
                node["tool"] = "find_offers"
        bind.execute(
            sa.text("UPDATE flow_versions SET graph = CAST(:g AS jsonb) WHERE id = :i"),
            {"g": json.dumps(graph), "i": row_id},
        )


def upgrade() -> None:
    _retire_tools()
    op.drop_table("seen_offers")
    op.add_column("flow_runs", sa.Column("parent_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_flow_runs_parent_run_id_flow_runs"),
        "flow_runs",
        "flow_runs",
        ["parent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_flow_runs_parent_run_id", "flow_runs", ["parent_run_id"])
    op.drop_constraint(op.f("ck_flow_runs_trigger"), "flow_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_flow_runs_trigger"),
        "flow_runs",
        "trigger IN ('manual', 'schedule', 'flow')",
    )


def downgrade() -> None:
    op.create_table(
        "seen_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_seen_offers_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_seen_offers_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seen_offers")),
        sa.UniqueConstraint(
            "user_id", "url_hash", name=op.f("uq_seen_offers_user_id_url_hash")
        ),
    )
    op.create_index("ix_seen_offers_org_id", "seen_offers", ["org_id"])
    op.create_index(
        "ix_seen_offers_run_id_node_id", "seen_offers", ["run_id", "node_id"]
    )
    op.execute("UPDATE flow_runs SET trigger = 'manual' WHERE trigger = 'flow'")
    op.drop_constraint(op.f("ck_flow_runs_trigger"), "flow_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_flow_runs_trigger"), "flow_runs", "trigger IN ('manual', 'schedule')"
    )
    op.drop_index("ix_flow_runs_parent_run_id", table_name="flow_runs")
    op.drop_constraint(
        op.f("fk_flow_runs_parent_run_id_flow_runs"), "flow_runs", type_="foreignkey"
    )
    op.drop_column("flow_runs", "parent_run_id")
