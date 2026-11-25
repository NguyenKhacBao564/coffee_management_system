"""Upgrade the existing per-agent heartbeat snapshot to contract v1."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7a31c9d0f44"
down_revision = "e7a31c9d0f43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scale_agent_heartbeats",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("scale_agent_heartbeats", sa.Column("heartbeat_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("heartbeat_sequence", sa.BigInteger(), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("payload_sha256", sa.String(64), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("agent_version", sa.String(80), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("process_uptime_seconds", sa.BigInteger(), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("vendor_process_running", sa.Boolean(), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("reader_status", sa.String(16), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("last_successful_read_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("pending_event_count", sa.Integer(), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("last_signal_ack_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scale_agent_heartbeats", sa.Column("last_error_code", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_scale_agent_heartbeats_schema_version",
        "scale_agent_heartbeats",
        "schema_version IN (0, 1)",
    )
    op.create_check_constraint(
        "ck_scale_agent_heartbeats_heartbeat_sequence_positive",
        "scale_agent_heartbeats",
        "heartbeat_sequence IS NULL OR heartbeat_sequence > 0",
    )
    op.create_check_constraint(
        "ck_scale_agent_heartbeats_reader_status",
        "scale_agent_heartbeats",
        "reader_status IS NULL OR reader_status IN ('starting','ok','empty','error','unavailable')",
    )
    op.create_check_constraint(
        "ck_scale_agent_heartbeats_uptime_nonnegative",
        "scale_agent_heartbeats",
        "process_uptime_seconds IS NULL OR process_uptime_seconds >= 0",
    )
    op.create_check_constraint(
        "ck_scale_agent_heartbeats_pending_events_nonnegative",
        "scale_agent_heartbeats",
        "pending_event_count IS NULL OR pending_event_count >= 0",
    )
    op.create_check_constraint(
        "ck_scale_agent_heartbeats_v1_payload_complete",
        "scale_agent_heartbeats",
        "schema_version = 0 OR (heartbeat_id IS NOT NULL AND heartbeat_sequence IS NOT NULL AND payload_sha256 IS NOT NULL AND reader_status IS NOT NULL AND pending_event_count IS NOT NULL)",
    )
    op.alter_column("scale_agent_heartbeats", "schema_version", server_default=None)


def downgrade() -> None:
    for name in (
        "ck_scale_agent_heartbeats_v1_payload_complete",
        "ck_scale_agent_heartbeats_pending_events_nonnegative",
        "ck_scale_agent_heartbeats_uptime_nonnegative",
        "ck_scale_agent_heartbeats_reader_status",
        "ck_scale_agent_heartbeats_heartbeat_sequence_positive",
        "ck_scale_agent_heartbeats_schema_version",
    ):
        op.drop_constraint(name, "scale_agent_heartbeats", type_="check")
    for name in (
        "last_error_code",
        "last_signal_ack_at_utc",
        "pending_event_count",
        "last_successful_read_at_utc",
        "reader_status",
        "vendor_process_running",
        "process_uptime_seconds",
        "agent_version",
        "payload_sha256",
        "heartbeat_sequence",
        "heartbeat_id",
        "schema_version",
    ):
        op.drop_column("scale_agent_heartbeats", name)
