"""Separate immutable action provenance from an explicitly reviewed confirmation base."""
from alembic import op
import sqlalchemy as sa

revision = '20261025_0027'
down_revision = '20261025_0026'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('source_analysis_thread_id', 'source_analysis_result_id', 'source_requirement_extraction_id',
                 'confirmation_base_profile_id', 'origin_proposal_id'):
        op.add_column('evidence_proposals', sa.Column(name, sa.String(100), nullable=True))
    op.add_column('evidence_proposals', sa.Column('confirmation_base_profile_version', sa.Integer(), nullable=True))
    op.add_column('evidence_proposals', sa.Column('command_digest', sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table('evidence_proposals') as batch:
        for name in ('command_digest', 'confirmation_base_profile_version', 'origin_proposal_id', 'confirmation_base_profile_id',
                     'source_requirement_extraction_id', 'source_analysis_result_id', 'source_analysis_thread_id'):
            batch.drop_column(name)
