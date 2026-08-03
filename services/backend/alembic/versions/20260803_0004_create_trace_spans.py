"""create trace spans

Revision ID: 20260803_0004
Revises: 20260803_0003
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0004"
down_revision: str | None = "20260803_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trace_spans",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("capability", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name="ck_trace_spans_latency_non_negative",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_trace_spans_input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_trace_spans_output_tokens_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trace_spans_created_at",
        "trace_spans",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_trace_spans_capability_created_at",
        "trace_spans",
        ["capability", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trace_spans_capability_created_at", table_name="trace_spans")
    op.drop_index("ix_trace_spans_created_at", table_name="trace_spans")
    op.drop_table("trace_spans")
