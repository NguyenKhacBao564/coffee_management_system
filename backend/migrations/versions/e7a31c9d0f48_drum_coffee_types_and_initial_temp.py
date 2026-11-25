"""Add initial temperature and blend ratios to drum_runs.

Revision ID: e7a31c9d0f48
Revises: e7a31c9d0f47
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f48"
down_revision = "e7a31c9d0f47"
branch_labels = depends_on = None


def upgrade():
    op.add_column("drum_runs", sa.Column("initial_temperature_celsius", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_runs", sa.Column("blend_ratio_qua_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("drum_runs", sa.Column("blend_ratio_lua_percent", sa.Numeric(5, 2), nullable=True))


def downgrade():
    op.drop_column("drum_runs", "blend_ratio_lua_percent")
    op.drop_column("drum_runs", "blend_ratio_qua_percent")
    op.drop_column("drum_runs", "initial_temperature_celsius")
