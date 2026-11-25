from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, utcnow


class WeighEvent(Base):
    __tablename__ = "weigh_events"
    __table_args__ = (UniqueConstraint("trip_id", "sequence", name="uq_weigh_events_trip_sequence"), CheckConstraint("source = 'manual'", name="ck_weigh_events_manual_source"), CheckConstraint("status IN ('pending','ready','selected','excluded','cancelled')", name="ck_weigh_events_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), nullable=False, index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    weighed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    reweigh_of_event_id: Mapped[int | None] = mapped_column(ForeignKey("weigh_events.id"))
    vehicle_position_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    people_exited_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledgement_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledgement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WeighResult(Base):
    __tablename__ = "weigh_results"
    __table_args__ = (CheckConstraint("weight_kg >= 0", name="ck_weigh_results_nonnegative_weight"), CheckConstraint("status IN ('pending','selected','excluded','cancelled','replaced')", name="ck_weigh_results_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("weigh_events.id"), nullable=False, index=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    replaces_result_id: Mapped[int | None] = mapped_column(ForeignKey("weigh_results.id"), unique=True)
    edit_reason: Mapped[str | None] = mapped_column(Text)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
