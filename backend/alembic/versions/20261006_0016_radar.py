"""radar_searches, radar_results, radar_runs (ADR 0021)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "radar_searches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("query", sa.String(), nullable=True),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("contract_type", sa.String(), nullable=True),
        sa.Column("min_score", sa.Integer(), server_default="70", nullable=False),
        sa.Column("daily_limit", sa.Integer(), server_default="5", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.CheckConstraint(
            "min_score BETWEEN 0 AND 100", name=op.f("ck_radar_searches_min_score")
        ),
        sa.CheckConstraint(
            "daily_limit BETWEEN 1 AND 10", name=op.f("ck_radar_searches_daily_limit")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_radar_searches_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radar_searches")),
    )
    op.create_index("ix_radar_searches_org_id", "radar_searches", ["org_id"])

    op.create_table(
        "radar_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("search_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), server_default="new", nullable=False),
        sa.Column(
            "found_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('new', 'approved', 'dismissed', 'skipped')",
            name=op.f("ck_radar_results_status"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_radar_results_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["search_id"],
            ["radar_searches.id"],
            name=op.f("fk_radar_results_search_id_radar_searches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_postings.id"],
            name=op.f("fk_radar_results_job_id_job_postings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radar_results")),
        sa.UniqueConstraint(
            "org_id",
            "source",
            "external_id",
            name=op.f("uq_radar_results_org_id_source_external_id"),
        ),
    )
    op.create_index(
        "ix_radar_results_org_id_status", "radar_results", ["org_id", "status"]
    )
    op.create_index(
        "ix_radar_results_search_id_found_at",
        "radar_results",
        ["search_id", "found_at"],
    )

    op.create_table(
        "radar_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("search_id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), server_default="ok", nullable=False),
        sa.Column("stop_reason", sa.String(), nullable=True),
        sa.Column("found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scored", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shortlisted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ok', 'partial', 'error')", name=op.f("ck_radar_runs_status")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_radar_runs_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["search_id"],
            ["radar_searches.id"],
            name=op.f("fk_radar_runs_search_id_radar_searches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radar_runs")),
    )
    op.create_index(
        "ix_radar_runs_org_id_started_at", "radar_runs", ["org_id", "started_at"]
    )


def downgrade() -> None:
    op.drop_table("radar_runs")
    op.drop_table("radar_results")
    op.drop_table("radar_searches")
