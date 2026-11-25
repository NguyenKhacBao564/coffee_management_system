"""Add explicit pilot evidence expiry metadata and state."""

from alembic import op
import sqlalchemy as sa


revision = "e7a31c9d0f43"
down_revision = "e7a31c9d0f42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("camera_evidence", sa.Column("retention_until_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("camera_evidence", sa.Column("purged_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE camera_evidence SET retention_until_utc = received_at_utc + INTERVAL '30 days'")
    op.alter_column("camera_evidence", "retention_until_utc", nullable=False)
    op.drop_constraint("ck_camera_evidence_storage_state", "camera_evidence", type_="check")
    op.create_check_constraint(
        "ck_camera_evidence_storage_state",
        "camera_evidence",
        "storage_state IN ('pending','stored','missing','expired')",
    )
    op.create_index("ix_camera_evidence_retention", "camera_evidence", ["storage_state", "retention_until_utc"])


def downgrade() -> None:
    op.drop_index("ix_camera_evidence_retention", table_name="camera_evidence")
    op.drop_constraint("ck_camera_evidence_storage_state", "camera_evidence", type_="check")
    op.create_check_constraint(
        "ck_camera_evidence_storage_state",
        "camera_evidence",
        "storage_state IN ('pending','stored','missing')",
    )
    op.drop_column("camera_evidence", "retention_until_utc")
    op.drop_column("camera_evidence", "purged_at_utc")
