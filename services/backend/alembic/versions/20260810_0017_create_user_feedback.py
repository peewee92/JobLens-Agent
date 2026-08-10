"""create immutable user feedback

Revision ID: 20260810_0017
Revises: 20260810_0016
Create Date: 2026-08-10
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0017"
down_revision: str | None = "20260810_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("match_report_id", sa.String(length=100), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["match_report_id"], ["match_reports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_feedback_match_report_created_at",
        "user_feedback",
        ["match_report_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_feedback_job_created_at",
        "user_feedback",
        ["job_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_feedback_job_created_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_match_report_created_at", table_name="user_feedback")
    op.drop_table("user_feedback")
