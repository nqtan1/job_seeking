"""applications and application_events

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = (
    "'to_apply', 'applied', 'in_review', 'interview', 'offer', 'rejected', 'ghosted'"
)


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("job_title", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="to_apply", nullable=False),
        sa.Column("applied_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            f"status IN ({_STATUSES})", name=op.f("ck_applications_status")
        ),
        sa.CheckConstraint(
            "source IN ('linkedin', 'indeed', 'france_travail', 'referral',"
            " 'company_site', 'other')",
            name=op.f("ck_applications_source"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_applications_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_postings.id"],
            name=op.f("fk_applications_job_id_job_postings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    op.create_index(
        "ix_applications_org_id_created_at", "applications", ["org_id", "created_at"]
    )
    op.create_index(
        "ix_applications_org_id_status", "applications", ["org_id", "status"]
    )
    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})",
            name=op.f("ck_application_events_from_status"),
        ),
        sa.CheckConstraint(
            f"to_status IN ({_STATUSES})", name=op.f("ck_application_events_to_status")
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_events_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_application_events_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(
        "ix_application_events_application_id_at",
        "application_events",
        ["application_id", "at"],
    )
    op.create_index(
        "ix_application_events_org_id_at", "application_events", ["org_id", "at"]
    )


def downgrade() -> None:
    op.drop_table("application_events")
    op.drop_table("applications")
