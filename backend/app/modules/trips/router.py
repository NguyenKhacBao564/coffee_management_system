from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import utcnow
from app.modules.accounts.models import AuthSession, User
from app.modules.accounts.security import require_csrf, session_from_request
from app.modules.facilities.models import Facility
from app.modules.goods.models import GoodsItem, GoodsTransaction
from app.modules.trips.models import BusinessAudit, Schedule, ScheduleLine, Trip, Vehicle
from app.modules.weighings.models import WeighEvent, WeighResult

router = APIRouter(prefix="/api", tags=["D02 operations"])
VN = timezone(timedelta(hours=7))


class ScheduleLineIn(BaseModel):
    goods_name: str = Field(min_length=1, max_length=120)
    expected_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)


class ScheduleIn(BaseModel):
    expected_at: datetime
    direction: str
    partner: str | None = Field(default=None, max_length=160)
    expected_vehicle_id: int | None = None
    note: str | None = None
    lines: list[ScheduleLineIn] = Field(default_factory=list)

    @field_validator("direction")
    @classmethod
    def direction_valid(cls, value):
        if value not in {"import", "export", "mixed"}: raise ValueError("Loại lịch không hợp lệ")
        return value


class VehicleIn(BaseModel):
    plate_original: str = Field(min_length=2, max_length=32)
    nickname: str | None = Field(default=None, max_length=120)
    note: str | None = None


class TripIn(BaseModel):
    trip_code: str = Field(min_length=1, max_length=48)
    schedule_id: int | None = None
    vehicle_id: int | None = None
    partner: str | None = Field(default=None, max_length=160)
    arrived_at: datetime | None = None
    note: str | None = None


class WeighIn(BaseModel):
    weighed_at: datetime
    weight_kg: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    reweigh_of_event_id: int | None = None
    vehicle_position_confirmed: bool = False
    people_exited_confirmed: bool = False


class ReplaceWeighIn(BaseModel):
    weight_kg: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    reason: str = Field(min_length=3, max_length=1000)


class TxIn(BaseModel):
    goods_item_id: int
    direction: str
    before_result_id: int
    after_result_id: int
    note: str | None = None
    replacement_for_id: int | None = None


class TxUpdate(BaseModel):
    goods_item_id: int
    direction: str
    before_result_id: int
    after_result_id: int
    note: str | None = None
    version: int


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class CompleteIn(BaseModel):
    version: int


def _actor(request: Request, db: Session, write: bool = False) -> tuple[AuthSession, User]:
    session, user = session_from_request(request, db, allow_anonymous=False)
    if user is None: raise HTTPException(401, "Cần đăng nhập.")
    if write: require_csrf(request, session)
    return session, user


def _facility(db: Session, session: AuthSession, user: User, facility_id: int | None = None) -> int:
    fid = facility_id or session.facility_id
    if fid is None: raise HTTPException(409, "Hãy chọn cơ sở đang hoạt động.")
    facility = db.get(Facility, fid)
    if not facility or not facility.is_active or (user.role != "admin" and fid not in {f.id for f in user.facilities if f.is_active}):
        raise HTTPException(404, "Không tìm thấy dữ liệu tại cơ sở này.")
    return fid


def _writer(user: User):
    if user.role not in {"staff", "manager"}: raise HTTPException(403, "Quản trị viên chỉ có quyền xem nghiệp vụ trong D02.")


def _manager(user: User):
    if user.role != "manager": raise HTTPException(403, "Chỉ quản lý được xác nhận hoặc hủy nghiệp vụ.")


def _audit(db, actor, facility_id, kind, entity_id, event, detail=None):
    db.add(BusinessAudit(facility_id=facility_id, actor_user_id=actor.id, entity_type=kind, entity_id=entity_id, event=event, detail=detail or {}))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None: raise HTTPException(422, "Thời gian phải có múi giờ.")
    return value.astimezone(timezone.utc)


def _vehicle_plate(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
    if len(normalized) < 2: raise HTTPException(422, "Biển số không hợp lệ.")
    return normalized


def _schedule_out(db, item):
    lines = list(db.scalars(select(ScheduleLine).where(ScheduleLine.schedule_id == item.id).order_by(ScheduleLine.id)))
    trip_ids = list(db.scalars(select(Trip.id).where(Trip.schedule_id == item.id).order_by(Trip.id)))
    return {"id": item.id, "facility_id": item.facility_id, "expected_at": item.expected_at, "direction": item.direction, "partner": item.partner, "expected_vehicle_id": item.expected_vehicle_id, "note": item.note, "status": item.status, "cancel_reason": item.cancel_reason, "trip_ids": trip_ids, "lines": [{"id": l.id, "goods_name": l.goods_name, "expected_weight_kg": l.expected_weight_kg} for l in lines]}


def _result_out(result, event):
    return {"id": result.id, "event_id": event.id, "sequence": event.sequence, "weighed_at": event.weighed_at, "weight_kg": result.weight_kg, "result_status": result.status, "source": event.source, "reweigh_of_event_id": event.reweigh_of_event_id, "vehicle_position_confirmed": event.vehicle_position_confirmed, "people_exited_confirmed": event.people_exited_confirmed, "recorded_at": result.recorded_at, "edit_reason": result.edit_reason}


def _trip_out(db, trip, detail=False):
    vehicle = db.get(Vehicle, trip.vehicle_id) if trip.vehicle_id else None
    base = {"id": trip.id, "facility_id": trip.facility_id, "trip_code": trip.trip_code, "schedule_id": trip.schedule_id, "vehicle_id": trip.vehicle_id, "plate_original": vehicle.plate_original if vehicle else None, "partner": trip.partner, "arrived_at": trip.arrived_at, "departed_at": trip.departed_at, "note": trip.note, "status": trip.status, "cancel_reason": trip.cancel_reason, "version": trip.version, "created_at": trip.created_at}
    if detail:
        events = list(db.scalars(select(WeighEvent).where(WeighEvent.trip_id == trip.id).order_by(WeighEvent.sequence)))
        weights = []
        for event in events:
            for result in db.scalars(select(WeighResult).where(WeighResult.event_id == event.id).order_by(WeighResult.id)):
                weights.append(_result_out(result, event))
        transactions = list(db.scalars(select(GoodsTransaction).where(GoodsTransaction.trip_id == trip.id).order_by(GoodsTransaction.id)))
        base["weighings"] = weights
        base["transactions"] = [_tx_out(db, tx) for tx in transactions]
    return base


def _tx_out(db, tx):
    item = db.get(GoodsItem, tx.goods_item_id)
    return {"id": tx.id, "facility_id": tx.facility_id, "trip_id": tx.trip_id, "goods_item_id": tx.goods_item_id, "goods_name": item.name if item else "", "direction": tx.direction, "before_result_id": tx.before_result_id, "after_result_id": tx.after_result_id, "weight_kg": tx.weight_kg, "status": tx.status, "needs_review": tx.needs_review, "note": tx.note, "return_reason": tx.return_reason, "cancel_reason": tx.cancel_reason, "replacement_for_id": tx.replacement_for_id, "created_by": tx.created_by, "confirmed_by": tx.confirmed_by, "confirmed_at": tx.confirmed_at, "version": tx.version, "created_at": tx.created_at}


def _valid_refs(db, trip, fid, payload):
    ar = db.get(WeighResult, payload.before_result_id)
    br = db.get(WeighResult, payload.after_result_id)
    if not ar or not br: raise HTTPException(422, "Không tìm thấy kết quả cân.")
    ae = db.get(WeighEvent, ar.event_id); be = db.get(WeighEvent, br.event_id)
    if ar.id == br.id or ae.id == be.id: raise HTTPException(422, "Hai mốc cân phải khác nhau.")
    if ae.trip_id != trip.id or be.trip_id != trip.id or ae.facility_id != fid or be.facility_id != fid: raise HTTPException(404, "Mốc cân không thuộc chuyến xe/cơ sở này.")
    if ae.sequence >= be.sequence or ae.weighed_at >= be.weighed_at: raise HTTPException(422, "Mốc trước phải có thứ tự và thời điểm trước mốc sau.")
    if ae.status != "selected" or be.status != "selected" or ar.status != "selected" or br.status != "selected": raise HTTPException(409, "Chỉ được dùng kết quả cân đang được chọn.")
    item = db.get(GoodsItem, payload.goods_item_id)
    if not item or item.facility_id != fid or not item.is_active: raise HTTPException(404, "Không tìm thấy loại hàng tại cơ sở này.")
    delta = br.weight_kg - ar.weight_kg if payload.direction == "export" else ar.weight_kg - br.weight_kg
    if payload.direction not in {"import", "export"}: raise HTTPException(422, "Loại giao dịch không hợp lệ.")
    if delta <= Decimal("0"): raise HTTPException(422, "Chiều giao dịch tạo chênh lệch bằng 0 hoặc âm.")
    return delta, ae.sequence, be.sequence


def _check_overlap(db, tx, a, b):
    query = select(GoodsTransaction).where(GoodsTransaction.trip_id == tx.trip_id, GoodsTransaction.id != tx.id, GoodsTransaction.status.in_(["pending", "confirmed"]))
    for other in db.scalars(query):
        ra = db.get(WeighResult, other.before_result_id); rb = db.get(WeighResult, other.after_result_id)
        ea = db.get(WeighEvent, ra.event_id); eb = db.get(WeighEvent, rb.event_id)
        if a < eb.sequence and ea.sequence < b:
            raise HTTPException(409, f"Khoảng cân chồng lấn với giao dịch #{other.id} ({other.status}).")


@router.get("/d02/overview")
def overview(request: Request, facility_id: int | None = None, day: str | None = None, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user, facility_id)
    local_day = datetime.strptime(day, "%Y-%m-%d").date() if day else datetime.now(VN).date()
    start = datetime.combine(local_day, time.min, VN).astimezone(timezone.utc); end = start + timedelta(days=1)
    return {"facility_id": fid, "day": local_day.isoformat(), "timezone": "Asia/Ho_Chi_Minh", "trips_today": db.scalar(select(func.count()).select_from(Trip).where(Trip.facility_id == fid, Trip.created_at >= start, Trip.created_at < end)) or 0, "open_weighings": db.scalar(select(func.count()).select_from(WeighEvent).where(WeighEvent.facility_id == fid, WeighEvent.status.in_(["pending", "ready"]))) or 0, "pending_transactions": db.scalar(select(func.count()).select_from(GoodsTransaction).where(GoodsTransaction.facility_id == fid, GoodsTransaction.status == "pending")) or 0, "confirmed_import_kg": db.scalar(select(func.coalesce(func.sum(GoodsTransaction.weight_kg), 0)).where(GoodsTransaction.facility_id == fid, GoodsTransaction.status == "confirmed", GoodsTransaction.direction == "import", GoodsTransaction.created_at >= start, GoodsTransaction.created_at < end)), "confirmed_export_kg": db.scalar(select(func.coalesce(func.sum(GoodsTransaction.weight_kg), 0)).where(GoodsTransaction.facility_id == fid, GoodsTransaction.status == "confirmed", GoodsTransaction.direction == "export", GoodsTransaction.created_at >= start, GoodsTransaction.created_at < end))}


@router.get("/d02/audit")
def business_audit(request: Request, entity_type: str | None = None, entity_id: int | None = None, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user)
    query = select(BusinessAudit, User.display_name).outerjoin(User, BusinessAudit.actor_user_id == User.id).where(BusinessAudit.facility_id == fid).order_by(BusinessAudit.created_at.desc())
    if entity_type == "trip" and entity_id is not None:
        trip = db.scalar(select(Trip.id).where(Trip.id == entity_id, Trip.facility_id == fid))
        if not trip: raise HTTPException(404, "Không tìm thấy chuyến xe.")
        event_ids = select(WeighEvent.id).where(WeighEvent.trip_id == trip)
        transaction_ids = select(GoodsTransaction.id).where(GoodsTransaction.trip_id == trip)
        query = query.where(((BusinessAudit.entity_type == "trip") & (BusinessAudit.entity_id == trip)) | ((BusinessAudit.entity_type == "weighing") & BusinessAudit.entity_id.in_(event_ids)) | ((BusinessAudit.entity_type == "transaction") & BusinessAudit.entity_id.in_(transaction_ids)))
    else:
        if entity_type: query = query.where(BusinessAudit.entity_type == entity_type)
        if entity_id is not None: query = query.where(BusinessAudit.entity_id == entity_id)
    return [{"id": item.id, "entity_type": item.entity_type, "entity_id": item.entity_id, "event": item.event, "actor": actor or "Hệ thống", "detail": item.detail, "created_at": item.created_at} for item, actor in db.execute(query.limit(100))]


@router.get("/d02/goods")
def goods_list(request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user)
    return [{"id": g.id, "name": g.name} for g in db.scalars(select(GoodsItem).where(GoodsItem.facility_id == fid, GoodsItem.is_active.is_(True)).order_by(GoodsItem.name))]


@router.post("/d02/goods")
def goods_create(payload: dict, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user)
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 120: raise HTTPException(422, "Tên loại hàng không hợp lệ.")
    item = GoodsItem(facility_id=fid, name=name); db.add(item); db.flush(); _audit(db, user, fid, "goods", item.id, "created"); db.commit()
    return {"id": item.id, "name": item.name}


@router.get("/d02/vehicles")
def vehicles(request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user)
    return [{"id": v.id, "plate_original": v.plate_original, "nickname": v.nickname} for v in db.scalars(select(Vehicle).where(Vehicle.facility_id == fid).order_by(Vehicle.plate_normalized))]


@router.post("/d02/vehicles")
def vehicle_create(payload: VehicleIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); normalized = _vehicle_plate(payload.plate_original)
    if db.scalar(select(Vehicle).where(Vehicle.facility_id == fid, Vehicle.plate_normalized == normalized)): raise HTTPException(409, "Biển số đã có trong danh mục cơ sở; không tự ghép xe.")
    vehicle = Vehicle(facility_id=fid, plate_original=payload.plate_original.strip(), plate_normalized=normalized, nickname=payload.nickname, note=payload.note); db.add(vehicle); db.flush(); _audit(db, user, fid, "vehicle", vehicle.id, "created"); db.commit()
    return {"id": vehicle.id, "plate_original": vehicle.plate_original, "nickname": vehicle.nickname}


@router.get("/d02/schedules")
def schedules(request: Request, from_day: str | None = None, to_day: str | None = None, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user); q = select(Schedule).where(Schedule.facility_id == fid).order_by(Schedule.expected_at.desc())
    if from_day: q = q.where(Schedule.expected_at >= datetime.combine(datetime.strptime(from_day, "%Y-%m-%d").date(), time.min, VN).astimezone(timezone.utc))
    if to_day: q = q.where(Schedule.expected_at < datetime.combine(datetime.strptime(to_day, "%Y-%m-%d").date() + timedelta(days=1), time.min, VN).astimezone(timezone.utc))
    return [_schedule_out(db, s) for s in db.scalars(q.limit(250))]


@router.post("/d02/schedules")
def schedule_create(payload: ScheduleIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user)
    if payload.expected_vehicle_id and not db.scalar(select(Vehicle).where(Vehicle.id == payload.expected_vehicle_id, Vehicle.facility_id == fid)): raise HTTPException(404, "Không tìm thấy xe tại cơ sở này.")
    item = Schedule(facility_id=fid, expected_at=_aware(payload.expected_at), direction=payload.direction, partner=payload.partner, expected_vehicle_id=payload.expected_vehicle_id, note=payload.note, created_by=user.id); db.add(item); db.flush()
    for line in payload.lines: db.add(ScheduleLine(schedule_id=item.id, goods_name=line.goods_name.strip(), expected_weight_kg=line.expected_weight_kg))
    _audit(db, user, fid, "schedule", item.id, "created"); db.commit(); return _schedule_out(db, item)


@router.patch("/d02/schedules/{schedule_id}")
def schedule_update(schedule_id: int, payload: ScheduleIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); item = db.scalar(select(Schedule).where(Schedule.id == schedule_id, Schedule.facility_id == fid))
    if not item: raise HTTPException(404, "Không tìm thấy lịch tại cơ sở này.")
    if item.status != "planned": raise HTTPException(409, "Lịch đã hủy không thể sửa.")
    if payload.expected_vehicle_id and not db.scalar(select(Vehicle).where(Vehicle.id == payload.expected_vehicle_id, Vehicle.facility_id == fid)): raise HTTPException(404, "Không tìm thấy xe tại cơ sở này.")
    item.expected_at = _aware(payload.expected_at); item.direction = payload.direction; item.partner = payload.partner; item.expected_vehicle_id = payload.expected_vehicle_id; item.note = payload.note
    db.query(ScheduleLine).filter(ScheduleLine.schedule_id == item.id).delete()
    for line in payload.lines: db.add(ScheduleLine(schedule_id=item.id, goods_name=line.goods_name.strip(), expected_weight_kg=line.expected_weight_kg))
    _audit(db, user, fid, "schedule", item.id, "updated"); db.commit(); return _schedule_out(db, item)


@router.post("/d02/schedules/{schedule_id}/cancel")
def schedule_cancel(schedule_id: int, payload: ReasonIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _manager(user); fid = _facility(db, session, user); item = db.scalar(select(Schedule).where(Schedule.id == schedule_id, Schedule.facility_id == fid))
    if not item: raise HTTPException(404, "Không tìm thấy lịch.")
    item.status = "cancelled"; item.cancel_reason = payload.reason; _audit(db, user, fid, "schedule", item.id, "cancelled", {"reason": payload.reason}); db.commit(); return _schedule_out(db, item)


@router.get("/d02/trips")
def trips(request: Request, facility_id: int | None = None, from_day: str | None = None, to_day: str | None = None, plate: str | None = None, plate_missing: bool = False, status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user, facility_id); q = select(Trip).where(Trip.facility_id == fid).order_by(Trip.created_at.desc())
    if from_day: q = q.where(Trip.created_at >= datetime.combine(datetime.strptime(from_day, "%Y-%m-%d").date(), time.min, VN).astimezone(timezone.utc))
    if to_day: q = q.where(Trip.created_at < datetime.combine(datetime.strptime(to_day, "%Y-%m-%d").date() + timedelta(days=1), time.min, VN).astimezone(timezone.utc))
    if status: q = q.where(Trip.status == status)
    if plate_missing: q = q.where(Trip.vehicle_id.is_(None))
    if plate: q = q.join(Vehicle, Trip.vehicle_id == Vehicle.id).where(Vehicle.plate_normalized.contains(_vehicle_plate(plate)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0; rows = list(db.scalars(q.offset((page - 1) * page_size).limit(page_size)))
    return {"items": [_trip_out(db, t) for t in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/d02/trips")
def trip_create(payload: TripIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user)
    if payload.schedule_id:
        schedule = db.scalar(select(Schedule).where(Schedule.id == payload.schedule_id, Schedule.facility_id == fid, Schedule.status == "planned"))
        if not schedule: raise HTTPException(404, "Không tìm thấy lịch đang hoạt động tại cơ sở này.")
    if payload.vehicle_id and not db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicle_id, Vehicle.facility_id == fid)): raise HTTPException(404, "Không tìm thấy xe tại cơ sở này.")
    trip = Trip(facility_id=fid, trip_code=payload.trip_code.strip(), schedule_id=payload.schedule_id, vehicle_id=payload.vehicle_id, partner=payload.partner, arrived_at=_aware(payload.arrived_at) if payload.arrived_at else utcnow(), note=payload.note, created_by=user.id)
    db.add(trip); db.flush(); _audit(db, user, fid, "trip", trip.id, "created"); db.commit(); return _trip_out(db, trip)


@router.get("/d02/trips/{trip_id}")
def trip_detail(trip_id: int, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user); trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.facility_id == fid))
    if not trip: raise HTTPException(404, "Không tìm thấy chuyến xe.")
    return _trip_out(db, trip, True)


@router.post("/d02/trips/{trip_id}/vehicle")
def trip_vehicle(trip_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.facility_id == fid).with_for_update())
    if not trip or trip.status != "open": raise HTTPException(404, "Không tìm thấy chuyến đang mở.")
    vehicle_id = payload.get("vehicle_id")
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.facility_id == fid)) if vehicle_id else None
    if not vehicle: raise HTTPException(404, "Hãy chọn xe đã có trong danh mục cơ sở.")
    trip.vehicle_id = vehicle.id; trip.version += 1; _audit(db, user, fid, "trip", trip.id, "vehicle_linked", {"vehicle_id": vehicle.id}); db.commit(); return _trip_out(db, trip)


@router.post("/d02/trips/{trip_id}/weighings")
def weigh_create(trip_id: int, payload: WeighIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.facility_id == fid).with_for_update())
    if not trip or trip.status != "open": raise HTTPException(404, "Không tìm thấy chuyến đang mở.")
    when = _aware(payload.weighed_at)
    if payload.reweigh_of_event_id:
        original = db.scalar(select(WeighEvent).where(WeighEvent.id == payload.reweigh_of_event_id, WeighEvent.trip_id == trip.id, WeighEvent.facility_id == fid))
        if not original: raise HTTPException(404, "Lượt cân gốc không thuộc chuyến này.")
    seq = (db.scalar(select(func.max(WeighEvent.sequence)).where(WeighEvent.trip_id == trip.id)) or 0) + 1
    event = WeighEvent(trip_id=trip.id, facility_id=fid, sequence=seq, weighed_at=when, source="manual", reweigh_of_event_id=payload.reweigh_of_event_id, vehicle_position_confirmed=payload.vehicle_position_confirmed, people_exited_confirmed=payload.people_exited_confirmed, acknowledgement_by=user.id if payload.vehicle_position_confirmed and payload.people_exited_confirmed else None, acknowledgement_at=utcnow() if payload.vehicle_position_confirmed and payload.people_exited_confirmed else None, status="pending" if not (payload.vehicle_position_confirmed and payload.people_exited_confirmed) else "ready", created_by=user.id)
    db.add(event); db.flush(); result = WeighResult(event_id=event.id, weight_kg=payload.weight_kg, status="pending", recorded_by=user.id); db.add(result); db.flush(); _audit(db, user, fid, "weighing", event.id, "manual_recorded", {"result_id": result.id, "source": "manual"}); db.commit()
    return _result_out(result, event)


@router.post("/d02/weighings/{event_id}/select/{result_id}")
def weigh_select(event_id: int, result_id: int, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); event = db.scalar(select(WeighEvent).where(WeighEvent.id == event_id, WeighEvent.facility_id == fid).with_for_update())
    if not event: raise HTTPException(404, "Không tìm thấy lượt cân.")
    if not event.vehicle_position_confirmed or not event.people_exited_confirmed: raise HTTPException(409, "Cần ghi nhận xác nhận vị trí xe và người đã xuống xe trước khi chọn kết quả.")
    result = db.scalar(select(WeighResult).where(WeighResult.id == result_id, WeighResult.event_id == event.id))
    if not result or result.status in {"cancelled", "replaced", "excluded"}: raise HTTPException(404, "Không tìm thấy kết quả hợp lệ.")
    for other in db.scalars(select(WeighResult).where(WeighResult.event_id == event.id, WeighResult.id != result.id, WeighResult.status == "selected")): other.status = "excluded"; other.exclusion_reason = "Chọn kết quả khác trong cùng lượt cân"
    result.status = "selected"; event.status = "selected"; _audit(db, user, fid, "weighing", event.id, "result_selected", {"result_id": result.id}); db.commit(); return _result_out(result, event)


@router.post("/d02/weighings/{event_id}/acknowledge")
def weigh_ack(event_id: int, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); event = db.scalar(select(WeighEvent).where(WeighEvent.id == event_id, WeighEvent.facility_id == fid).with_for_update())
    if not event: raise HTTPException(404, "Không tìm thấy lượt cân.")
    event.vehicle_position_confirmed = True; event.people_exited_confirmed = True; event.acknowledgement_by = user.id; event.acknowledgement_at = utcnow(); event.status = "ready"; _audit(db, user, fid, "weighing", event.id, "manual_acknowledgement"); db.commit(); return {"id": event.id, "status": event.status, "vehicle_position_confirmed": True, "people_exited_confirmed": True}


@router.post("/d02/weighings/{event_id}/results/{result_id}/replace")
def weigh_replace(event_id: int, result_id: int, payload: ReplaceWeighIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); event = db.scalar(select(WeighEvent).where(WeighEvent.id == event_id, WeighEvent.facility_id == fid).with_for_update())
    old = db.scalar(select(WeighResult).where(WeighResult.id == result_id, WeighResult.event_id == event_id)) if event else None
    if not old or old.status in {"cancelled", "replaced"}: raise HTTPException(404, "Không tìm thấy kết quả cân.")
    used_confirmed = db.scalar(select(GoodsTransaction.id).where(GoodsTransaction.status == "confirmed", (GoodsTransaction.before_result_id == old.id) | (GoodsTransaction.after_result_id == old.id)))
    if used_confirmed: raise HTTPException(409, "Kết quả đã xác nhận; hãy hủy giao dịch có lý do trước khi thay.")
    old.status = "replaced"; replacement = WeighResult(event_id=event.id, weight_kg=payload.weight_kg, status="pending", replaces_result_id=old.id, edit_reason=payload.reason, recorded_by=user.id); db.add(replacement); db.flush()
    db.query(GoodsTransaction).filter(GoodsTransaction.status.in_(["draft", "pending"]), (GoodsTransaction.before_result_id == old.id) | (GoodsTransaction.after_result_id == old.id)).update({GoodsTransaction.needs_review: True, GoodsTransaction.version: GoodsTransaction.version + 1}, synchronize_session=False)
    event.status = "pending"; _audit(db, user, fid, "weighing", event.id, "result_replaced", {"old_result_id": old.id, "new_result_id": replacement.id, "reason": payload.reason}); db.commit(); return _result_out(replacement, event)


@router.post("/d02/weighings/{event_id}/exclude")
def weigh_exclude(event_id: int, payload: ReasonIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); event = db.scalar(select(WeighEvent).where(WeighEvent.id == event_id, WeighEvent.facility_id == fid).with_for_update())
    if not event: raise HTTPException(404, "Không tìm thấy lượt cân.")
    event_result_ids = select(WeighResult.id).where(WeighResult.event_id == event_id)
    if db.scalar(select(GoodsTransaction.id).where(GoodsTransaction.status.in_(["pending", "confirmed"]), (GoodsTransaction.before_result_id.in_(event_result_ids) | GoodsTransaction.after_result_id.in_(event_result_ids)))): raise HTTPException(409, "Kết quả đang được giao dịch chờ hoặc đã xác nhận sử dụng.")
    for result in db.scalars(select(WeighResult).where(WeighResult.event_id == event.id, WeighResult.status == "selected")): result.status = "excluded"; result.exclusion_reason = payload.reason
    event.status = "excluded"; _audit(db, user, fid, "weighing", event.id, "excluded", {"reason": payload.reason}); db.commit(); return {"id": event.id, "status": event.status}


@router.post("/d02/trips/{trip_id}/transactions")
def tx_create(trip_id: int, payload: TxIn, request: Request, idempotency_key: str = Header(min_length=8, max_length=80, alias="Idempotency-Key"), db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.facility_id == fid).with_for_update())
    if not trip or trip.status != "open": raise HTTPException(404, "Không tìm thấy chuyến đang mở.")
    key = idempotency_key
    previous = db.scalar(select(GoodsTransaction).where(GoodsTransaction.facility_id == fid, GoodsTransaction.idempotency_key == key))
    if previous:
        same = (previous.trip_id == trip.id and previous.goods_item_id == payload.goods_item_id and previous.direction == payload.direction and previous.before_result_id == payload.before_result_id and previous.after_result_id == payload.after_result_id and previous.replacement_for_id == payload.replacement_for_id and previous.created_by == user.id)
        if not same: raise HTTPException(409, "Idempotency-Key đã được dùng cho một giao dịch khác.")
        return _tx_out(db, previous)
    weight, _, _ = _valid_refs(db, trip, fid, payload)
    if payload.replacement_for_id:
        original = db.scalar(select(GoodsTransaction).where(GoodsTransaction.id == payload.replacement_for_id, GoodsTransaction.facility_id == fid, GoodsTransaction.trip_id == trip.id, GoodsTransaction.status == "cancelled"))
        if not original: raise HTTPException(404, "Giao dịch cần thay thế không tồn tại hoặc chưa được hủy.")
    tx = GoodsTransaction(facility_id=fid, trip_id=trip.id, goods_item_id=payload.goods_item_id, direction=payload.direction, before_result_id=payload.before_result_id, after_result_id=payload.after_result_id, weight_kg=weight, note=payload.note, created_by=user.id, idempotency_key=key, replacement_for_id=payload.replacement_for_id)
    try:
        db.add(tx); db.flush(); _audit(db, user, fid, "transaction", tx.id, "draft_created", {"direction": tx.direction, "weight_kg": str(weight)})
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(GoodsTransaction).where(GoodsTransaction.facility_id == fid, GoodsTransaction.idempotency_key == key))
        if previous and previous.created_by == user.id and previous.trip_id == trip.id and previous.before_result_id == payload.before_result_id and previous.after_result_id == payload.after_result_id and previous.goods_item_id == payload.goods_item_id and previous.direction == payload.direction and previous.replacement_for_id == payload.replacement_for_id:
            return _tx_out(db, previous)
        raise HTTPException(409, "Yêu cầu giao dịch bị trùng hoặc dữ liệu đã thay đổi. Tải lại chuyến.")
    return _tx_out(db, tx)


@router.patch("/d02/transactions/{tx_id}")
def tx_update(tx_id: int, payload: TxUpdate, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); tx = db.scalar(select(GoodsTransaction).where(GoodsTransaction.id == tx_id, GoodsTransaction.facility_id == fid).with_for_update())
    if not tx: raise HTTPException(404, "Không tìm thấy giao dịch.")
    if tx.status != "draft": raise HTTPException(409, "Chỉ sửa giao dịch nháp mới.")
    if tx.version != payload.version: raise HTTPException(409, "Dữ liệu đã được người khác thay đổi. Tải lại trước khi sửa.")
    trip = db.scalar(select(Trip).where(Trip.id == tx.trip_id, Trip.facility_id == fid).with_for_update()); weight, _, _ = _valid_refs(db, trip, fid, payload)
    tx.goods_item_id = payload.goods_item_id; tx.direction = payload.direction; tx.before_result_id = payload.before_result_id; tx.after_result_id = payload.after_result_id; tx.weight_kg = weight; tx.note = payload.note; tx.needs_review = False; tx.version += 1; _audit(db, user, fid, "transaction", tx.id, "draft_updated"); db.commit(); return _tx_out(db, tx)


@router.post("/d02/transactions/{tx_id}/submit")
def tx_submit(tx_id: int, payload: CompleteIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _writer(user); fid = _facility(db, session, user); tx = db.scalar(select(GoodsTransaction).where(GoodsTransaction.id == tx_id, GoodsTransaction.facility_id == fid).with_for_update())
    if not tx: raise HTTPException(404, "Không tìm thấy giao dịch.")
    trip = db.scalar(select(Trip).where(Trip.id == tx.trip_id, Trip.facility_id == fid).with_for_update())
    if tx.status == "pending": return _tx_out(db, tx)
    if tx.status != "draft" or payload.version != tx.version: raise HTTPException(409, "Giao dịch đã thay đổi. Tải lại trước khi gửi.")
    if tx.needs_review: raise HTTPException(409, "Giao dịch cần kiểm tra lại do kết quả cân đã thay đổi.")
    refs = TxIn(goods_item_id=tx.goods_item_id, direction=tx.direction, before_result_id=tx.before_result_id, after_result_id=tx.after_result_id, note=tx.note); tx.weight_kg, a, b = _valid_refs(db, trip, fid, refs); _check_overlap(db, tx, a, b)
    tx.status = "pending"; tx.version += 1; _audit(db, user, fid, "transaction", tx.id, "submitted"); db.commit(); return _tx_out(db, tx)


@router.get("/d02/transactions/pending")
def pending(request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db); fid = _facility(db, session, user)
    return [_tx_out(db, tx) for tx in db.scalars(select(GoodsTransaction).where(GoodsTransaction.facility_id == fid, GoodsTransaction.status == "pending").order_by(GoodsTransaction.created_at))]


@router.post("/d02/transactions/{tx_id}/confirm")
def tx_confirm(tx_id: int, payload: CompleteIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _manager(user); fid = _facility(db, session, user); tx = db.scalar(select(GoodsTransaction).where(GoodsTransaction.id == tx_id, GoodsTransaction.facility_id == fid).with_for_update())
    if not tx: raise HTTPException(404, "Không tìm thấy giao dịch.")
    trip = db.scalar(select(Trip).where(Trip.id == tx.trip_id, Trip.facility_id == fid).with_for_update())
    if tx.status == "confirmed": return _tx_out(db, tx)
    if tx.status != "pending" or tx.version != payload.version: raise HTTPException(409, "Giao dịch đã thay đổi. Tải lại trước khi xác nhận.")
    if tx.needs_review: raise HTTPException(409, "Giao dịch cần kiểm tra lại.")
    refs = TxIn(goods_item_id=tx.goods_item_id, direction=tx.direction, before_result_id=tx.before_result_id, after_result_id=tx.after_result_id, note=tx.note); tx.weight_kg, a, b = _valid_refs(db, trip, fid, refs); _check_overlap(db, tx, a, b)
    tx.status = "confirmed"; tx.confirmed_by = user.id; tx.confirmed_at = utcnow(); tx.version += 1; _audit(db, user, fid, "transaction", tx.id, "confirmed", {"weight_kg": str(tx.weight_kg)}); db.commit(); return _tx_out(db, tx)


@router.post("/d02/transactions/{tx_id}/return")
def tx_return(tx_id: int, payload: ReasonIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _manager(user); fid = _facility(db, session, user); tx = db.scalar(select(GoodsTransaction).where(GoodsTransaction.id == tx_id, GoodsTransaction.facility_id == fid).with_for_update())
    if not tx: raise HTTPException(404, "Không tìm thấy giao dịch.")
    if tx.status != "pending": raise HTTPException(409, "Chỉ giao dịch đang chờ mới được trả lại.")
    tx.status = "draft"; tx.return_reason = payload.reason; tx.needs_review = True; tx.version += 1; _audit(db, user, fid, "transaction", tx.id, "returned", {"reason": payload.reason}); db.commit(); return _tx_out(db, tx)


@router.post("/d02/transactions/{tx_id}/cancel")
def tx_cancel(tx_id: int, payload: ReasonIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _manager(user); fid = _facility(db, session, user); tx = db.scalar(select(GoodsTransaction).where(GoodsTransaction.id == tx_id, GoodsTransaction.facility_id == fid).with_for_update())
    if not tx: raise HTTPException(404, "Không tìm thấy giao dịch.")
    if tx.status not in {"draft", "pending", "confirmed"}: raise HTTPException(409, "Giao dịch đã hủy.")
    tx.status = "cancelled"; tx.cancel_reason = payload.reason; tx.version += 1; _audit(db, user, fid, "transaction", tx.id, "cancelled", {"reason": payload.reason}); db.commit(); return _tx_out(db, tx)


@router.post("/d02/trips/{trip_id}/cancel")
def trip_cancel(trip_id: int, payload: ReasonIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _manager(user); fid = _facility(db, session, user); trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.facility_id == fid).with_for_update())
    if not trip or trip.status != "open": raise HTTPException(404, "Không tìm thấy chuyến đang mở.")
    if db.scalar(select(GoodsTransaction.id).where(GoodsTransaction.trip_id == trip.id, GoodsTransaction.status.in_(["pending", "confirmed"]))): raise HTTPException(409, "Xử lý các giao dịch chờ/đã xác nhận trước khi hủy chuyến.")
    trip.status = "cancelled"; trip.cancel_reason = payload.reason; trip.version += 1; _audit(db, user, fid, "trip", trip.id, "cancelled", {"reason": payload.reason}); db.commit(); return _trip_out(db, trip)


@router.post("/d02/trips/{trip_id}/complete")
def trip_complete(trip_id: int, payload: CompleteIn, request: Request, db: Session = Depends(get_db)):
    session, user = _actor(request, db, True); _manager(user); fid = _facility(db, session, user); trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.facility_id == fid).with_for_update())
    if not trip: raise HTTPException(404, "Không tìm thấy chuyến xe.")
    if trip.status == "completed": return _trip_out(db, trip)
    if payload.version != trip.version: raise HTTPException(409, "Chuyến xe đã thay đổi. Tải lại.")
    if not trip.vehicle_id: raise HTTPException(409, "Cần bổ sung xe/biển số trước khi hoàn tất chính thức.")
    if db.scalar(select(GoodsTransaction.id).where(GoodsTransaction.trip_id == trip.id, GoodsTransaction.status.in_(["draft", "pending"]))): raise HTTPException(409, "Còn giao dịch chưa xử lý.")
    if db.scalar(select(WeighEvent.id).where(WeighEvent.trip_id == trip.id, WeighEvent.status.in_(["pending", "ready"]))): raise HTTPException(409, "Còn lượt cân cần chọn hoặc xác nhận.")
    trip.status = "completed"; trip.departed_at = utcnow(); trip.version += 1; _audit(db, user, fid, "trip", trip.id, "completed"); db.commit(); return _trip_out(db, trip)
