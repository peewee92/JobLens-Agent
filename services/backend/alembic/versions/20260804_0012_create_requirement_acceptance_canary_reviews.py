"""create immutable Requirement acceptance Canary reviews

Revision ID: 20260804_0012
Revises: 20260804_0011
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0012"
down_revision: str | None = "20260804_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_acceptance_canary_reviews",
        sa.Column("id", sa.String(length=110), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_case_ids", sa.JSON(), nullable=False),
        sa.Column("reviewed_extraction_ids", sa.JSON(), nullable=False),
        sa.Column("reviewed_trace_run_ids", sa.JSON(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('continue', 'stop')",
            name="ck_requirement_acceptance_canary_reviews_decision",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["requirement_acceptance_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            name="uq_requirement_acceptance_canary_reviews_run_id",
        ),
    )
    op.create_index(
        "ix_requirement_acceptance_canary_reviews_reviewed_at",
        "requirement_acceptance_canary_reviews",
        ["reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_acceptance_canary_reviews_reviewed_at",
        table_name="requirement_acceptance_canary_reviews",
    )
    op.drop_table("requirement_acceptance_canary_reviews")
