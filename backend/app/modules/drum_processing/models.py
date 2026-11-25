from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, utcnow


class Drum(Base):
    __tablename__ = "drums"
    __table_args__ = (
        UniqueConstraint("facility_id", "drum_code", name="uq_drums_facility_code"),
        CheckConstraint("status IN ('idle', 'running', 'maintenance')", name="ck_drums_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    drum_code: Mapped[str] = mapped_column(String(32), nullable=False)
    drum_name: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Phương thức / vị trí đo của trống: 'center_only' (giữa trống), 'two_ends' (2 đầu), 'three_points' (đầu/giữa/đuôi)
    measurement_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="center_only")
    # Đặc tính / Khiếm khuyết cơ khí của trống
    has_moisture_imbalance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_blade_issue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    characteristics_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    runs: Mapped[list["DrumRun"]] = relationship("DrumRun", back_populates="drum", cascade="all, delete-orphan")


class DrumRun(Base):
    __tablename__ = "drum_runs"
    __table_args__ = (
        Index("ix_drum_runs_facility_status", "facility_id", "status"),
        Index("ix_drum_runs_drum_id", "drum_id"),
        CheckConstraint("status IN ('in_progress', 'completed', 'cancelled')", name="ck_drum_runs_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    drum_id: Mapped[int] = mapped_column(Integer, ForeignKey("drums.id", ondelete="RESTRICT"), nullable=False)
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_lot_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    traceability: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ground_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    drying_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    drying_route: Mapped[str | None] = mapped_column(String(24), nullable=True)
    times_estimated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    water_exposure: Mapped[str | None] = mapped_column(String(24), nullable=True)
    water_exposure_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    water_exposure_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    coffee_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    initial_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Nhiệt độ ban đầu khi nạp vào trống
    initial_temperature_celsius: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    initial_temperature_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Tỷ lệ phối trộn (% Cà quả / % Cà lụa) nếu là loại trộn
    blend_ratio_qua_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    blend_ratio_lua_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cycle_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Ngày/giờ vào trống
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Thời điểm tắt nhiệt luồng hơi
    heat_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Thời điểm tắt trống quay
    rotation_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Độ ẩm khi tắt nhiệt
    moisture_at_heat_off: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Thời gian ủ trong trống (phút) trước khi ra trống
    incubation_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Ngày/giờ ra trống (xả cà)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name: Mapped[str] = mapped_column(String(120), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")

    # Đánh giá phẩm chất mẻ cà: 'ca_dep', 'dat_chuan', 'ca_xau'
    quality_assessment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quality_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Kết quả độ ẩm của cà khi đã ra trống (sau khi ủ)
    final_moisture_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    final_moisture_head_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    final_moisture_tail_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    final_discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discharge_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Nguồn cà vào trống
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_bed_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("static_drying_beds.id", ondelete="SET NULL"), nullable=True)
    source_bed_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_bed_batch_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("static_bed_batches.id", ondelete="SET NULL"), nullable=True, index=True)

    drum: Mapped["Drum"] = relationship("Drum", back_populates="runs")
    source_bed: Mapped["StaticDryingBed | None"] = relationship("StaticDryingBed")
    source_bed_batch: Mapped["StaticBedBatch | None"] = relationship("StaticBedBatch", back_populates="drum_runs")
    logs: Mapped[list["DrumPeriodicLog"]] = relationship("DrumPeriodicLog", back_populates="run", cascade="all, delete-orphan", order_by="DrumPeriodicLog.sequence")
    inspections: Mapped[list["DrumInspection"]] = relationship("DrumInspection", back_populates="run", cascade="all, delete-orphan", order_by="DrumInspection.inspected_at.desc()")


class DrumPeriodicLog(Base):
    __tablename__ = "drum_periodic_logs"
    __table_args__ = (
        Index("ix_drum_periodic_logs_run_id", "run_id"),
        CheckConstraint("compliance_status IN ('on_time', 'late', 'anomalous')", name="ck_drum_logs_compliance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("drum_runs.id", ondelete="CASCADE"), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Độ ẩm của cà trong trống (trung bình / hiệu dụng)
    moisture_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    # Chi tiết đo theo vị trí (nếu trống đo 2 đầu hoặc 3 điểm)
    moisture_head_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    moisture_center_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    moisture_tail_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Độ chênh lệch giữa 2 đầu (|đầu - đuôi|)
    moisture_diff_ends: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Nhiệt độ luồng hơi thổi vào trống
    temperature_celsius: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    temperature_location: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Thời điểm đo thực tế và thời điểm máy chủ ghi nhận
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compliance_status: Mapped[str] = mapped_column(String(32), nullable=False, default="on_time")

    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    run: Mapped["DrumRun"] = relationship("DrumRun", back_populates="logs")


class DrumInspection(Base):
    __tablename__ = "drum_inspections"
    __table_args__ = (
        Index("ix_drum_inspections_run_id", "run_id"),
        CheckConstraint("evaluation IN ('passed', 'warning', 'failed')", name="ck_drum_inspections_evaluation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("drum_runs.id", ondelete="CASCADE"), nullable=False)
    inspector_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    inspector_name: Mapped[str] = mapped_column(String(120), nullable=False)

    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    sample_moisture_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sample_moisture_head_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sample_moisture_center_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sample_moisture_tail_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sample_temperature_celsius: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    nearest_log_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("drum_periodic_logs.id", ondelete="SET NULL"), nullable=True)
    moisture_diff: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    temperature_diff: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    evaluation: Mapped[str] = mapped_column(String(32), nullable=False, default="passed")
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    run: Mapped["DrumRun"] = relationship("DrumRun", back_populates="inspections")



class DrumIncident(Base):
    __tablename__ = 'drum_incidents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('drum_runs.id', ondelete='CASCADE'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(1000))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    recorded_name: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DrumQC(Base):
    __tablename__ = 'drum_qc'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('drum_runs.id', ondelete='CASCADE'), nullable=False, unique=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_point: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    sample_size: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    total_defect: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    black_defect: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    burnt_defect: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    recorded_name: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StaticDryingBed(Base):
    __tablename__ = "static_drying_beds"
    __table_args__ = (
        UniqueConstraint("facility_id", "bed_code", name="uq_static_beds_facility_code"),
        UniqueConstraint("facility_id", "bed_number", name="uq_static_beds_facility_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    bed_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bed_code: Mapped[str] = mapped_column(String(32), nullable=False)
    bed_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_type: Mapped[str] = mapped_column(String(32), nullable=False, default="indoor")
    capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    batches: Mapped[list["StaticBedBatch"]] = relationship("StaticBedBatch", back_populates="bed", cascade="all, delete-orphan", order_by="StaticBedBatch.entered_at.desc()")


class StaticBedBatch(Base):
    __tablename__ = "static_bed_batches"
    __table_args__ = (
        Index("ix_static_bed_batches_facility_status", "facility_id", "status"),
        Index("ix_static_bed_batches_bed_id", "bed_id"),
        CheckConstraint("status IN ('on_bed', 'discharged', 'cancelled')", name="ck_static_bed_batches_status"),
        CheckConstraint("water_drained_status IN ('drained', 'wet')", name="ck_static_bed_batches_water_drained"),
        CheckConstraint("raw_material_status IN ('fresh', 'spoiled')", name="ck_static_bed_batches_raw_material"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    bed_id: Mapped[int] = mapped_column(Integer, ForeignKey("static_drying_beds.id", ondelete="RESTRICT"), nullable=False)
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False)
    coffee_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Tình trạng ráo nước: 'drained' (Ráo) hoặc 'wet' (Ướt)
    water_drained_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Tình trạng nguyên liệu: 'fresh' (Tươi) hoặc 'spoiled' (Úng)
    raw_material_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Tỷ lệ cà úng ước tính (%): từ 0 đến 100, None nghĩa là "Chưa ước tính"
    estimated_spoiled_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Trạng thái mẻ: 'on_bed' (Đang trên sàn) / 'discharged' (Đã ra sàn) / 'cancelled' (Đã hủy)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="on_bed")

    # Khi ra sàn:
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Mức ráo nước sau sàn tĩnh: 'even' (Ráo đều) hoặc 'uneven' (Chưa ráo đều)
    discharge_drain_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Tình trạng cà có bị khô không: 'not_dry' (Không bị khô) hoặc 'dry' (Bị khô)
    dry_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discharge_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_bed_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    bed: Mapped["StaticDryingBed"] = relationship("StaticDryingBed", back_populates="batches")
    stirrings: Mapped[list["StaticBedStirring"]] = relationship("StaticBedStirring", back_populates="batch", cascade="all, delete-orphan", order_by="StaticBedStirring.stirring_number")
    drum_runs: Mapped[list["DrumRun"]] = relationship("DrumRun", back_populates="source_bed_batch")


class StaticBedStirring(Base):
    __tablename__ = "static_bed_stirrings"
    __table_args__ = (
        Index("ix_static_bed_stirrings_batch_id", "batch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("static_bed_batches.id", ondelete="CASCADE"), nullable=False)
    stirring_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stirring_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_name: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    batch: Mapped["StaticBedBatch"] = relationship("StaticBedBatch", back_populates="stirrings")
