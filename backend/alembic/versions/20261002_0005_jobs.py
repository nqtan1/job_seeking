"""job_postings and job_search_cache

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'file', 'france_travail')",
            name=op.f("ck_job_postings_source"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_job_postings_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_postings")),
        sa.UniqueConstraint(
            "org_id",
            "source",
            "external_id",
            name=op.f("uq_job_postings_org_id_source_external_id"),
        ),
    )
    op.create_index(
        "ix_job_postings_org_id_created_at", "job_postings", ["org_id", "created_at"]
    )
    op.create_table(
        "job_search_cache",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_job_search_cache")),
    )
    op.create_index(
        "ix_job_search_cache_expires_at", "job_search_cache", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("job_search_cache")
    op.drop_table("job_postings")
