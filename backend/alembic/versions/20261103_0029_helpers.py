"""helpers: agents, agent_versions, flows, flow_versions, flow_runs, flow_run_steps, flow_run_handoffs (ADR 0031)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-02 14:16:26.107410
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("avatar", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(name) BETWEEN 1 AND 80", name=op.f("ck_agents_name")
        ),
        sa.CheckConstraint(
            "current_version >= 1", name=op.f("ck_agents_current_version")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_agents_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
    )
    op.create_index("ix_agents_org_id", "agents", ["org_id"], unique=False)
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.String(), nullable=False),
        sa.Column("model_tier", sa.String(length=8), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "context_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "output_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "model_tier IN ('fast', 'smart')", name=op.f("ck_agent_versions_model_tier")
        ),
        sa.CheckConstraint(
            "char_length(instructions) BETWEEN 1 AND 4000",
            name=op.f("ck_agent_versions_instructions"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_agent_versions_version")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_versions_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_agent_versions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_versions")),
        sa.UniqueConstraint(
            "agent_id", "version", name=op.f("uq_agent_versions_agent_id_version")
        ),
    )
    op.create_index(
        "ix_agent_versions_org_id", "agent_versions", ["org_id"], unique=False
    )
    op.create_table(
        "flows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(name) BETWEEN 1 AND 80", name=op.f("ck_flows_name")
        ),
        sa.CheckConstraint(
            "current_version >= 1", name=op.f("ck_flows_current_version")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flows_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flows")),
    )
    op.create_index("ix_flows_org_id", "flows", ["org_id"], unique=False)
    op.create_table(
        "flow_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("flow_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_flow_versions_version")),
        sa.ForeignKeyConstraint(
            ["flow_id"],
            ["flows.id"],
            name=op.f("fk_flow_versions_flow_id_flows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flow_versions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_versions")),
        sa.UniqueConstraint(
            "flow_id", "version", name=op.f("uq_flow_versions_flow_id_version")
        ),
    )
    op.create_index(
        "ix_flow_versions_org_id", "flow_versions", ["org_id"], unique=False
    )
    op.create_table(
        "flow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("flow_id", sa.Uuid(), nullable=False),
        sa.Column("flow_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="queued", nullable=False
        ),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')",
            name=op.f("ck_flow_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["flow_id"],
            ["flows.id"],
            name=op.f("fk_flow_runs_flow_id_flows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["flow_version_id"],
            ["flow_versions.id"],
            name=op.f("fk_flow_runs_flow_version_id_flow_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_postings.id"],
            name=op.f("fk_flow_runs_job_id_job_postings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flow_runs_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_flow_runs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_runs")),
    )
    op.create_index(
        "ix_flow_runs_org_id_created_at",
        "flow_runs",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_flow_runs_flow_id_created_at",
        "flow_runs",
        ["flow_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_flow_runs_created_at", "flow_runs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_flow_runs_running_updated_at",
        "flow_runs",
        ["updated_at"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "uq_flow_runs_org_id_idempotency_key",
        "flow_runs",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "flow_run_handoffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("edge_id", sa.Uuid(), nullable=False),
        sa.Column("from_node", sa.Uuid(), nullable=False),
        sa.Column("to_node", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("truncated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flow_run_handoffs_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["flow_runs.id"],
            name=op.f("fk_flow_run_handoffs_run_id_flow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_run_handoffs")),
        sa.UniqueConstraint(
            "run_id", "edge_id", name=op.f("uq_flow_run_handoffs_run_id_edge_id")
        ),
    )
    op.create_index(
        "ix_flow_run_handoffs_org_id", "flow_run_handoffs", ["org_id"], unique=False
    )
    op.create_table(
        "flow_run_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed', 'skipped')",
            name=op.f("ck_flow_run_steps_status"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_flow_run_steps_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["flow_runs.id"],
            name=op.f("fk_flow_run_steps_run_id_flow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_run_steps")),
        sa.UniqueConstraint(
            "run_id", "node_id", name=op.f("uq_flow_run_steps_run_id_node_id")
        ),
    )
    op.create_index(
        "ix_flow_run_steps_org_id", "flow_run_steps", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_flow_run_handoffs_org_id", table_name="flow_run_handoffs")
    op.drop_table("flow_run_handoffs")
    op.drop_index("ix_flow_run_steps_org_id", table_name="flow_run_steps")
    op.drop_table("flow_run_steps")
    op.drop_index(
        "uq_flow_runs_org_id_idempotency_key",
        table_name="flow_runs",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index(
        "ix_flow_runs_running_updated_at",
        table_name="flow_runs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index("ix_flow_runs_created_at", table_name="flow_runs")
    op.drop_index("ix_flow_runs_flow_id_created_at", table_name="flow_runs")
    op.drop_index("ix_flow_runs_org_id_created_at", table_name="flow_runs")
    op.drop_table("flow_runs")
    op.drop_index("ix_flow_versions_org_id", table_name="flow_versions")
    op.drop_table("flow_versions")
    op.drop_index("ix_flows_org_id", table_name="flows")
    op.drop_table("flows")
    op.drop_index("ix_agent_versions_org_id", table_name="agent_versions")
    op.drop_table("agent_versions")
    op.drop_index("ix_agents_org_id", table_name="agents")
    op.drop_table("agents")
