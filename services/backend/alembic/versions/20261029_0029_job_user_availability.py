"""Store an explicit user flag, not an inferred external job status."""
from alembic import op
import sqlalchemy as sa

revision = "20261029_0029"
down_revision = "20261028_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("user_marked_inactive", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("jobs", sa.Column("availability_revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("availability_revision")
        batch.drop_column("user_marked_inactive")
