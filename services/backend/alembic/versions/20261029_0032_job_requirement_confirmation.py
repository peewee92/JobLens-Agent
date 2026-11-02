"""Persist single-posting user confirmations separately from quality reviews."""
from alembic import op
import sqlalchemy as sa

revision = "20261029_0032"
down_revision = "20261029_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("job_requirement_confirmations",
        sa.Column("action_id", sa.String(100), primary_key=True),
        sa.Column("job_id", sa.String(40), nullable=False),
        sa.Column("extraction_id", sa.String(90), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("facts_digest", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["extraction_id", "job_id"],
            ["job_requirement_extractions.id", "job_requirement_extractions.job_id"]),
    )
    op.create_index("ix_requirement_confirmation_extraction", "job_requirement_confirmations", ["extraction_id"])


def downgrade():
    op.drop_table("job_requirement_confirmations")
