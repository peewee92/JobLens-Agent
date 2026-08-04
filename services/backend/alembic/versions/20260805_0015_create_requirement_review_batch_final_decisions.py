"""create Requirement review batch final decisions

Revision ID: 20260805_0015
Revises: 20260805_0014
Create Date: 2026-08-05
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0015"
down_revision: str | None = "20260805_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_review_batch_final_decisions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("batch_id", sa.String(length=90), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("reviewed_count", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("stale_case_count", sa.Integer(), nullable=False),
        sa.Column("issue_code_counts", sa.JSON(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accept_for_match', 'reject_for_match')",
            name="ck_requirement_review_batch_final_decisions_decision",
        ),
        sa.CheckConstraint(
            "sample_size >= 1 AND reviewed_count >= 0 AND accepted_count >= 0 "
            "AND rejected_count >= 0 AND stale_case_count >= 0",
            name="ck_requirement_review_batch_final_decisions_counts_non_negative",
        ),
        sa.CheckConstraint(
            "reviewed_count = accepted_count + rejected_count",
            name="ck_requirement_review_batch_final_decisions_reviewed_count",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["requirement_review_batches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            name="uq_requirement_review_batch_final_decisions_batch",
        ),
    )
    op.create_index(
        "ix_requirement_review_batch_final_decisions_decision_decided_at",
        "requirement_review_batch_final_decisions",
        ["decision", "decided_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_review_batch_final_decisions_decision_decided_at",
        table_name="requirement_review_batch_final_decisions",
    )
    op.drop_table("requirement_review_batch_final_decisions")
