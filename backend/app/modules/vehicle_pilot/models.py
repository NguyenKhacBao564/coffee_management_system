from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, utcnow


class CameraVisit(Base):
    __tablename__ = "camera_visits"
    __table_args__ = (
        CheckConstraint("source_mode IN ('live','replay')", name="ck_camera_visits_source_mode"),
        CheckConstraint("status IN ('open','departed','interrupted','needs_review','closed')", name="ck_camera_visits_status"),
        Index("ix_camera_visits_facility_created", "facility_id", "created_at"),
        Index("ix_camera_visits_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(12), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(240))
    start_media_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    end_media_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    observed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="needs_review")
    create_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CameraEvidence(Base):
    __tablename__ = "camera_evidence"
    __table_args__ = (
        CheckConstraint("kind IN ('overview','vehicle_crop','plate_crop','painted_text_crop','container_crop','other')", name="ck_camera_evidence_kind"),
        CheckConstraint("storage_state IN ('pending','stored','missing','expired')", name="ck_camera_evidence_storage_state"),
        UniqueConstraint("visit_id", "id", name="uq_camera_evidence_visit_id_id"),
        Index("ix_camera_evidence_facility_received", "facility_id", "received_at_utc"),
        Index("ix_camera_evidence_visit_received", "visit_id", "received_at_utc"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("camera_visits.id", ondelete="CASCADE"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(12), nullable=False)
    media_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    observed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    retention_until_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    storage_state: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    purged_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bbox_json: Mapped[dict | None] = mapped_column(JSON)
    transform_json: Mapped[dict | None] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class VehiclePrediction(Base):
    __tablename__ = "vehicle_predictions"
    __table_args__ = (
        CheckConstraint("source IN ('local','api','mock')", name="ck_vehicle_predictions_source"),
        CheckConstraint("identifier_kind IN ('tractor_plate','trailer_plate','painted_text','container_id','unknown')", name="ck_vehicle_predictions_identifier_kind"),
        Index("ix_vehicle_predictions_visit_created", "visit_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("camera_visits.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[UUID | None] = mapped_column(ForeignKey("camera_evidence.id"))
    source: Mapped[str] = mapped_column(String(12), nullable=False)
    identifier_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(String(160))
    visible_text: Mapped[str | None] = mapped_column(String(160))
    reading_status: Mapped[str] = mapped_column(String(24), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(120))
    score_info: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    raw_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class VisitConfirmation(Base):
    __tablename__ = "camera_visit_confirmations"
    __table_args__ = (UniqueConstraint("visit_id", "version", name="uq_camera_confirmation_visit_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("camera_visits.id", ondelete="CASCADE"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class VehiclePilotAuditEvent(Base):
    __tablename__ = "vehicle_pilot_audit_events"
    __table_args__ = (Index("ix_vehicle_pilot_audit_visit_created", "visit_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("camera_visits.id", ondelete="CASCADE"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class VehicleAIJob(Base):
    __tablename__ = "vehicle_ai_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','claimed','succeeded','needs_review','failed','expired','mock_completed')", name="ck_vehicle_ai_jobs_status"),
        UniqueConstraint("idempotency_key", name="uq_vehicle_ai_jobs_idempotency"),
        Index("ix_vehicle_ai_jobs_queue", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    visit_id: Mapped[UUID] = mapped_column(ForeignKey("camera_visits.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VehicleAIAttempt(Base):
    __tablename__ = "vehicle_ai_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_number", name="uq_vehicle_ai_attempt_job_number"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("vehicle_ai_jobs.id", ondelete="CASCADE"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))


class VehicleAIDailyBudget(Base):
    __tablename__ = "vehicle_ai_daily_budgets"

    budget_date: Mapped[date] = mapped_column(Date, primary_key=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    actual_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CameraRuntime(Base):
    """Latest worker snapshot, separate from visits and scale heartbeats."""
    __tablename__ = "camera_runtime"
    camera_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CameraDiagnostic(Base):
    __tablename__ = "camera_diagnostics"
    __table_args__ = (Index("ix_camera_diagnostic_camera_created", "camera_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("camera_runtime.camera_id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(240))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
