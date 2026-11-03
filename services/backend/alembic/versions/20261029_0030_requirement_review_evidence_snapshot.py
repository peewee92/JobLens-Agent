"""Preserve evidence at the time of a formal requirement review decision."""
from alembic import op
import sqlalchemy as sa

revision = "20261029_0030"
down_revision = "20261029_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("requirement_review_batch_final_decisions", sa.Column("evidence_snapshot", sa.JSON(), nullable=True))
    op.add_column("requirement_review_batch_final_decisions", sa.Column("evidence_snapshot_sha256", sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table("requirement_review_batch_final_decisions") as batch:
        batch.drop_column("evidence_snapshot_sha256")
        batch.drop_column("evidence_snapshot")
