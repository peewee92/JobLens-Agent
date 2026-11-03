"""Persist a versioned Career Agent analysis in its authoritative run."""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0025"
down_revision = "20261025_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("career_agent_runs", sa.Column("analysis_result", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("career_agent_runs") as batch:
        batch.drop_column("analysis_result")
