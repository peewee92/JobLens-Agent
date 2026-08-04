"""create Requirement manual quality review batches

Revision ID: 20260803_0010
Revises: 20260803_0009
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0010"
down_revision: str | None = "20260803_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_review_batches",
        sa.Column("id", sa.String(length=90), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "sample_size >= 1 AND sample_size <= 20",
            name="ck_requirement_review_batches_sample_size",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_requirement_review_batches_created_at",
        "requirement_review_batches",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_review_batches_cohort",
        "requirement_review_batches",
        ["provider", "model", "extractor_version", "prompt_version"],
        unique=False,
    )

    op.create_table(
        "requirement_review_batch_cases",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("batch_id", sa.String(length=90), nullable=False),
        sa.Column("case_index", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("extraction_id", sa.String(length=90), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "case_index >= 0",
            name="ck_requirement_review_cases_index_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["requirement_review_batches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id", "job_id"],
            ["job_requirement_extractions.id", "job_requirement_extractions.job_id"],
            name="fk_requirement_review_cases_extraction_job",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "case_index",
            name="uq_requirement_review_cases_batch_index",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "extraction_id",
            name="uq_requirement_review_cases_batch_extraction",
        ),
    )
    op.create_index(
        "ix_requirement_review_cases_batch_id",
        "requirement_review_batch_cases",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_review_cases_job_id",
        "requirement_review_batch_cases",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_review_cases_extraction_id",
        "requirement_review_batch_cases",
        ["extraction_id"],
        unique=False,
    )

    op.create_table(
        "requirement_review_case_reviews",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("batch_case_id", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("issue_codes", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted', 'rejected')",
            name="ck_requirement_review_case_reviews_decision",
        ),
        sa.ForeignKeyConstraint(
            ["batch_case_id"],
            ["requirement_review_batch_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_case_id",
            name="uq_requirement_review_case_reviews_case",
        ),
    )
    op.create_index(
        "ix_requirement_review_case_reviews_decision_reviewed_at",
        "requirement_review_case_reviews",
        ["decision", "reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_review_case_reviews_decision_reviewed_at",
        table_name="requirement_review_case_reviews",
    )
    op.drop_table("requirement_review_case_reviews")
    op.drop_index(
        "ix_requirement_review_cases_extraction_id",
        table_name="requirement_review_batch_cases",
    )
    op.drop_index(
        "ix_requirement_review_cases_job_id",
        table_name="requirement_review_batch_cases",
    )
    op.drop_index(
        "ix_requirement_review_cases_batch_id",
        table_name="requirement_review_batch_cases",
    )
    op.drop_table("requirement_review_batch_cases")
    op.drop_index(
        "ix_requirement_review_batches_cohort",
        table_name="requirement_review_batches",
    )
    op.drop_index(
        "ix_requirement_review_batches_created_at",
        table_name="requirement_review_batches",
    )
    op.drop_table("requirement_review_batches")
