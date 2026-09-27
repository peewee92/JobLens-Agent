"""add evidence proposal confirmation provenance

Revision ID: 20260927_0022
Revises: 20260927_0021
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0022"
down_revision = "20260927_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_proposals", sa.Column("confirmed_profile_id", sa.String(length=100), nullable=True))
    op.add_column("evidence_proposals", sa.Column("confirmed_profile_version", sa.Integer(), nullable=True))
    op.add_column("evidence_proposals", sa.Column("confirmed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_proposals", "confirmed_at")
    op.drop_column("evidence_proposals", "confirmed_profile_version")
    op.drop_column("evidence_proposals", "confirmed_profile_id")
