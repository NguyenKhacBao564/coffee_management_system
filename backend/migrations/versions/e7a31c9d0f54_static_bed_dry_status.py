"""Add dry_status to static_bed_batches.

Revision ID: e7a31c9d0f54
Revises: e7a31c9d0f53
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f54"
down_revision = "e7a31c9d0f53"
branch_labels = depends_on = None


def upgrade():
    op.add_column("static_bed_batches", sa.Column("dry_status", sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column("static_bed_batches", "dry_status")
