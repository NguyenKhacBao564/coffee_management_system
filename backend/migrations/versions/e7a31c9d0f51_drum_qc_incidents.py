"""Add incidents and output QC for drum runs."""
from alembic import op
import sqlalchemy as sa
revision = 'e7a31c9d0f51'
down_revision = 'e7a31c9d0f50'
branch_labels = depends_on = None

def upgrade():
    op.create_table('drum_incidents', sa.Column('id', sa.Integer, primary_key=True), sa.Column('run_id', sa.Integer, sa.ForeignKey('drum_runs.id', ondelete='CASCADE'), nullable=False), sa.Column('kind', sa.String(32), nullable=False), sa.Column('started_at', sa.DateTime(timezone=True)), sa.Column('ended_at', sa.DateTime(timezone=True)), sa.Column('note', sa.String(1000)), sa.Column('recorded_by', sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL')), sa.Column('recorded_name', sa.String(120), nullable=False), sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_drum_incidents_run_id', 'drum_incidents', ['run_id'])
    op.create_table('drum_qc', sa.Column('id', sa.Integer, primary_key=True), sa.Column('run_id', sa.Integer, sa.ForeignKey('drum_runs.id', ondelete='CASCADE'), nullable=False, unique=True), sa.Column('sampled_at', sa.DateTime(timezone=True), nullable=False), sa.Column('sample_point', sa.String(200), nullable=False), sa.Column('method', sa.String(16), nullable=False), sa.Column('sample_size', sa.Numeric(14, 3), nullable=False), sa.Column('total_defect', sa.Numeric(14, 3), nullable=False), sa.Column('black_defect', sa.Numeric(14, 3)), sa.Column('burnt_defect', sa.Numeric(14, 3)), sa.Column('recorded_by', sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL')), sa.Column('recorded_name', sa.String(120), nullable=False), sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table('drum_qc')
    op.drop_index('ix_drum_incidents_run_id', table_name='drum_incidents')
    op.drop_table('drum_incidents')
