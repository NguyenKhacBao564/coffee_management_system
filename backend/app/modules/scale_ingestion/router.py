import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.models import utcnow
from app.modules.facilities.models import Facility
from app.modules.scale_ingestion.models import ScaleAgent, ScaleSignal
from app.modules.scale_ingestion.models import ScaleAgentHeartbeat
from app.modules.scale_ingestion.schemas import ScaleBatchIn, ScaleHeartbeatIn

router = APIRouter(prefix="/api/scale-ingestion", tags=["scale-ingestion"])


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _agent_from_bearer(request: Request, db: Session = Depends(get_db)) -> ScaleAgent:
    header = request.headers.get("authorization", "")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(status_code=401, detail={"code": "invalid_bearer", "message": "Cần Bearer token thiết bị hợp lệ."}, headers={"WWW-Authenticate": "Bearer"})
    agent = db.scalar(select(ScaleAgent).where(ScaleAgent.token_hash == _digest(parts[1])))
    if agent is None:
        raise HTTPException(status_code=401, detail={"code": "invalid_bearer", "message": "Cần Bearer token thiết bị hợp lệ."}, headers={"WWW-Authenticate": "Bearer"})
    facility_active = db.scalar(select(Facility.is_active).where(Facility.id == agent.facility_id))
    if not agent.is_active or not facility_active:
        raise HTTPException(status_code=403, detail={"code": "agent_inactive", "message": "Agent hoặc cơ sở đã bị vô hiệu hóa."})
    return agent


def _conflict(message: str, code: str = "event_conflict") -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": message})


@router.post("/batches")
def ingest_batch(payload: ScaleBatchIn, request: Request, agent: ScaleAgent = Depends(_agent_from_bearer), db: Session = Depends(get_db)):
    if str(payload.agent_id) != agent.agent_id:
        raise HTTPException(status_code=403, detail={"code": "agent_mismatch", "message": "agent_id không khớp với token thiết bị."})

    event_ids: set[UUID] = set()
    sequences: set[int] = set()
    now = utcnow()
    future_limit = now + timedelta(seconds=get_settings().scale_ingestion_max_future_seconds)
    normalized: list[tuple[object, Decimal]] = []
    for index, event in enumerate(payload.events):
        if event.event_id in event_ids:
            raise HTTPException(status_code=422, detail={"code": "duplicate_event_in_batch", "event_index": index, "event_id": str(event.event_id), "message": "event_id phải là duy nhất trong batch."})
        if event.sequence in sequences:
            raise HTTPException(status_code=422, detail={"code": "duplicate_sequence_in_batch", "event_index": index, "event_id": str(event.event_id), "message": "sequence phải là duy nhất trong batch."})
        event_ids.add(event.event_id); sequences.add(event.sequence)
        if event.observed_at_utc > future_limit:
            raise HTTPException(status_code=422, detail={"code": "timestamp_too_far_in_future", "event_index": index, "event_id": str(event.event_id), "message": "observed_at_utc vượt ngưỡng thời gian tương lai cho phép."})
        normalized.append((event, Decimal(event.weight_kg)))

    inserted_count = 0
    duplicate_count = 0
    try:
        for event, weight in normalized:
            values = {
                "agent_id": agent.agent_id,
                "event_id": event.event_id,
                "sequence": event.sequence,
                "observed_at_utc": event.observed_at_utc,
                "received_at_utc": utcnow(),
                "weight_kg": weight,
                "vendor_text": event.vendor_text,
                "source": event.source,
                "schema_version": payload.schema_version,
            }
            inserted = db.execute(pg_insert(ScaleSignal).values(**values).on_conflict_do_nothing().returning(ScaleSignal.id)).scalar_one_or_none()
            if inserted is not None:
                inserted_count += 1
                continue

            existing = list(db.scalars(select(ScaleSignal).where(
                ScaleSignal.agent_id == agent.agent_id,
                or_(ScaleSignal.event_id == event.event_id, ScaleSignal.sequence == event.sequence),
            )))
            if len(existing) != 1:
                db.rollback()
                raise _conflict("event_id hoặc sequence đã tồn tại với nội dung khác.")
            prior = existing[0]
            same_content = (
                prior.event_id == event.event_id
                and prior.sequence == event.sequence
                and prior.observed_at_utc == event.observed_at_utc
                and Decimal(prior.weight_kg) == weight
                and prior.vendor_text == event.vendor_text
                and prior.source == event.source
                and prior.schema_version == payload.schema_version
            )
            if not same_content:
                db.rollback()
                raise _conflict("event_id hoặc sequence đã được dùng cho nội dung khác.")
            duplicate_count += 1

        db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # Construct ACK only after the PostgreSQL transaction has committed.
    return {
        "schema_version": 1,
        "agent_id": agent.agent_id,
        "persisted": True,
        "acknowledged_event_ids": [str(event.event_id) for event in payload.events],
        "inserted_count": inserted_count,
        "duplicate_count": duplicate_count,
        "server_received_at_utc": utcnow(),
    }


@router.post("/heartbeat")
def heartbeat(payload: ScaleHeartbeatIn, agent: ScaleAgent = Depends(_agent_from_bearer), db: Session = Depends(get_db)):
    """Upsert one current agent snapshot; never creates or changes a scale signal."""
    locked_agent = db.scalar(select(ScaleAgent).where(ScaleAgent.agent_id == agent.agent_id).with_for_update())
    if locked_agent is None or not locked_agent.is_active:
        raise HTTPException(status_code=403, detail={"code": "agent_inactive", "message": "Agent đã bị vô hiệu hóa."})

    payload_sha256 = hashlib.sha256(json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    row = db.scalar(select(ScaleAgentHeartbeat).where(ScaleAgentHeartbeat.agent_id == agent.agent_id).with_for_update())
    now = utcnow()
    if row is not None and row.heartbeat_id == payload.heartbeat_id:
        if row.heartbeat_sequence != payload.heartbeat_sequence or row.payload_sha256 != payload_sha256:
            raise _conflict("heartbeat_id đã được dùng với nội dung khác.", "heartbeat_id_conflict")
        db.commit()
        return _heartbeat_ack(agent.agent_id, payload, row, applied=False, duplicate=True, stale=False)

    if row is not None and row.heartbeat_sequence is not None:
        if payload.heartbeat_sequence == row.heartbeat_sequence:
            raise _conflict("heartbeat_sequence đã được dùng cho heartbeat khác.", "heartbeat_sequence_conflict")
        if payload.heartbeat_sequence < row.heartbeat_sequence:
            snapshot_received_at = row.received_at_utc
            db.commit()
            return {
                "schema_version": 1, "agent_id": agent.agent_id,
                "heartbeat_id": str(payload.heartbeat_id), "heartbeat_sequence": payload.heartbeat_sequence,
                "acknowledged": True, "persisted": False, "applied": False,
                "duplicate": False, "stale": True,
                "received_at_utc": snapshot_received_at,
            }

    legacy_reader_status = {"starting": "unknown", "ok": "reading", "empty": "idle", "error": "error", "unavailable": "unknown"}[payload.reader_status]
    values = {
        "facility_id": locked_agent.facility_id,
        "source_status": legacy_reader_status,
        "pending_count": payload.pending_event_count,
        "last_sequence": None,
        "received_at_utc": now,
        "schema_version": payload.schema_version,
        "heartbeat_id": payload.heartbeat_id,
        "heartbeat_sequence": payload.heartbeat_sequence,
        "payload_sha256": payload_sha256,
        "agent_version": payload.agent_version,
        "process_uptime_seconds": payload.process_uptime_seconds,
        "vendor_process_running": payload.vendor_process_running,
        "reader_status": payload.reader_status,
        "last_successful_read_at_utc": payload.last_successful_read_at_utc,
        "pending_event_count": payload.pending_event_count,
        "last_signal_ack_at_utc": payload.last_signal_ack_at_utc,
        "last_error_code": payload.last_error_code,
    }
    if row is None:
        row = ScaleAgentHeartbeat(agent_id=agent.agent_id, **values)
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _heartbeat_ack(agent.agent_id, payload, row, applied=True, duplicate=False, stale=False)


def _heartbeat_ack(agent_id: str, payload: ScaleHeartbeatIn, row: ScaleAgentHeartbeat, *, applied: bool, duplicate: bool, stale: bool) -> dict:
    return {
        "schema_version": 1,
        "agent_id": agent_id,
        "heartbeat_id": str(payload.heartbeat_id),
        "heartbeat_sequence": payload.heartbeat_sequence,
        "acknowledged": True,
        "persisted": True,
        "applied": applied,
        "duplicate": duplicate,
        "stale": stale,
        "received_at_utc": row.received_at_utc,
    }
