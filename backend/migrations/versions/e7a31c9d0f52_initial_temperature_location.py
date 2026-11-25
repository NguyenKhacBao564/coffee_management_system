"""Record the location of the initial temperature."""
from alembic import op
import sqlalchemy as sa
revision = 'e7a31c9d0f52'
down_revision = 'e7a31c9d0f51'
branch_labels = depends_on = None

def upgrade():
    op.add_column('drum_runs', sa.Column('initial_temperature_location', sa.String(120), nullable=True))

def downgrade():
    op.drop_column('drum_runs', 'initial_temperature_location')
