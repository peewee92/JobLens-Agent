"""create grounded resume variants

Revision ID: 20260927_0019
Revises: 20260927_0018
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0019"
down_revision = "20260927_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_variants",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("workspace_id", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_profile_id", sa.String(length=100), nullable=False),
        sa.Column("source_profile_version", sa.Integer(), nullable=False),
        sa.Column("requirement_extraction_id", sa.String(length=100), nullable=False),
        sa.Column("highlights", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["application_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_resume_variant_actor_idempotency"),
    )
    op.create_index("ix_resume_variants_workspace_created", "resume_variants", ["workspace_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_resume_variants_workspace_created", table_name="resume_variants")
    op.drop_table("resume_variants")
