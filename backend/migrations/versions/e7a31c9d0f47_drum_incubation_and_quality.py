"""Add heat off, rotation off, incubation and quality assessment to drum_runs.

Revision ID: e7a31c9d0f47
Revises: e7a31c9d0f46
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f47"
down_revision = "e7a31c9d0f46"
branch_labels = depends_on = None


def upgrade():
    op.add_column("drum_runs", sa.Column("heat_off_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("drum_runs", sa.Column("rotation_off_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("drum_runs", sa.Column("moisture_at_heat_off", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_runs", sa.Column("incubation_minutes", sa.Integer(), nullable=True))
    op.add_column("drum_runs", sa.Column("quality_assessment", sa.String(32), nullable=True))
    op.add_column("drum_runs", sa.Column("quality_note", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("drum_runs", "quality_note")
    op.drop_column("drum_runs", "quality_assessment")
    op.drop_column("drum_runs", "incubation_minutes")
    op.drop_column("drum_runs", "moisture_at_heat_off")
    op.drop_column("drum_runs", "rotation_off_at")
    op.drop_column("drum_runs", "heat_off_at")

