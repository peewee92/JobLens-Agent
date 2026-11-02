"""Journal explicitly authorized single-posting semantic matching calls."""
from alembic import op
import sqlalchemy as sa

revision = "20261030_0034"
down_revision = "20261030_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("semantic_calls",
        sa.Column("action_id", sa.String(100), primary_key=True),
        sa.Column("job_id", sa.String(40), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("command_digest", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("report_id", sa.String(90)),
        sa.Column("error_code", sa.String(80)),
    )
    op.create_index("ix_semantic_calls_job_id", "semantic_calls", ["job_id"])


def downgrade():
    op.drop_table("semantic_calls")
