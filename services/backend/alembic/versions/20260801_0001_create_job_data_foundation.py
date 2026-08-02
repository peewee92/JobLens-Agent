"""create job data foundation

Revision ID: 20260801_0001
Revises:
Create Date: 2026-08-01
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260801_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


remote_status_enum = sa.Enum(
    "confirmed",
    "rejected",
    "unknown",
    name="remote_status_enum",
    native_enum=False,
    create_constraint=True,
)
remote_confidence_enum = sa.Enum(
    "high",
    "medium",
    "low",
    name="remote_confidence_enum",
    native_enum=False,
    create_constraint=True,
)
import_outcome_enum = sa.Enum(
    "created",
    "updated",
    "skipped",
    "error",
    name="import_outcome_enum",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("canonical_key", sa.String(length=512), nullable=False),
        sa.Column(
            "canonical_key_version",
            sa.String(length=20),
            server_default="v1",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("area", sa.String(length=255), nullable=True),
        sa.Column("salary_min_k", sa.Float(), nullable=True),
        sa.Column("salary_max_k", sa.Float(), nullable=True),
        sa.Column("experience", sa.String(length=100), nullable=True),
        sa.Column("education", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column(
            "remote_status",
            remote_status_enum,
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "remote_confidence",
            remote_confidence_enum,
            server_default="low",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "salary_min_k IS NULL OR salary_min_k >= 0",
            name="ck_jobs_salary_min_non_negative",
        ),
        sa.CheckConstraint(
            "salary_max_k IS NULL OR salary_max_k >= 0",
            name="ck_jobs_salary_max_non_negative",
        ),
        sa.CheckConstraint(
            "salary_min_k IS NULL OR salary_max_k IS NULL OR salary_max_k >= salary_min_k",
            name="ck_jobs_salary_range",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_key", name="uq_jobs_canonical_key"),
    )
    op.create_index("ix_jobs_area", "jobs", ["area"], unique=False)
    op.create_index(
        "ix_jobs_salary_min_k", "jobs", ["salary_min_k"], unique=False
    )
    op.create_index(
        "ix_jobs_remote_status", "jobs", ["remote_status"], unique=False
    )

    op.create_table(
        "job_imports",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("collector_version", sa.String(length=100), nullable=True),
        sa.Column("received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("search_intent_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "received >= 0", name="ck_job_imports_received_non_negative"
        ),
        sa.CheckConstraint(
            "created >= 0", name="ck_job_imports_created_non_negative"
        ),
        sa.CheckConstraint(
            "updated >= 0", name="ck_job_imports_updated_non_negative"
        ),
        sa.CheckConstraint(
            "skipped >= 0", name="ck_job_imports_skipped_non_negative"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_sources",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=True),
        sa.Column("source_raw", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "normalized_source_url",
            name="uq_job_sources_source_normalized_url",
        ),
    )
    op.create_index(
        "ix_job_sources_job_id", "job_sources", ["job_id"], unique=False
    )
    op.create_index(
        "ix_job_sources_source_source_job_id",
        "job_sources",
        ["source", "source_job_id"],
        unique=False,
    )

    op.create_table(
        "job_import_items",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("import_id", sa.String(length=40), nullable=False),
        sa.Column("input_index", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=True),
        sa.Column("job_source_id", sa.String(length=40), nullable=True),
        sa.Column("outcome", import_outcome_enum, nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_index >= 0",
            name="ck_job_import_items_input_index_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["job_imports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["job_source_id"], ["job_sources.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_id",
            "input_index",
            name="uq_job_import_items_import_input_index",
        ),
    )
    op.create_index(
        "ix_job_import_items_import_id",
        "job_import_items",
        ["import_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_import_items_job_id",
        "job_import_items",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_import_items_job_id", table_name="job_import_items")
    op.drop_index("ix_job_import_items_import_id", table_name="job_import_items")
    op.drop_table("job_import_items")

    op.drop_index(
        "ix_job_sources_source_source_job_id", table_name="job_sources"
    )
    op.drop_index("ix_job_sources_job_id", table_name="job_sources")
    op.drop_table("job_sources")

    op.drop_table("job_imports")

    op.drop_index("ix_jobs_remote_status", table_name="jobs")
    op.drop_index("ix_jobs_salary_min_k", table_name="jobs")
    op.drop_index("ix_jobs_area", table_name="jobs")
    op.drop_table("jobs")
