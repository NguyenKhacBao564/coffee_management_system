"""Add optional source and measurement metadata for drum runs."""
from alembic import op
import sqlalchemy as sa

revision = 'e7a31c9d0f50'
down_revision = 'e7a31c9d0f49'
branch_labels = depends_on = None


def upgrade():
    for name, typ in [
        ('source_lot_code', sa.String(120)), ('traceability', sa.String(24)),
        ('source_note', sa.String(500)), ('ground_at', sa.DateTime(timezone=True)),
        ('drying_started_at', sa.DateTime(timezone=True)), ('drying_route', sa.String(24)),
        ('times_estimated', sa.Boolean()), ('water_exposure', sa.String(24)),
        ('water_exposure_minutes', sa.Integer()), ('water_exposure_note', sa.String(500)),
    ]:
        op.add_column('drum_runs', sa.Column(name, typ, nullable=True))
    op.add_column('drum_periodic_logs', sa.Column('temperature_location', sa.String(120), nullable=True))


def downgrade():
    op.drop_column('drum_periodic_logs', 'temperature_location')
    for name in ('water_exposure_note', 'water_exposure_minutes', 'water_exposure', 'times_estimated', 'drying_route', 'drying_started_at', 'ground_at', 'source_note', 'traceability', 'source_lot_code'):
        op.drop_column('drum_runs', name)
