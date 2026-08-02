"""create job import candidates

Revision ID: 20260802_0002
Revises: 20260801_0001
Create Date: 2026-08-02
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_0002"
down_revision: str | None = "20260801_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_import_candidates",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("import_id", sa.String(length=40), nullable=False),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("keep", sa.Boolean(), nullable=True),
        sa.Column("decision", sa.String(length=512), nullable=True),
        sa.Column("pending_detail", sa.Boolean(), nullable=True),
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("candidate_raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_index >= 0",
            name="ck_job_import_candidates_index_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["job_imports.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_id",
            "candidate_index",
            name="uq_job_import_candidates_import_candidate_index",
        ),
    )
    op.create_index(
        "ix_job_import_candidates_import_id",
        "job_import_candidates",
        ["import_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_import_candidates_import_keep",
        "job_import_candidates",
        ["import_id", "keep"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_import_candidates_import_keep",
        table_name="job_import_candidates",
    )
    op.drop_index(
        "ix_job_import_candidates_import_id",
        table_name="job_import_candidates",
    )
    op.drop_table("job_import_candidates")
