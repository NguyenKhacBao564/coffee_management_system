from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, utcnow


class ScaleAgent(Base):
    __tablename__ = "scale_agents"
    __table_args__ = (
        UniqueConstraint("facility_id", "scale_code", name="uq_scale_agents_facility_code"),
        UniqueConstraint("token_hash", name="uq_scale_agents_token_hash"),
        CheckConstraint("length(display_name) > 0", name="ck_scale_agents_display_name"),
        CheckConstraint("length(scale_code) > 0", name="ck_scale_agents_scale_code"),
    )

    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    scale_code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ScaleSignal(Base):
    __tablename__ = "scale_signals"
    __table_args__ = (
        UniqueConstraint("agent_id", "event_id", name="uq_scale_signals_agent_event"),
        UniqueConstraint("agent_id", "sequence", name="uq_scale_signals_agent_sequence"),
        CheckConstraint("sequence > 0", name="ck_scale_signals_positive_sequence"),
        CheckConstraint("weight_kg >= 1000", name="ck_scale_signals_minimum_weight"),
        CheckConstraint("source = 'canxe2015_ui'", name="ck_scale_signals_source"),
        CheckConstraint("schema_version = 1", name="ck_scale_signals_schema_version"),
        Index("ix_scale_signals_agent_observed", "agent_id", "observed_at_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("scale_agents.agent_id"), nullable=False)
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    vendor_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)


class ScaleAgentHeartbeat(Base):
    __tablename__ = "scale_agent_heartbeats"
    __table_args__ = (
        CheckConstraint("source_status IN ('reading','idle','error','unknown')", name="ck_scale_agent_heartbeats_source_status"),
        CheckConstraint("pending_count >= 0", name="ck_scale_agent_heartbeats_pending_nonnegative"),
        CheckConstraint("last_sequence IS NULL OR last_sequence >= 0", name="ck_scale_agent_heartbeats_sequence_nonnegative"),
        CheckConstraint("schema_version IN (0, 1)", name="ck_scale_agent_heartbeats_schema_version"),
        CheckConstraint("heartbeat_sequence IS NULL OR heartbeat_sequence > 0", name="ck_scale_agent_heartbeats_heartbeat_sequence_positive"),
        CheckConstraint("reader_status IS NULL OR reader_status IN ('starting','ok','empty','error','unavailable')", name="ck_scale_agent_heartbeats_reader_status"),
        CheckConstraint("process_uptime_seconds IS NULL OR process_uptime_seconds >= 0", name="ck_scale_agent_heartbeats_uptime_nonnegative"),
        CheckConstraint("pending_event_count IS NULL OR pending_event_count >= 0", name="ck_scale_agent_heartbeats_pending_events_nonnegative"),
        CheckConstraint("schema_version = 0 OR (heartbeat_id IS NOT NULL AND heartbeat_sequence IS NOT NULL AND payload_sha256 IS NOT NULL AND reader_status IS NOT NULL AND pending_event_count IS NOT NULL)", name="ck_scale_agent_heartbeats_v1_payload_complete"),
        Index("ix_scale_agent_heartbeats_facility_received", "facility_id", "received_at_utc"),
    )

    agent_id: Mapped[str] = mapped_column(ForeignKey("scale_agents.agent_id", ondelete="CASCADE"), primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    source_status: Mapped[str] = mapped_column(String(12), nullable=False)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_sequence: Mapped[int | None] = mapped_column(BigInteger)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    heartbeat_sequence: Mapped[int | None] = mapped_column(BigInteger)
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    agent_version: Mapped[str | None] = mapped_column(String(80))
    process_uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)
    vendor_process_running: Mapped[bool | None] = mapped_column(Boolean)
    reader_status: Mapped[str | None] = mapped_column(String(16))
    last_successful_read_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_event_count: Mapped[int | None] = mapped_column(Integer)
    last_signal_ack_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
