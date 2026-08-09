"""create immutable match reports

Revision ID: 20260810_0016
Revises: 20260805_0015
Create Date: 2026-08-10
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0016"
down_revision: str | None = "20260805_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_reports",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.String(length=100), nullable=False),
        sa.Column("eligibility", sa.String(length=20), nullable=False),
        sa.Column("recommendation", sa.String(length=20), nullable=False),
        sa.Column("matcher_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("trace_run_id", sa.String(length=100), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_reports_job_created_at",
        "match_reports",
        ["job_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_match_reports_trace_run_id",
        "match_reports",
        ["trace_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_match_reports_trace_run_id", table_name="match_reports")
    op.drop_index("ix_match_reports_job_created_at", table_name="match_reports")
    op.drop_table("match_reports")
