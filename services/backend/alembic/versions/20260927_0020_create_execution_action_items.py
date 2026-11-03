"""create execution action items

Revision ID: 20260927_0020
Revises: 20260927_0019
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0020"
down_revision = "20260927_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_action_items",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("workspace_id", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_requirement_ids", sa.JSON(), nullable=False),
        sa.Column("source_gap_capability", sa.String(length=200), nullable=True),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("completion_criteria", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["application_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_execution_action_actor_idempotency"),
    )
    op.create_index("ix_execution_actions_workspace_created", "execution_action_items", ["workspace_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_actions_workspace_created", table_name="execution_action_items")
    op.drop_table("execution_action_items")
