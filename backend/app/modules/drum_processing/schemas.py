from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DrumCreate(BaseModel):
    drum_code: str = Field(min_length=1, max_length=32)
    drum_name: str = Field(min_length=1, max_length=120)
    capacity_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    measurement_mode: Literal["center_only", "two_ends", "three_points"] = "center_only"
    has_moisture_imbalance: bool = False
    has_blade_issue: bool = False
    characteristics_notes: str | None = Field(default=None, max_length=500)

    @field_validator("drum_code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        return value.strip().upper()


class DrumUpdate(BaseModel):
    drum_name: str | None = Field(default=None, min_length=1, max_length=120)
    capacity_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    measurement_mode: Literal["center_only", "two_ends", "three_points"] | None = None
    has_moisture_imbalance: bool | None = None
    has_blade_issue: bool | None = None
    characteristics_notes: str | None = Field(default=None, max_length=500)


class DrumOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    facility_id: int
    drum_code: str
    drum_name: str
    capacity_kg: Decimal | None = None
    measurement_mode: str = "center_only"
    has_moisture_imbalance: bool = False
    has_blade_issue: bool = False
    characteristics_notes: str | None = None
    status: str
    is_active: bool
    created_at: datetime
    active_run_id: int | None = None
    active_batch_code: str | None = None


class SourceBedBatchInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    batch_code: str
    bed_number: int
    bed_code: str
    entered_at: datetime
    water_drained_status: str
    raw_material_status: str
    estimated_spoiled_percent: Decimal | None = None
    discharged_at: datetime | None = None
    discharge_drain_status: str | None = None
    dry_status: str | None = None
    discharge_note: str | None = None
    total_bed_duration_minutes: int | None = None
    stirring_count: int = 0


class DrumRunCreate(BaseModel):
    drum_id: int
    batch_code: str = Field(min_length=2, max_length=64)
    coffee_type: str | None = Field(default=None, max_length=120)
    initial_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    initial_temperature_celsius: Decimal | None = Field(default=None, ge=0, le=350, max_digits=5, decimal_places=2)
    initial_temperature_location: str | None = Field(default=None, max_length=120)
    blend_ratio_qua_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    blend_ratio_lua_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    cycle_minutes: int = Field(default=30, ge=5, le=240)
    entry_time: datetime
    source_type: Literal["indoor", "outdoor"] | None = None
    source_bed_id: int | None = None
    source_bed_number: int | None = None
    source_bed_batch_id: int | None = None

    @field_validator("batch_code")
    @classmethod
    def clean_batch(cls, value: str) -> str:
        return value.strip().upper()


class DrumPeriodicLogIn(BaseModel):
    moisture_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    moisture_head_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    moisture_center_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    moisture_tail_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    temperature_celsius: Decimal = Field(ge=0, le=350, max_digits=5, decimal_places=2)
    temperature_location: str | None = Field(default=None, max_length=120)
    measured_at: datetime
    note: str | None = Field(default=None, max_length=255)


class DrumPeriodicLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    operator_id: int | None = None
    operator_name: str
    sequence: int
    moisture_percent: Decimal
    moisture_head_percent: Decimal | None = None
    moisture_center_percent: Decimal | None = None
    moisture_tail_percent: Decimal | None = None
    moisture_diff_ends: Decimal | None = None
    temperature_celsius: Decimal
    temperature_location: str | None = None
    measured_at: datetime
    recorded_at: datetime
    scheduled_time: datetime | None = None
    delay_seconds: int | None = None
    compliance_status: str
    note: str | None = None
    created_at: datetime


class DrumStopHeatIn(BaseModel):
    heat_off_at: datetime
    rotation_off_at: datetime | None = None
    moisture_at_heat_off: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    note: str | None = Field(default=None, max_length=255)


class DrumDischargeIn(BaseModel):
    exit_time: datetime
    final_moisture_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    final_moisture_head_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    final_moisture_tail_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    incubation_minutes: int | None = Field(default=None, ge=0, le=720)
    quality_assessment: Literal["ca_dep", "dat_chuan", "ca_xau"] = "dat_chuan"
    quality_note: str | None = Field(default=None, max_length=500)
    discharge_note: str | None = Field(default=None, max_length=500)


class DrumInspectionIn(BaseModel):
    sample_moisture_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    sample_moisture_head_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    sample_moisture_center_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    sample_moisture_tail_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    sample_temperature_celsius: Decimal = Field(ge=0, le=350, max_digits=5, decimal_places=2)
    inspected_at: datetime
    notes: str | None = Field(default=None, max_length=1000)


class DrumInspectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    inspector_id: int | None = None
    inspector_name: str
    inspected_at: datetime
    recorded_at: datetime
    sample_moisture_percent: Decimal
    sample_moisture_head_percent: Decimal | None = None
    sample_moisture_center_percent: Decimal | None = None
    sample_moisture_tail_percent: Decimal | None = None
    sample_temperature_celsius: Decimal
    nearest_log_id: int | None = None
    moisture_diff: Decimal | None = None
    temperature_diff: Decimal | None = None
    evaluation: str
    notes: str | None = None
    created_at: datetime


class AdherenceSummary(BaseModel):
    total_logs: int
    on_time_count: int
    late_count: int
    max_delay_seconds: int
    compliance_rate_percent: float


class DrumRunItemOut(BaseModel):
    id: int
    facility_id: int
    drum_id: int
    drum_code: str
    drum_name: str
    measurement_mode: str = "center_only"
    has_moisture_imbalance: bool = False
    has_blade_issue: bool = False
    batch_code: str
    coffee_type: str | None = None
    initial_weight_kg: Decimal | None = None
    initial_temperature_celsius: Decimal | None = None
    blend_ratio_qua_percent: Decimal | None = None
    blend_ratio_lua_percent: Decimal | None = None
    cycle_minutes: int
    entry_time: datetime
    heat_off_at: datetime | None = None
    incubation_minutes: int | None = None
    exit_time: datetime | None = None
    operator_name: str
    status: str
    log_count: int
    latest_moisture_percent: Decimal | None = None
    latest_temperature_celsius: Decimal | None = None
    moisture_at_heat_off: Decimal | None = None
    final_moisture_percent: Decimal | None = None
    final_moisture_head_percent: Decimal | None = None
    final_moisture_tail_percent: Decimal | None = None
    quality_assessment: str | None = None
    quality_note: str | None = None
    inspection_count: int
    created_at: datetime
    source_type: str | None = None
    source_bed_id: int | None = None
    source_bed_number: int | None = None
    source_bed_batch_id: int | None = None
    source_bed_batch: SourceBedBatchInfo | None = None


class DrumRunDetailOut(BaseModel):
    id: int
    facility_id: int
    drum_id: int
    drum_code: str
    drum_name: str
    drum_measurement_mode: str = "center_only"
    drum_has_moisture_imbalance: bool = False
    drum_has_blade_issue: bool = False
    drum_characteristics_notes: str | None = None
    batch_code: str
    coffee_type: str | None = None
    initial_weight_kg: Decimal | None = None
    initial_temperature_celsius: Decimal | None = None
    initial_temperature_location: str | None = None
    blend_ratio_qua_percent: Decimal | None = None
    blend_ratio_lua_percent: Decimal | None = None
    cycle_minutes: int
    entry_time: datetime
    heat_off_at: datetime | None = None
    rotation_off_at: datetime | None = None
    moisture_at_heat_off: Decimal | None = None
    incubation_minutes: int | None = None
    exit_time: datetime | None = None
    operator_id: int | None = None
    operator_name: str
    status: str
    quality_assessment: str | None = None
    quality_note: str | None = None
    final_moisture_percent: Decimal | None = None
    final_moisture_head_percent: Decimal | None = None
    final_moisture_tail_percent: Decimal | None = None
    final_discharged_at: datetime | None = None
    discharge_note: str | None = None
    source_type: str | None = None
    source_bed_id: int | None = None
    source_bed_number: int | None = None
    source_bed_batch_id: int | None = None
    source_bed_batch: SourceBedBatchInfo | None = None
    created_at: datetime
    updated_at: datetime
    logs: list[DrumPeriodicLogOut]
    inspections: list[DrumInspectionOut]
    adherence: AdherenceSummary


class DrumRunSummaryItem(BaseModel):
    id: int
    batch_code: str
    coffee_type: str | None = None
    initial_temperature_celsius: Decimal | None = None
    blend_ratio_qua_percent: Decimal | None = None
    blend_ratio_lua_percent: Decimal | None = None
    entry_time: datetime
    heat_off_at: datetime | None = None
    exit_time: datetime | None = None
    heat_duration_minutes: int | None = None
    incubation_minutes: int | None = None
    moisture_at_heat_off: Decimal | None = None
    final_moisture_percent: Decimal | None = None
    final_moisture_head_percent: Decimal | None = None
    final_moisture_tail_percent: Decimal | None = None
    moisture_drop_in_incubation: Decimal | None = None
    avg_temperature_celsius: Decimal | None = None
    quality_assessment: str | None = None
    quality_note: str | None = None
    operator_name: str
    source_type: str | None = None
    source_bed_number: int | None = None
    source_bed_batch_code: str | None = None
    raw_material_status: str | None = None
    estimated_spoiled_percent: Decimal | None = None
    discharge_drain_status: str | None = None


class DrumRecommendedStrategy(BaseModel):
    recommended_heat_temp_celsius: Decimal | None = None
    recommended_stop_heat_moisture: Decimal | None = None
    recommended_incubation_minutes: int | None = None
    expected_incubation_moisture_drop: Decimal | None = None
    expected_final_moisture: Decimal | None = None
    sample_size_ca_dep: int
    strategy_summary: str


class DrumAnalyticsOut(BaseModel):
    drum_id: int
    drum_code: str
    drum_name: str
    capacity_kg: Decimal | None = None
    total_runs: int
    ca_dep_count: int
    dat_chuan_count: int
    ca_xau_count: int
    ca_dep_rate_percent: float
    strategy: DrumRecommendedStrategy
    history: list[DrumRunSummaryItem]


class DrumKPIOut(BaseModel):
    facility_id: int
    total_runs: int
    in_progress_runs: int
    completed_runs: int
    total_logs: int
    on_time_logs: int
    late_logs: int
    compliance_rate_percent: float
    total_inspections: int
    passed_inspections: int
    warning_inspections: int
    failed_inspections: int


class DrumSourceInput(BaseModel):
    source_lot_code: str | None = Field(default=None, max_length=120)
    traceability: Literal['known', 'unknown', 'mixed'] | None = None
    source_note: str | None = Field(default=None, max_length=500)
    ground_at: datetime | None = None
    drying_started_at: datetime | None = None
    drying_route: Literal['static', 'direct', 'unknown'] | None = None
    times_estimated: bool | None = None
    water_exposure: Literal['yes', 'no', 'unknown'] | None = None
    water_exposure_minutes: int | None = Field(default=None, ge=0)
    water_exposure_note: str | None = Field(default=None, max_length=500)


class DrumIncidentInput(BaseModel):
    kind: Literal['blade', 'rotation', 'heat', 'other']
    started_at: datetime | None = None
    ended_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)


class DrumQCInput(BaseModel):
    sampled_at: datetime
    sample_point: str = Field(min_length=1, max_length=200)
    method: Literal['gram', 'count']
    sample_size: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    total_defect: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    black_defect: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    burnt_defect: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)


class StaticDryingBedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    facility_id: int
    bed_number: int
    bed_code: str
    bed_name: str
    location_type: str
    capacity_kg: Decimal | None = None
    is_active: bool
    created_at: datetime
    active_batch_id: int | None = None
    active_batch_code: str | None = None
    active_batch_status: str | None = None


class StaticDryingBedCreate(BaseModel):
    bed_number: int = Field(ge=1, le=100)
    bed_code: str = Field(min_length=1, max_length=32)
    bed_name: str = Field(min_length=1, max_length=120)
    capacity_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class StaticBedStirringCreate(BaseModel):
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    stirring_method: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=255)


class StaticBedStirringOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    stirring_number: int
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: int | None = None
    stirring_method: str | None = None
    note: str | None = None
    operator_name: str
    recorded_at: datetime


class StaticBedBatchCreate(BaseModel):
    bed_id: int
    batch_code: str = Field(min_length=2, max_length=64)
    coffee_type: str | None = Field(default=None, max_length=120)
    input_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    entered_at: datetime
    water_drained_status: Literal["drained", "wet"]
    raw_material_status: Literal["fresh", "spoiled"]
    estimated_spoiled_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class StaticBedBatchDischarge(BaseModel):
    discharged_at: datetime
    discharge_drain_status: Literal["even", "uneven"]
    dry_status: Literal["not_dry", "dry"] | None = Field(default="not_dry")
    discharge_note: str | None = Field(default=None, max_length=500)


class StaticBedBatchItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    facility_id: int
    bed_id: int
    bed_number: int
    bed_code: str
    bed_name: str
    batch_code: str
    coffee_type: str | None = None
    input_weight_kg: Decimal | None = None
    entered_at: datetime
    water_drained_status: str
    raw_material_status: str
    estimated_spoiled_percent: Decimal | None = None
    status: str
    discharged_at: datetime | None = None
    discharge_drain_status: str | None = None
    dry_status: str | None = None
    discharge_note: str | None = None
    total_bed_duration_minutes: int | None = None
    operator_name: str
    stirring_count: int = 0
    created_at: datetime


class StaticBedBatchDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    facility_id: int
    bed_id: int
    bed_number: int
    bed_code: str
    bed_name: str
    batch_code: str
    coffee_type: str | None = None
    input_weight_kg: Decimal | None = None
    entered_at: datetime
    water_drained_status: str
    raw_material_status: str
    estimated_spoiled_percent: Decimal | None = None
    status: str
    discharged_at: datetime | None = None
    discharge_drain_status: str | None = None
    dry_status: str | None = None
    discharge_note: str | None = None
    total_bed_duration_minutes: int | None = None
    operator_name: str
    stirrings: list[StaticBedStirringOut]
    created_at: datetime
    updated_at: datetime
