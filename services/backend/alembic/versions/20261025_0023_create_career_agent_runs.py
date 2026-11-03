"""Primary-database Career Agent runs and append-only transitions.

Revision ID: 20261025_0023
Revises: 20260927_0022
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0023"
down_revision = "20260927_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("career_agent_runs",
        sa.Column("thread_id", sa.String(100), primary_key=True),
        sa.Column("run_id", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_index("ix_career_agent_runs_updated_at", "career_agent_runs", ["updated_at"])
    op.create_table("career_agent_run_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.String(100), sa.ForeignKey("career_agent_runs.thread_id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("thread_id", "revision", name="uq_career_agent_event_revision"))


def downgrade():
    op.drop_table("career_agent_run_events")
    op.drop_index("ix_career_agent_runs_updated_at", table_name="career_agent_runs")
    op.drop_table("career_agent_runs")
