"""Add drum characteristics and measurement points.

Revision ID: e7a31c9d0f49
Revises: e7a31c9d0f48
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f49"
down_revision = "e7a31c9d0f48"
branch_labels = depends_on = None


def upgrade():
    # 1. Drum mechanical & measurement characteristics
    op.add_column("drums", sa.Column("measurement_mode", sa.String(32), server_default="center_only", nullable=False))
    op.add_column("drums", sa.Column("has_moisture_imbalance", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("drums", sa.Column("has_blade_issue", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("drums", sa.Column("characteristics_notes", sa.String(500), nullable=True))

    # 2. Periodic log multi-point measurement
    op.add_column("drum_periodic_logs", sa.Column("moisture_head_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_periodic_logs", sa.Column("moisture_center_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_periodic_logs", sa.Column("moisture_tail_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_periodic_logs", sa.Column("moisture_diff_ends", sa.Numeric(5, 2), nullable=True))

    # 3. Inspection multi-point measurement
    op.add_column("drum_inspections", sa.Column("sample_moisture_head_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_inspections", sa.Column("sample_moisture_center_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_inspections", sa.Column("sample_moisture_tail_percent", sa.Numeric(5, 2), nullable=True))

    # 4. Discharge multi-point measurement
    op.add_column("drum_runs", sa.Column("final_moisture_head_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_runs", sa.Column("final_moisture_tail_percent", sa.Numeric(5, 2), nullable=True))


def downgrade():
    op.drop_column("drum_runs", "final_moisture_tail_percent")
    op.drop_column("drum_runs", "final_moisture_head_percent")

    op.drop_column("drum_inspections", "sample_moisture_tail_percent")
    op.drop_column("drum_inspections", "sample_moisture_center_percent")
    op.drop_column("drum_inspections", "sample_moisture_head_percent")

    op.drop_column("drum_periodic_logs", "moisture_diff_ends")
    op.drop_column("drum_periodic_logs", "moisture_tail_percent")
    op.drop_column("drum_periodic_logs", "moisture_center_percent")
    op.drop_column("drum_periodic_logs", "moisture_head_percent")

    op.drop_column("drums", "characteristics_notes")
    op.drop_column("drums", "has_blade_issue")
    op.drop_column("drums", "has_moisture_imbalance")
    op.drop_column("drums", "measurement_mode")
