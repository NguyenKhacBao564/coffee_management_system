"""Camera live snapshot and bounded diagnostics.

Revision ID: e7a31c9d0f45
Revises: e7a31c9d0f44
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f45"
down_revision = "e7a31c9d0f44"
branch_labels = depends_on = None

def upgrade():
    op.create_table("camera_runtime",
        sa.Column("camera_id", sa.String(64), primary_key=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("owner", sa.String(120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False))
    op.create_index("ix_camera_runtime_facility_id", "camera_runtime", ["facility_id"])
    op.create_table("camera_diagnostics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("camera_id", sa.String(64), sa.ForeignKey("camera_runtime.camera_id"), nullable=False),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_key", sa.String(240)),
        sa.Column("size_bytes", sa.BigInteger()), sa.Column("sha256", sa.String(64)),
        sa.Column("metadata_json", sa.JSON(), nullable=False))
    op.create_index("ix_camera_diagnostic_camera_created", "camera_diagnostics", ["camera_id", "created_at"])

def downgrade():
    op.drop_table("camera_diagnostics")
    op.drop_table("camera_runtime")
