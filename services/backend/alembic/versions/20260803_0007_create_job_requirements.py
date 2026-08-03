"""create immutable Job Requirement Extraction Runs

Revision ID: 20260803_0007
Revises: 20260803_0006
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0007"
down_revision: str | None = "20260803_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_requirement_extractions",
        sa.Column("id", sa.String(length=90), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("description_characters", sa.Integer(), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("trace_run_id", sa.String(length=80), nullable=False),
        sa.Column("requirement_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "description_characters >= 0",
            name="ck_job_requirement_extractions_description_chars_non_negative",
        ),
        sa.CheckConstraint(
            "requirement_count >= 1",
            name="ck_job_requirement_extractions_count_positive",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["trace_run_id"],
            ["trace_spans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "job_id",
            name="uq_job_requirement_extractions_id_job",
        ),
    )
    op.create_index(
        "ix_job_requirement_extractions_job_created",
        "job_requirement_extractions",
        ["job_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "job_requirements",
        sa.Column("id", sa.String(length=90), nullable=False),
        sa.Column("extraction_id", sa.String(length=90), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("requirement_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("normalized_capability", sa.String(length=255), nullable=True),
        sa.Column("importance", sa.String(length=20), nullable=False),
        sa.Column("evidence_span", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "requirement_index >= 0",
            name="ck_job_requirements_index_non_negative",
        ),
        sa.CheckConstraint(
            "type IN ('skill', 'experience', 'education', 'responsibility', 'domain', 'constraint')",
            name="ck_job_requirements_type",
        ),
        sa.CheckConstraint(
            "importance IN ('must_have', 'preferred', 'bonus')",
            name="ck_job_requirements_importance",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_job_requirements_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id", "job_id"],
            ["job_requirement_extractions.id", "job_requirement_extractions.job_id"],
            ondelete="CASCADE",
            name="fk_job_requirements_extraction_job",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_id",
            "requirement_index",
            name="uq_job_requirements_extraction_index",
        ),
    )
    op.create_index(
        "ix_job_requirements_job_id",
        "job_requirements",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_requirements_capability",
        "job_requirements",
        ["normalized_capability"],
        unique=False,
    )
    op.create_index(
        "ix_job_requirements_importance",
        "job_requirements",
        ["importance"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_requirements_importance", table_name="job_requirements")
    op.drop_index("ix_job_requirements_capability", table_name="job_requirements")
    op.drop_index("ix_job_requirements_job_id", table_name="job_requirements")
    op.drop_table("job_requirements")
    op.drop_index(
        "ix_job_requirement_extractions_job_created",
        table_name="job_requirement_extractions",
    )
    op.drop_table("job_requirement_extractions")
