"""Keep each imported observation without exposing it through public APIs."""
from alembic import op
import sqlalchemy as sa

revision = "20261028_0028"
down_revision = "20261025_0027"
branch_labels = None
depends_on = None


def upgrade():
    # Older observations cannot be reconstructed reliably from the current source.
    op.add_column("job_import_items", sa.Column("source_raw_snapshot", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("job_import_items") as batch:
        batch.drop_column("source_raw_snapshot")
