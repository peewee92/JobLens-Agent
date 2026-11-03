"""create evidence proposals

Revision ID: 20260927_0021
Revises: 20260927_0020
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0021"
down_revision = "20260927_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_proposals",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("workspace_id", sa.String(length=100), sa.ForeignKey("application_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.String(length=100), sa.ForeignKey("execution_action_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_requirement_ids", sa.JSON(), nullable=False),
        sa.Column("capability", sa.String(length=200), nullable=False),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("evidence_summary", sa.String(length=2000), nullable=False),
        sa.Column("evidence_source", sa.String(length=1000), nullable=False),
        sa.Column("skill_level", sa.String(length=30), nullable=False),
        sa.Column("source_profile_id", sa.String(length=100), nullable=False),
        sa.Column("source_profile_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_evidence_proposal_actor_idempotency"),
    )
    op.create_index("ix_evidence_proposals_workspace_created", "evidence_proposals", ["workspace_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_evidence_proposals_workspace_created", table_name="evidence_proposals")
    op.drop_table("evidence_proposals")
