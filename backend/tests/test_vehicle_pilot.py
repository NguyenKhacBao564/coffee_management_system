import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.database import SessionLocal, engine
from app.core.models import utcnow
from app.main import app
from app.modules.accounts.models import User
from app.modules.accounts.security import create_session
from app.modules.facilities.models import Facility
from app.modules.goods.models import GoodsTransaction
from app.modules.scale_ingestion.models import ScaleAgent, ScaleAgentHeartbeat, ScaleSignal
from app.modules.trips.models import Trip
from app.modules.vehicle_pilot.models import CameraEvidence, CameraVisit, VehiclePrediction, VisitConfirmation
from app.modules.vehicle_pilot.storage import EvidenceStorage
from app.modules.weighings.models import WeighEvent


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    assert engine.url.database.startswith("nhutung_d05m_test_"), "Pilot tests require the disposable database runner"
    with SessionLocal.begin() as db:
        db.execute(text("TRUNCATE facilities, users, auth_sessions, account_audit_logs, login_attempts RESTART IDENTITY CASCADE"))
    monkeypatch.setattr("app.modules.vehicle_pilot.router.storage", EvidenceStorage(tmp_path / "private-evidence"))
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def context():
    clients = {}
    with SessionLocal.begin() as db:
        a = Facility(code="PILOT-A", name="Pilot A", is_active=True)
        b = Facility(code="PILOT-B", name="Pilot B", is_active=True)
        db.add_all([a, b]); db.flush()
        for role, facilities in [("admin", []), ("manager", [a]), ("staff", [a]), ("staff_other", [b])]:
            user = User(username=f"pilot.{role}", display_name=role, role="staff" if role == "staff_other" else role,
                        password_hash="not-used-by-session-test", is_active=True, facilities=facilities)
            db.add(user); db.flush()
            _, cookie, csrf = create_session(db, user, facilities[0].id if facilities else None)
            client = TestClient(app); client.cookies.set("nt_session", cookie)
            clients[role] = {"client": client, "csrf": csrf, "user_id": user.id}
        ids = {"a": a.id, "b": b.id}
    return {"clients": clients, "ids": ids}


def create_visit(client, csrf, facility_id, visit_id=None, camera="camera-185"):
    payload = {"visit_id": str(visit_id or uuid4()), "facility_id": facility_id, "camera_id": camera,
        "source_mode": "replay", "source_ref": "video-abcd1234", "start_media_seconds": "10.250",
        "end_media_seconds": "14.000", "status": "needs_review", "metadata": {"video_sha256": "a" * 64}}
    response = client.post("/api/vehicle-pilot/visits", json=payload, headers={"X-CSRF-Token": csrf})
    return payload, response


def test_visit_idempotency_conflict_and_scope(context):
    staff = context["clients"]["staff"]
    payload, first = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    assert first.status_code == 201 and first.json()["duplicate"] is False
    retry = staff["client"].post("/api/vehicle-pilot/visits", json=payload, headers={"X-CSRF-Token": staff["csrf"]})
    assert retry.status_code == 201 and retry.json()["duplicate"] is True
    changed = {**payload, "camera_id": "camera-172"}
    assert staff["client"].post("/api/vehicle-pilot/visits", json=changed, headers={"X-CSRF-Token": staff["csrf"]}).status_code == 409
    forbidden = {**payload, "visit_id": str(uuid4()), "facility_id": context["ids"]["b"]}
    assert staff["client"].post("/api/vehicle-pilot/visits", json=forbidden, headers={"X-CSRF-Token": staff["csrf"]}).status_code == 404
    other = context["clients"]["staff_other"]["client"]
    assert other.get(f"/api/vehicle-pilot/visits/{payload['visit_id']}").status_code == 404
    assert TestClient(app).get("/api/vehicle-pilot/visits").status_code == 401


def test_private_evidence_idempotency_and_content_scope(context):
    staff = context["clients"]["staff"]
    payload, created = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    visit_id = payload["visit_id"]
    evidence_uuid = uuid4()
    evidence_id = str(evidence_uuid)
    body = b"\xff\xd8\xffpilot-test-image"
    path = f"/api/vehicle-pilot/visits/{visit_id}/evidence/{evidence_id}?kind=plate_crop&media_seconds=11.250"
    headers = {"X-CSRF-Token": staff["csrf"], "Content-Type": "image/jpeg", "X-Evidence-Metadata": '{"frame":4}', "X-Evidence-Bbox": '{"x1":1,"y1":2,"x2":20,"y2":8}'}
    first = staff["client"].post(path, content=body, headers=headers)
    assert first.status_code == 201 and first.json()["evidence"]["storage_state"] == "stored"
    retry = staff["client"].post(path, content=body, headers=headers)
    assert retry.status_code == 201 and retry.json()["duplicate"] is True
    assert staff["client"].get(first.json()["evidence"]["content_url"]).content == body
    different = staff["client"].post(path, content=body + b"x", headers=headers)
    assert different.status_code == 409
    other = context["clients"]["staff_other"]["client"]
    assert other.get(first.json()["evidence"]["content_url"]).status_code == 404
    assert other.get(f"/api/vehicle-pilot/visits/{visit_id}").status_code == 404


def test_confirmation_is_versioned_and_prediction_is_append_only(context):
    staff = context["clients"]["staff"]
    payload, response = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    visit_id = payload["visit_id"]
    decision = {"action": "corrected", "identifier_kind": "painted_text", "evidence_id": None,
        "confirmed_text": "29R52755", "visible_text": "29R52755"}
    first = staff["client"].post(f"/api/vehicle-pilot/visits/{visit_id}/confirmations", json={"expected_version": 1, "decision": decision}, headers={"X-CSRF-Token": staff["csrf"]})
    assert first.status_code == 201 and first.json()["version"] == 2
    stale = staff["client"].post(f"/api/vehicle-pilot/visits/{visit_id}/confirmations", json={"expected_version": 1, "decision": decision}, headers={"X-CSRF-Token": staff["csrf"]})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "version_conflict"
    prediction_id = str(uuid4())
    prediction = {"prediction_id": prediction_id, "source": "local", "identifier_kind": "unknown",
        "raw_text": "29K52755", "normalized_text": "29K52755", "visible_text": "29K52755",
        "reading_status": "partial", "model_version": "test-model", "score_info": {"score": 0.4}, "raw_result": {"raw": "kept"}}
    assert staff["client"].post(f"/api/vehicle-pilot/visits/{visit_id}/predictions", json=prediction, headers={"X-CSRF-Token": staff["csrf"]}).status_code == 201
    detail = staff["client"].get(f"/api/vehicle-pilot/visits/{visit_id}").json()
    assert detail["visit"]["version"] == 2
    assert detail["confirmations"][0]["decision"]["confirmed_text"] == "29R52755"
    assert detail["predictions"][0]["raw_text"] == "29K52755"
    assert any(event["event"] == "visit_confirmed" for event in detail["audit"])
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Trip)) == 0
        assert db.scalar(select(func.count()).select_from(WeighEvent)) == 0
        assert db.scalar(select(func.count()).select_from(GoodsTransaction)) == 0


def test_visit_list_filters_plate_review_and_facility_summary(context):
    staff = context["clients"]["staff"]
    payload, created = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    assert created.status_code == 201
    visit_id = payload["visit_id"]
    suggestion = {"prediction_id": str(uuid4()), "source": "local", "identifier_kind": "tractor_plate",
        "raw_text": "29R-52755", "normalized_text": "29R52755", "visible_text": "29R52755",
        "reading_status": "readable", "model_version": "test-model", "score_info": {}, "raw_result": {}}
    assert staff["client"].post(f"/api/vehicle-pilot/visits/{visit_id}/predictions", json=suggestion,
        headers={"X-CSRF-Token": staff["csrf"]}).status_code == 201
    listing = staff["client"].get("/api/vehicle-pilot/visits?plate=29R&page_size=10").json()
    assert listing["total"] == 1
    assert listing["items"][0]["plate_text"] == "29R52755"
    assert listing["items"][0]["plate_source"] == "suggestion"
    assert listing["items"][0]["review_state"] == "needs_review"
    assert staff["client"].get("/api/vehicle-pilot/visits?plate=NOT-A-PLATE").json()["total"] == 0
    assert staff["client"].get("/api/vehicle-pilot/visits?needs_review=true").json()["total"] == 1
    summary = staff["client"].get(f"/api/vehicle-pilot/visits/summary?facility_id={context['ids']['a']}")
    assert summary.status_code == 200 and summary.json()["needs_review"] == 1
    assert summary.json()["plate_unknown"] == 0
    denied = staff["client"].get(f"/api/vehicle-pilot/visits/summary?facility_id={context['ids']['b']}")
    assert denied.status_code == 404
    confirmed = {"action": "confirmed", "identifier_kind": "tractor_plate", "confirmed_text": "29R52755"}
    assert staff["client"].post(f"/api/vehicle-pilot/visits/{visit_id}/confirmations",
        json={"expected_version": 1, "decision": confirmed}, headers={"X-CSRF-Token": staff["csrf"]}).status_code == 201
    listing = staff["client"].get("/api/vehicle-pilot/visits?plate=29R&needs_review=true").json()
    assert listing["total"] == 0
    listing = staff["client"].get("/api/vehicle-pilot/visits?plate=29R").json()
    assert listing["items"][0]["plate_source"] == "confirmed"
    assert listing["items"][0]["plate_text"] == "29R52755"


def _heartbeat_payload(sequence=1, *, heartbeat_id=None, reader_status="ok"):
    return {
        "schema_version": 1,
        "heartbeat_id": str(heartbeat_id or uuid4()),
        "heartbeat_sequence": sequence,
        "agent_version": "2.4.1",
        "process_uptime_seconds": 720,
        "vendor_process_running": True,
        "reader_status": reader_status,
        "last_successful_read_at_utc": "2026-10-09T01:00:00.123456Z",
        "pending_event_count": 2,
        "last_signal_ack_at_utc": "2026-10-09T00:59:55Z",
        "last_error_code": "READER_EMPTY" if reader_status == "empty" else None,
    }


def test_scale_heartbeat_is_separate_from_signal_and_agent_bearer_stays_scoped(context):
    token = "heartbeat-test-token"
    with SessionLocal.begin() as db:
        agent = ScaleAgent(agent_id=str(uuid4()), display_name="Pilot test scale", facility_id=context["ids"]["a"],
            scale_code="TEST-SCALE", is_active=True, token_hash=hashlib.sha256(token.encode()).hexdigest())
        db.add(agent); db.flush(); agent_id = agent.agent_id
    client = TestClient(app)
    payload = _heartbeat_payload()
    response = client.post("/api/scale-ingestion/heartbeat", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200 and response.json()["persisted"] is True
    assert response.json()["applied"] is True and response.json()["acknowledged"] is True
    assert client.get("/api/vehicle-pilot/visits", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/scale-monitoring/agents", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    admin = context["clients"]["admin"]["client"]
    status = admin.get("/api/vehicle-pilot/heartbeat/scale-agents").json()["items"]
    admin_row = next(row for row in status if row["agent_id"] == agent_id)
    assert admin_row["state"] == "communicating"
    assert admin_row["reader_status"] == "ok"
    assert admin_row["agent_version"] == "2.4.1"
    staff = context["clients"]["staff"]["client"].get("/api/vehicle-pilot/heartbeat/scale-agents").json()["items"]
    staff_row = next(row for row in staff if row["agent_id"] == agent_id)
    assert staff_row["reader_status"] == "ok"
    assert "agent_version" not in staff_row and "pending_event_count" not in staff_row
    manager = context["clients"]["manager"]["client"]
    assert manager.get(f"/api/vehicle-pilot/heartbeat/scale-agents?facility_id={context['ids']['b']}").status_code == 404
    assert context["clients"]["staff"]["client"].get(
        f"/api/vehicle-pilot/heartbeat/scale-agents?facility_id={context['ids']['b']}"
    ).status_code == 404
    assert client.get("/api/scale-ingestion/heartbeat").status_code == 405
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ScaleSignal)) == 0
        row = db.get(ScaleAgentHeartbeat, agent_id)
        assert row.pending_event_count == 2 and row.reader_status == "ok"
        assert str(row.heartbeat_id) == payload["heartbeat_id"]


def test_paused_signal_sender_is_visible_as_operational_status_with_facility_scope(context):
    token = "paused-sender-test-token"
    agent_id = str(uuid4())
    with SessionLocal.begin() as db:
        db.add(ScaleAgent(agent_id=agent_id, display_name="Paused sender", facility_id=context["ids"]["a"],
                          scale_code="PAUSED", is_active=True, token_hash=hashlib.sha256(token.encode()).hexdigest()))
    payload = {**_heartbeat_payload(reader_status="empty"), "pending_event_count": 1309,
               "last_error_code": "SIGNAL_SENDER_PAUSED"}
    assert TestClient(app).post("/api/scale-ingestion/heartbeat", json=payload,
                               headers={"Authorization": f"Bearer {token}"}).status_code == 200
    path = "/api/vehicle-pilot/heartbeat/scale-agents"
    for role in ["staff", "manager"]:
        row = next(r for r in context["clients"][role]["client"].get(path).json()["items"] if r["agent_id"] == agent_id)
        assert row["state"] == "communicating" and row["reader_status"] == "empty"
        assert row["signal_delivery_state"] == "paused" and row["pending_signal_count"] == 1309
        assert "last_error_code" not in row and "heartbeat_id" not in row
    assert not context["clients"]["staff_other"]["client"].get(path).json()["items"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ScaleSignal)) == 0


def test_heartbeat_duplicate_conflict_and_late_delivery_keep_one_current_snapshot(context, monkeypatch):
    from app.modules.scale_ingestion import router as ingestion_router

    base = datetime(2026, 10, 9, 1, 0, tzinfo=timezone.utc)
    clock = {"now": base}
    monkeypatch.setattr(ingestion_router, "utcnow", lambda: clock["now"])
    token = "heartbeat-idempotency-token"
    with SessionLocal.begin() as db:
        agent = ScaleAgent(agent_id=str(uuid4()), display_name="Heartbeat test", facility_id=context["ids"]["a"],
            scale_code="HEARTBEAT-TEST", is_active=True, token_hash=hashlib.sha256(token.encode()).hexdigest())
        db.add(agent); db.flush(); agent_id = agent.agent_id
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    first_payload = _heartbeat_payload(1)
    first = client.post("/api/scale-ingestion/heartbeat", json=first_payload, headers=auth)
    assert first.status_code == 200 and first.json()["applied"] is True
    with SessionLocal() as db:
        first_received_at = db.get(ScaleAgentHeartbeat, agent_id).received_at_utc
        assert db.get(ScaleAgentHeartbeat, agent_id) is not None  # commit is visible before the ACK returns

    clock["now"] = base + timedelta(seconds=5)
    duplicate = client.post("/api/scale-ingestion/heartbeat", json=first_payload, headers=auth)
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
    with SessionLocal() as db:
        assert db.get(ScaleAgentHeartbeat, agent_id).received_at_utc == first_received_at

    reused_id = {**first_payload, "pending_event_count": 9}
    assert client.post("/api/scale-ingestion/heartbeat", json=reused_id, headers=auth).status_code == 409
    same_sequence_new_id = _heartbeat_payload(1)
    assert client.post("/api/scale-ingestion/heartbeat", json=same_sequence_new_id, headers=auth).status_code == 409

    clock["now"] = base + timedelta(seconds=30)
    newer_payload = _heartbeat_payload(2, reader_status="empty")
    newer = client.post("/api/scale-ingestion/heartbeat", json=newer_payload, headers=auth)
    assert newer.status_code == 200 and newer.json()["applied"] is True
    clock["now"] = base + timedelta(seconds=60)
    late = client.post("/api/scale-ingestion/heartbeat", json=first_payload, headers=auth)
    assert late.status_code == 200 and late.json()["stale"] is True and late.json()["persisted"] is False
    with SessionLocal() as db:
        rows = db.scalars(select(ScaleAgentHeartbeat).where(ScaleAgentHeartbeat.agent_id == agent_id)).all()
        assert len(rows) == 1 and str(rows[0].heartbeat_id) == newer_payload["heartbeat_id"]
        assert rows[0].reader_status == "empty"
        assert db.scalar(select(func.count()).select_from(ScaleSignal)) == 0
        assert db.scalar(select(func.count()).select_from(WeighEvent)) == 0
        assert db.scalar(select(func.count()).select_from(Trip)) == 0
        assert db.scalar(select(func.count()).select_from(GoodsTransaction)) == 0


def test_heartbeat_status_thresholds_use_server_clock_and_no_heartbeat_is_distinct(context, monkeypatch):
    from app.modules.scale_ingestion import router as ingestion_router
    from app.modules.vehicle_pilot import router as pilot_router

    base = datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(ingestion_router, "utcnow", lambda: base)
    token = "heartbeat-threshold-token"
    with SessionLocal.begin() as db:
        agent = ScaleAgent(agent_id=str(uuid4()), display_name="Heartbeat threshold", facility_id=context["ids"]["a"],
            scale_code="THRESHOLD-TEST", is_active=True, token_hash=hashlib.sha256(token.encode()).hexdigest())
        no_signal = ScaleAgent(agent_id=str(uuid4()), display_name="No heartbeat", facility_id=context["ids"]["a"],
            scale_code="NEVER-TEST", is_active=True, token_hash=hashlib.sha256(b"never-used-token").hexdigest())
        db.add_all([agent, no_signal]); db.flush(); agent_id = agent.agent_id
    response = TestClient(app).post("/api/scale-ingestion/heartbeat", json=_heartbeat_payload(), headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    status_client = context["clients"]["admin"]["client"]
    for seconds, expected in [(90, "communicating"), (90.001, "delayed"), (180, "delayed"), (180.001, "lost")]:
        monkeypatch.setattr(pilot_router, "utcnow", lambda seconds=seconds: base + timedelta(seconds=seconds))
        rows = status_client.get("/api/vehicle-pilot/heartbeat/scale-agents").json()["items"]
        row = next(item for item in rows if item["agent_id"] == agent_id)
        never = next(item for item in rows if item["scale_code"] == "NEVER-TEST")
        assert row["state"] == expected
        assert never["state"] == "never_received" and never["reader_status"] is None


def test_ai_job_api_remains_disabled_until_provider_and_model_are_verified(context):
    staff = context["clients"]["staff"]
    payload, response = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    result = staff["client"].post(f"/api/vehicle-pilot/visits/{payload['visit_id']}/ai-jobs", json=[], headers={"X-CSRF-Token": staff["csrf"]})
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "ai_provider_not_configured"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CameraVisit)) == 1
        assert db.scalar(select(func.count()).select_from(CameraEvidence)) == 0


def test_replay_bundle_ingests_private_evidence_and_reviewable_visit(context, tmp_path, monkeypatch):
    from app.modules.vehicle_pilot import replay

    bundle = tmp_path / "replay"
    (bundle / "evidence").mkdir(parents=True)
    paths = {name: f"evidence/{name}.jpg" for name in ("overview", "annotated", "vehicle", "plate")}
    for relative in paths.values():
        (bundle / relative).write_bytes(b"\xff\xd8\xffpilot-e2e-image")
    report = {
        "pipeline_version": "test-pipeline", "camera_id": "camera-185",
        "source_video": {"sha256": "a" * 64, "video_start_utc": None},
        "models": {"plate": {"sha256": "b" * 64}, "ocr": {"version": "fastplate-test"}},
        "sessions": [{
            "session_id": "session-1", "start_media_seconds": 3.5, "end_media_seconds": 7.0,
            "track_ids": [1], "decision": "unknown", "candidates": [],
            "proposed_plate": "49C02151", "raw_ocr": [{"raw": "49C02151"}],
            "evidence": {
                "overview": paths["overview"], "annotated": paths["annotated"],
                "vehicle_crop": paths["vehicle"], "overview_media_seconds": 4.0,
                "plate_crops": [{"path": paths["plate"], "media_seconds": 5.0,
                                 "box_in_vehicle_crop": [4, 8, 80, 30]}],
            },
        }],
    }
    (bundle / "result.json").write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(replay, "EvidenceStorage", lambda: EvidenceStorage(tmp_path / "replay-private"))

    result = replay.ingest_run(bundle, "PILOT-A")
    assert result["visits_seen"] == 1 and result["evidence_seen"] == 4
    assert result["predictions_added"] == 1 and result["d02_written"] is False
    staff = context["clients"]["staff"]
    rows = staff["client"].get("/api/vehicle-pilot/visits").json()["items"]
    assert len(rows) == 1 and rows[0]["source_mode"] == "replay"
    detail = staff["client"].get(f"/api/vehicle-pilot/visits/{rows[0]['visit_id']}").json()
    assert detail["visit"]["observed_at_utc"] is None
    assert len(detail["evidence"]) == 4
    assert all(item["storage_state"] == "stored" for item in detail["evidence"])
    assert detail["predictions"][0]["source"] == "local"
    assert detail["predictions"][0]["raw_text"] == "49C02151"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Trip)) == 0
        assert db.scalar(select(func.count()).select_from(WeighEvent)) == 0
        assert db.scalar(select(func.count()).select_from(GoodsTransaction)) == 0


def test_expired_evidence_is_hidden_then_purged_by_retention_worker(context, tmp_path):
    from app.modules.vehicle_pilot.retention import run_once
    from app.modules.vehicle_pilot.router import storage

    staff = context["clients"]["staff"]
    payload, _ = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    evidence_uuid = uuid4()
    evidence_id = str(evidence_uuid)
    path = f"/api/vehicle-pilot/visits/{payload['visit_id']}/evidence/{evidence_id}?kind=plate_crop"
    uploaded = staff["client"].post(path, content=b"\xff\xd8\xffretention-test",
        headers={"X-CSRF-Token": staff["csrf"], "Content-Type": "image/jpeg"})
    assert uploaded.status_code == 201
    row_out = uploaded.json()["evidence"]
    assert row_out["retention_until_utc"] is not None
    with SessionLocal.begin() as db:
        row = db.get(CameraEvidence, evidence_uuid)
        row.retention_until_utc = utcnow() - timedelta(seconds=1)
        object_key = row.object_key

    result = run_once(SessionLocal, storage, now=utcnow())
    assert result == {"due": 1, "purged": 1, "errors": 0}
    assert not storage.path(object_key).exists()
    unavailable = staff["client"].get(row_out["content_url"])
    assert unavailable.status_code == 503
    with SessionLocal() as db:
        row = db.get(CameraEvidence, evidence_uuid)
        assert row.storage_state == "expired" and row.purged_at_utc is not None


def test_live_camera_health_preview_and_diagnostics_scope(context, tmp_path, monkeypatch):
    from app.core.models import utcnow
    from app.modules.vehicle_pilot.models import CameraRuntime, CameraDiagnostic
    from app.modules.vehicle_pilot.router import camera_health
    from datetime import timedelta
    storage = EvidenceStorage(tmp_path / 'camera-store')
    monkeypatch.setattr('app.modules.vehicle_pilot.router.storage', storage)
    now = utcnow()
    body = b'\xff\xd8\xffprivate-preview'
    storage.write('live/diagnostics/camera-185/preview.jpg', body, __import__('hashlib').sha256(body).hexdigest())
    with SessionLocal.begin() as db:
        row = CameraRuntime(camera_id='camera-185', facility_id=context['ids']['a'], owner='test-worker', updated_at=now,
            snapshot={'source_state':'receiving', 'processing_state':'processing', 'last_frame_received_at':now.isoformat(),
                'last_frame_decoded_at':now.isoformat(), 'last_frame_processed_at':now.isoformat(),
                'preview_key':'live/diagnostics/camera-185/preview.jpg', 'queue_depth':2})
        db.add(row)
    staff = context['clients']['staff']; other = context['clients']['staff_other']['client']
    assert TestClient(app).get('/api/vehicle-pilot/cameras').status_code == 401
    assert TestClient(app).get('/api/vehicle-pilot/cameras/camera-185/preview', headers={'Authorization':'Bearer not-a-user-session'}).status_code == 401
    assert staff['client'].get('/api/vehicle-pilot/cameras').json()['items'][0]['source_state'] == 'receiving'
    assert other.get('/api/vehicle-pilot/cameras').json()['items'] == []
    assert other.get('/api/vehicle-pilot/cameras/camera-185/preview').status_code == 404
    assert staff['client'].get('/api/vehicle-pilot/cameras/camera-185/preview').status_code == 409
    preview_request = {'request_id': str(uuid4()), 'action': 'preview', 'duration_seconds': 120}
    assert staff['client'].post('/api/vehicle-pilot/cameras/camera-185/actions', json=preview_request,
        headers={'X-CSRF-Token':staff['csrf']}).status_code == 202
    assert staff['client'].get('/api/vehicle-pilot/cameras/camera-185/preview').content == body
    path = '/api/vehicle-pilot/cameras/camera-185/diagnostics'
    assert staff['client'].post(path).status_code == 403
    assert other.post(path, headers={'X-CSRF-Token':context['clients']['staff_other']['csrf']}).status_code == 404
    first = staff['client'].post(path, headers={'X-CSRF-Token':staff['csrf']})
    again = staff['client'].post(path, headers={'X-CSRF-Token':staff['csrf']})
    assert first.status_code == again.status_code == 202
    assert first.json()['diagnostic_id'] == again.json()['diagnostic_id']
    with SessionLocal() as db:
        row = db.get(CameraRuntime, 'camera-185')
        health = camera_health(row, now + timedelta(seconds=46))
        assert health['worker_reporting'] and health['source_state'] == 'interrupted'
        assert health['processing_state'] == 'interrupted'
        # Worker can report while inference is stale; source/decode remains independent.
        row.snapshot = {**row.snapshot, 'last_frame_decoded_at':(now + timedelta(seconds=46)).isoformat()}
        health = camera_health(row, now + timedelta(seconds=46))
        assert health['source_state'] == 'receiving' and health['processing_state'] == 'interrupted'
        assert camera_health(row, now + timedelta(seconds=76))['worker_reporting'] is False
        row.snapshot = {**row.snapshot, 'source_state':'reconnecting'}
        assert camera_health(row, now + timedelta(seconds=46))['source_state'] == 'reconnecting'
        assert db.scalar(select(func.count()).select_from(CameraDiagnostic)) == 2


def test_live_outbox_restart_commit_duplicate_and_evidence(context, tmp_path):
    from app.modules.vehicle_pilot.live_worker import Outbox, ingest
    from app.modules.vehicle_pilot.models import VehiclePilotAuditEvent
    from app.core.models import utcnow
    from uuid import uuid5
    vid = uuid4()
    event = {'visit_id':str(vid), 'event_id':str(uuid5(vid,'opened')), 'stage':'opened',
        'facility_id':context['ids']['a'], 'camera_id':'camera-185', 'observed_at_utc':utcnow().isoformat(),
        'identity':{'worker_visit_identity':str(vid)}, 'evidence':[], 'reads':[]}
    outbox = Outbox(tmp_path / 'outbox.sqlite3')
    outbox.put('open', event); outbox.put('open', event)
    with pytest.raises(ValueError): outbox.put('open', {**event, 'stage':'finished'})
    restarted = Outbox(tmp_path / 'outbox.sqlite3')
    assert restarted.count() == 1 and restarted.head()[1] == event
    storage = EvidenceStorage(tmp_path / 'live-storage')
    ingest(SessionLocal, storage, event); ingest(SessionLocal, storage, event)
    with pytest.raises(ValueError, match='LIVE_EVENT_ID_CONFLICT'):
        ingest(SessionLocal, storage, {**event, 'reads':[{'raw':'changed'}]})
    # Persistent queue is only ACKed after the DB transaction returns successfully.
    restarted.ack('open'); assert restarted.count() == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CameraVisit)) == 1
        assert db.scalar(select(func.count()).select_from(VehiclePilotAuditEvent)) == 1
        assert db.scalar(select(func.count()).select_from(WeighEvent)) == 0


def test_live_interruption_ids_and_native_crop_provenance():
    from app.modules.vehicle_pilot.live_worker import Worker
    from types import SimpleNamespace
    worker=Worker.__new__(Worker)
    worker.owner='same-process'; worker.facility_id=1; worker.camera_id='camera-185'
    worker.config={'model_hashes':{'plate':'pinned'}}
    worker.config['event_policy'] = {}
    worker.gate=SimpleNamespace(state={})
    worker.cfg=SimpleNamespace(roi_status='provisional',snapshot=lambda:{'sample_hz':3,'roi':[[0,0],[1,0],[1,1]]})
    session=SimpleNamespace(session_id=str(uuid4()),started=100.5,last_seen=120.5,ended=None,end_reason=None,
        track_ids=['t1'],reads=[],plate_observations=[{'media_seconds':110.5,'vehicle_crop_origin':[10,20],'box_in_vehicle_crop':[1,2,30,10]}])
    restart=worker._event(session,'interrupted','restart')
    shutdown=worker._event(session,'interrupted','shutdown')
    assert restart['event_id'] != shutdown['event_id']
    assert worker._event(session,'interrupted','shutdown') == shutdown
    finished=worker._event(session,'finished')
    assert finished['plate_observations'][0]['vehicle_crop_origin'] == [10,20]
    assert finished['identity']['camera_config']['sample_hz'] == 3
    opened=worker._event(session,'opened')
    session.last_seen=150.5; session.track_ids.append('t2')
    assert worker._event(session,'opened') == opened


def test_camera_actions_scope_idempotency_expiry_and_idle(context):
    from app.modules.vehicle_pilot.models import CameraRuntime, CameraDiagnostic
    from app.modules.vehicle_pilot.router import camera_health
    now = utcnow()
    with SessionLocal.begin() as db:
        db.add(CameraRuntime(camera_id='camera-185', facility_id=context['ids']['a'], owner='test', updated_at=now,
            snapshot={'source_state':'idle_unchecked','processing_state':'idle', 'last_frame_decoded_at':now.isoformat()}))
    staff = context['clients']['staff']; client = staff['client']; other = context['clients']['staff_other']
    path = '/api/vehicle-pilot/cameras/camera-185/actions'
    payload = {'request_id':str(uuid4()),'action':'process','duration_seconds':120}
    assert TestClient(app).post(path,json=payload).status_code == 401
    assert client.post(path,json=payload).status_code == 403
    assert other['client'].post(path,json=payload,headers={'X-CSRF-Token':other['csrf']}).status_code == 404
    headers={'X-CSRF-Token':staff['csrf']}
    first=client.post(path,json=payload,headers=headers)
    assert first.status_code == 202
    assert client.post(path,json=payload,headers=headers).json() == first.json()
    assert client.post(path,json={**payload,'action':'photo'},headers=headers).status_code == 409
    assert client.post(path,json={**payload,'request_id':str(uuid4())},headers=headers).json() == first.json()
    with SessionLocal() as db:
        row = db.get(CameraRuntime,'camera-185')
        health = camera_health(row,now)
        assert health['worker_reporting'] and health['source_state']=='idle_unchecked' and health['processing_state']=='idle'
        assert db.scalar(select(func.count()).select_from(CameraDiagnostic))==1
    photo={'request_id':str(uuid4()),'action':'photo','duration_seconds':10}
    captured=client.post(path,json=photo,headers=headers)
    with SessionLocal.begin() as db:
        row=db.get(CameraDiagnostic,__import__('uuid').UUID(photo['request_id'])); row.status='saving'
    again=client.post(path,json={**photo,'request_id':str(uuid4())},headers=headers)
    assert again.json()['diagnostic_id']==captured.json()['diagnostic_id'] and again.json()['status']=='saving'
    preview={'request_id':str(uuid4()),'action':'preview','duration_seconds':10}
    assert client.post(path,json=preview,headers=headers).status_code==202
    stop={'request_id':str(uuid4()),'action':'preview_stop','duration_seconds':10}
    assert client.post(path,json=stop,headers=headers).status_code==202
    assert client.get('/api/vehicle-pilot/cameras/camera-185/preview').status_code==409
    with SessionLocal.begin() as db:
        row=db.get(CameraRuntime,'camera-185'); row.updated_at=now-timedelta(seconds=76)
    assert client.post(path,json={'request_id':str(uuid4()),'action':'photo'},headers=headers).status_code==409


def test_event_window_ocr_budget_respects_frozen_config(tmp_path):
    from types import SimpleNamespace
    from app.modules.vehicle_pilot.live_worker import Worker
    from dataclasses import dataclass
    from offline_vision.event_gate import EventGate
    @dataclass(frozen=True)
    class FrozenConfig:
        max_ocr_reads: int = 8
    cfg=FrozenConfig()
    worker=Worker.__new__(Worker)
    worker.config={'mode':'event_driven','event_policy':{'max_ocr_calls':4}}
    worker.gate=EventGate({'capture_seconds':20,'max_inference_frames':30,'max_evidence_frames':4,
        'signal_max_age_seconds':10,'signal_rearm_gap_seconds':120})
    worker.gate.trigger(1000,'manual','fixture')
    worker.output=tmp_path
    worker._event=lambda *args: {'evidence':[]}
    worker._session_state=lambda *args: {}
    worker.outbox=SimpleNamespace(put=lambda *args:None)
    stats={'ocr_model_calls':0}
    class Pool:
        config=cfg
        pools={}
        def recognize(self,session,ocr,stats,output):
            assert self.config.max_ocr_reads==4
            stats['ocr_model_calls']+=4
    pool=Pool()
    session=SimpleNamespace(session_id='fixture',reads=[],evidence={'plate_crops':[]},ocr_calls=0)
    worker._complete_session(session,pool,None,stats,None)
    assert pool.config is cfg and cfg.max_ocr_reads==8
    assert worker.gate.state['ocr_model_calls']==4


def test_window_evidence_has_separate_durable_outbox_files(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.modules.vehicle_pilot.live_worker import Worker, Outbox
    from offline_vision.event_gate import EventGate
    worker=Worker.__new__(Worker)
    policy={'capture_seconds':20,'max_inference_frames':30,'max_evidence_frames':4,
        'signal_max_age_seconds':10,'signal_rearm_gap_seconds':120,'evidence_spacing_seconds':4}
    worker.config={'event_policy':policy}; worker.gate=EventGate(policy); worker.gate.trigger(1000,'manual','request')
    worker.output=tmp_path/'work'; worker.outbox=Outbox(tmp_path/'outbox.sqlite3')
    original=tmp_path/'diagnostic.jpg'; original.write_bytes(b'\xff\xd8\xffnative')
    worker._manual_photo=lambda *args:original
    worker._event=lambda *args:{'evidence':[]}
    session=SimpleNamespace(session_id=str(uuid4()),ended=None)
    manager=SimpleNamespace(sessions=[session]); image=SimpleNamespace(shape=(1080,1920,3))
    for second in [1001,1006,1011,1016,1021]:
        monkeypatch.setattr('app.modules.vehicle_pilot.live_worker.time.time',lambda:second)
        worker._window_evidence(image,'2026-10-10T00:00:00+00:00',manager)
    assert worker.outbox.count()==4 and worker.gate.state['evidence_count']==4
    original.unlink()  # Diagnostic retention cannot destroy unacknowledged visit evidence.
    from pathlib import Path
    assert Path(worker.outbox.head()[1]['evidence'][0]['path']).read_bytes()==b'\xff\xd8\xffnative'


def test_manual_photo_claim_prevents_recapture_before_commit(context, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.modules.vehicle_pilot.live_worker import Worker, Outbox
    from app.modules.vehicle_pilot.models import CameraRuntime, CameraDiagnostic
    import sys
    worker=Worker.__new__(Worker)
    worker.factory=SessionLocal; worker.camera_id='camera-185'; worker.facility_id=context['ids']['a']
    worker.live_root=tmp_path/'live'; folder=worker.live_root/'diagnostics'/'camera-185'; folder.mkdir(parents=True)
    worker.storage=EvidenceStorage(tmp_path); worker.outbox=Outbox(tmp_path/'outbox.sqlite3')
    worker.gate=SimpleNamespace(state={}); worker._diagnostic_space=lambda *args:folder
    class Encoded(bytes):
        def tobytes(self): return bytes(self)
    calls=[]
    monkeypatch.setitem(sys.modules,'cv2',SimpleNamespace(IMWRITE_JPEG_QUALITY=1,
        imencode=lambda *args:(calls.append(1) or True,Encoded(b'\xff\xd8\xffnative'))))
    item_id=uuid4(); now=utcnow()
    with SessionLocal.begin() as db:
        db.add(CameraRuntime(camera_id='camera-185',facility_id=worker.facility_id,owner='test',updated_at=now,snapshot={}))
        db.flush()
        db.add(CameraDiagnostic(id=item_id,camera_id='camera-185',facility_id=worker.facility_id,kind='photo',
            status='capturing',created_at=now,expires_at=now+timedelta(hours=24),metadata_json={'request_id':str(item_id)}))
    image=SimpleNamespace(shape=(1080,1920,3))
    path=worker._manual_photo(image,now.isoformat(),str(item_id))
    # Sender has not committed file metadata yet. A new tick/retry cannot encode again.
    worker._manual_photo(image,(now+timedelta(seconds=1)).isoformat(),str(item_id))
    assert len(calls)==1 and worker.outbox.count()==1
    with SessionLocal() as db: assert db.get(CameraDiagnostic,item_id).status=='saving'
    restarted=Outbox(tmp_path/'outbox.sqlite3'); payload=restarted.head()[1]
    worker._persist_diagnostic(str(item_id),payload['kind'],path,payload['metadata'])
    restarted.ack('diagnostic:'+str(item_id))
    with SessionLocal() as db:
        row=db.get(CameraDiagnostic,item_id)
        assert row.status=='stored' and row.metadata_json['native_pixels']==[1920,1080]
        assert row.metadata_json['observed_at_utc']==now.isoformat()
        assert row.sha256==hashlib.sha256(path.read_bytes()).hexdigest()
        assert row.metadata_json['trigger_id']==str(item_id)


def test_gemini_ocr_and_trips_endpoint(context, tmp_path, monkeypatch):
    staff = context["clients"]["staff"]
    payload, created = create_visit(staff["client"], staff["csrf"], context["ids"]["a"])
    visit_id = payload["visit_id"]
    evidence_id = str(uuid4())
    img_body = b"\xff\xd8\xfffake_jpeg_content"
    storage_root = tmp_path / "evidence"
    storage_root.mkdir()
    from app.modules.vehicle_pilot import router as vrouter
    monkeypatch.setattr(vrouter, "storage", EvidenceStorage(storage_root))
    monkeypatch.setattr(vrouter.get_settings(), "gemini_api_key", "test-key")

    upload = staff["client"].post(
        f"/api/vehicle-pilot/visits/{visit_id}/evidence/{evidence_id}?kind=plate_crop&media_seconds=1.000",
        content=img_body,
        headers={"Content-Type": "image/jpeg", "X-CSRF-Token": staff["csrf"]}
    )
    assert upload.status_code == 201

    class MockResp:
        def read(self):
            return json.dumps({
                "candidates": [
                    {"content": {"parts": [{"text": "49C-026.55"}]}}
                ]
            }).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr(vrouter.urllib.request, "urlopen", lambda *args, **kwargs: MockResp())

    res = staff["client"].post(
        f"/api/vehicle-pilot/visits/{visit_id}/gemini-ocr",
        headers={"X-CSRF-Token": staff["csrf"]}
    )
    assert res.status_code == 200
    assert res.json()["plate_text"] == "49C-026.55"
    assert res.json()["normalized_text"] == "49C02655"

    # Test trips endpoint
    trips_resp = staff["client"].get(f"/api/vehicle-pilot/visits/trips?facility_id={context['ids']['a']}")
    assert trips_resp.status_code == 200
    trips_data = trips_resp.json()
    assert trips_data["total_trips"] >= 1
    t = next(tr for tr in trips_data["trips"] if tr["first_visit"]["visit_id"] == visit_id)
    assert t["plate_text"] == "49C02655"
    assert t["status"] == "in_yard"

