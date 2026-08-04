"""create Requirement acceptance execution leases

Revision ID: 20260805_0014
Revises: 20260804_0013
Create Date: 2026-08-05
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0014"
down_revision: str | None = "20260804_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_acceptance_execution_leases",
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("lease_token", sa.String(length=100), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "expires_at > acquired_at",
            name="ck_requirement_acceptance_execution_leases_expiry",
        ),
        sa.PrimaryKeyConstraint("identity_key"),
    )
    op.create_index(
        "ix_requirement_acceptance_execution_leases_expires_at",
        "requirement_acceptance_execution_leases",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_acceptance_execution_leases_expires_at",
        table_name="requirement_acceptance_execution_leases",
    )
    op.drop_table("requirement_acceptance_execution_leases")
