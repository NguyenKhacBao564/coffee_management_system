from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import utcnow
from app.modules.accounts.models import AuthSession, User
from app.modules.accounts.security import require_csrf, session_from_request
from app.modules.facilities.models import Facility
from app.modules.drum_processing.models import (
    Drum,
    DrumIncident,
    DrumInspection,
    DrumPeriodicLog,
    DrumQC,
    DrumRun,
    StaticBedBatch,
    StaticBedStirring,
    StaticDryingBed,
)
from app.modules.drum_processing.schemas import (
    AdherenceSummary,
    DrumAnalyticsOut,
    DrumCreate,
    DrumDischargeIn,
    DrumIncidentInput,
    DrumInspectionIn,
    DrumInspectionOut,
    DrumKPIOut,
    DrumOut,
    DrumPeriodicLogIn,
    DrumPeriodicLogOut,
    DrumQCInput,
    DrumRecommendedStrategy,
    DrumRunCreate,
    DrumRunDetailOut,
    DrumRunItemOut,
    DrumRunSummaryItem,
    DrumSourceInput,
    DrumStopHeatIn,
    DrumUpdate,
    SourceBedBatchInfo,
    StaticBedBatchCreate,
    StaticBedBatchDetailOut,
    StaticBedBatchDischarge,
    StaticBedBatchItemOut,
    StaticBedStirringCreate,
    StaticBedStirringOut,
    StaticDryingBedCreate,
    StaticDryingBedOut,
)

router = APIRouter(prefix="/api/drum-processing", tags=["drum processing"])
VN_TZ = timezone(timedelta(hours=7))


def _actor(request: Request, db: Session, write: bool = False) -> tuple[AuthSession, User]:
    session, user = session_from_request(request, db, allow_anonymous=False)
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    if write:
        require_csrf(request, session)
    return session, user


def _facility(db: Session, session: AuthSession, user: User, facility_id: int | None = None) -> int:
    fid = facility_id or session.facility_id
    if fid is None:
        raise HTTPException(status_code=409, detail="Hãy chọn cơ sở đang hoạt động.")
    facility = db.get(Facility, fid)
    if not facility or not facility.is_active or (user.role != "admin" and fid not in {f.id for f in user.facilities if f.is_active}):
        raise HTTPException(status_code=404, detail="Không tìm thấy cơ sở hoặc chưa được phân quyền.")
    return fid


def _operator(user: User):
    if user.role not in {"drum_operator", "staff", "manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ thợ trông trống hoặc quản lý được ghi nhận mẻ sấy.")


def _inspector(user: User):
    if user.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc quản trị viên có quyền thanh tra đột xuất.")


def _build_source_bed_batch_info(batch: StaticBedBatch | None) -> SourceBedBatchInfo | None:
    if not batch:
        return None
    return SourceBedBatchInfo(
        batch_id=batch.id,
        batch_code=batch.batch_code,
        bed_number=batch.bed.bed_number if batch.bed else 0,
        bed_code=batch.bed.bed_code if batch.bed else "",
        entered_at=batch.entered_at,
        water_drained_status=batch.water_drained_status,
        raw_material_status=batch.raw_material_status,
        estimated_spoiled_percent=batch.estimated_spoiled_percent,
        discharged_at=batch.discharged_at,
        discharge_drain_status=batch.discharge_drain_status,
        dry_status=batch.dry_status,
        discharge_note=batch.discharge_note,
        total_bed_duration_minutes=batch.total_bed_duration_minutes,
        stirring_count=len(batch.stirrings),
    )


@router.get("/drums", response_model=list[DrumOut])
def list_drums(
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> list[DrumOut]:
    session, user = _actor(request, db, write=False)
    fid = _facility(db, session, user, facility_id)

    drums = list(db.scalars(
        select(Drum).where(Drum.facility_id == fid, Drum.is_active.is_(True)).order_by(Drum.drum_code)
    ))

    result: list[DrumOut] = []
    for drum in drums:
        active_run = db.scalar(
            select(DrumRun).where(DrumRun.drum_id == drum.id, DrumRun.status == "in_progress").order_by(DrumRun.entry_time.desc()).limit(1)
        )
        result.append(DrumOut(
            id=drum.id,
            facility_id=drum.facility_id,
            drum_code=drum.drum_code,
            drum_name=drum.drum_name,
            capacity_kg=drum.capacity_kg,
            measurement_mode=drum.measurement_mode,
            has_moisture_imbalance=drum.has_moisture_imbalance,
            has_blade_issue=drum.has_blade_issue,
            characteristics_notes=drum.characteristics_notes,
            status="running" if active_run else drum.status,
            is_active=drum.is_active,
            created_at=drum.created_at,
            active_run_id=active_run.id if active_run else None,
            active_batch_code=active_run.batch_code if active_run else None,
        ))
    return result


@router.post("/drums", response_model=DrumOut)
def create_drum(
    payload: DrumCreate,
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumOut:
    session, user = _actor(request, db, write=True)
    if user.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc quản trị viên được tạo trống mới.")
    fid = _facility(db, session, user, facility_id)

    existing = db.scalar(select(Drum).where(Drum.facility_id == fid, Drum.drum_code == payload.drum_code))
    if existing:
        raise HTTPException(status_code=409, detail=f"Mã trống '{payload.drum_code}' đã tồn tại trong cơ sở.")

    drum = Drum(
        facility_id=fid,
        drum_code=payload.drum_code,
        drum_name=payload.drum_name,
        capacity_kg=payload.capacity_kg,
        measurement_mode=payload.measurement_mode,
        has_moisture_imbalance=payload.has_moisture_imbalance,
        has_blade_issue=payload.has_blade_issue,
        characteristics_notes=payload.characteristics_notes,
        status="idle",
        is_active=True,
    )
    db.add(drum)
    db.commit()
    db.refresh(drum)
    return DrumOut(
        id=drum.id,
        facility_id=drum.facility_id,
        drum_code=drum.drum_code,
        drum_name=drum.drum_name,
        capacity_kg=drum.capacity_kg,
        measurement_mode=drum.measurement_mode,
        has_moisture_imbalance=drum.has_moisture_imbalance,
        has_blade_issue=drum.has_blade_issue,
        characteristics_notes=drum.characteristics_notes,
        status=drum.status,
        is_active=drum.is_active,
        created_at=drum.created_at,
    )


@router.get("/drums/{drum_id}", response_model=DrumOut)
def get_drum(
    drum_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumOut:
    session, user = _actor(request, db, write=False)
    drum = db.get(Drum, drum_id)
    if not drum:
        raise HTTPException(status_code=404, detail="Không tìm thấy trống sấy.")
    _facility(db, session, user, drum.facility_id)

    active_run = db.scalar(
        select(DrumRun).where(DrumRun.drum_id == drum.id, DrumRun.status == "in_progress").order_by(DrumRun.entry_time.desc()).limit(1)
    )
    return DrumOut(
        id=drum.id,
        facility_id=drum.facility_id,
        drum_code=drum.drum_code,
        drum_name=drum.drum_name,
        capacity_kg=drum.capacity_kg,
        measurement_mode=drum.measurement_mode,
        has_moisture_imbalance=drum.has_moisture_imbalance,
        has_blade_issue=drum.has_blade_issue,
        characteristics_notes=drum.characteristics_notes,
        status="running" if active_run else drum.status,
        is_active=drum.is_active,
        created_at=drum.created_at,
        active_run_id=active_run.id if active_run else None,
        active_batch_code=active_run.batch_code if active_run else None,
    )


@router.patch("/drums/{drum_id}", response_model=DrumOut)
def update_drum(
    drum_id: int,
    payload: DrumUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumOut:
    session, user = _actor(request, db, write=True)
    if user.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc quản trị viên được cập nhật đặc tính trống.")
    drum = db.get(Drum, drum_id)
    if not drum:
        raise HTTPException(status_code=404, detail="Không tìm thấy trống.")
    _facility(db, session, user, drum.facility_id)

    if payload.drum_name is not None:
        drum.drum_name = payload.drum_name
    if payload.capacity_kg is not None:
        drum.capacity_kg = payload.capacity_kg
    if payload.measurement_mode is not None:
        drum.measurement_mode = payload.measurement_mode
    if payload.has_moisture_imbalance is not None:
        drum.has_moisture_imbalance = payload.has_moisture_imbalance
    if payload.has_blade_issue is not None:
        drum.has_blade_issue = payload.has_blade_issue
    if payload.characteristics_notes is not None:
        drum.characteristics_notes = payload.characteristics_notes

    db.commit()
    db.refresh(drum)
    active_run = db.scalar(
        select(DrumRun).where(DrumRun.drum_id == drum.id, DrumRun.status == "in_progress").order_by(DrumRun.entry_time.desc()).limit(1)
    )
    return DrumOut(
        id=drum.id,
        facility_id=drum.facility_id,
        drum_code=drum.drum_code,
        drum_name=drum.drum_name,
        capacity_kg=drum.capacity_kg,
        measurement_mode=drum.measurement_mode,
        has_moisture_imbalance=drum.has_moisture_imbalance,
        has_blade_issue=drum.has_blade_issue,
        characteristics_notes=drum.characteristics_notes,
        status="running" if active_run else drum.status,
        is_active=drum.is_active,
        created_at=drum.created_at,
        active_run_id=active_run.id if active_run else None,
        active_batch_code=active_run.batch_code if active_run else None,
    )


@router.delete("/drums/{drum_id}", status_code=204)
def delete_drum(
    drum_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
):
    session, user = _actor(request, db, write=True)
    if user.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc quản trị viên được xóa trống sấy.")
    drum = db.get(Drum, drum_id)
    if not drum:
        raise HTTPException(status_code=404, detail="Không tìm thấy trống.")
    _facility(db, session, user, drum.facility_id)

    runs = db.scalars(select(DrumRun).where(DrumRun.drum_id == drum.id)).all()
    for run in runs:
        db.delete(run)
    db.delete(drum)
    db.commit()
    return None


@router.get("/runs", response_model=list[DrumRunItemOut])
def list_runs(
    status: str | None = Query(default=None),
    drum_id: int | None = Query(default=None),
    source_type: str | None = Query(default=None),
    source_bed_number: int | None = Query(default=None),
    discharge_drain_status: str | None = Query(default=None),
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> list[DrumRunItemOut]:
    session, user = _actor(request, db, write=False)
    fid = _facility(db, session, user, facility_id)

    query = select(DrumRun).where(DrumRun.facility_id == fid)
    if status:
        query = query.where(DrumRun.status == status)
    if drum_id:
        query = query.where(DrumRun.drum_id == drum_id)
    if source_type:
        if source_type == "unrecorded":
            query = query.where(DrumRun.source_type.is_(None))
        else:
            query = query.where(DrumRun.source_type == source_type)
    if source_bed_number:
        query = query.where(DrumRun.source_bed_number == source_bed_number)
    if discharge_drain_status:
        query = query.join(DrumRun.source_bed_batch).where(StaticBedBatch.discharge_drain_status == discharge_drain_status)

    runs = list(db.scalars(query.order_by(DrumRun.entry_time.desc()).limit(100)))
    result: list[DrumRunItemOut] = []
    for r in runs:
        logs = r.logs
        latest_log = logs[-1] if logs else None
        result.append(DrumRunItemOut(
            id=r.id,
            facility_id=r.facility_id,
            drum_id=r.drum_id,
            drum_code=r.drum.drum_code,
            drum_name=r.drum.drum_name,
            measurement_mode=r.drum.measurement_mode,
            has_moisture_imbalance=r.drum.has_moisture_imbalance,
            has_blade_issue=r.drum.has_blade_issue,
            batch_code=r.batch_code,
            coffee_type=r.coffee_type,
            initial_weight_kg=r.initial_weight_kg,
            initial_temperature_celsius=r.initial_temperature_celsius,
            blend_ratio_qua_percent=r.blend_ratio_qua_percent,
            blend_ratio_lua_percent=r.blend_ratio_lua_percent,
            cycle_minutes=r.cycle_minutes,
            entry_time=r.entry_time,
            heat_off_at=r.heat_off_at,
            incubation_minutes=r.incubation_minutes,
            exit_time=r.exit_time,
            operator_name=r.operator_name,
            status=r.status,
            log_count=len(logs),
            latest_moisture_percent=latest_log.moisture_percent if latest_log else None,
            latest_temperature_celsius=latest_log.temperature_celsius if latest_log else None,
            moisture_at_heat_off=r.moisture_at_heat_off,
            final_moisture_percent=r.final_moisture_percent,
            final_moisture_head_percent=r.final_moisture_head_percent,
            final_moisture_tail_percent=r.final_moisture_tail_percent,
            quality_assessment=r.quality_assessment,
            quality_note=r.quality_note,
            inspection_count=len(r.inspections),
            created_at=r.created_at,
            source_type=r.source_type,
            source_bed_id=r.source_bed_id,
            source_bed_number=r.source_bed_number,
            source_bed_batch_id=r.source_bed_batch_id,
            source_bed_batch=_build_source_bed_batch_info(r.source_bed_batch),
        ))
    return result


@router.post("/runs", response_model=DrumRunDetailOut)
def start_drum_run(
    payload: DrumRunCreate,
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumRunDetailOut:
    session, user = _actor(request, db, write=True)
    _operator(user)
    fid = _facility(db, session, user, facility_id)

    drum = db.get(Drum, payload.drum_id)
    if not drum or drum.facility_id != fid or not drum.is_active:
        raise HTTPException(status_code=404, detail="Không tìm thấy trống sấy phù hợp.")

    # Check if drum already has an active run
    active_run = db.scalar(select(DrumRun).where(DrumRun.drum_id == drum.id, DrumRun.status == "in_progress"))
    if active_run:
        raise HTTPException(status_code=409, detail=f"Trống {drum.drum_code} đang có mẻ chạy ({active_run.batch_code}). Cần xả trống trước khi nạp mẻ mới.")

    _aware(payload.entry_time)

    # Validate source
    source_bed = None
    source_bed_id = None
    source_bed_number = None
    source_bed_batch_id = None

    if payload.source_type == "indoor":
        if payload.source_bed_id:
            source_bed = db.get(StaticDryingBed, payload.source_bed_id)
        elif payload.source_bed_number:
            source_bed = db.scalar(
                select(StaticDryingBed).where(
                    StaticDryingBed.facility_id == fid,
                    StaticDryingBed.bed_number == payload.source_bed_number,
                )
            )
        if not source_bed or source_bed.facility_id != fid or not source_bed.is_active:
            raise HTTPException(status_code=422, detail="Vui lòng chọn sàn sấy tĩnh xưởng trong hợp lệ.")

        source_bed_id = source_bed.id
        source_bed_number = source_bed.bed_number

        if payload.source_bed_batch_id:
            source_batch = db.get(StaticBedBatch, payload.source_bed_batch_id)
            if not source_batch or source_batch.facility_id != fid:
                raise HTTPException(status_code=422, detail="Không tìm thấy mẻ sàn nguồn.")
            if source_batch.bed_id != source_bed.id:
                raise HTTPException(status_code=422, detail="Mẻ sàn được chọn không thuộc đúng sàn sấy này.")
            if source_batch.status != "discharged":
                raise HTTPException(status_code=422, detail="Mẻ sàn nguồn phải ở trạng thái Đã ra sàn.")
            if source_batch.discharged_at and source_batch.discharged_at > payload.entry_time:
                raise HTTPException(status_code=422, detail="Mẻ sàn nguồn phải hoàn tất trước hoặc đúng thời điểm nạp trống.")
            source_bed_batch_id = source_batch.id
    elif payload.source_type == "outdoor":
        # Outdoor source does not require bed number or bed batch
        pass

    run = DrumRun(
        facility_id=fid,
        drum_id=drum.id,
        batch_code=payload.batch_code,
        coffee_type=payload.coffee_type,
        initial_weight_kg=payload.initial_weight_kg,
        initial_temperature_celsius=payload.initial_temperature_celsius,
        initial_temperature_location=payload.initial_temperature_location,
        blend_ratio_qua_percent=payload.blend_ratio_qua_percent,
        blend_ratio_lua_percent=payload.blend_ratio_lua_percent,
        cycle_minutes=payload.cycle_minutes,
        entry_time=payload.entry_time,
        source_type=payload.source_type,
        source_bed_id=source_bed_id,
        source_bed_number=source_bed_number,
        source_bed_batch_id=source_bed_batch_id,
        operator_id=user.id,
        operator_name=user.display_name,
        status="in_progress",
    )
    drum.status = "running"
    db.add(run)
    db.commit()
    db.refresh(run)

    return get_drum_run_detail(run.id, request, db)


@router.get("/runs/{run_id}", response_model=DrumRunDetailOut)
def get_drum_run_detail(
    run_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumRunDetailOut:
    session, user = _actor(request, db, write=False)
    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sấy.")
    _facility(db, session, user, run.facility_id)

    logs = run.logs
    inspections = run.inspections

    total_logs = len(logs)
    on_time = sum(1 for l in logs if l.compliance_status == "on_time")
    late = sum(1 for l in logs if l.compliance_status == "late")
    max_delay = max([l.delay_seconds or 0 for l in logs] or [0])
    rate = round((on_time / total_logs) * 100, 1) if total_logs > 0 else 100.0

    return DrumRunDetailOut(
        id=run.id,
        facility_id=run.facility_id,
        drum_id=run.drum_id,
        drum_code=run.drum.drum_code,
        drum_name=run.drum.drum_name,
        drum_measurement_mode=run.drum.measurement_mode,
        drum_has_moisture_imbalance=run.drum.has_moisture_imbalance,
        drum_has_blade_issue=run.drum.has_blade_issue,
        drum_characteristics_notes=run.drum.characteristics_notes,
        batch_code=run.batch_code,
        coffee_type=run.coffee_type,
        initial_weight_kg=run.initial_weight_kg,
        initial_temperature_celsius=run.initial_temperature_celsius,
        initial_temperature_location=run.initial_temperature_location,
        blend_ratio_qua_percent=run.blend_ratio_qua_percent,
        blend_ratio_lua_percent=run.blend_ratio_lua_percent,
        cycle_minutes=run.cycle_minutes,
        entry_time=run.entry_time,
        heat_off_at=run.heat_off_at,
        rotation_off_at=run.rotation_off_at,
        moisture_at_heat_off=run.moisture_at_heat_off,
        incubation_minutes=run.incubation_minutes,
        exit_time=run.exit_time,
        operator_id=run.operator_id,
        operator_name=run.operator_name,
        status=run.status,
        quality_assessment=run.quality_assessment,
        quality_note=run.quality_note,
        final_moisture_percent=run.final_moisture_percent,
        final_moisture_head_percent=run.final_moisture_head_percent,
        final_moisture_tail_percent=run.final_moisture_tail_percent,
        final_discharged_at=run.final_discharged_at,
        discharge_note=run.discharge_note,
        source_type=run.source_type,
        source_bed_id=run.source_bed_id,
        source_bed_number=run.source_bed_number,
        source_bed_batch_id=run.source_bed_batch_id,
        source_bed_batch=_build_source_bed_batch_info(run.source_bed_batch),
        created_at=run.created_at,
        updated_at=run.updated_at,
        logs=[DrumPeriodicLogOut.model_validate(l) for l in logs],
        inspections=[DrumInspectionOut.model_validate(i) for i in inspections],
        adherence=AdherenceSummary(
            total_logs=total_logs,
            on_time_count=on_time,
            late_count=late,
            max_delay_seconds=max_delay,
            compliance_rate_percent=rate,
        ),
    )


@router.post("/runs/{run_id}/logs", response_model=DrumPeriodicLogOut)
def record_periodic_log(
    run_id: int,
    payload: DrumPeriodicLogIn,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumPeriodicLogOut:
    session, user = _actor(request, db, write=True)
    _operator(user)

    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sấy.")
    _facility(db, session, user, run.facility_id)

    if run.status != "in_progress":
        raise HTTPException(status_code=409, detail="Mẻ sấy này đã hoàn tất hoặc đã hủy; không thể ghi nhật ký chu kỳ mới.")

    seq = len(run.logs) + 1
    scheduled = run.entry_time + timedelta(minutes=seq * run.cycle_minutes)
    now = utcnow()

    # Delay is recorded_at - scheduled_time (positive means late)
    delay_sec = int((now - scheduled).total_seconds())

    # Compliance: If submitted more than 15 mins after scheduled, mark as late
    if delay_sec > 900:
        compliance = "late"
    elif abs((now - payload.measured_at).total_seconds()) > 7200:
        compliance = "anomalous"
    else:
        compliance = "on_time"

    # Determine effective moisture and end-to-end difference
    moist_head = payload.moisture_head_percent
    moist_tail = payload.moisture_tail_percent
    moist_center = payload.moisture_center_percent
    moist_diff = None

    if moist_head is not None and moist_tail is not None:
        moist_diff = abs(moist_head - moist_tail)
        calc_moisture = round((moist_head + moist_tail) / Decimal("2"), 2)
        effective_moist = payload.moisture_percent if payload.moisture_percent is not None else calc_moisture
    elif moist_head is not None or moist_tail is not None:
        effective_moist = payload.moisture_percent if payload.moisture_percent is not None else (moist_head if moist_head is not None else moist_tail)
    elif moist_center is not None:
        effective_moist = payload.moisture_percent if payload.moisture_percent is not None else moist_center
    else:
        effective_moist = payload.moisture_percent

    if effective_moist is None:
        raise HTTPException(status_code=422, detail="Vui lòng nhập độ ẩm đo được.")

    log = DrumPeriodicLog(
        run_id=run.id,
        operator_id=user.id,
        operator_name=user.display_name,
        sequence=seq,
        moisture_percent=effective_moist,
        moisture_head_percent=moist_head,
        moisture_center_percent=moist_center,
        moisture_tail_percent=moist_tail,
        moisture_diff_ends=moist_diff,
        temperature_celsius=payload.temperature_celsius,
        temperature_location=payload.temperature_location,
        measured_at=payload.measured_at,
        recorded_at=now,
        scheduled_time=scheduled,
        delay_seconds=delay_sec,
        compliance_status=compliance,
        note=payload.note,
    )
    run.updated_at = now
    db.add(log)
    db.commit()
    db.refresh(log)
    return DrumPeriodicLogOut.model_validate(log)


@router.post("/runs/{run_id}/stop-heat", response_model=DrumRunDetailOut)
def stop_heat_run(
    run_id: int,
    payload: DrumStopHeatIn,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumRunDetailOut:
    session, user = _actor(request, db, write=True)
    _operator(user)

    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sấy.")
    _facility(db, session, user, run.facility_id)

    if run.status != "in_progress":
        raise HTTPException(status_code=409, detail="Mẻ sấy này không trong trạng thái đang chạy.")

    now = utcnow()
    run.heat_off_at = payload.heat_off_at
    run.rotation_off_at = payload.rotation_off_at or payload.heat_off_at
    if payload.moisture_at_heat_off is not None:
        run.moisture_at_heat_off = payload.moisture_at_heat_off
    elif run.logs:
        run.moisture_at_heat_off = run.logs[-1].moisture_percent
    run.updated_at = now
    db.commit()
    db.refresh(run)
    return get_drum_run_detail(run.id, request, db)


@router.post("/runs/{run_id}/discharge", response_model=DrumRunDetailOut)
def discharge_drum_run(
    run_id: int,
    payload: DrumDischargeIn,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumRunDetailOut:
    session, user = _actor(request, db, write=True)
    _operator(user)

    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sấy.")
    _facility(db, session, user, run.facility_id)

    if run.status != "in_progress":
        raise HTTPException(status_code=409, detail="Mẻ sấy này không trong trạng thái đang chạy.")

    now = utcnow()
    run.status = "completed"
    run.exit_time = payload.exit_time

    final_moist = payload.final_moisture_percent
    if payload.final_moisture_head_percent is not None and payload.final_moisture_tail_percent is not None:
        if final_moist is None:
            final_moist = round((payload.final_moisture_head_percent + payload.final_moisture_tail_percent) / Decimal("2"), 2)
        run.final_moisture_head_percent = payload.final_moisture_head_percent
        run.final_moisture_tail_percent = payload.final_moisture_tail_percent
    if final_moist is None:
        raise HTTPException(status_code=422, detail="Vui lòng nhập độ ẩm khi ra trống.")

    run.final_moisture_percent = final_moist
    run.final_discharged_at = now
    run.quality_assessment = payload.quality_assessment
    run.quality_note = payload.quality_note
    run.discharge_note = payload.discharge_note

    # Calculate incubation minutes
    if payload.incubation_minutes is not None:
        run.incubation_minutes = payload.incubation_minutes
    elif run.heat_off_at:
        diff_sec = (payload.exit_time - run.heat_off_at).total_seconds()
        run.incubation_minutes = max(0, int(diff_sec / 60))

    run.updated_at = now

    drum = run.drum
    drum.status = "idle"

    db.commit()
    db.refresh(run)
    return get_drum_run_detail(run.id, request, db)


@router.post("/runs/{run_id}/inspections", response_model=DrumInspectionOut)
def record_random_inspection(
    run_id: int,
    payload: DrumInspectionIn,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumInspectionOut:
    session, user = _actor(request, db, write=True)
    _inspector(user)

    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sấy.")
    _facility(db, session, user, run.facility_id)

    now = utcnow()

    # Find the nearest periodic log recorded by operator
    nearest_log = None
    min_delta = None
    for l in run.logs:
        delta = abs((l.measured_at - payload.inspected_at).total_seconds())
        if min_delta is None or delta < min_delta:
            min_delta = delta
            nearest_log = l

    sample_moist = payload.sample_moisture_percent
    if payload.sample_moisture_head_percent is not None and payload.sample_moisture_tail_percent is not None:
        if sample_moist is None:
            sample_moist = round((payload.sample_moisture_head_percent + payload.sample_moisture_tail_percent) / Decimal("2"), 2)
    elif payload.sample_moisture_center_percent is not None:
        if sample_moist is None:
            sample_moist = payload.sample_moisture_center_percent

    if sample_moist is None:
        raise HTTPException(status_code=422, detail="Vui lòng nhập độ ẩm thanh tra đo được.")

    moisture_diff = None
    temp_diff = None
    evaluation = "passed"

    if nearest_log:
        moisture_diff = sample_moist - nearest_log.moisture_percent
        temp_diff = payload.sample_temperature_celsius - nearest_log.temperature_celsius

        # Evaluation criteria
        if abs(moisture_diff) > Decimal("2.0") or abs(temp_diff) > Decimal("5.0"):
            evaluation = "failed"
        elif abs(moisture_diff) > Decimal("1.0") or abs(temp_diff) > Decimal("3.0"):
            evaluation = "warning"
        else:
            evaluation = "passed"

    inspection = DrumInspection(
        run_id=run.id,
        inspector_id=user.id,
        inspector_name=user.display_name,
        inspected_at=payload.inspected_at,
        recorded_at=now,
        sample_moisture_percent=sample_moist,
        sample_moisture_head_percent=payload.sample_moisture_head_percent,
        sample_moisture_center_percent=payload.sample_moisture_center_percent,
        sample_moisture_tail_percent=payload.sample_moisture_tail_percent,
        sample_temperature_celsius=payload.sample_temperature_celsius,
        nearest_log_id=nearest_log.id if nearest_log else None,
        moisture_diff=moisture_diff,
        temperature_diff=temp_diff,
        evaluation=evaluation,
        notes=payload.notes,
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return DrumInspectionOut.model_validate(inspection)


@router.get("/drums/{drum_id}/analytics", response_model=DrumAnalyticsOut)
def get_drum_analytics(
    drum_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumAnalyticsOut:
    session, user = _actor(request, db, write=False)
    drum = db.get(Drum, drum_id)
    if not drum:
        raise HTTPException(status_code=404, detail="Không tìm thấy trống sấy.")
    _facility(db, session, user, drum.facility_id)

    # Get completed runs for this drum
    runs = list(db.scalars(
        select(DrumRun)
        .where(DrumRun.drum_id == drum.id, DrumRun.status == "completed")
        .order_by(DrumRun.entry_time.desc())
        .limit(100)
    ))

    total_runs = len(runs)
    ca_dep_runs = [r for r in runs if r.quality_assessment == "ca_dep"]
    dat_chuan_runs = [r for r in runs if r.quality_assessment == "dat_chuan"]
    ca_xau_runs = [r for r in runs if r.quality_assessment == "ca_xau"]

    ca_dep_count = len(ca_dep_runs)
    dat_chuan_count = len(dat_chuan_runs)
    ca_xau_count = len(ca_xau_runs)
    rate = round((ca_dep_count / total_runs) * 100, 1) if total_runs > 0 else 0.0

    benchmark_runs = ca_dep_runs if ca_dep_runs else [r for r in runs if r.quality_assessment in {"ca_dep", "dat_chuan"}]

    rec_temp = None
    rec_stop_moisture = None
    rec_incubation = None
    rec_drop = None
    rec_final = None

    if benchmark_runs:
        all_temps = [l.temperature_celsius for r in benchmark_runs for l in r.logs if l.temperature_celsius]
        if all_temps:
            rec_temp = Decimal(str(round(sum(all_temps) / len(all_temps), 1)))

        stop_moistures = [r.moisture_at_heat_off for r in benchmark_runs if r.moisture_at_heat_off is not None]
        if stop_moistures:
            rec_stop_moisture = Decimal(str(round(sum(stop_moistures) / len(stop_moistures), 2)))

        incubations = [r.incubation_minutes for r in benchmark_runs if r.incubation_minutes is not None]
        if incubations:
            rec_incubation = int(round(sum(incubations) / len(incubations)))

        finals = [r.final_moisture_percent for r in benchmark_runs if r.final_moisture_percent is not None]
        if finals:
            rec_final = Decimal(str(round(sum(finals) / len(finals), 2)))

        if rec_stop_moisture is not None and rec_final is not None:
            rec_drop = Decimal(str(round(rec_stop_moisture - rec_final, 2)))

    if benchmark_runs and rec_stop_moisture and rec_incubation:
        summary_text = (
            f"Chiến lược khuyến nghị cho {drum.drum_code}: Giữ luồng hơi nhiệt độ ~{rec_temp or 75}°C. "
            f"Tắt nhiệt khi độ ẩm trong trống đạt khoảng {rec_stop_moisture}%. "
            f"Ủ trong trống khoảng {rec_incubation} phút trước khi xả ra để độ ẩm giảm thêm ~{rec_drop or '2-3'}%, "
            f"giúp cà chín đều và đạt độ ẩm thành phẩm đẹp ~{rec_final or '12.5'}%."
        )
    elif benchmark_runs and rec_temp:
        summary_text = (
            f"Chiến lược ban đầu cho {drum.drum_code}: Duy trì luồng hơi nhiệt độ ~{rec_temp}°C. "
            f"Ghi nhận thêm thời điểm tắt nhiệt và ủ để có gợi ý thời gian ủ chính xác hơn."
        )
    else:
        summary_text = (
            f"Chưa có mẻ đạt chuẩn trên {drum.drum_code} để đúc kết chiến lược. "
            f"Khi có các mẻ cà đẹp, hệ thống sẽ tự động phân tích nhiệt độ và thời gian ủ tối ưu riêng cho trống này."
        )

    if drum.has_moisture_imbalance:
        summary_text += " ⚠️ Lưu ý: Trống này bị lệch độ ẩm cà 2 đầu nặng, cần đo kiểm soát cả 2 đầu trống kỹ lưỡng."
    if drum.has_blade_issue:
        summary_text += " ⚠️ Lưu ý: Trống bị lỗi cánh đảo cà khiến cà bên trong ra không đều, cần đảo tay bổ sung hoặc kiểm tra kỹ hạt bên trong lõi."
    if drum.characteristics_notes:
        summary_text += f" (Ghi chú thiết bị: {drum.characteristics_notes})"

    strategy = DrumRecommendedStrategy(
        recommended_heat_temp_celsius=rec_temp,
        recommended_stop_heat_moisture=rec_stop_moisture,
        recommended_incubation_minutes=rec_incubation,
        expected_incubation_moisture_drop=rec_drop,
        expected_final_moisture=rec_final,
        sample_size_ca_dep=len(benchmark_runs),
        strategy_summary=summary_text,
    )

    history_items: list[DrumRunSummaryItem] = []
    for r in runs:
        temps = [l.temperature_celsius for l in r.logs if l.temperature_celsius]
        avg_t = Decimal(str(round(sum(temps) / len(temps), 1))) if temps else None

        heat_duration = None
        if r.heat_off_at and r.entry_time:
            heat_duration = max(0, int((r.heat_off_at - r.entry_time).total_seconds() / 60))
        elif r.exit_time and r.entry_time and not r.incubation_minutes:
            heat_duration = max(0, int((r.exit_time - r.entry_time).total_seconds() / 60))

        drop = None
        if r.moisture_at_heat_off is not None and r.final_moisture_percent is not None:
            drop = r.moisture_at_heat_off - r.final_moisture_percent

        history_items.append(DrumRunSummaryItem(
            id=r.id,
            batch_code=r.batch_code,
            coffee_type=r.coffee_type,
            initial_temperature_celsius=r.initial_temperature_celsius,
            blend_ratio_qua_percent=r.blend_ratio_qua_percent,
            blend_ratio_lua_percent=r.blend_ratio_lua_percent,
            entry_time=r.entry_time,
            heat_off_at=r.heat_off_at,
            exit_time=r.exit_time,
            heat_duration_minutes=heat_duration,
            incubation_minutes=r.incubation_minutes,
            moisture_at_heat_off=r.moisture_at_heat_off,
            final_moisture_percent=r.final_moisture_percent,
            final_moisture_head_percent=r.final_moisture_head_percent,
            final_moisture_tail_percent=r.final_moisture_tail_percent,
            moisture_drop_in_incubation=drop,
            avg_temperature_celsius=avg_t,
            quality_assessment=r.quality_assessment,
            quality_note=r.quality_note,
            operator_name=r.operator_name,
            source_type=r.source_type,
            source_bed_number=r.source_bed_number,
            source_bed_batch_code=r.source_bed_batch.batch_code if r.source_bed_batch else None,
            raw_material_status=r.source_bed_batch.raw_material_status if r.source_bed_batch else None,
            estimated_spoiled_percent=r.source_bed_batch.estimated_spoiled_percent if r.source_bed_batch else None,
            discharge_drain_status=r.source_bed_batch.discharge_drain_status if r.source_bed_batch else None,
        ))

    return DrumAnalyticsOut(
        drum_id=drum.id,
        drum_code=drum.drum_code,
        drum_name=drum.drum_name,
        capacity_kg=drum.capacity_kg,
        total_runs=total_runs,
        ca_dep_count=ca_dep_count,
        dat_chuan_count=dat_chuan_count,
        ca_xau_count=ca_xau_count,
        ca_dep_rate_percent=rate,
        strategy=strategy,
        history=history_items,
    )


@router.get("/audit/kpi", response_model=DrumKPIOut)
def get_kpi_summary(
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> DrumKPIOut:
    session, user = _actor(request, db, write=False)
    fid = _facility(db, session, user, facility_id)

    runs = list(db.scalars(select(DrumRun).where(DrumRun.facility_id == fid)))
    total_runs = len(runs)
    in_progress_runs = sum(1 for r in runs if r.status == "in_progress")
    completed_runs = sum(1 for r in runs if r.status == "completed")

    all_logs = list(db.scalars(
        select(DrumPeriodicLog).join(DrumRun).where(DrumRun.facility_id == fid)
    ))
    total_logs = len(all_logs)
    on_time_logs = sum(1 for l in all_logs if l.compliance_status == "on_time")
    late_logs = sum(1 for l in all_logs if l.compliance_status == "late")
    compliance_rate = round((on_time_logs / total_logs) * 100, 1) if total_logs > 0 else 100.0

    all_inspections = list(db.scalars(
        select(DrumInspection).join(DrumRun).where(DrumRun.facility_id == fid)
    ))
    total_inspections = len(all_inspections)
    passed_inspections = sum(1 for i in all_inspections if i.evaluation == "passed")
    warning_inspections = sum(1 for i in all_inspections if i.evaluation == "warning")
    failed_inspections = sum(1 for i in all_inspections if i.evaluation == "failed")

    return DrumKPIOut(
        facility_id=fid,
        total_runs=total_runs,
        in_progress_runs=in_progress_runs,
        completed_runs=completed_runs,
        total_logs=total_logs,
        on_time_logs=on_time_logs,
        late_logs=late_logs,
        compliance_rate_percent=compliance_rate,
        total_inspections=total_inspections,
        passed_inspections=passed_inspections,
        warning_inspections=warning_inspections,
        failed_inspections=failed_inspections,
    )


@router.get('/runs/{run_id}/source')
def get_run_source(run_id: int, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db)
    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(404, 'Không tìm thấy mẻ sấy.')
    _facility(db, session, user, run.facility_id)
    fields = ('source_lot_code', 'traceability', 'source_note', 'ground_at', 'drying_started_at', 'drying_route', 'times_estimated', 'water_exposure', 'water_exposure_minutes', 'water_exposure_note')
    result = {name: getattr(run, name) for name in fields}
    result['waiting_minutes'] = ((run.drying_started_at - run.ground_at).total_seconds() / 60 if run.ground_at and run.drying_started_at else None)
    return result


@router.put('/runs/{run_id}/source')
def put_run_source(run_id: int, payload: DrumSourceInput, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, write=True)
    _operator(user)
    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(404, 'Không tìm thấy mẻ sấy.')
    _facility(db, session, user, run.facility_id)
    for value in (payload.ground_at, payload.drying_started_at):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(422, 'Thời gian cần có múi giờ.')
    if payload.ground_at and payload.drying_started_at and payload.drying_started_at < payload.ground_at:
        raise HTTPException(422, 'Giờ bắt đầu sấy phải sau hoặc bằng giờ xay.')
    if payload.drying_route == 'static' and payload.drying_started_at and payload.drying_started_at > run.entry_time:
        raise HTTPException(422, 'Giờ bắt đầu sấy tĩnh phải trước hoặc bằng giờ vào trống.')
    if payload.traceability == 'known' and not (payload.source_lot_code or '').strip():
        raise HTTPException(422, 'Cần mã truy xuất lô gốc.')
    if payload.traceability in ('unknown', 'mixed') and payload.source_lot_code:
        raise HTTPException(422, 'Mẻ không xác định hoặc trộn nhiều lô không dùng mã lô đơn.')
    for name, value in payload.model_dump().items():
        setattr(run, name, value.strip() if name == 'source_lot_code' and value else value)
    db.commit()
    return get_run_source(run_id, request, db)


def _run_for_user(run_id: int, request: Request, db: Session, write: bool = False):
    session, user = _actor(request, db, write=write)
    run = db.get(DrumRun, run_id)
    if not run:
        raise HTTPException(404, 'Không tìm thấy mẻ sấy.')
    _facility(db, session, user, run.facility_id)
    return run, user


def _aware(value):
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise HTTPException(422, 'Thời gian cần có múi giờ.')


@router.get('/runs/{run_id}/incidents')
def list_incidents(run_id: int, request: Request, db: Session = Depends(get_db)):
    _run_for_user(run_id, request, db)
    return list(db.scalars(select(DrumIncident).where(DrumIncident.run_id == run_id).order_by(DrumIncident.recorded_at)))


@router.post('/runs/{run_id}/incidents')
def create_incident(run_id: int, payload: DrumIncidentInput, request: Request, db: Session = Depends(get_db)):
    run, user = _run_for_user(run_id, request, db, True)
    _operator(user)
    _aware(payload.started_at)
    _aware(payload.ended_at)
    if payload.started_at and payload.ended_at and payload.ended_at < payload.started_at:
        raise HTTPException(422, 'Giờ kết thúc phải sau giờ bắt đầu.')
    incident = DrumIncident(run_id=run.id, recorded_by=user.id, recorded_name=user.display_name, **payload.model_dump())
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def _qc_result(qc: DrumQC | None):
    if qc is None:
        return None
    return {'id': qc.id, 'run_id': qc.run_id, 'sampled_at': qc.sampled_at, 'sample_point': qc.sample_point, 'method': qc.method, 'sample_size': qc.sample_size, 'total_defect': qc.total_defect, 'black_defect': qc.black_defect, 'burnt_defect': qc.burnt_defect, 'recorded_name': qc.recorded_name, 'recorded_at': qc.recorded_at, 'total_percent': qc.total_defect * 100 / qc.sample_size, 'black_percent': qc.black_defect * 100 / qc.sample_size if qc.black_defect is not None else None, 'burnt_percent': qc.burnt_defect * 100 / qc.sample_size if qc.burnt_defect is not None else None}


@router.get('/runs/{run_id}/qc')
def get_run_qc(run_id: int, request: Request, db: Session = Depends(get_db)):
    _run_for_user(run_id, request, db)
    return _qc_result(db.scalar(select(DrumQC).where(DrumQC.run_id == run_id)))


@router.post('/runs/{run_id}/qc')
def create_run_qc(run_id: int, payload: DrumQCInput, request: Request, db: Session = Depends(get_db)):
    run, user = _run_for_user(run_id, request, db, True)
    _inspector(user)
    _aware(payload.sampled_at)
    if run.status != 'completed':
        raise HTTPException(409, 'Chỉ ghi QC sau khi xả mẻ.')
    if run.exit_time and payload.sampled_at < run.exit_time:
        raise HTTPException(422, 'Thời điểm lấy mẫu phải sau hoặc bằng giờ xả.')
    if not payload.sample_point.strip():
        raise HTTPException(422, 'Cần nhập điểm lấy mẫu.')
    if payload.total_defect > payload.sample_size or (payload.black_defect or 0) + (payload.burnt_defect or 0) > payload.total_defect:
        raise HTTPException(422, 'Lượng lỗi không phù hợp với cỡ mẫu hoặc tổng lỗi.')
    if payload.method == 'count' and any(v is not None and v != v.to_integral_value() for v in (payload.sample_size, payload.total_defect, payload.black_defect, payload.burnt_defect)):
        raise HTTPException(422, 'Số hạt phải là số nguyên.')
    if db.scalar(select(DrumQC.id).where(DrumQC.run_id == run.id)):
        raise HTTPException(409, 'Mẻ đã có kết quả QC.')
    qc = DrumQC(run_id=run.id, recorded_by=user.id, recorded_name=user.display_name, **payload.model_dump())
    db.add(qc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Mẻ đã có kết quả QC.')
    db.refresh(qc)
    return _qc_result(qc)


@router.get('/reports/qc')
def qc_report(
    request: Request,
    facility_id: int | None = None,
    drum_id: int | None = None,
    start_day: str | None = None,
    end_day: str | None = None,
    method: str | None = None,
    source_type: str | None = None,
    source_bed_number: int | None = None,
    discharge_drain_status: str | None = None,
    db: Session = Depends(get_db),
):
    session, user = _actor(request, db)
    fid = _facility(db, session, user, facility_id)
    query = select(DrumRun).where(DrumRun.facility_id == fid, DrumRun.status == 'completed')
    if drum_id:
        query = query.where(DrumRun.drum_id == drum_id)
    if source_type:
        if source_type == "unrecorded":
            query = query.where(DrumRun.source_type.is_(None))
        else:
            query = query.where(DrumRun.source_type == source_type)
    if source_bed_number:
        query = query.where(DrumRun.source_bed_number == source_bed_number)
    if discharge_drain_status:
        query = query.join(DrumRun.source_bed_batch).where(StaticBedBatch.discharge_drain_status == discharge_drain_status)
    try:
        if start_day:
            start = datetime.fromisoformat(start_day).replace(tzinfo=VN_TZ)
            query = query.where(DrumRun.exit_time >= start)
        if end_day:
            end = datetime.fromisoformat(end_day).replace(tzinfo=VN_TZ) + timedelta(days=1)
            query = query.where(DrumRun.exit_time < end)
    except ValueError:
        raise HTTPException(422, 'Ngày lọc không hợp lệ.')
    if method and method not in ('gram', 'count'):
        raise HTTPException(422, 'Phương pháp QC không hợp lệ.')
    runs = list(db.scalars(query.order_by(DrumRun.exit_time.desc())))
    ids = [r.id for r in runs]
    qcs = {q.run_id: q for q in db.scalars(select(DrumQC).where(DrumQC.run_id.in_(ids)))} if ids else {}
    if method:
        runs = [r for r in runs if r.id not in qcs or qcs[r.id].method == method]
    rows = [{
        'run_id': r.id,
        'drum_id': r.drum_id,
        'drum_code': r.drum.drum_code,
        'batch_code': r.batch_code,
        'exit_time': r.exit_time,
        'source_type': r.source_type,
        'source_bed_number': r.source_bed_number,
        'source_bed_batch_code': r.source_bed_batch.batch_code if r.source_bed_batch else None,
        'water_drained_status': r.source_bed_batch.water_drained_status if r.source_bed_batch else None,
        'raw_material_status': r.source_bed_batch.raw_material_status if r.source_bed_batch else None,
        'estimated_spoiled_percent': r.source_bed_batch.estimated_spoiled_percent if r.source_bed_batch else None,
        'discharge_drain_status': r.source_bed_batch.discharge_drain_status if r.source_bed_batch else None,
        'qc': _qc_result(qcs.get(r.id))
    } for r in runs]
    groups = {}
    for r in runs:
        qc = qcs.get(r.id)
        if qc is None:
            continue
        key = (qc.method, qc.sample_point)
        group = groups.setdefault(key, {'method': qc.method, 'sample_point': qc.sample_point, 'count': 0, 'sample_size': Decimal(0), 'total': Decimal(0), 'black_size': Decimal(0), 'black': Decimal(0), 'black_count': 0, 'burnt_size': Decimal(0), 'burnt': Decimal(0), 'burnt_count': 0})
        group['count'] += 1
        group['sample_size'] += qc.sample_size
        group['total'] += qc.total_defect
        for name in ('black', 'burnt'):
            value = getattr(qc, name + '_defect')
            if value is not None:
                group[name] += value
                group[name + '_size'] += qc.sample_size
                group[name + '_count'] += 1
    for group in groups.values():
        group['total_percent'] = group['total'] * 100 / group['sample_size']
        for name in ('black', 'burnt'):
            group[name + '_percent'] = group[name] * 100 / group[name + '_size'] if group[name + '_size'] else None
    return {'total_runs': len(runs), 'qc_count': sum(r.id in qcs for r in runs), 'pending_count': sum(r.id not in qcs for r in runs), 'groups': list(groups.values()), 'runs': rows}


@router.get('/reports/lot-comparison')
def lot_comparison(request: Request, lot: str = Query(min_length=1, max_length=120), db: Session = Depends(get_db)):
    session, user = _actor(request, db)
    allowed = list(db.scalars(select(Facility.id).where(Facility.is_active.is_(True)))) if user.role == 'admin' else [f.id for f in user.facilities if f.is_active]
    runs = list(db.scalars(select(DrumRun).where(DrumRun.facility_id.in_(allowed), DrumRun.traceability == 'known', DrumRun.source_lot_code == lot.strip()).order_by(DrumRun.entry_time)))
    result = []
    for run in runs:
        qc = db.scalar(select(DrumQC).where(DrumQC.run_id == run.id))
        incidents = list(db.scalars(select(DrumIncident).where(DrumIncident.run_id == run.id)))
        temps = {}
        for log in run.logs:
            key = log.temperature_location or 'Chưa xác định'
            temps.setdefault(key, []).append(log.temperature_celsius)
        facility = db.get(Facility, run.facility_id)
        result.append({'run_id': run.id, 'facility': facility.name, 'drum': run.drum.drum_code, 'batch': run.batch_code, 'waiting_minutes': (run.drying_started_at - run.ground_at).total_seconds() / 60 if run.ground_at and run.drying_started_at else None, 'times_estimated': run.times_estimated, 'water_exposure': run.water_exposure, 'qc': _qc_result(qc), 'temperatures': [{'location': k, 'min': min(v), 'max': max(v), 'count': len(v)} for k, v in temps.items()], 'moisture_differences': [l.moisture_diff_ends for l in run.logs if l.moisture_diff_ends is not None], 'incidents': [{'kind': i.kind, 'started_at': i.started_at, 'ended_at': i.ended_at} for i in incidents]})
    return {'lot': lot.strip(), 'runs': result}


# ==========================================
# STATIC DRYING BEDS (SÀN SẤY TĨNH) ENDPOINTS
# ==========================================

@router.get("/static-beds", response_model=list[StaticDryingBedOut])
def list_static_beds(
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> list[StaticDryingBedOut]:
    session, user = _actor(request, db, write=False)
    fid = _facility(db, session, user, facility_id)

    beds = list(db.scalars(
        select(StaticDryingBed)
        .where(StaticDryingBed.facility_id == fid, StaticDryingBed.is_active.is_(True))
        .order_by(StaticDryingBed.bed_number)
    ))

    result: list[StaticDryingBedOut] = []
    for bed in beds:
        active_batch = db.scalar(
            select(StaticBedBatch)
            .where(StaticBedBatch.bed_id == bed.id, StaticBedBatch.status == "on_bed")
            .order_by(StaticBedBatch.entered_at.desc())
            .limit(1)
        )
        result.append(StaticDryingBedOut(
            id=bed.id,
            facility_id=bed.facility_id,
            bed_number=bed.bed_number,
            bed_code=bed.bed_code,
            bed_name=bed.bed_name,
            location_type=bed.location_type,
            capacity_kg=bed.capacity_kg,
            is_active=bed.is_active,
            created_at=bed.created_at,
            active_batch_id=active_batch.id if active_batch else None,
            active_batch_code=active_batch.batch_code if active_batch else None,
            active_batch_status=active_batch.status if active_batch else None,
        ))
    return result


@router.post("/static-beds", response_model=StaticDryingBedOut)
def create_static_bed(
    payload: StaticDryingBedCreate,
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> StaticDryingBedOut:
    session, user = _actor(request, db, write=True)
    if user.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc quản trị viên có quyền cấu hình sàn sấy tĩnh.")
    fid = _facility(db, session, user, facility_id)

    existing = db.scalar(
        select(StaticDryingBed).where(
            StaticDryingBed.facility_id == fid,
            (StaticDryingBed.bed_number == payload.bed_number) | (StaticDryingBed.bed_code == payload.bed_code)
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Số sàn {payload.bed_number} hoặc mã sàn '{payload.bed_code}' đã tồn tại trong cơ sở.")

    bed = StaticDryingBed(
        facility_id=fid,
        bed_number=payload.bed_number,
        bed_code=payload.bed_code,
        bed_name=payload.bed_name,
        location_type="indoor",
        capacity_kg=payload.capacity_kg,
        is_active=True,
    )
    db.add(bed)
    db.commit()
    db.refresh(bed)
    return StaticDryingBedOut(
        id=bed.id,
        facility_id=bed.facility_id,
        bed_number=bed.bed_number,
        bed_code=bed.bed_code,
        bed_name=bed.bed_name,
        location_type=bed.location_type,
        capacity_kg=bed.capacity_kg,
        is_active=bed.is_active,
        created_at=bed.created_at,
        active_batch_id=None,
        active_batch_code=None,
        active_batch_status=None,
    )


@router.get("/static-bed-batches", response_model=list[StaticBedBatchItemOut])
def list_static_bed_batches(
    bed_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> list[StaticBedBatchItemOut]:
    session, user = _actor(request, db, write=False)
    fid = _facility(db, session, user, facility_id)

    query = select(StaticBedBatch).where(StaticBedBatch.facility_id == fid)
    if bed_id:
        query = query.where(StaticBedBatch.bed_id == bed_id)
    if status:
        query = query.where(StaticBedBatch.status == status)

    batches = list(db.scalars(query.order_by(StaticBedBatch.entered_at.desc()).limit(100)))
    result: list[StaticBedBatchItemOut] = []
    for b in batches:
        result.append(StaticBedBatchItemOut(
            id=b.id,
            facility_id=b.facility_id,
            bed_id=b.bed_id,
            bed_number=b.bed.bed_number,
            bed_code=b.bed.bed_code,
            bed_name=b.bed.bed_name,
            batch_code=b.batch_code,
            coffee_type=b.coffee_type,
            input_weight_kg=b.input_weight_kg,
            entered_at=b.entered_at,
            water_drained_status=b.water_drained_status,
            raw_material_status=b.raw_material_status,
            estimated_spoiled_percent=b.estimated_spoiled_percent,
            status=b.status,
            discharged_at=b.discharged_at,
            discharge_drain_status=b.discharge_drain_status,
            discharge_note=b.discharge_note,
            total_bed_duration_minutes=b.total_bed_duration_minutes,
            operator_name=b.operator_name,
            stirring_count=len(b.stirrings),
            created_at=b.created_at,
        ))
    return result


@router.post("/static-bed-batches", response_model=StaticBedBatchDetailOut)
def create_static_bed_batch(
    payload: StaticBedBatchCreate,
    facility_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
) -> StaticBedBatchDetailOut:
    session, user = _actor(request, db, write=True)
    _operator(user)
    fid = _facility(db, session, user, facility_id)

    bed = db.get(StaticDryingBed, payload.bed_id)
    if not bed or bed.facility_id != fid or not bed.is_active:
        raise HTTPException(status_code=404, detail="Không tìm thấy sàn sấy tĩnh phù hợp.")

    # Check if bed already has an active batch
    active_batch = db.scalar(
        select(StaticBedBatch).where(StaticBedBatch.bed_id == bed.id, StaticBedBatch.status == "on_bed")
    )
    if active_batch:
        raise HTTPException(
            status_code=409,
            detail=f"Sàn {bed.bed_number} đang có mẻ cà sấy ({active_batch.batch_code}). Cần đưa cà ra sàn trước khi nạp mẻ mới."
        )

    _aware(payload.entered_at)

    batch = StaticBedBatch(
        facility_id=fid,
        bed_id=bed.id,
        batch_code=payload.batch_code.strip().upper(),
        coffee_type=payload.coffee_type,
        input_weight_kg=payload.input_weight_kg,
        entered_at=payload.entered_at,
        water_drained_status=payload.water_drained_status,
        raw_material_status=payload.raw_material_status,
        estimated_spoiled_percent=payload.estimated_spoiled_percent if payload.raw_material_status == "spoiled" else None,
        status="on_bed",
        operator_id=user.id,
        operator_name=user.display_name,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    return get_static_bed_batch_detail(batch.id, request, db)


@router.get("/static-bed-batches/{batch_id}", response_model=StaticBedBatchDetailOut)
def get_static_bed_batch_detail(
    batch_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
) -> StaticBedBatchDetailOut:
    session, user = _actor(request, db, write=False)
    batch = db.get(StaticBedBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sàn sấy tĩnh.")
    _facility(db, session, user, batch.facility_id)

    stirrings_out = [
        StaticBedStirringOut(
            id=s.id,
            batch_id=s.batch_id,
            stirring_number=s.stirring_number,
            started_at=s.started_at,
            ended_at=s.ended_at,
            duration_minutes=s.duration_minutes,
            stirring_method=s.stirring_method,
            note=s.note,
            operator_name=s.operator_name,
            recorded_at=s.recorded_at,
        )
        for s in batch.stirrings
    ]

    return StaticBedBatchDetailOut(
        id=batch.id,
        facility_id=batch.facility_id,
        bed_id=batch.bed_id,
        bed_number=batch.bed.bed_number,
        bed_code=batch.bed.bed_code,
        bed_name=batch.bed.bed_name,
        batch_code=batch.batch_code,
        coffee_type=batch.coffee_type,
        input_weight_kg=batch.input_weight_kg,
        entered_at=batch.entered_at,
        water_drained_status=batch.water_drained_status,
        raw_material_status=batch.raw_material_status,
        estimated_spoiled_percent=batch.estimated_spoiled_percent,
        status=batch.status,
        discharged_at=batch.discharged_at,
        discharge_drain_status=batch.discharge_drain_status,
        dry_status=batch.dry_status,
        discharge_note=batch.discharge_note,
        total_bed_duration_minutes=batch.total_bed_duration_minutes,
        operator_name=batch.operator_name,
        stirrings=stirrings_out,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


@router.post("/static-bed-batches/{batch_id}/stirrings", response_model=StaticBedStirringOut)
def record_static_bed_stirring(
    batch_id: int,
    payload: StaticBedStirringCreate,
    request: Request = None,
    db: Session = Depends(get_db),
) -> StaticBedStirringOut:
    session, user = _actor(request, db, write=True)
    _operator(user)

    batch = db.get(StaticBedBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sàn sấy tĩnh.")
    _facility(db, session, user, batch.facility_id)

    if batch.status != "on_bed":
        raise HTTPException(status_code=409, detail="Mẻ cà này đã ra sàn; không thể ghi thêm lượt đảo.")

    _aware(payload.started_at)
    _aware(payload.ended_at)
    if payload.ended_at and payload.ended_at < payload.started_at:
        raise HTTPException(status_code=422, detail="Giờ kết thúc đảo phải sau hoặc bằng giờ bắt đầu.")

    duration = payload.duration_minutes
    if duration is None and payload.ended_at:
        duration = max(1, int((payload.ended_at - payload.started_at).total_seconds() / 60))

    stirring_number = len(batch.stirrings) + 1
    stirring = StaticBedStirring(
        batch_id=batch.id,
        stirring_number=stirring_number,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_minutes=duration,
        stirring_method=payload.stirring_method,
        note=payload.note,
        operator_name=user.display_name,
    )
    db.add(stirring)
    batch.updated_at = utcnow()
    db.commit()
    db.refresh(stirring)

    return StaticBedStirringOut(
        id=stirring.id,
        batch_id=stirring.batch_id,
        stirring_number=stirring.stirring_number,
        started_at=stirring.started_at,
        ended_at=stirring.ended_at,
        duration_minutes=stirring.duration_minutes,
        stirring_method=stirring.stirring_method,
        note=stirring.note,
        operator_name=stirring.operator_name,
        recorded_at=stirring.recorded_at,
    )


@router.post("/static-bed-batches/{batch_id}/discharge", response_model=StaticBedBatchDetailOut)
def discharge_static_bed_batch(
    batch_id: int,
    payload: StaticBedBatchDischarge,
    request: Request = None,
    db: Session = Depends(get_db),
) -> StaticBedBatchDetailOut:
    session, user = _actor(request, db, write=True)
    _operator(user)

    batch = db.get(StaticBedBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sàn sấy tĩnh.")
    _facility(db, session, user, batch.facility_id)

    if batch.status != "on_bed":
        raise HTTPException(status_code=409, detail="Mẻ cà này không trong trạng thái đang trên sàn.")

    _aware(payload.discharged_at)
    if payload.discharged_at < batch.entered_at:
        raise HTTPException(status_code=422, detail="Thời điểm ra sàn phải sau hoặc bằng thời điểm vào sàn.")

    now = utcnow()
    batch.status = "discharged"
    batch.discharged_at = payload.discharged_at
    batch.discharge_drain_status = payload.discharge_drain_status
    batch.dry_status = payload.dry_status
    batch.discharge_note = payload.discharge_note
    batch.total_bed_duration_minutes = max(0, int((payload.discharged_at - batch.entered_at).total_seconds() / 60))
    batch.updated_at = now

    db.commit()
    db.refresh(batch)

    return get_static_bed_batch_detail(batch.id, request, db)


@router.delete("/static-bed-batches/{batch_id}", status_code=204)
def delete_static_bed_batch(
    batch_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
):
    session, user = _actor(request, db, write=True)
    if user.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc quản trị viên được xóa mẻ sàn sấy tĩnh.")

    batch = db.get(StaticBedBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẻ sàn sấy tĩnh.")
    _facility(db, session, user, batch.facility_id)

    db.delete(batch)
    db.commit()
    return None
