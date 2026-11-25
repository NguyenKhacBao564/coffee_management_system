from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, utcnow


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("facility_id", "plate_normalized", name="uq_vehicles_facility_plate"), CheckConstraint("length(plate_normalized) > 0", name="ck_vehicles_normalized_plate"))
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    plate_original: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (CheckConstraint("direction IN ('import','export','mixed')", name="ck_schedules_direction"), CheckConstraint("status IN ('planned','cancelled')", name="ck_schedules_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    expected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    partner: Mapped[str | None] = mapped_column(String(160))
    expected_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScheduleLine(Base):
    __tablename__ = "schedule_lines"
    __table_args__ = (CheckConstraint("expected_weight_kg IS NULL OR expected_weight_kg >= 0", name="ck_schedule_lines_expected_weight"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    goods_name: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (UniqueConstraint("facility_id", "trip_code", name="uq_trips_facility_code"), CheckConstraint("status IN ('open','completed','cancelled')", name="ck_trips_status"), CheckConstraint("departed_at IS NULL OR arrived_at IS NULL OR departed_at >= arrived_at", name="ck_trips_time_order"))
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    trip_code: Mapped[str] = mapped_column(String(48), nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), index=True)
    partner: Mapped[str | None] = mapped_column(String(160))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BusinessAudit(Base):
    __tablename__ = "business_audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
