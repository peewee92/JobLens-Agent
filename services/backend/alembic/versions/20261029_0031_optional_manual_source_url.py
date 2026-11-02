"""Allow pasted postings to have no external source URL."""
from alembic import op
import sqlalchemy as sa

revision = "20261029_0031"
down_revision = "20261029_0030"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("job_sources") as batch:
        batch.alter_column("normalized_source_url", existing_type=sa.String(2048), nullable=True)


def downgrade():
    # Missing source URLs cannot be truthfully converted to external URLs.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM job_sources WHERE normalized_source_url IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade while manually pasted postings without source URLs exist")
    with op.batch_alter_table("job_sources") as batch:
        batch.alter_column("normalized_source_url", existing_type=sa.String(2048), nullable=False)
