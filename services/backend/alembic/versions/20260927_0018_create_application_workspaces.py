"""create application workspaces

Revision ID: 20260927_0018
Revises: 20260810_0017
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0018"
down_revision = "20260810_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_workspaces",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("search_intent_id", sa.String(length=100), nullable=False),
        sa.Column("search_intent_version", sa.Integer(), nullable=False),
        sa.Column("requirement_extraction_id", sa.String(length=100), nullable=False),
        sa.Column("match_report_id", sa.String(length=100), nullable=False),
        sa.Column("current_fact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_application_workspace_actor_idempotency"),
    )
    op.create_index(
        "ix_application_workspaces_job_updated",
        "application_workspaces",
        ["job_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "application_timeline_events",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("workspace_id", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["application_workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_application_timeline_actor_idempotency"),
    )
    op.create_index(
        "ix_application_timeline_workspace_created",
        "application_timeline_events",
        ["workspace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_timeline_workspace_created", table_name="application_timeline_events")
    op.drop_table("application_timeline_events")
    op.drop_index("ix_application_workspaces_job_updated", table_name="application_workspaces")
    op.drop_table("application_workspaces")
