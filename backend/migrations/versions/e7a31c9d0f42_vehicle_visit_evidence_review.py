"""Vehicle pilot persistence, private evidence metadata, AI job ledger and scale heartbeat."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e7a31c9d0f42"
down_revision: Union[str, None] = "d31a9c72b045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "camera_visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.String(64), nullable=False),
        sa.Column("source_mode", sa.String(12), nullable=False),
        sa.Column("source_ref", sa.String(240)),
        sa.Column("start_media_seconds", sa.Numeric(12, 3)),
        sa.Column("end_media_seconds", sa.Numeric(12, 3)),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True)),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("create_fingerprint", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_mode IN ('live','replay')", name="ck_camera_visits_source_mode"),
        sa.CheckConstraint("status IN ('open','departed','interrupted','needs_review','closed')", name="ck_camera_visits_status"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_camera_visits_facility_created", "camera_visits", ["facility_id", "created_at"])
    op.create_index("ix_camera_visits_status_created", "camera_visits", ["status", "created_at"])

    op.create_table(
        "camera_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source_mode", sa.String(12), nullable=False),
        sa.Column("media_seconds", sa.Numeric(12, 3)),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True)),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(240), nullable=False),
        sa.Column("storage_state", sa.String(12), nullable=False),
        sa.Column("bbox_json", sa.JSON()),
        sa.Column("transform_json", sa.JSON()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("kind IN ('overview','vehicle_crop','plate_crop','painted_text_crop','container_crop','other')", name="ck_camera_evidence_kind"),
        sa.CheckConstraint("storage_state IN ('pending','stored','missing')", name="ck_camera_evidence_storage_state"),
        sa.ForeignKeyConstraint(["visit_id"], ["camera_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("visit_id", "id", name="uq_camera_evidence_visit_id_id"),
    )
    op.create_index("ix_camera_evidence_facility_received", "camera_evidence", ["facility_id", "received_at_utc"])
    op.create_index("ix_camera_evidence_visit_received", "camera_evidence", ["visit_id", "received_at_utc"])

    op.create_table(
        "vehicle_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("identifier_kind", sa.String(24), nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("normalized_text", sa.String(160)),
        sa.Column("visible_text", sa.String(160)),
        sa.Column("reading_status", sa.String(24), nullable=False),
        sa.Column("model_version", sa.String(120)),
        sa.Column("prompt_version", sa.String(120)),
        sa.Column("score_info", sa.JSON(), nullable=False),
        sa.Column("raw_result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('local','api','mock')", name="ck_vehicle_predictions_source"),
        sa.CheckConstraint("identifier_kind IN ('tractor_plate','trailer_plate','painted_text','container_id','unknown')", name="ck_vehicle_predictions_identifier_kind"),
        sa.ForeignKeyConstraint(["visit_id"], ["camera_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["camera_evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_predictions_visit_created", "vehicle_predictions", ["visit_id", "created_at"])

    op.create_table(
        "camera_visit_confirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["visit_id"], ["camera_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visit_id", "version", name="uq_camera_confirmation_visit_version"),
    )

    op.create_table(
        "vehicle_pilot_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer()),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["visit_id"], ["camera_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_pilot_audit_visit_created", "vehicle_pilot_audit_events", ["visit_id", "created_at"])

    op.create_table(
        "vehicle_ai_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(120)),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(120)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("reserved_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("actual_usd", sa.Numeric(12, 6)),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued','claimed','succeeded','needs_review','failed','expired','mock_completed')", name="ck_vehicle_ai_jobs_status"),
        sa.ForeignKeyConstraint(["visit_id"], ["camera_visits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_vehicle_ai_jobs_idempotency"),
    )
    op.create_index("ix_vehicle_ai_jobs_queue", "vehicle_ai_jobs", ["status", "created_at"])

    op.create_table(
        "vehicle_ai_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("reserved_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("actual_usd", sa.Numeric(12, 6)),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.ForeignKeyConstraint(["job_id"], ["vehicle_ai_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_vehicle_ai_attempt_job_number"),
    )

    op.create_table(
        "vehicle_ai_daily_budgets",
        sa.Column("budget_date", sa.Date(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("actual_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("budget_date"),
    )

    op.create_table(
        "scale_agent_heartbeats",
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("source_status", sa.String(12), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger()),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_status IN ('reading','idle','error','unknown')", name="ck_scale_agent_heartbeats_source_status"),
        sa.CheckConstraint("pending_count >= 0", name="ck_scale_agent_heartbeats_pending_nonnegative"),
        sa.CheckConstraint("last_sequence IS NULL OR last_sequence >= 0", name="ck_scale_agent_heartbeats_sequence_nonnegative"),
        sa.ForeignKeyConstraint(["agent_id"], ["scale_agents.agent_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.PrimaryKeyConstraint("agent_id"),
    )
    op.create_index("ix_scale_agent_heartbeats_facility_received", "scale_agent_heartbeats", ["facility_id", "received_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_scale_agent_heartbeats_facility_received", table_name="scale_agent_heartbeats")
    op.drop_table("scale_agent_heartbeats")
    op.drop_table("vehicle_ai_daily_budgets")
    op.drop_table("vehicle_ai_attempts")
    op.drop_index("ix_vehicle_ai_jobs_queue", table_name="vehicle_ai_jobs")
    op.drop_table("vehicle_ai_jobs")
    op.drop_index("ix_vehicle_pilot_audit_visit_created", table_name="vehicle_pilot_audit_events")
    op.drop_table("vehicle_pilot_audit_events")
    op.drop_table("camera_visit_confirmations")
    op.drop_index("ix_vehicle_predictions_visit_created", table_name="vehicle_predictions")
    op.drop_table("vehicle_predictions")
    op.drop_index("ix_camera_evidence_visit_received", table_name="camera_evidence")
    op.drop_index("ix_camera_evidence_facility_received", table_name="camera_evidence")
    op.drop_table("camera_evidence")
    op.drop_index("ix_camera_visits_status_created", table_name="camera_visits")
    op.drop_index("ix_camera_visits_facility_created", table_name="camera_visits")
    op.drop_table("camera_visits")
