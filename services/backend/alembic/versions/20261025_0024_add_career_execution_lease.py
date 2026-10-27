"""Short execution leases for primary Career Agent runs."""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0024"
down_revision = "20261025_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("career_agent_runs", sa.Column("lease_token", sa.String(64), nullable=True))
    op.add_column("career_agent_runs", sa.Column("lease_expires_at", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("career_agent_runs") as batch:
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_token")
