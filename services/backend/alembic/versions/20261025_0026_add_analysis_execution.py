"""Workspace references to saved analysis and atomic start-execution receipts."""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0026"
down_revision = "20261025_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("application_workspaces", sa.Column("current_analysis_thread_id", sa.String(100), nullable=True))
    op.add_column("application_workspaces", sa.Column("current_analysis_result_id", sa.String(100), nullable=True))
    op.add_column("execution_action_items", sa.Column("source_analysis_thread_id", sa.String(100), nullable=True))
    op.add_column("execution_action_items", sa.Column("source_analysis_result_id", sa.String(100), nullable=True))
    op.create_table("analysis_execution_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("command_id", sa.String(120), nullable=False),
        sa.Column("thread_id", sa.String(100), nullable=False),
        sa.Column("command_digest", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("actor_id", "command_id", name="uq_analysis_execution_actor_command"))
    op.create_index("ix_analysis_execution_receipts_thread_id", "analysis_execution_receipts", ["thread_id"])


def downgrade():
    op.drop_table("analysis_execution_receipts")
    with op.batch_alter_table("execution_action_items") as batch:
        batch.drop_column("source_analysis_result_id")
        batch.drop_column("source_analysis_thread_id")
    with op.batch_alter_table("application_workspaces") as batch:
        batch.drop_column("current_analysis_result_id")
        batch.drop_column("current_analysis_thread_id")
