from datetime import datetime, timedelta, timezone
from decimal import Decimal
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.accounts.models import User
from app.modules.accounts.security import hash_password
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
from app.main import app

VN_TZ = timezone(timedelta(hours=7))


@pytest.fixture(autouse=True)
def clean_database():
    with SessionLocal.begin() as db:
        db.execute(text("TRUNCATE static_bed_stirrings, static_bed_batches, static_drying_beds, drum_qc, drum_incidents, drum_inspections, drum_periodic_logs, drum_runs, drums, account_audit_logs, auth_sessions, login_attempts, user_facilities, users, facilities RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def drum_data():
    passwords = {key: secrets.token_urlsafe(18) for key in ("operator", "manager", "other", "admin")}
    with SessionLocal.begin() as db:
        f_a = Facility(code="FAC-A", name="Cơ sở A", is_active=True)
        f_b = Facility(code="FAC-B", name="Cơ sở B", is_active=True)
        db.add_all([f_a, f_b])
        db.flush()

        for num in (1, 2, 3, 4):
            db.add(StaticDryingBed(
                facility_id=f_a.id,
                bed_number=num,
                bed_code=f"SAN-0{num}",
                bed_name=f"Sàn sấy tĩnh số {num} (Xưởng trong)",
                location_type="indoor",
                capacity_kg=Decimal("2500.00"),
                is_active=True,
            ))
            db.add(StaticDryingBed(
                facility_id=f_b.id,
                bed_number=num,
                bed_code=f"SAN-B-0{num}",
                bed_name=f"Sàn B số {num}",
                location_type="indoor",
                capacity_kg=Decimal("2500.00"),
                is_active=True,
            ))
        db.flush()

        operator = User(
            username="drum.operator",
            display_name="Thợ Trông Trống",
            role="drum_operator",
            password_hash=hash_password(passwords["operator"]),
            is_active=True,
            facilities=[f_a],
        )
        manager = User(
            username="drum.manager",
            display_name="Quản Lý Xưởng",
            role="manager",
            password_hash=hash_password(passwords["manager"]),
            is_active=True,
            facilities=[f_a],
        )
        other = User(
            username="drum.other",
            display_name="Thợ Cơ Sở B",
            role="drum_operator",
            password_hash=hash_password(passwords["other"]),
            is_active=True,
            facilities=[f_b],
        )
        admin = User(
            username="drum.admin",
            display_name="Quản Trị Viên",
            role="admin",
            password_hash=hash_password(passwords["admin"]),
            is_active=True,
        )
        db.add_all([operator, manager, other, admin])
        db.flush()

        # Add initial drum
        drum_1 = Drum(
            facility_id=f_a.id,
            drum_code="TRONG-01",
            drum_name="Trống Sấy 01",
            capacity_kg=Decimal("1500.00"),
            status="idle",
            is_active=True,
        )
        db.add(drum_1)
        db.flush()

        facility_a_id = f_a.id
        facility_b_id = f_b.id
        drum_1_id = drum_1.id

    clients = {}
    csrfs = {}
    for role in passwords:
        client = TestClient(app)
        anon_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        resp = client.post(
            "/api/auth/login",
            json={
                "username": f"drum.{role}",
                "password": passwords[role],
            },
            headers={"X-CSRF-Token": anon_csrf},
        )
        assert resp.status_code == 200, resp.text
        auth_csrf = resp.json()["csrf_token"]
        # Switch facility for operator / manager / other
        if role in {"operator", "manager"}:
            client.post("/api/auth/active-facility", json={"facility_id": facility_a_id}, headers={"X-CSRF-Token": auth_csrf})
        elif role == "other":
            client.post("/api/auth/active-facility", json={"facility_id": facility_b_id}, headers={"X-CSRF-Token": auth_csrf})
        clients[role] = client
        csrfs[role] = auth_csrf

    return {
        "clients": clients,
        "csrfs": csrfs,
        "facility_a_id": facility_a_id,
        "facility_b_id": facility_b_id,
        "drum_1_id": drum_1_id,
    }


def test_drum_operator_role_and_listing(drum_data):
    operator = drum_data["clients"]["operator"]
    drums = operator.get("/api/drum-processing/drums").json()
    assert len(drums) == 1
    assert drums[0]["drum_code"] == "TRONG-01"
    assert drums[0]["status"] == "idle"

    # Test GET single drum
    drum_1 = operator.get(f"/api/drum-processing/drums/{drum_data['drum_1_id']}").json()
    assert drum_1["drum_code"] == "TRONG-01"
    assert drum_1["status"] == "idle"


def test_manager_can_create_drum_operator_cannot(drum_data):
    operator = drum_data["clients"]["operator"]
    manager = drum_data["clients"]["manager"]
    csrf_op = drum_data["csrfs"]["operator"]
    csrf_mgr = drum_data["csrfs"]["manager"]

    # Operator cannot create drum
    resp = operator.post(
        "/api/drum-processing/drums",
        json={"drum_code": "TRONG-02", "drum_name": "Trống Sấy 02", "capacity_kg": 2000},
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp.status_code == 403

    # Manager can create drum
    resp = manager.post(
        "/api/drum-processing/drums",
        json={"drum_code": "TRONG-02", "drum_name": "Trống Sấy 02", "capacity_kg": 2000},
        headers={"X-CSRF-Token": csrf_mgr},
    )
    assert resp.status_code == 200
    assert resp.json()["drum_code"] == "TRONG-02"


def test_drum_run_lifecycle_logs_inspection_and_discharge(drum_data):
    operator = drum_data["clients"]["operator"]
    manager = drum_data["clients"]["manager"]
    csrf_op = drum_data["csrfs"]["operator"]
    csrf_mgr = drum_data["csrfs"]["manager"]
    drum_id = drum_data["drum_1_id"]

    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(hours=2)

    # 1. Start drum run (Ngày/giờ vào trống)
    resp = operator.post(
        "/api/drum-processing/runs",
        json={
            "drum_id": drum_id,
            "batch_code": "ME-ROBUSTA-01",
            "coffee_type": "Robusta ướt loại 1",
            "initial_weight_kg": 1450.50,
            "cycle_minutes": 30,
            "entry_time": entry_time.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp.status_code == 200, resp.text
    run_detail = resp.json()
    run_id = run_detail["id"]
    assert run_detail["status"] == "in_progress"
    assert run_detail["batch_code"] == "ME-ROBUSTA-01"

    # Drum is now running; another run on the same drum must conflict (409)
    resp_conflict = operator.post(
        "/api/drum-processing/runs",
        json={
            "drum_id": drum_id,
            "batch_code": "ME-ROBUSTA-02",
            "cycle_minutes": 30,
            "entry_time": now.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_conflict.status_code == 409

    # 2. Record periodic logs (Độ ẩm cà trong trống & nhiệt độ luồng hơi)
    # Log 1: on time
    t1 = entry_time + timedelta(minutes=30)
    resp_log1 = operator.post(
        f"/api/drum-processing/runs/{run_id}/logs",
        json={
            "moisture_percent": 34.50,
            "temperature_celsius": 75.00,
            "measured_at": t1.isoformat(),
            "note": "Kiểm tra đầu mẻ, luồng hơi ổn định",
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_log1.status_code == 200
    log1 = resp_log1.json()
    assert log1["sequence"] == 1
    assert log1["moisture_percent"] == "34.50"
    assert log1["temperature_celsius"] == "75.00"

    # Log 2: late submission
    t2 = entry_time + timedelta(minutes=60)
    resp_log2 = operator.post(
        f"/api/drum-processing/runs/{run_id}/logs",
        json={
            "moisture_percent": 28.20,
            "temperature_celsius": 78.50,
            "measured_at": t2.isoformat(),
            "note": "Hơi nóng tăng nhẹ",
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_log2.status_code == 200
    log2 = resp_log2.json()
    assert log2["sequence"] == 2
    assert log2["moisture_percent"] == "28.20"

    # 3. Manager performs random spot inspection (Thanh tra ngẫu nhiên)
    t_inspect = t2 + timedelta(minutes=5)
    resp_inspect = manager.post(
        f"/api/drum-processing/runs/{run_id}/inspections",
        json={
            "sample_moisture_percent": 28.50,
            "sample_temperature_celsius": 78.00,
            "inspected_at": t_inspect.isoformat(),
            "notes": "Kiểm tra đột xuất mẻ sấy, đối chiếu máy đo cầm tay",
        },
        headers={"X-CSRF-Token": csrf_mgr},
    )
    assert resp_inspect.status_code == 200
    inspection = resp_inspect.json()
    assert inspection["evaluation"] == "passed"
    # Moisture diff: 28.50 - 28.20 = 0.30
    assert float(inspection["moisture_diff"]) == pytest.approx(0.30, abs=0.01)

    # 4. Discharge coffee (Ngày/giờ ra trống & Kết quả độ ẩm cuối)
    exit_time = now
    resp_discharge = operator.post(
        f"/api/drum-processing/runs/{run_id}/discharge",
        json={
            "exit_time": exit_time.isoformat(),
            "final_moisture_percent": 12.50,
            "discharge_note": "Cà đạt chuẩn lưu kho 12.5%, hạt đều màu",
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_discharge.status_code == 200
    discharged = resp_discharge.json()
    assert discharged["status"] == "completed"
    assert discharged["final_moisture_percent"] == "12.50"
    assert discharged["exit_time"] is not None

    # Check drum status returned to idle
    drum_check = operator.get("/api/drum-processing/drums").json()[0]
    assert drum_check["status"] == "idle"

    # Cannot add log to completed run
    resp_late_log = operator.post(
        f"/api/drum-processing/runs/{run_id}/logs",
        json={
            "moisture_percent": 12.0,
            "temperature_celsius": 40.0,
            "measured_at": now.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_late_log.status_code == 409


def test_kpi_summary(drum_data):
    manager = drum_data["clients"]["manager"]
    resp = manager.get("/api/drum-processing/audit/kpi")
    assert resp.status_code == 200
    kpi = resp.json()
    assert "compliance_rate_percent" in kpi
    assert "total_inspections" in kpi


def test_drum_heat_off_incubation_and_analytics(drum_data):
    operator = drum_data["clients"]["operator"]
    admin = drum_data["clients"]["admin"]
    csrf_op = drum_data["csrfs"]["operator"]
    csrf_admin = drum_data["csrfs"]["admin"]
    drum_id = drum_data["drum_1_id"]

    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(hours=3)

    # 1. Start a run
    resp_start = operator.post(
        "/api/drum-processing/runs",
        json={
            "drum_id": drum_id,
            "batch_code": "BATCH-STRATEGY-01",
            "coffee_type": "Cà quả trộn cà lụa đã sấy ráo (60% / 40%)",
            "initial_weight_kg": 1400.0,
            "initial_temperature_celsius": 68.50,
            "blend_ratio_qua_percent": 60.0,
            "blend_ratio_lua_percent": 40.0,
            "cycle_minutes": 30,
            "entry_time": entry_time.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_start.status_code == 200
    start_data = resp_start.json()
    run_id = start_data["id"]
    assert float(start_data["initial_temperature_celsius"]) == 68.50
    assert float(start_data["blend_ratio_qua_percent"]) == 60.0
    assert float(start_data["blend_ratio_lua_percent"]) == 40.0

    # 2. Add periodic log
    operator.post(
        f"/api/drum-processing/runs/{run_id}/logs",
        json={
            "moisture_percent": 16.50,
            "temperature_celsius": 76.0,
            "measured_at": (entry_time + timedelta(hours=2)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_op},
    )

    # 3. Stop heat (tắt nhiệt và bắt đầu ủ)
    heat_off_time = entry_time + timedelta(hours=2, minutes=15)
    resp_heat_off = operator.post(
        f"/api/drum-processing/runs/{run_id}/stop-heat",
        json={
            "heat_off_at": heat_off_time.isoformat(),
            "rotation_off_at": heat_off_time.isoformat(),
            "moisture_at_heat_off": 15.20,
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_heat_off.status_code == 200
    detail = resp_heat_off.json()
    assert detail["heat_off_at"] is not None
    assert detail["moisture_at_heat_off"] == "15.20"

    # 4. Discharge with quality assessment (Cà đẹp) and incubation
    exit_time = heat_off_time + timedelta(minutes=45)
    resp_discharge = operator.post(
        f"/api/drum-processing/runs/{run_id}/discharge",
        json={
            "exit_time": exit_time.isoformat(),
            "final_moisture_percent": 12.40,
            "quality_assessment": "ca_dep",
            "quality_note": "Ủ 45 phút cà xuống độ ẩm rất đều và bóng hạt",
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_discharge.status_code == 200
    run_done = resp_discharge.json()
    assert run_done["status"] == "completed"
    assert run_done["quality_assessment"] == "ca_dep"
    assert run_done["incubation_minutes"] == 45

    # 5. Check Drum Analytics / Strategy
    resp_analytics = operator.get(f"/api/drum-processing/drums/{drum_id}/analytics")
    assert resp_analytics.status_code == 200
    analytics = resp_analytics.json()
    assert analytics["drum_code"] == "TRONG-01"
    assert analytics["ca_dep_count"] >= 1
    assert analytics["strategy"]["recommended_stop_heat_moisture"] is not None
    assert analytics["strategy"]["recommended_incubation_minutes"] == 45
    assert len(analytics["history"]) >= 1

    # 6. Admin can create new facility/branch
    resp_facility = admin.post(
        "/api/admin/facilities",
        json={"code": "FAC-NEW", "name": "Chi nhánh Gia Lai"},
        headers={"X-CSRF-Token": csrf_admin},
    )
    assert resp_facility.status_code == 201
    assert resp_facility.json()["code"] == "FAC-NEW"


def test_drum_characteristics_and_two_ends_measurement(drum_data):
    manager = drum_data["clients"]["manager"]
    csrf_mgr = drum_data["csrfs"]["manager"]
    operator = drum_data["clients"]["operator"]
    csrf_op = drum_data["csrfs"]["operator"]

    # 1. Manager creates a drum with two_ends measurement mode and defects
    resp_create = manager.post(
        "/api/drum-processing/drums",
        json={
            "drum_code": "TRONG-03-LECH",
            "drum_name": "Trống Sấy 03 (Lệch đầu)",
            "capacity_kg": 2000.0,
            "measurement_mode": "two_ends",
            "has_moisture_imbalance": True,
            "has_blade_issue": True,
            "characteristics_notes": "Lệch nhiệt đầu đuôi nặng, cánh đảo số 2 hơi vênh",
        },
        headers={"X-CSRF-Token": csrf_mgr},
    )
    assert resp_create.status_code == 200, resp_create.text
    drum_created = resp_create.json()
    drum_id = drum_created["id"]
    assert drum_created["measurement_mode"] == "two_ends"
    assert drum_created["has_moisture_imbalance"] is True
    assert drum_created["has_blade_issue"] is True
    assert "Lệch nhiệt" in drum_created["characteristics_notes"]

    # 2. Manager updates drum characteristics via PATCH
    resp_patch = manager.patch(
        f"/api/drum-processing/drums/{drum_id}",
        json={
            "characteristics_notes": "Đã chỉnh cánh đảo, vẫn lệch nhiệt 2 đầu nhẹ",
            "has_blade_issue": False,
        },
        headers={"X-CSRF-Token": csrf_mgr},
    )
    assert resp_patch.status_code == 200
    patched = resp_patch.json()
    assert patched["has_blade_issue"] is False
    assert patched["has_moisture_imbalance"] is True
    assert "Đã chỉnh cánh đảo" in patched["characteristics_notes"]

    # 3. Operator starts a run on this drum
    now = datetime.now(timezone.utc)
    resp_start = operator.post(
        "/api/drum-processing/runs",
        json={
            "drum_id": drum_id,
            "batch_code": "BATCH-LECH-01",
            "coffee_type": "Cà quả sấy ráo",
            "initial_weight_kg": 1800.0,
            "initial_temperature_celsius": 75.0,
            "cycle_minutes": 30,
            "entry_time": now.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_start.status_code == 200
    run_detail = resp_start.json()
    run_id = run_detail["id"]
    assert run_detail["drum_measurement_mode"] == "two_ends"
    assert run_detail["drum_has_moisture_imbalance"] is True

    # 4. Operator records periodic log with head and tail measurements
    resp_log = operator.post(
        f"/api/drum-processing/runs/{run_id}/logs",
        json={
            "moisture_head_percent": 25.5,
            "moisture_tail_percent": 22.5,
            "temperature_celsius": 76.5,
            "measured_at": (now + timedelta(minutes=30)).isoformat(),
            "note": "Đầu trống ẩm hơn đuôi trống 3%",
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_log.status_code == 200, resp_log.text
    log_data = resp_log.json()
    assert float(log_data["moisture_percent"]) == 24.0  # Average of 25.5 and 22.5
    assert float(log_data["moisture_head_percent"]) == 25.5
    assert float(log_data["moisture_tail_percent"]) == 22.5
    assert float(log_data["moisture_diff_ends"]) == 3.0

    # 5. Operator discharges specifying final moisture for head and tail
    resp_discharge = operator.post(
        f"/api/drum-processing/runs/{run_id}/discharge",
        json={
            "exit_time": (now + timedelta(hours=3)).isoformat(),
            "final_moisture_head_percent": 12.8,
            "final_moisture_tail_percent": 12.2,
            "quality_assessment": "dat_chuan",
            "quality_note": "Hạt ra đều đạt chuẩn",
        },
        headers={"X-CSRF-Token": csrf_op},
    )
    assert resp_discharge.status_code == 200
    dc_data = resp_discharge.json()
    assert float(dc_data["final_moisture_percent"]) == 12.5  # Average of 12.8 and 12.2
    assert float(dc_data["final_moisture_head_percent"]) == 12.8
    assert float(dc_data["final_moisture_tail_percent"]) == 12.2

    # 6. Analytics check: warning message is included in strategy summary
    resp_an = operator.get(f"/api/drum-processing/drums/{drum_id}/analytics")
    assert resp_an.status_code == 200
    an_data = resp_an.json()
    assert "lệch độ ẩm cà 2 đầu" in an_data["strategy"]["strategy_summary"]



def test_new_source_incident_qc_report(drum_data):
    op, mgr, other = (drum_data['clients'][x] for x in ('operator', 'manager', 'other'))
    oh, mh = ({'X-CSRF-Token': drum_data['csrfs'][x]} for x in ('operator', 'manager'))
    now = datetime.now(timezone.utc)
    ground = (now - timedelta(hours=1)).isoformat()
    def create(code):
        res = op.post('/api/drum-processing/runs', headers=oh, json={'drum_id': drum_data['drum_1_id'], 'batch_code': code, 'entry_time': ground})
        assert res.status_code == 200, res.text
        return res.json()['id']
    r1 = create('M001')
    url = f'/api/drum-processing/runs/{r1}'
    source = {'traceability': 'known', 'source_lot_code': 'SAME', 'ground_at': ground, 'drying_started_at': now.isoformat(), 'drying_route': 'direct'}
    res = op.put(url + '/source', headers=oh, json=source)
    assert res.status_code == 200 and round(res.json()['waiting_minutes']) == 60
    assert op.put(url + '/source', headers=oh, json=dict(source, drying_started_at=(now - timedelta(hours=2)).isoformat())).status_code == 422
    assert other.get(url + '/source').status_code == 404
    assert op.post(url + '/incidents', headers=oh, json={'kind': 'blade'}).status_code == 200
    log = op.post(url + '/logs', headers=oh, json={'temperature_celsius': 80, 'temperature_location': 'Khí cấp', 'moisture_head_percent': 13, 'moisture_tail_percent': 11, 'measured_at': now.isoformat()})
    assert log.status_code == 200 and Decimal(log.json()['moisture_diff_ends']) == 2
    log = op.post(url + '/logs', headers=oh, json={'temperature_celsius': 80, 'moisture_head_percent': 13, 'measured_at': now.isoformat()})
    assert log.status_code == 200 and log.json()['moisture_diff_ends'] is None
    assert op.post(url + '/discharge', headers=oh, json={'exit_time': now.isoformat(), 'final_moisture_percent': 12}).status_code == 200
    assert op.get(url + '/qc').json() is None
    qc = {'sampled_at': now.isoformat(), 'sample_point': 'Trước gộp', 'method': 'gram', 'sample_size': 100, 'total_defect': 40, 'black_defect': 0}
    assert op.post(url + '/qc', headers=oh, json=qc).status_code == 403
    assert mgr.post(url + '/qc', headers=mh, json=dict(qc, total_defect=101)).status_code == 422
    result = mgr.post(url + '/qc', headers=mh, json=qc)
    assert result.status_code == 200, result.text
    assert float(result.json()['black_percent']) == 0 and result.json()['burnt_percent'] is None
    r2 = create('M002')
    assert op.post(f'/api/drum-processing/runs/{r2}/discharge', headers=oh, json={'exit_time': now.isoformat(), 'final_moisture_percent': 12}).status_code == 200
    assert mgr.post(f'/api/drum-processing/runs/{r2}/qc', headers=mh, json=dict(qc, sample_size=300, total_defect=90)).status_code == 200
    report = mgr.get('/api/drum-processing/reports/qc').json()
    assert report['qc_count'] == 2 and float(report['groups'][0]['total_percent']) == 32.5
    assert other.get('/api/drum-processing/reports/qc', params={'facility_id': drum_data['facility_a_id']}).status_code == 404
    assert op.get('/api/health/ready').status_code == 200

    r3 = create('M003')
    url3 = f'/api/drum-processing/runs/{r3}'
    assert op.get(url3 + '/source').json()['waiting_minutes'] is None
    assert op.post(url3 + '/discharge', headers=oh, json={'exit_time': now.isoformat(), 'final_moisture_percent': 12}).status_code == 200
    assert mgr.get('/api/drum-processing/reports/qc').json()['pending_count'] == 1
    exact = dict(qc, sample_size=200, total_defect=80, black_defect=50, burnt_defect=10)
    result = mgr.post(url3 + '/qc', headers=mh, json=exact)
    assert result.status_code == 200, result.text
    assert [float(result.json()[key]) for key in ('total_percent', 'black_percent', 'burnt_percent')] == [40, 25, 5]
    assert op.get('/api/health/live').status_code == 200

    comparison = mgr.get('/api/drum-processing/reports/lot-comparison', params={'lot': 'SAME'})
    assert comparison.status_code == 200 and len(comparison.json()['runs']) == 1
    assert other.get('/api/drum-processing/reports/lot-comparison', params={'lot': 'SAME'}).json()['runs'] == []


def test_static_drying_beds_and_drum_source_acceptance_criteria(drum_data):
    op = drum_data["clients"]["operator"]
    other = drum_data["clients"]["other"]
    oh = {"X-CSRF-Token": drum_data["csrfs"]["operator"]}

    # 1. Scope check: operator can access static beds in Facility A, but cannot access Facility B
    beds_res = op.get("/api/drum-processing/static-beds")
    assert beds_res.status_code == 200, beds_res.text
    beds = beds_res.json()
    assert len(beds) == 4
    assert [b["bed_number"] for b in beds] == [1, 2, 3, 4]

    # Attempting to access other facility returns 404
    assert op.get("/api/drum-processing/static-beds", params={"facility_id": drum_data["facility_b_id"]}).status_code == 404

    # Sàn 2 info
    bed_2 = next(b for b in beds if b["bed_number"] == 2)
    bed_2_id = bed_2["id"]

    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(hours=18)

    # 2. Tiêu chí 2: Ghi một mẻ vào Sàn 2 với "Ướt", "Úng", và 20% úng
    batch_payload = {
        "bed_id": bed_2_id,
        "batch_code": "SAN2-ME-01",
        "coffee_type": "Cà quả tươi thu hái",
        "input_weight_kg": 2400.0,
        "entered_at": entry_time.isoformat(),
        "water_drained_status": "wet",       # Ướt
        "raw_material_status": "spoiled",   # Úng
        "estimated_spoiled_percent": 20.0,  # 20%
    }
    create_batch_res = op.post("/api/drum-processing/static-bed-batches", headers=oh, json=batch_payload)
    assert create_batch_res.status_code == 200, create_batch_res.text
    batch = create_batch_res.json()
    batch_id = batch["id"]
    assert batch["status"] == "on_bed"
    assert float(batch["estimated_spoiled_percent"]) == 20.0
    assert batch["water_drained_status"] == "wet"
    assert batch["raw_material_status"] == "spoiled"

    # Cannot create a second concurrent batch on Sàn 2 while one is on_bed
    assert op.post("/api/drum-processing/static-bed-batches", headers=oh, json=dict(batch_payload, batch_code="SAN2-ME-DUP")).status_code == 409

    # Ghi nhận các lượt đảo cà
    stirring_1 = op.post(
        f"/api/drum-processing/static-bed-batches/{batch_id}/stirrings",
        headers=oh,
        json={
            "started_at": (entry_time + timedelta(hours=3)).isoformat(),
            "ended_at": (entry_time + timedelta(hours=3, minutes=20)).isoformat(),
            "note": "Đảo lần 1, mặt sàn ráo nhẹ",
        },
    )
    assert stirring_1.status_code == 200, stirring_1.text
    assert stirring_1.json()["stirring_number"] == 1
    assert stirring_1.json()["duration_minutes"] == 20

    stirring_2 = op.post(
        f"/api/drum-processing/static-bed-batches/{batch_id}/stirrings",
        headers=oh,
        json={
            "started_at": (entry_time + timedelta(hours=7)).isoformat(),
            "duration_minutes": 25,
            "note": "Đảo lần 2, cà khô ráo mặt trên",
        },
    )
    assert stirring_2.status_code == 200, stirring_2.text
    assert stirring_2.json()["stirring_number"] == 2

    # Hoàn tất mẻ với "Ráo đều" (even)
    discharge_time = entry_time + timedelta(hours=16)
    discharge_res = op.post(
        f"/api/drum-processing/static-bed-batches/{batch_id}/discharge",
        headers=oh,
        json={
            "discharged_at": discharge_time.isoformat(),
            "discharge_drain_status": "even",  # Ráo đều
            "discharge_note": "Cà ráo đều đẹp, chuyển sang khu vực nạp trống",
        },
    )
    assert discharge_res.status_code == 200, discharge_res.text
    discharged_batch = discharge_res.json()
    assert discharged_batch["status"] == "discharged"
    assert discharged_batch["discharge_drain_status"] == "even"
    # Lịch sử vẫn giữ 20% úng lúc vào và "Ráo đều" lúc ra
    assert float(discharged_batch["estimated_spoiled_percent"]) == 20.0
    assert discharged_batch["water_drained_status"] == "wet"
    assert discharged_batch["total_bed_duration_minutes"] == 960  # 16h = 960m
    assert len(discharged_batch["stirrings"]) == 2

    # Cannot stir after discharge
    assert op.post(
        f"/api/drum-processing/static-bed-batches/{batch_id}/stirrings",
        headers=oh,
        json={"started_at": now.isoformat(), "duration_minutes": 15},
    ).status_code == 409

    # 3. Tiêu chí 3: Nạp TRONG-01, chọn "Sàn tĩnh xưởng trong" thì phải chọn số sàn.
    # Khi chọn Sàn 2 và liên kết mẻ vừa hoàn tất, chi tiết mẻ trống hiển thị đúng nguồn và dữ liệu mẻ sàn.
    drum_entry_time = discharge_time + timedelta(minutes=30)

    # Missing bed selection with indoor -> 422
    invalid_indoor = {
        "drum_id": drum_data["drum_1_id"],
        "batch_code": "ME-TRONG-01",
        "coffee_type": "Cà quả sấy ráo",
        "entry_time": drum_entry_time.isoformat(),
        "source_type": "indoor",
    }
    assert op.post("/api/drum-processing/runs", headers=oh, json=invalid_indoor).status_code == 422

    # Valid indoor with Sàn 2 and linked batch
    valid_indoor = dict(
        invalid_indoor,
        source_bed_id=bed_2_id,
        source_bed_batch_id=batch_id,
        initial_temperature_celsius=75.0,
    )
    run_res = op.post("/api/drum-processing/runs", headers=oh, json=valid_indoor)
    assert run_res.status_code == 200, run_res.text
    run_detail = run_res.json()
    assert run_detail["source_type"] == "indoor"
    assert run_detail["source_bed_id"] == bed_2_id
    assert run_detail["source_bed_number"] == 2
    assert run_detail["source_bed_batch"] is not None
    assert run_detail["source_bed_batch"]["batch_code"] == "SAN2-ME-01"
    assert run_detail["source_bed_batch"]["water_drained_status"] == "wet"
    assert run_detail["source_bed_batch"]["raw_material_status"] == "spoiled"
    assert float(run_detail["source_bed_batch"]["estimated_spoiled_percent"]) == 20.0
    assert run_detail["source_bed_batch"]["discharge_drain_status"] == "even"
    assert run_detail["source_bed_batch"]["stirring_count"] == 2

    # Test multi-drum linking: một mẻ sàn có thể chia cho nhiều trống
    # Discharging TRONG-01 first so drum becomes idle
    op.post(
        f"/api/drum-processing/runs/{run_detail['id']}/discharge",
        headers=oh,
        json={"exit_time": (drum_entry_time + timedelta(hours=8)).isoformat(), "final_moisture_percent": 12.5},
    )
    # Start second drum run on same drum (or another drum) reusing the same bed batch
    run_2_res = op.post(
        "/api/drum-processing/runs",
        headers=oh,
        json={
            "drum_id": drum_data["drum_1_id"],
            "batch_code": "ME-TRONG-02",
            "entry_time": (drum_entry_time + timedelta(hours=9)).isoformat(),
            "source_type": "indoor",
            "source_bed_number": 2,
            "source_bed_batch_id": batch_id,
        },
    )
    assert run_2_res.status_code == 200, run_2_res.text
    run_2_detail = run_2_res.json()
    assert run_2_detail["source_bed_batch"]["batch_code"] == "SAN2-ME-01"

    # 4. Tiêu chí 4: Khi chọn "Sàn tĩnh xưởng ngoài", không yêu cầu số sàn. Sau khi tải lại / lấy detail, vẫn hiển thị đúng nguồn.
    op.post(
        f"/api/drum-processing/runs/{run_2_detail['id']}/discharge",
        headers=oh,
        json={"exit_time": (drum_entry_time + timedelta(hours=15)).isoformat(), "final_moisture_percent": 12.0},
    )
    run_outdoor_res = op.post(
        "/api/drum-processing/runs",
        headers=oh,
        json={
            "drum_id": drum_data["drum_1_id"],
            "batch_code": "ME-TRONG-OUTDOOR",
            "entry_time": (drum_entry_time + timedelta(hours=16)).isoformat(),
            "source_type": "outdoor",
        },
    )
    assert run_outdoor_res.status_code == 200, run_outdoor_res.text
    outdoor_id = run_outdoor_res.json()["id"]

    # Re-fetch run detail
    refetched = op.get(f"/api/drum-processing/runs/{outdoor_id}").json()
    assert refetched["source_type"] == "outdoor"
    assert refetched["source_bed_number"] is None
    assert refetched["source_bed_batch"] is None

    # Test filtering in list_runs
    indoor_runs = op.get("/api/drum-processing/runs", params={"source_type": "indoor"}).json()
    assert len(indoor_runs) == 2
    assert all(r["source_type"] == "indoor" for r in indoor_runs)

    bed_2_runs = op.get("/api/drum-processing/runs", params={"source_bed_number": 2}).json()
    assert len(bed_2_runs) == 2

    even_drain_runs = op.get("/api/drum-processing/runs", params={"discharge_drain_status": "even"}).json()
    assert len(even_drain_runs) == 2

    outdoor_runs = op.get("/api/drum-processing/runs", params={"source_type": "outdoor"}).json()
    assert len(outdoor_runs) == 1
    assert outdoor_runs[0]["batch_code"] == "ME-TRONG-OUTDOOR"
