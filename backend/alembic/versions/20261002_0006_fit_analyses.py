"""fit_analyses

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fit_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("company_type", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 100", name=op.f("ck_fit_analyses_score")
        ),
        sa.CheckConstraint(
            "verdict IN ('go', 'maybe', 'no_go')", name=op.f("ck_fit_analyses_verdict")
        ),
        sa.CheckConstraint(
            "company_type IN ('corporate', 'startup', 'phd')",
            name=op.f("ck_fit_analyses_company_type"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_fit_analyses_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_postings.id"],
            name=op.f("fk_fit_analyses_job_id_job_postings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_fit_analyses_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fit_analyses")),
    )
    op.create_index(
        "ix_fit_analyses_org_id_created_at", "fit_analyses", ["org_id", "created_at"]
    )
    op.create_index(
        "ix_fit_analyses_org_id_job_id", "fit_analyses", ["org_id", "job_id"]
    )


def downgrade() -> None:
    op.drop_table("fit_analyses")
