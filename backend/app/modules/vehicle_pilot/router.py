import base64
import hashlib
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from typing import Literal

from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.models import utcnow
from app.modules.accounts.models import User
from app.modules.accounts.security import require_csrf, session_from_request
from app.modules.facilities.models import Facility
from app.modules.vehicle_pilot.models import CameraDiagnostic, CameraEvidence, CameraRuntime, CameraVisit, VehicleAIJob, VehiclePilotAuditEvent, VehiclePrediction, VisitConfirmation
from app.modules.vehicle_pilot.schemas import ConfirmationCreate, PredictionCreate, VisitCreate
from app.modules.vehicle_pilot.storage import EvidenceStorage

logger = logging.getLogger("nhu_tung.vehicle_pilot")
router = APIRouter(prefix="/api/vehicle-pilot", tags=["vehicle-pilot"])
storage = EvidenceStorage()
_KINDS = {"overview", "vehicle_crop", "plate_crop", "painted_text_crop", "container_crop", "other"}


def _camera(db, camera_id, scope):
    row = db.scalar(select(CameraRuntime).where(CameraRuntime.camera_id == camera_id, CameraRuntime.facility_id.in_(scope)))
    if row is None:
        raise HTTPException(404, "Không tìm thấy camera trong phạm vi cơ sở.")
    return row


def camera_health(row, now):
    data = dict(row.snapshot)
    def recent(key, seconds=45):
        value = data.get(key)
        if not value:
            return False
        return 0 <= (now - datetime.fromisoformat(value)).total_seconds() <= seconds
    age = max(0, (now - row.updated_at).total_seconds())
    source_state = data.get("source_state")
    if age > 75:
        source_state = "interrupted"
    elif source_state not in {"reconnecting", "error", "stopped", "idle_unchecked", "starting"}:
        source_state = "receiving" if recent("last_frame_decoded_at") else "interrupted"
    data.update(camera_id=row.camera_id, facility_id=row.facility_id, health_received_at=row.updated_at,
                worker_reporting=age <= 75,
                source_state=source_state,
                processing_state=("processing" if recent("last_frame_processed_at") and data.get("processing_state") == "processing" else data.get("processing_state") if data.get("processing_state") in {"error", "stopped", "idle", "preview_only"} else "interrupted"),
                preview_url=f"/api/vehicle-pilot/cameras/{row.camera_id}/preview")
    return data


class CameraAction(BaseModel):
    request_id: UUID
    action: Literal["process", "photo", "preview", "preview_stop"]
    duration_seconds: int = Field(default=120, ge=10, le=120)


@router.post("/cameras/{camera_id}/actions", status_code=202)
def request_camera_action(camera_id: str, payload: CameraAction, request: Request, db: Session = Depends(get_db)):
    user, scope = _identity(request, db, write=True)
    row = _camera(db, camera_id, scope)
    db.refresh(row, with_for_update=True)
    now = utcnow()
    if not camera_health(row, now)["worker_reporting"]:
        raise HTTPException(409, "Worker chưa báo health; hãy chạy worker trước.")
    previous = db.get(CameraDiagnostic, payload.request_id)
    identity = {"action": payload.action, "duration_seconds": payload.duration_seconds}
    if previous:
        if previous.camera_id != camera_id or previous.requested_by != user.id or previous.metadata_json.get("request") != identity:
            raise HTTPException(409, "request_id đã được dùng với nội dung khác.")
        return {"diagnostic_id": str(previous.id), "status": previous.status}
    if payload.action == "preview_stop":
        for active in db.scalars(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == camera_id,
                CameraDiagnostic.kind == "preview", CameraDiagnostic.status.in_(["queued", "capturing"]))):
            active.status = "completed"
    else:
        active = db.scalar(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == camera_id,
            CameraDiagnostic.kind == payload.action, CameraDiagnostic.status.in_(["queued", "capturing", "saving"]),
            CameraDiagnostic.created_at > now - timedelta(seconds=120)).order_by(CameraDiagnostic.created_at.desc()).limit(1))
        if active:
            return {"diagnostic_id": str(active.id), "status": active.status}
    item = CameraDiagnostic(id=payload.request_id, camera_id=camera_id, facility_id=row.facility_id,
        kind=payload.action, status="completed" if payload.action == "preview_stop" else "queued",
        requested_by=user.id, created_at=now, expires_at=now + timedelta(hours=24),
        metadata_json={"request": identity, "deadline_at": (now + timedelta(seconds=30)).isoformat(),
            "preview_until": (now + timedelta(seconds=payload.duration_seconds)).isoformat(), "purpose": "manual_camera_control"})
    db.add(item); db.commit()
    return {"diagnostic_id": str(item.id), "status": item.status}


@router.get("/cameras")
def camera_list(request: Request, facility_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    now = utcnow()
    rows = db.scalars(select(CameraRuntime).where(CameraRuntime.facility_id.in_(scope),
        *([CameraRuntime.facility_id == facility_id] if facility_id else [])).order_by(CameraRuntime.camera_id))
    return {"items": [camera_health(row, now) for row in rows], "server_time_utc": now}


@router.get("/cameras/{camera_id}/preview")
def camera_preview(camera_id: str, request: Request, db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    row = _camera(db, camera_id, scope)
    now = utcnow()
    lease = db.scalar(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == camera_id,
        CameraDiagnostic.kind == "preview", CameraDiagnostic.status.in_(["queued", "capturing"])).order_by(CameraDiagnostic.created_at.desc()).limit(1))
    if not lease or datetime.fromisoformat(lease.metadata_json["preview_until"]) <= now:
        raise HTTPException(409, "Preview đang tắt hoặc hết thời hạn.")
    health = camera_health(row, now)
    if health["source_state"] != "receiving":
        raise HTTPException(409, "Chưa có frame mới; không trả ảnh cũ như preview live.")
    key = row.snapshot.get("preview_key")
    if not key:
        raise HTTPException(404, "Chưa có preview.")
    try:
        body = storage.read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Preview chưa sẵn sàng.") from None
    return Response(body, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/cameras/{camera_id}/diagnostics", status_code=202)
def request_camera_clip(camera_id: str, request: Request, db: Session = Depends(get_db)):
    user, scope = _identity(request, db, write=True)
    row = _camera(db, camera_id, scope)
    # Lock the camera row so concurrent requests cannot enqueue duplicate captures.
    db.refresh(row, with_for_update=True)
    now = utcnow()
    health = camera_health(row, now)
    if health["source_state"] != "receiving":
        raise HTTPException(409, "Nguồn chưa cung cấp frame; không thể thu clip kiểm tra.")
    active = db.scalar(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == camera_id,
        CameraDiagnostic.kind == "clip", CameraDiagnostic.status.in_(["queued", "capturing"]), CameraDiagnostic.created_at > now - timedelta(seconds=60)))
    if active:
        return {"diagnostic_id": str(active.id), "status": active.status}
    previous = db.scalar(select(CameraDiagnostic.created_at).where(CameraDiagnostic.camera_id == camera_id,
        CameraDiagnostic.kind == "clip").order_by(CameraDiagnostic.created_at.desc()).limit(1))
    if previous and (now - previous).total_seconds() < 60:
        raise HTTPException(429, "Chờ ít nhất 60 giây giữa hai clip kiểm tra.")
    item = CameraDiagnostic(id=uuid4(), camera_id=camera_id, facility_id=row.facility_id,
        kind="clip", status="queued", requested_by=user.id, created_at=now,
        expires_at=now + timedelta(hours=24), metadata_json={"duration_seconds": 15, "capture_fps": 3, "purpose": "diagnostic_no_ai"})
    db.add(item)
    db.commit()
    return {"diagnostic_id": str(item.id), "status": item.status}


@router.get("/cameras/{camera_id}/diagnostics")
def camera_diagnostics(camera_id: str, request: Request, db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    _camera(db, camera_id, scope)
    rows = db.scalars(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == camera_id,
        CameraDiagnostic.expires_at > utcnow()).order_by(CameraDiagnostic.created_at.desc(), CameraDiagnostic.id).limit(30))
    return {"items": [{"diagnostic_id": str(r.id), "kind": r.kind, "status": r.status,
        "created_at": r.created_at, "metadata": r.metadata_json,
        "content_url": f"/api/vehicle-pilot/diagnostics/{r.id}/content" if r.status == "stored" else None} for r in rows]}


@router.get("/diagnostics/{diagnostic_id}/content")
def diagnostic_content(diagnostic_id: UUID, request: Request, db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    row = db.scalar(select(CameraDiagnostic).where(CameraDiagnostic.id == diagnostic_id,
        CameraDiagnostic.facility_id.in_(scope), CameraDiagnostic.expires_at > utcnow(), CameraDiagnostic.status == "stored"))
    if row is None or not row.object_key:
        raise HTTPException(404, "Không tìm thấy bằng chứng kiểm tra.")
    try:
        body = storage.read(row.object_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "File kiểm tra không sẵn sàng.") from None
    return Response(body, media_type="video/mp4" if row.kind == "clip" else "image/jpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _identity(request: Request, db: Session, *, write: bool = False) -> tuple[User, list[int]]:
    session, user = session_from_request(request, db, allow_anonymous=False)
    assert user is not None
    if write:
        require_csrf(request, session)
    query = select(Facility.id).where(Facility.is_active.is_(True))
    if user.role != "admin":
        query = query.where(Facility.id.in_([f.id for f in user.facilities if f.is_active]))
    return user, list(db.scalars(query))


def _visit(db: Session, visit_id: UUID, scope: list[int], *, lock: bool = False) -> CameraVisit:
    query = select(CameraVisit).where(CameraVisit.id == visit_id, CameraVisit.facility_id.in_(scope))
    if lock:
        query = query.with_for_update()
    visit = db.scalar(query)
    if visit is None:
        raise HTTPException(404, "Không tìm thấy lượt camera trong phạm vi cơ sở được phép.")
    return visit


def _visit_out(visit: CameraVisit) -> dict:
    return {
        "visit_id": str(visit.id), "facility_id": visit.facility_id, "camera_id": visit.camera_id,
        "source_mode": visit.source_mode, "source_ref": visit.source_ref,
        "start_media_seconds": str(visit.start_media_seconds) if visit.start_media_seconds is not None else None,
        "end_media_seconds": str(visit.end_media_seconds) if visit.end_media_seconds is not None else None,
        "observed_at_utc": visit.observed_at_utc, "received_at_utc": visit.received_at_utc,
        "status": visit.status, "version": visit.version, "metadata": visit.metadata_json,
        "created_at": visit.created_at, "updated_at": visit.updated_at,
    }


def _audit(db: Session, visit: CameraVisit, actor: User | None, event: str, details: dict) -> None:
    db.add(VehiclePilotAuditEvent(id=uuid4(), visit_id=visit.id, facility_id=visit.facility_id,
        actor_user_id=actor.id if actor else None, event=event, details=details, created_at=utcnow()))


def _evidence_out(item: CameraEvidence) -> dict:
    return {
        "evidence_id": str(item.id), "kind": item.kind, "source_mode": item.source_mode,
        "media_seconds": str(item.media_seconds) if item.media_seconds is not None else None,
        "observed_at_utc": item.observed_at_utc, "received_at_utc": item.received_at_utc,
        "retention_until_utc": item.retention_until_utc,
        "purged_at_utc": item.purged_at_utc,
        "content_type": item.content_type, "size_bytes": item.size_bytes, "sha256": item.sha256,
        "storage_state": item.storage_state, "bbox": item.bbox_json, "transform": item.transform_json,
        "metadata": item.metadata_json, "content_url": f"/api/vehicle-pilot/evidence/{item.id}/content",
    }


@router.post("/visits", status_code=201)
def create_visit(payload: VisitCreate, request: Request, db: Session = Depends(get_db)):
    user, scope = _identity(request, db, write=True)
    if payload.facility_id not in scope:
        raise HTTPException(404, "Không tìm thấy cơ sở được phép ghi.")
    canonical = payload.model_dump(mode="json", exclude={"visit_id"})
    if payload.source_ref and ("/" in payload.source_ref or "\\" in payload.source_ref or "://" in payload.source_ref or "@" in payload.source_ref):
        raise HTTPException(422, "source_ref chỉ được là nhãn an toàn, không phải đường dẫn hoặc URL.")
    if len(json.dumps(payload.metadata, ensure_ascii=False)) > 16_384:
        raise HTTPException(413, "Metadata visit vượt giới hạn.")
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    existing = db.get(CameraVisit, payload.visit_id)
    if existing:
        if existing.facility_id not in scope:
            raise HTTPException(404, "Không tìm thấy lượt camera trong phạm vi cơ sở được phép.")
        if existing.create_fingerprint != fingerprint:
            raise HTTPException(409, detail={"code": "visit_conflict", "message": "visit_id đã được dùng với nội dung khác."})
        return {"visit": _visit_out(existing), "duplicate": True}
    now = utcnow()
    visit = CameraVisit(
        id=payload.visit_id, facility_id=payload.facility_id, camera_id=payload.camera_id,
        source_mode=payload.source_mode, source_ref=payload.source_ref,
        start_media_seconds=payload.start_media_seconds, end_media_seconds=payload.end_media_seconds,
        observed_at_utc=payload.observed_at_utc.astimezone(timezone.utc) if payload.observed_at_utc else None,
        status=payload.status, create_fingerprint=fingerprint, metadata_json=payload.metadata,
        created_at=now, updated_at=now,
    )
    db.add(visit)
    _audit(db, visit, user, "visit_created", {"camera_id": visit.camera_id, "source_mode": visit.source_mode, "status": visit.status})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.get(CameraVisit, payload.visit_id)
        if prior and prior.create_fingerprint == fingerprint and prior.facility_id in scope:
            return {"visit": _visit_out(prior), "duplicate": True}
        raise HTTPException(409, detail={"code": "visit_conflict", "message": "visit_id đã được dùng với nội dung khác."})
    logger.info("Camera visit persisted", extra={"visit_id": str(visit.id), "facility_id": visit.facility_id, "mode": visit.source_mode})
    return {"visit": _visit_out(visit), "duplicate": False}


@router.post("/visits/{visit_id}/evidence/{evidence_id}", status_code=201)
async def upload_evidence(
    visit_id: UUID, evidence_id: UUID, request: Request,
    kind: str = Query(...), media_seconds: Decimal | None = Query(None, ge=0),
    observed_at_utc: datetime | None = Query(None),
    metadata_json: str = Header(default="{}", alias="X-Evidence-Metadata"),
    bbox_json: str | None = Header(default=None, alias="X-Evidence-Bbox"),
    transform_json: str | None = Header(default=None, alias="X-Evidence-Transform"),
    db: Session = Depends(get_db),
):
    user, scope = _identity(request, db, write=True)
    visit = _visit(db, visit_id, scope, lock=True)
    if kind not in _KINDS:
        raise HTTPException(422, "kind không hợp lệ.")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    max_bytes = get_settings().pilot_evidence_max_file_bytes
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(413, "Ảnh vượt giới hạn kích thước.")
        except ValueError:
            raise HTTPException(400, "Content-Length không hợp lệ.")
    chunks = []
    byte_count = 0
    async for chunk in request.stream():
        byte_count += len(chunk)
        if byte_count > max_bytes:
            raise HTTPException(413, "Ảnh vượt giới hạn kích thước.")
        chunks.append(chunk)
    body = b"".join(chunks)
    digest = storage.validate(body, content_type)
    if len(metadata_json) > 4096 or (bbox_json and len(bbox_json) > 2048) or (transform_json and len(transform_json) > 2048):
        raise HTTPException(413, "Metadata ảnh vượt giới hạn.")
    try:
        metadata = json.loads(metadata_json)
        bbox = json.loads(bbox_json) if bbox_json else None
        transform = json.loads(transform_json) if transform_json else None
    except (ValueError, TypeError):
        raise HTTPException(422, "Metadata ảnh không phải JSON hợp lệ.")
    if not isinstance(metadata, dict) or (bbox is not None and not isinstance(bbox, dict)) or (transform is not None and not isinstance(transform, dict)):
        raise HTTPException(422, "Metadata/bbox/transform phải là object JSON.")
    if observed_at_utc is not None and (observed_at_utc.tzinfo is None or observed_at_utc.utcoffset() is None):
        raise HTTPException(422, "observed_at_utc phải có múi giờ.")
    existing = db.get(CameraEvidence, evidence_id)
    if existing:
        if existing.visit_id != visit_id or existing.facility_id not in scope:
            raise HTTPException(404, "Không tìm thấy bằng chứng trong phạm vi được phép.")
        same = (existing.sha256 == digest and existing.kind == kind and existing.content_type == content_type
                and existing.media_seconds == media_seconds and existing.bbox_json == bbox
                and existing.transform_json == transform and existing.metadata_json == metadata)
        if not same:
            raise HTTPException(409, detail={"code": "evidence_conflict", "message": "evidence_id đã được dùng với nội dung/metadata khác."})
        if existing.storage_state != "stored":
            try:
                storage.write(existing.object_key, body, digest)
                existing.storage_state = "stored"
                db.commit()
            except Exception:
                db.rollback()
                raise
        return {"evidence": _evidence_out(existing), "duplicate": True}

    # Reserve quota while holding the facility row lock; pending records reserve bytes too.
    locked_facility = db.scalar(select(Facility).where(Facility.id == visit.facility_id).with_for_update())
    if locked_facility is None or not locked_facility.is_active:
        raise HTTPException(404, "Cơ sở không còn hoạt động.")
    reserved = db.scalar(select(func.coalesce(func.sum(CameraEvidence.size_bytes), 0)).where(
        CameraEvidence.facility_id == visit.facility_id, CameraEvidence.storage_state.in_(["pending", "stored"]))) or 0
    settings = get_settings()
    if reserved + len(body) > settings.pilot_evidence_quota_per_facility_bytes:
        raise HTTPException(507, detail={"code": "evidence_quota_exceeded", "message": "Đã đạt quota lưu evidence của cơ sở."})
    if storage.free_bytes() < len(body) + 16 * 1024 * 1024:
        raise HTTPException(507, detail={"code": "evidence_disk_low", "message": "Dung lượng lưu evidence không đủ an toàn."})
    key = storage.object_key(visit.facility_id, visit_id, evidence_id, content_type)
    row = CameraEvidence(
        id=evidence_id, visit_id=visit_id, facility_id=visit.facility_id, kind=kind,
        source_mode=visit.source_mode, media_seconds=media_seconds,
        observed_at_utc=observed_at_utc.astimezone(timezone.utc) if observed_at_utc else None,
        received_at_utc=utcnow(),
        retention_until_utc=utcnow() + timedelta(days=settings.pilot_evidence_retention_days),
        content_type=content_type, size_bytes=len(body), sha256=digest,
        object_key=key, storage_state="pending", bbox_json=bbox, transform_json=transform, metadata_json=metadata,
    )
    db.add(row)
    _audit(db, visit, user, "evidence_stored", {"evidence_id": str(row.id), "kind": row.kind, "sha256": row.sha256, "size_bytes": row.size_bytes})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "evidence_id đã được tạo đồng thời; hãy đọc lại lượt camera.")
    try:
        storage.write(key, body, digest)
        row.storage_state = "stored"
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Evidence storage pending reconciliation", extra={"visit_id": str(visit_id), "evidence_id": str(evidence_id)})
        raise HTTPException(507, detail={"code": "evidence_storage_pending", "message": "Metadata đã được giữ nhưng file chưa hoàn tất; cần phục hồi/đối soát trước khi retry."})
    logger.info("Camera evidence stored", extra={"visit_id": str(visit_id), "evidence_id": str(evidence_id), "size_bytes": len(body)})
    return {"evidence": _evidence_out(row), "duplicate": False}


def _attach_weights_and_thumbnails(db: Session, items: list[dict], visit_rows: list) -> None:
    if not items or not visit_rows:
        return
    visit_ids = [row.id for row, *_ in visit_rows]
    evidences = db.execute(
        select(CameraEvidence.visit_id, CameraEvidence.id, CameraEvidence.kind)
        .where(CameraEvidence.visit_id.in_(visit_ids), CameraEvidence.storage_state == "stored")
        .order_by(CameraEvidence.visit_id,
                  case({"plate_crop": 1, "vehicle_crop": 2, "overview": 3}, value=CameraEvidence.kind, else_=4))
    ).all()
    thumbnails = {}
    for v_id, e_id, _ in evidences:
        if v_id not in thumbnails:
            thumbnails[v_id] = f"/api/vehicle-pilot/evidence/{e_id}/content"
    
    from app.modules.scale_ingestion.models import ScaleAgent, ScaleSignal
    visit_times = [(row.id, row.facility_id, row.observed_at_utc or row.created_at) for row, *_ in visit_rows]
    nearest_weights = {}
    if visit_times:
        min_time = min(t for _, _, t in visit_times) - timedelta(minutes=5)
        max_time = max(t for _, _, t in visit_times) + timedelta(minutes=5)
        facility_ids = list({f for _, f, _ in visit_times})
        signals = db.execute(
            select(ScaleAgent.facility_id, ScaleSignal.observed_at_utc, ScaleSignal.weight_kg)
            .join(ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id)
            .where(ScaleAgent.facility_id.in_(facility_ids),
                   ScaleSignal.observed_at_utc >= min_time,
                   ScaleSignal.observed_at_utc <= max_time)
            .order_by(ScaleSignal.observed_at_utc.asc())
        ).all()
        for v_id, fac_id, v_time in visit_times:
            best_sig = None
            best_diff = timedelta(minutes=5)
            for s_fac, s_time, s_wt in signals:
                if s_fac == fac_id:
                    diff = abs(s_time - v_time)
                    if diff <= best_diff:
                        best_diff = diff
                        best_sig = s_wt
            if best_sig is not None:
                nearest_weights[v_id] = format(best_sig, ".3f")
                
    for item, (row, *_) in zip(items, visit_rows):
        item["thumbnail_url"] = thumbnails.get(row.id)
        raw_meta_wt = row.metadata_json.get("weight_kg")
        item["scale_weight_kg"] = nearest_weights.get(row.id) or (str(raw_meta_wt) if raw_meta_wt else None)


@router.get("/visits")
def list_visits(request: Request, facility_id: int | None = Query(None, ge=1), status: str | None = None,
                observed_from: datetime | None = None, observed_to: datetime | None = None,
                plate: str | None = Query(None, max_length=64), needs_review: bool = False,
                page: int = Query(1, ge=1, le=10000), page_size: int = Query(30, ge=1, le=100),
                db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    if facility_id is not None and facility_id not in scope:
        raise HTTPException(404, "Không tìm thấy cơ sở được phép xem.")
    where = [CameraVisit.facility_id.in_([facility_id] if facility_id is not None else scope)]
    if status:
        where.append(CameraVisit.status == status)
    observed = func.coalesce(CameraVisit.observed_at_utc, CameraVisit.created_at)
    if observed_from is not None:
        if observed_from.tzinfo is None:
            raise HTTPException(422, "observed_from phải có múi giờ.")
        where.append(observed >= observed_from.astimezone(timezone.utc))
    if observed_to is not None:
        if observed_to.tzinfo is None:
            raise HTTPException(422, "observed_to phải có múi giờ.")
        where.append(observed <= observed_to.astimezone(timezone.utc))
    if observed_from is not None and observed_to is not None and observed_from > observed_to:
        raise HTTPException(422, "Thời gian bắt đầu phải trước hoặc bằng thời gian kết thúc.")

    latest_prediction = (select(VehiclePrediction.visit_id.label("visit_id"),
        VehiclePrediction.normalized_text.label("normalized_text"), VehiclePrediction.visible_text.label("visible_text"),
        VehiclePrediction.raw_text.label("raw_text"), VehiclePrediction.identifier_kind.label("identifier_kind"),
        VehiclePrediction.source.label("source"),
        func.row_number().over(partition_by=VehiclePrediction.visit_id,
            order_by=(VehiclePrediction.created_at.desc(), VehiclePrediction.id.desc())).label("row_number"))
        .where(VehiclePrediction.identifier_kind.in_(("tractor_plate", "trailer_plate")))
        .subquery())
    latest_confirmation = (select(VisitConfirmation.visit_id.label("visit_id"),
        VisitConfirmation.decision["action"].as_string().label("action"),
        VisitConfirmation.decision["confirmed_text"].as_string().label("confirmed_text"),
        VisitConfirmation.decision["identifier_kind"].as_string().label("identifier_kind"),
        func.row_number().over(partition_by=VisitConfirmation.visit_id,
            order_by=(VisitConfirmation.version.desc(), VisitConfirmation.created_at.desc())).label("row_number"))
        .subquery())
    pred = latest_prediction.alias("latest_prediction")
    conf = latest_confirmation.alias("latest_confirmation")
    query = (select(CameraVisit, pred.c.normalized_text, pred.c.visible_text, pred.c.raw_text,
        pred.c.identifier_kind, pred.c.source, conf.c.action, conf.c.confirmed_text, conf.c.identifier_kind)
        .outerjoin(pred, and_(pred.c.visit_id == CameraVisit.id, pred.c.row_number == 1))
        .outerjoin(conf, and_(conf.c.visit_id == CameraVisit.id, conf.c.row_number == 1))
        .where(*where))
    confirmed = and_(conf.c.action.in_(("confirmed", "corrected")),
        conf.c.identifier_kind.in_(("tractor_plate", "trailer_plate")))
    displayed = case((confirmed, conf.c.confirmed_text), else_=func.coalesce(pred.c.normalized_text, pred.c.visible_text, pred.c.raw_text))
    if needs_review:
        query = query.where(or_(conf.c.action.is_(None), ~confirmed))
    if plate and plate.strip():
        query = query.where(displayed.ilike(f"%{plate.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(CameraVisit.created_at.desc(), CameraVisit.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for row, normalized, visible, raw, identifier_kind, source, action, confirmed_text, conf_kind in rows:
        item = _visit_out(row)
        is_confirmed = action in ("confirmed", "corrected") and conf_kind in ("tractor_plate", "trailer_plate")
        item.update(plate_text=(confirmed_text if is_confirmed else normalized or visible or raw),
            plate_source=("confirmed" if is_confirmed and confirmed_text else "suggestion" if normalized or visible or raw else "unknown"),
            review_state=("confirmed" if is_confirmed and confirmed_text else "unknown" if action == "unknown" else "needs_review"),
            identifier_kind=identifier_kind, prediction_source=source)
        items.append(item)
    _attach_weights_and_thumbnails(db, items, rows)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/visits/summary")
def visit_summary(request: Request, facility_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    if facility_id is not None and facility_id not in scope:
        raise HTTPException(404, "Không tìm thấy cơ sở được phép xem.")
    facilities = [facility_id] if facility_id is not None else scope
    now = utcnow()
    local_now = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    local_end = local_start + timedelta(days=1)
    confirmed_action = VisitConfirmation.decision["action"].as_string().in_(("confirmed", "corrected"))
    latest_confirmation = (select(VisitConfirmation.visit_id.label("visit_id"),
        VisitConfirmation.decision["action"].as_string().label("action"),
        VisitConfirmation.decision["confirmed_text"].as_string().label("confirmed_text"),
        VisitConfirmation.decision["identifier_kind"].as_string().label("identifier_kind"),
        func.row_number().over(partition_by=VisitConfirmation.visit_id,
            order_by=(VisitConfirmation.version.desc(), VisitConfirmation.created_at.desc())).label("row_number"))
        .subquery())
    latest_prediction = (select(VehiclePrediction.visit_id.label("visit_id"),
        func.coalesce(VehiclePrediction.normalized_text, VehiclePrediction.visible_text, VehiclePrediction.raw_text).label("plate"),
        func.row_number().over(partition_by=VehiclePrediction.visit_id,
            order_by=(VehiclePrediction.created_at.desc(), VehiclePrediction.id.desc())).label("row_number"))
        .where(VehiclePrediction.identifier_kind.in_(("tractor_plate", "trailer_plate")))
        .subquery())
    conf = latest_confirmation.alias("summary_confirmation")
    pred = latest_prediction.alias("summary_prediction")
    base = (select(CameraVisit.id, CameraVisit.created_at, conf.c.action, conf.c.confirmed_text,
        conf.c.identifier_kind, pred.c.plate)
        .outerjoin(conf, and_(conf.c.visit_id == CameraVisit.id, conf.c.row_number == 1))
        .outerjoin(pred, and_(pred.c.visit_id == CameraVisit.id, pred.c.row_number == 1))
        .where(CameraVisit.facility_id.in_(facilities)).subquery())
    today_count = db.scalar(select(func.count()).select_from(base).where(base.c.created_at >= local_start, base.c.created_at < local_end)) or 0
    plate_confirmed = and_(base.c.action.in_(("confirmed", "corrected")), base.c.identifier_kind.in_(("tractor_plate", "trailer_plate")))
    not_plate_confirmed = or_(base.c.action.is_(None), ~plate_confirmed)
    unknown_count = db.scalar(select(func.count()).select_from(base).where(or_(
        and_(plate_confirmed, or_(base.c.confirmed_text.is_(None), base.c.confirmed_text == "")),
        and_(not_plate_confirmed, or_(base.c.plate.is_(None), base.c.plate == ""))))) or 0
    review_count = db.scalar(select(func.count()).select_from(base).where(not_plate_confirmed)) or 0
    return {"camera_visits_today": today_count, "plate_unknown": unknown_count,
        "needs_review": review_count, "server_time_utc": now}


@router.get("/visits/trips")
def list_trips(request: Request, facility_id: int | None = Query(None, ge=1),
               day: str | None = Query(None, description="YYYY-MM-DD in Asia/Ho_Chi_Minh"),
               db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    if facility_id is not None and facility_id not in scope:
        raise HTTPException(404, "Không tìm thấy cơ sở được phép xem.")
    facilities = [facility_id] if facility_id is not None else scope

    vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    if day:
        try:
            target_date = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, "Định dạng ngày phải là YYYY-MM-DD.")
    else:
        target_date = utcnow().astimezone(vn_tz).date()

    start_local = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=vn_tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    latest_prediction = (select(VehiclePrediction.visit_id.label("visit_id"),
        VehiclePrediction.normalized_text.label("normalized_text"), VehiclePrediction.visible_text.label("visible_text"),
        VehiclePrediction.raw_text.label("raw_text"), VehiclePrediction.identifier_kind.label("identifier_kind"),
        VehiclePrediction.source.label("source"),
        func.row_number().over(partition_by=VehiclePrediction.visit_id,
            order_by=(VehiclePrediction.created_at.desc(), VehiclePrediction.id.desc())).label("row_number"))
        .where(VehiclePrediction.identifier_kind.in_(("tractor_plate", "trailer_plate")))
        .subquery())
    latest_confirmation = (select(VisitConfirmation.visit_id.label("visit_id"),
        VisitConfirmation.decision["action"].as_string().label("action"),
        VisitConfirmation.decision["confirmed_text"].as_string().label("confirmed_text"),
        VisitConfirmation.decision["identifier_kind"].as_string().label("identifier_kind"),
        func.row_number().over(partition_by=VisitConfirmation.visit_id,
            order_by=(VisitConfirmation.version.desc(), VisitConfirmation.created_at.desc())).label("row_number"))
        .subquery())
    pred = latest_prediction.alias("trip_pred")
    conf = latest_confirmation.alias("trip_conf")

    observed = func.coalesce(CameraVisit.observed_at_utc, CameraVisit.created_at)
    query = (select(CameraVisit, pred.c.normalized_text, pred.c.visible_text, pred.c.raw_text,
                    pred.c.identifier_kind, pred.c.source, conf.c.action, conf.c.confirmed_text, conf.c.identifier_kind)
             .outerjoin(pred, and_(pred.c.visit_id == CameraVisit.id, pred.c.row_number == 1))
             .outerjoin(conf, and_(conf.c.visit_id == CameraVisit.id, conf.c.row_number == 1))
             .where(CameraVisit.facility_id.in_(facilities), observed >= start_utc, observed < end_utc)
             .order_by(observed.asc(), CameraVisit.id.asc()))

    rows = db.execute(query).all()
    visit_items = []
    for row, normalized, visible, raw, identifier_kind, source, action, confirmed_text, conf_kind in rows:
        item = _visit_out(row)
        is_confirmed = action in ("confirmed", "corrected") and conf_kind in ("tractor_plate", "trailer_plate")
        plate = confirmed_text if is_confirmed and confirmed_text else normalized or visible or raw
        item.update(plate_text=plate or "Chưa rõ biển",
                    plate_source=("confirmed" if is_confirmed and confirmed_text else "suggestion" if plate else "unknown"),
                    review_state=("confirmed" if is_confirmed and confirmed_text else "unknown" if action == "unknown" else "needs_review"),
                    identifier_kind=identifier_kind, prediction_source=source)
        visit_items.append(item)

    _attach_weights_and_thumbnails(db, visit_items, rows)

    plate_groups: dict[str, list[dict]] = {}
    for item in visit_items:
        raw_plate = (item.get("plate_text") or "").strip()
        clean_key = raw_plate.replace(" ", "").replace("-", "").replace(".", "").upper() if raw_plate and raw_plate != "Chưa rõ biển" else f"unknown_{item['visit_id']}"
        plate_groups.setdefault(clean_key, []).append(item)

    trips = []
    total_import_kg = Decimal("0")
    total_export_kg = Decimal("0")
    in_yard_count = 0
    completed_count = 0

    for clean_key, group in plate_groups.items():
        for i in range(0, len(group), 2):
            v1 = group[i]
            v2 = group[i + 1] if i + 1 < len(group) else None

            w1 = Decimal(v1["scale_weight_kg"]) if v1.get("scale_weight_kg") else None
            w2 = Decimal(v2["scale_weight_kg"]) if v2 and v2.get("scale_weight_kg") else None

            trip_type = "unknown"
            goods_weight_kg = None
            status = "in_yard"

            if v2 is not None:
                status = "completed"
                completed_count += 1
                if w1 is not None and w2 is not None:
                    if w1 > w2:
                        trip_type = "import"
                        goods_weight_kg = w1 - w2
                        total_import_kg += goods_weight_kg
                    elif w1 < w2:
                        trip_type = "export"
                        goods_weight_kg = w2 - w1
                        total_export_kg += goods_weight_kg
                    else:
                        trip_type = "reweigh"
                        goods_weight_kg = Decimal("0")
            else:
                status = "in_yard"
                in_yard_count += 1

            trip_id = f"{v1['visit_id']}_{v2['visit_id'] if v2 else 'pending'}"
            trips.append({
                "trip_id": trip_id,
                "plate_text": v1.get("plate_text") or (v2.get("plate_text") if v2 else "Chưa rõ biển"),
                "status": status,
                "trip_type": trip_type,
                "goods_weight_kg": format(goods_weight_kg, ".3f") if goods_weight_kg is not None else None,
                "first_visit": v1,
                "second_visit": v2,
                "created_at": v1["created_at"],
            })

    trips.sort(key=lambda t: t["second_visit"]["created_at"] if t["second_visit"] else t["first_visit"]["created_at"], reverse=True)

    return {
        "trips": trips,
        "total_trips": len(trips),
        "kpis": {
            "total_import_kg": format(total_import_kg, ".3f"),
            "total_export_kg": format(total_export_kg, ".3f"),
            "total_import_tons": format(total_import_kg / Decimal("1000"), ".3f"),
            "total_export_tons": format(total_export_kg / Decimal("1000"), ".3f"),
            "in_yard_count": in_yard_count,
            "completed_count": completed_count,
            "total_trips": len(trips),
        },
        "date": target_date.isoformat(),
        "total_visits_today": len(visit_items),
    }


@router.post("/visits/{visit_id}/gemini-ocr")
def gemini_ocr(visit_id: UUID, request: Request, db: Session = Depends(get_db)):
    actor, scope = _identity(request, db, write=True)
    visit = _visit(db, visit_id, scope, lock=True)

    settings = get_settings()
    api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(400, "Chưa cấu hình GEMINI_API_KEY trong hệ thống.")

    evidence = db.scalar(
        select(CameraEvidence)
        .where(CameraEvidence.visit_id == visit.id, CameraEvidence.storage_state == "stored")
        .order_by(case({"plate_crop": 1, "vehicle_crop": 2, "overview": 3}, value=CameraEvidence.kind, else_=4))
        .limit(1)
    )
    if evidence is None:
        raise HTTPException(404, "Không tìm thấy ảnh bằng chứng để nhận diện.")

    try:
        image_bytes = storage.read(evidence.object_key)
    except Exception as e:
        logger.error(f"Không thể đọc file ảnh bằng chứng: {e}")
        raise HTTPException(500, "Không tìm thấy tệp ảnh trên ổ cứng.")

    base64_data = base64.b64encode(image_bytes).decode("utf-8")

    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt_text = (
        "Bạn là chuyên gia nhận diện biển số xe cơ giới tại Việt Nam. "
        "Hãy đọc CHÍNH XÁC biển số xe trong bức ảnh này. "
        "Chỉ trả về chuỗi biển số chuẩn hóa (ví dụ: 49C-026.55, 51D-123.45, 29H-987.65, 72A-12345). "
        "Nếu biển số có 2 dòng (dòng trên mã tỉnh, dòng dưới số thứ tự), hãy ghép lại thành 1 chuỗi hoàn chỉnh. "
        "Tuyệt đối không giải thích, không thêm dấu ngoặc kép hay markdown. "
        "Nếu hoàn toàn không có biển số trong ảnh hoặc không thể đọc được, chỉ trả về: UNKNOWN"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": evidence.content_type,
                            "data": base64_data
                        }
                    }
                ]
            }
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw_text = raw_text.replace("```", "").replace("\n", " ").strip()
    except Exception as e:
        logger.error(f"Lỗi khi gọi Gemini API: {e}")
        raise HTTPException(502, f"Không thể gọi Google Gemini API: {e}")

    reading_status = "readable" if raw_text and raw_text != "UNKNOWN" else "unreadable"
    clean_plate = raw_text if reading_status == "readable" else None
    normalized = clean_plate.replace(" ", "").replace("-", "").replace(".", "").upper() if clean_plate else None

    prediction = VehiclePrediction(
        id=uuid4(),
        visit_id=visit.id,
        evidence_id=evidence.id,
        source="api",
        identifier_kind="tractor_plate",
        raw_text=clean_plate,
        normalized_text=normalized,
        visible_text=clean_plate,
        reading_status=reading_status,
        model_version=model,
        prompt_version="v1-vn-plate",
        score_info={"provider": "google_gemini", "model": model},
        raw_result={"gemini_response": raw_text},
        created_at=utcnow(),
    )
    db.add(prediction)
    _audit(db, visit, actor, "gemini_ocr_performed", {"detected_text": clean_plate, "model": model})
    db.commit()

    return {
        "visit_id": str(visit.id),
        "plate_text": clean_plate or "Chưa rõ biển",
        "normalized_text": normalized,
        "reading_status": reading_status,
        "source": "api",
        "model": model,
    }


@router.get("/visits/{visit_id}")
def visit_detail(visit_id: UUID, request: Request, db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    visit = _visit(db, visit_id, scope)
    evidence = db.scalars(select(CameraEvidence).where(CameraEvidence.visit_id == visit_id)
                          .order_by(CameraEvidence.received_at_utc, CameraEvidence.id)).all()
    predictions = db.scalars(select(VehiclePrediction).where(VehiclePrediction.visit_id == visit_id)
                             .order_by(VehiclePrediction.created_at, VehiclePrediction.id)).all()
    audit_events = db.scalars(select(VehiclePilotAuditEvent).where(VehiclePilotAuditEvent.visit_id == visit_id)
                              .order_by(VehiclePilotAuditEvent.created_at, VehiclePilotAuditEvent.id)).all()
    confirmations = db.scalars(select(VisitConfirmation).where(VisitConfirmation.visit_id == visit_id)
                               .order_by(VisitConfirmation.version)).all()
    jobs = db.scalars(select(VehicleAIJob).where(VehicleAIJob.visit_id == visit_id)
                      .order_by(VehicleAIJob.created_at.desc())).all()
    nearby_signals = []
    if visit.observed_at_utc is not None:
        from app.modules.scale_ingestion.models import ScaleAgent, ScaleSignal
        nearby_signals = db.execute(select(ScaleSignal, ScaleAgent).join(ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id)
            .where(ScaleAgent.facility_id == visit.facility_id,
                   ScaleSignal.observed_at_utc >= visit.observed_at_utc - timedelta(minutes=5),
                   ScaleSignal.observed_at_utc <= visit.observed_at_utc + timedelta(minutes=5))
            .order_by(ScaleSignal.observed_at_utc.desc(), ScaleSignal.id.desc()).limit(10)).all()
    return {
        "visit": _visit_out(visit), "evidence": [_evidence_out(item) for item in evidence],
        "predictions": [{"prediction_id": str(p.id), "evidence_id": str(p.evidence_id) if p.evidence_id else None,
            "source": p.source, "identifier_kind": p.identifier_kind, "raw_text": p.raw_text,
            "normalized_text": p.normalized_text, "visible_text": p.visible_text, "reading_status": p.reading_status,
            "model_version": p.model_version, "prompt_version": p.prompt_version, "score_info": p.score_info,
            "raw_result": p.raw_result, "created_at": p.created_at} for p in predictions],
        "confirmations": [{"confirmation_id": str(c.id), "version": c.version, "user_id": c.user_id,
            "decision": c.decision, "note": c.note, "created_at": c.created_at} for c in confirmations],
        "audit": [{"event_id": str(event.id), "actor_user_id": event.actor_user_id, "event": event.event,
            "details": event.details, "created_at": event.created_at} for event in audit_events],
        "nearby_scale_signals": [{"event_id": str(s.event_id), "agent_id": s.agent_id, "sequence": str(s.sequence),
            "weight_kg": format(s.weight_kg, ".3f"), "observed_at_utc": s.observed_at_utc,
            "received_at_utc": s.received_at_utc, "scale_code": a.scale_code,
            "association": "time_proximity_only_not_linked"} for s, a in nearby_signals],
        "ai_jobs": [{"job_id": str(j.id), "provider": j.provider, "model_id": j.model_id, "status": j.status,
            "attempts": j.attempts, "queued_at": j.queued_at, "deadline_at": j.deadline_at,
            "reserved_usd": str(j.reserved_usd), "actual_usd": str(j.actual_usd) if j.actual_usd is not None else None,
            "error_code": j.error_code} for j in jobs],
    }


@router.get("/evidence/{evidence_id}/content")
def evidence_content(evidence_id: UUID, request: Request, db: Session = Depends(get_db)):
    _, scope = _identity(request, db)
    row = db.scalar(select(CameraEvidence).where(CameraEvidence.id == evidence_id, CameraEvidence.facility_id.in_(scope)))
    if row is None:
        raise HTTPException(404, "Không tìm thấy bằng chứng trong phạm vi cơ sở được phép.")
    if row.storage_state != "stored":
        raise HTTPException(503, detail={"code": "evidence_unavailable", "message": "File bằng chứng chưa sẵn sàng; cần đối soát."})
    try:
        body = storage.read(row.object_key)
    except FileNotFoundError:
        row.storage_state = "missing"
        db.commit()
        raise HTTPException(503, detail={"code": "evidence_missing", "message": "Thiếu file bằng chứng; đã đánh dấu để phục hồi."})
    if hashlib.sha256(body).hexdigest() != row.sha256:
        raise HTTPException(503, detail={"code": "evidence_integrity_error", "message": "Hash file khác manifest; file bị cách ly khỏi giao diện."})
    return Response(body, media_type=row.content_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/visits/{visit_id}/predictions", status_code=201)
def append_prediction(visit_id: UUID, payload: PredictionCreate, request: Request, db: Session = Depends(get_db)):
    user, scope = _identity(request, db, write=True)
    visit = _visit(db, visit_id, scope)
    if len(json.dumps(payload.raw_result, ensure_ascii=False)) > 65_536 or len(json.dumps(payload.score_info, ensure_ascii=False)) > 8_192:
        raise HTTPException(413, "Kết quả prediction vượt giới hạn lưu trữ.")
    if payload.evidence_id is not None:
        evidence = db.scalar(select(CameraEvidence).where(CameraEvidence.id == payload.evidence_id,
            CameraEvidence.visit_id == visit_id, CameraEvidence.storage_state == "stored"))
        if evidence is None:
            raise HTTPException(422, "evidence_id không thuộc lượt hoặc file chưa sẵn sàng.")
    existing = db.get(VehiclePrediction, payload.prediction_id)
    content = payload.model_dump(exclude={"prediction_id"})
    if existing:
        same = existing.visit_id == visit_id and existing.evidence_id == payload.evidence_id and existing.source == payload.source and existing.raw_result == payload.raw_result and existing.raw_text == payload.raw_text
        if not same:
            raise HTTPException(409, detail={"code": "prediction_conflict", "message": "prediction_id đã được dùng cho nội dung khác."})
        return {"prediction_id": str(existing.id), "duplicate": True}
    row = VehiclePrediction(id=payload.prediction_id, visit_id=visit_id, **content)
    db.add(row)
    _audit(db, visit, user, "prediction_appended", {"prediction_id": str(row.id), "source": row.source,
        "identifier_kind": row.identifier_kind, "evidence_id": str(row.evidence_id) if row.evidence_id else None,
        "model_version": row.model_version, "prompt_version": row.prompt_version})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "prediction_id đã được ghi đồng thời.")
    return {"prediction_id": str(row.id), "duplicate": False}


@router.post("/visits/{visit_id}/confirmations", status_code=201)
def confirm_visit(visit_id: UUID, payload: ConfirmationCreate, request: Request, db: Session = Depends(get_db)):
    user, scope = _identity(request, db, write=True)
    visit = _visit(db, visit_id, scope, lock=True)
    if payload.expected_version != visit.version:
        raise HTTPException(409, detail={"code": "version_conflict", "current_version": visit.version, "message": "Lượt đã được người khác cập nhật; tải lại trước khi xác nhận."})
    next_version = visit.version + 1
    row = VisitConfirmation(id=uuid4(), visit_id=visit.id, facility_id=visit.facility_id,
                            user_id=user.id, version=next_version, decision=payload.decision.model_dump(mode="json"),
                            note=payload.note, created_at=utcnow())
    visit.version = next_version
    visit.updated_at = utcnow()
    db.add(row)
    _audit(db, visit, user, "visit_confirmed", {"confirmation_id": str(row.id), "version": next_version,
        "action": payload.decision.action, "identifier_kind": payload.decision.identifier_kind,
        "evidence_id": str(payload.decision.evidence_id) if payload.decision.evidence_id else None})
    db.commit()
    return {"confirmation_id": str(row.id), "version": row.version, "created_at": row.created_at}


@router.post("/visits/{visit_id}/ai-jobs", status_code=202)
def enqueue_ai_job(visit_id: UUID, request: Request, evidence_ids: list[UUID], db: Session = Depends(get_db)):
    """Only the safe mock adapter is enabled until provider, model, privacy and pricing are verified."""
    user, scope = _identity(request, db, write=True)
    visit = _visit(db, visit_id, scope, lock=True)
    settings = get_settings()
    if settings.pilot_ai_mode != "mock":
        raise HTTPException(503, detail={"code": "ai_provider_not_configured", "message": "API AI thật đang khóa cho tới khi xác thực key, model, chính sách ảnh và giá."})
    if not evidence_ids or len(evidence_ids) > 7 or len(set(evidence_ids)) != len(evidence_ids):
        raise HTTPException(422, "Chọn từ 1 đến 7 evidence khác nhau cho job.")
    evidence = db.scalars(select(CameraEvidence).where(CameraEvidence.visit_id == visit_id,
        CameraEvidence.id.in_(evidence_ids), CameraEvidence.storage_state == "stored")).all()
    if len(evidence) != len(evidence_ids):
        raise HTTPException(422, "Mọi evidence phải thuộc đúng visit và đang sẵn sàng.")
    evidence_hash = hashlib.sha256("".join(sorted(item.sha256 for item in evidence)).encode()).hexdigest()
    idempotency_key = hashlib.sha256(f"{visit_id}:{evidence_hash}:mock:v1".encode()).hexdigest()
    existing = db.scalar(select(VehicleAIJob).where(VehicleAIJob.idempotency_key == idempotency_key))
    if existing:
        return {"job_id": str(existing.id), "status": existing.status, "duplicate": True}
    db.execute(text("SELECT pg_advisory_xact_lock(721934820144)"))
    prior_jobs = db.scalars(select(VehicleAIJob).where(VehicleAIJob.visit_id == visit_id)).all()
    reserved_visit_attempts = sum(job.attempts + (1 if job.status in {"queued", "claimed"} else 0) for job in prior_jobs)
    if reserved_visit_attempts >= 3:
        raise HTTPException(429, detail={"code": "ai_visit_attempt_limit", "message": "Đã đạt tối đa 3 attempt đã chạy/đang chờ cho visit này."})
    active_count = db.scalar(select(func.count()).select_from(VehicleAIJob).where(VehicleAIJob.status.in_(["queued", "claimed"]))) or 0
    if active_count >= settings.pilot_ai_queue_limit:
        raise HTTPException(429, detail={"code": "ai_queue_full", "message": "Hàng đợi API AI đã đầy; có thể tiếp tục xác nhận thủ công."})
    today = datetime.now(timezone(timedelta(hours=7))).date()
    day_start = datetime.combine(today, datetime.min.time(), timezone(timedelta(hours=7))).astimezone(timezone.utc)
    day_end = day_start + timedelta(days=1)
    day_slots = db.scalar(select(func.count()).select_from(VehicleAIJob).where(
        VehicleAIJob.queued_at >= day_start, VehicleAIJob.queued_at < day_end)) or 0
    if day_slots >= 300:
        raise HTTPException(429, detail={"code": "ai_daily_limit", "message": "Đã đạt giới hạn attempt pilot trong ngày VN."})
    now = utcnow()
    job = VehicleAIJob(id=uuid4(), visit_id=visit_id, provider="mock", model_id=None, prompt_version="mock-v1",
        evidence_hash=evidence_hash, idempotency_key=idempotency_key, evidence_ids=[str(item) for item in evidence_ids],
        status="queued", attempts=0, queued_at=now, deadline_at=now + timedelta(seconds=30), reserved_usd=Decimal("0"))
    db.add(job)
    _audit(db, visit, user, "mock_ai_job_queued", {"job_id": str(job.id), "evidence_hash": evidence_hash, "provider": "mock"})
    db.commit()
    logger.info("Vehicle AI mock job queued", extra={"visit_id": str(visit_id), "job_id": str(job.id)})
    return {"job_id": str(job.id), "status": job.status, "duplicate": False, "billable": False}


@router.get("/heartbeat/scale-agents")
def scale_agent_status(request: Request, facility_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    """Expose heartbeat receipt and reader state within the current D01 facility scope."""
    user, scope = _identity(request, db)
    if facility_id is not None and facility_id not in scope:
        raise HTTPException(404, "Không tìm thấy cơ sở được phép xem.")
    from app.modules.scale_ingestion.models import ScaleAgent, ScaleAgentHeartbeat
    rows = db.execute(select(ScaleAgent, Facility, ScaleAgentHeartbeat)
        .join(Facility, Facility.id == ScaleAgent.facility_id)
        .outerjoin(ScaleAgentHeartbeat, ScaleAgentHeartbeat.agent_id == ScaleAgent.agent_id)
        .where(ScaleAgent.facility_id.in_([facility_id] if facility_id else scope))
        .order_by(Facility.code, ScaleAgent.scale_code, ScaleAgent.agent_id)).all()
    now = utcnow()
    items = []
    for agent, facility, heartbeat in rows:
        current_v1 = heartbeat is not None and heartbeat.schema_version == 1 and heartbeat.heartbeat_id is not None
        age = max(0.0, (now - heartbeat.received_at_utc).total_seconds()) if heartbeat else None
        if not agent.is_active:
            state = "disabled"
        elif heartbeat is None:
            state = "never_received"
        elif not current_v1:
            state = "legacy_snapshot"
        elif age is not None and age <= 90:
            state = "communicating"
        elif age is not None and age <= 180:
            state = "delayed"
        else:
            state = "lost"
        item = {
            "agent_id": agent.agent_id,
            "scale_code": agent.scale_code,
            "facility_id": facility.id,
            "facility_name": facility.name,
            "agent_active": agent.is_active,
            "received_at_utc": heartbeat.received_at_utc if heartbeat else None,
            "age_seconds": int(age) if age is not None else None,
            "state": state,
            "reader_status": heartbeat.reader_status if current_v1 else None,
            # Operational delivery status is useful to staff as well as admins.
            # Expose safe meaning; detailed error codes remain admin-only.
            "signal_delivery_state": (
                "paused" if current_v1 and heartbeat.last_error_code == "SIGNAL_SENDER_PAUSED"
                else "pending" if current_v1 and heartbeat.pending_event_count > 0
                else "no_pending" if current_v1 and heartbeat.pending_event_count == 0
                else "unknown"
            ),
            "pending_signal_count": heartbeat.pending_event_count if current_v1 else None,
        }
        if user.role == "admin":
            item.update({
                "schema_version": heartbeat.schema_version if heartbeat else None,
                "heartbeat_id": str(heartbeat.heartbeat_id) if current_v1 else None,
                "heartbeat_sequence": str(heartbeat.heartbeat_sequence) if current_v1 else None,
                "agent_version": heartbeat.agent_version if current_v1 else None,
                "process_uptime_seconds": heartbeat.process_uptime_seconds if current_v1 else None,
                "vendor_process_running": heartbeat.vendor_process_running if current_v1 else None,
                "last_successful_read_at_utc": heartbeat.last_successful_read_at_utc if current_v1 else None,
                "pending_event_count": heartbeat.pending_event_count if current_v1 else None,
                "last_signal_ack_at_utc": heartbeat.last_signal_ack_at_utc if current_v1 else None,
                "last_error_code": heartbeat.last_error_code if current_v1 else None,
            })
        items.append(item)
    return {"items": items, "server_time_utc": now}
