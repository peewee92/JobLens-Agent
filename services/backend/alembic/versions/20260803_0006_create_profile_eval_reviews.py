"""create profile evaluation reviews

Revision ID: 20260803_0006
Revises: 20260803_0005
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0006"
down_revision: str | None = "20260803_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_eval_reviews",
        sa.Column("id", sa.String(length=90), nullable=False),
        sa.Column("eval_run_id", sa.String(length=80), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted', 'rejected')",
            name="ck_profile_eval_reviews_decision",
        ),
        sa.ForeignKeyConstraint(
            ["eval_run_id"],
            ["profile_eval_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "eval_run_id",
            name="uq_profile_eval_reviews_eval_run_id",
        ),
    )
    op.create_index(
        "ix_profile_eval_reviews_decision_reviewed_at",
        "profile_eval_reviews",
        ["decision", "reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_profile_eval_reviews_decision_reviewed_at",
        table_name="profile_eval_reviews",
    )
    op.drop_table("profile_eval_reviews")
