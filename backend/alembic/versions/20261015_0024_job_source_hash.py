"""job_postings.source_hash: detect an input the org already added

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL for rows that predate this (they are never reported as repeats) and for provider
    # rows, which already dedupe on (source, external_id).
    op.add_column("job_postings", sa.Column("source_hash", sa.String(length=64)))
    op.create_index(
        "ix_job_postings_org_id_source_hash", "job_postings", ["org_id", "source_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_postings_org_id_source_hash", "job_postings")
    op.drop_column("job_postings", "source_hash")
