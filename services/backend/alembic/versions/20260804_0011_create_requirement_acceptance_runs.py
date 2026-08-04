"""create controlled Requirement acceptance execution runs

Revision ID: 20260804_0011
Revises: 20260803_0010
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0011"
down_revision: str | None = "20260803_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_acceptance_runs",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=32), nullable=False),
        sa.Column("dataset_generated_at", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("first_import_id", sa.String(length=40), nullable=False),
        sa.Column("last_import_id", sa.String(length=40), nullable=False),
        sa.Column("batch_id", sa.String(length=90), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "total_cases = 20",
            name="ck_requirement_acceptance_runs_formal_sample_size",
        ),
        sa.ForeignKeyConstraint(
            ["first_import_id"],
            ["job_imports.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_import_id"],
            ["job_imports.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["requirement_review_batches.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_fingerprint",
            "title",
            "reviewer",
            "provider",
            "model",
            "extractor_version",
            "prompt_version",
            name="uq_requirement_acceptance_runs_identity",
        ),
    )
    op.create_index(
        "ix_requirement_acceptance_runs_created_at",
        "requirement_acceptance_runs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_acceptance_runs_cohort",
        "requirement_acceptance_runs",
        ["provider", "model", "extractor_version", "prompt_version"],
        unique=False,
    )

    op.create_table(
        "requirement_acceptance_run_cases",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("case_index", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("description_hash", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.String(length=90), nullable=True),
        sa.Column("trace_run_id", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "case_index >= 0 AND case_index < 20",
            name="ck_requirement_acceptance_run_cases_index",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'reused', 'extracted', 'failed', 'deferred')",
            name="ck_requirement_acceptance_run_cases_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_requirement_acceptance_run_cases_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["requirement_acceptance_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["job_requirement_extractions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trace_run_id"],
            ["trace_spans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "case_index",
            name="uq_requirement_acceptance_run_cases_index",
        ),
        sa.UniqueConstraint(
            "run_id",
            "source_url",
            name="uq_requirement_acceptance_run_cases_source_url",
        ),
    )
    op.create_index(
        "ix_requirement_acceptance_run_cases_run_id",
        "requirement_acceptance_run_cases",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_acceptance_run_cases_job_id",
        "requirement_acceptance_run_cases",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_acceptance_run_cases_status",
        "requirement_acceptance_run_cases",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_acceptance_run_cases_status",
        table_name="requirement_acceptance_run_cases",
    )
    op.drop_index(
        "ix_requirement_acceptance_run_cases_job_id",
        table_name="requirement_acceptance_run_cases",
    )
    op.drop_index(
        "ix_requirement_acceptance_run_cases_run_id",
        table_name="requirement_acceptance_run_cases",
    )
    op.drop_table("requirement_acceptance_run_cases")
    op.drop_index(
        "ix_requirement_acceptance_runs_cohort",
        table_name="requirement_acceptance_runs",
    )
    op.drop_index(
        "ix_requirement_acceptance_runs_created_at",
        table_name="requirement_acceptance_runs",
    )
    op.drop_table("requirement_acceptance_runs")
