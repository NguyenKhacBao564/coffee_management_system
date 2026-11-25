from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.accounts.models import User
from app.modules.accounts.security import hash_password
from app.modules.facilities.models import Facility
from app.modules.goods.models import GoodsItem, GoodsTransaction
from app.modules.trips.models import Trip, Vehicle
from app.modules.weighings.models import WeighEvent, WeighResult
from app.main import app


class Setup(dict):
    __test__ = False
    def __repr__(self): return "<isolated D02 setup>"


@pytest.fixture(autouse=True)
def clean_database():
    with SessionLocal.begin() as db:
        db.execute(text("TRUNCATE business_audit_logs, goods_transactions, weigh_results, weigh_events, trips, schedule_lines, schedules, vehicles, goods_items, account_audit_logs, auth_sessions, login_attempts, user_facilities, users, facilities RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def data():
    passwords = {key: secrets.token_urlsafe(18) for key in ("staff", "manager", "other", "admin")}
    with SessionLocal.begin() as db:
        a = Facility(code="D02-A", name="Cơ sở A", is_active=True); b = Facility(code="D02-B", name="Cơ sở B", is_active=True)
        db.add_all([a,b]); db.flush()
        staff = User(username="d02.staff", display_name="Nhân viên", role="staff", password_hash=hash_password(passwords["staff"]), is_active=True, facilities=[a])
        manager = User(username="d02.manager", display_name="Quản lý", role="manager", password_hash=hash_password(passwords["manager"]), is_active=True, facilities=[a])
        other = User(username="d02.other", display_name="Cơ sở khác", role="staff", password_hash=hash_password(passwords["other"]), is_active=True, facilities=[b])
        admin = User(username="d02.admin", display_name="Admin", role="admin", password_hash=hash_password(passwords["admin"]), is_active=True)
        db.add_all([staff, manager, other, admin]); db.flush()
        ids = {"facility": a.id, "other_facility": b.id, "staff": staff.id, "manager": manager.id, "other": other.id, "admin": admin.id}
        db.add(GoodsItem(facility_id=a.id, name="Cà phê nhân")); db.add(GoodsItem(facility_id=b.id, name="Cà phê khác"))
    clients = {}
    for role in passwords:
        clients[role] = TestClient(app)
        csrf = clients[role].get("/api/auth/csrf").json()["csrf_token"]
        login = clients[role].post("/api/auth/login", json={"username": f"d02.{role}" if role != "other" else "d02.other", "password": passwords[role]}, headers={"X-CSRF-Token": csrf})
        assert login.status_code == 200, login.text
        clients[role].csrf = login.json()["csrf_token"]
    return Setup(ids=ids, clients=clients, passwords=passwords)


def post(client, url, body=None, headers=None):
    return client.post(url, json=body, headers={"X-CSRF-Token": client.csrf, **(headers or {})})


def new_trip(client, code="T-01", vehicle_id=None, schedule_id=None):
    response = post(client, "/api/d02/trips", {"trip_code": code, "vehicle_id": vehicle_id, "schedule_id": schedule_id})
    assert response.status_code == 200, response.text
    return response.json()


def weigh(client, trip_id, kg, *, time_minute, reweigh=None, acknowledge=True):
    stamp = datetime(2026, 5, 1, 4, time_minute, tzinfo=timezone.utc).isoformat()
    response = post(client, f"/api/d02/trips/{trip_id}/weighings", {"weighed_at": stamp, "weight_kg": str(kg), "reweigh_of_event_id": reweigh, "vehicle_position_confirmed": acknowledge, "people_exited_confirmed": acknowledge})
    assert response.status_code == 200, response.text
    result = response.json()
    if acknowledge:
        selected = post(client, f"/api/d02/weighings/{result['event_id']}/select/{result['id']}")
        assert selected.status_code == 200, selected.text
    return result


def transaction(client, trip, a, b, direction="import", key=None):
    return post(client, f"/api/d02/trips/{trip['id']}/transactions", {"goods_item_id": 1, "direction": direction, "before_result_id": a["id"], "after_result_id": b["id"]}, {"Idempotency-Key": key or str(uuid4())})


def test_manual_import_export_and_reweigh_does_not_double_count(data):
    staff = data["clients"]["staff"]
    trip = new_trip(staff)
    a = weigh(staff, trip["id"], 20000, time_minute=0)
    b = weigh(staff, trip["id"], 15000, time_minute=2)
    c = weigh(staff, trip["id"], 14980, time_minute=3, reweigh=(staff.get(f"/api/d02/trips/{trip['id']}").json()["weighings"][1]["event_id"]))
    d = weigh(staff, trip["id"], 10000, time_minute=4)
    excluded = post(staff, f"/api/d02/weighings/{c['event_id']}/exclude", {"reason": "Cân đối chiếu lại lượt B"})
    assert excluded.status_code == 200
    first = transaction(staff, trip, a, b)
    second = transaction(staff, trip, b, d)
    assert first.status_code == second.status_code == 200
    assert Decimal(first.json()["weight_kg"]) == Decimal("5000.000")
    assert Decimal(second.json()["weight_kg"]) == Decimal("5000.000")
    for tx_response in (first, second):
        tx = tx_response.json()
        assert post(staff, f"/api/d02/transactions/{tx['id']}/submit", {"version": tx["version"]}).status_code == 200
    assert transaction(staff, trip, a, d).status_code == 200  # draft creation is permitted; submission must block overlap
    overlap = staff.get(f"/api/d02/trips/{trip['id']}").json()["transactions"][-1]
    assert post(staff, f"/api/d02/transactions/{overlap['id']}/submit", {"version": overlap["version"]}).status_code == 409

    export_trip = new_trip(staff, "T-OUT")
    x = weigh(staff, export_trip["id"], 10000, time_minute=10)
    y = weigh(staff, export_trip["id"], 13500, time_minute=11)
    exported = transaction(staff, export_trip, x, y, direction="export")
    assert exported.status_code == 200 and Decimal(exported.json()["weight_kg"]) == Decimal("3500.000")


def test_wrong_direction_zero_staff_confirmation_and_duplicate_request(data):
    staff = data["clients"]["staff"]; manager = data["clients"]["manager"]; trip = new_trip(staff)
    a = weigh(staff, trip["id"], 1000, time_minute=0); b = weigh(staff, trip["id"], 1500, time_minute=1)
    assert transaction(staff, trip, a, b, "import").status_code == 422
    assert transaction(staff, trip, a, b, "export").status_code == 200
    same_key = "retry-transaction-1"
    first = transaction(staff, trip, a, b, "export", same_key)
    retry = transaction(staff, trip, a, b, "export", same_key)
    assert first.json()["id"] == retry.json()["id"]
    tx = first.json()
    submitted = post(staff, f"/api/d02/transactions/{tx['id']}/submit", {"version": tx["version"]})
    assert submitted.status_code == 200
    assert post(staff, f"/api/d02/transactions/{tx['id']}/confirm", {"version": submitted.json()["version"]}).status_code == 403
    confirmed = post(manager, f"/api/d02/transactions/{tx['id']}/confirm", {"version": submitted.json()["version"]})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    again = post(manager, f"/api/d02/transactions/{tx['id']}/confirm", {"version": 1})
    assert again.status_code == 200 and again.json()["id"] == tx["id"]


def test_permissions_cross_facility_ids_and_unknown_plate_then_add(data):
    staff = data["clients"]["staff"]; other = data["clients"]["other"]; admin = data["clients"]["admin"]
    vehicle = post(staff, "/api/d02/vehicles", {"plate_original": "51A-123.45"})
    assert vehicle.status_code == 200
    assert post(staff, "/api/d02/vehicles", {"plate_original": "51a 12345"}).status_code == 409
    trip = new_trip(staff, "UNKNOWN")
    a = weigh(staff, trip["id"], 10, time_minute=0)
    assert trip["vehicle_id"] is None
    attached = post(staff, f"/api/d02/trips/{trip['id']}/vehicle", {"vehicle_id": vehicle.json()["id"]})
    assert attached.status_code == 200 and attached.json()["plate_original"] == "51A-123.45"
    assert post(other, f"/api/d02/trips/{trip['id']}/vehicle", {"vehicle_id": vehicle.json()["id"]}).status_code == 404
    assert other.get(f"/api/d02/trips/{trip['id']}").status_code == 404
    assert post(admin, "/api/d02/trips", {"trip_code": "no"}).status_code == 403
    assert post(admin, "/api/d02/goods", {"name": "no"}).status_code == 403
    schedule = post(staff, "/api/d02/schedules", {"expected_at": "2026-05-01T04:00:00Z", "direction": "import", "expected_vehicle_id": vehicle.json()["id"]})
    assert schedule.status_code == 200 and schedule.json()["lines"] == []
    assert post(other, "/api/d02/trips", {"trip_code": "cross", "schedule_id": schedule.json()["id"]}).status_code == 404
    assert a["source"] == "manual"


def test_reweigh_replacement_keeps_history_and_flags_draft(data):
    staff = data["clients"]["staff"]; trip = new_trip(staff)
    a = weigh(staff, trip["id"], 5000, time_minute=0); b = weigh(staff, trip["id"], 3000, time_minute=1)
    draft = transaction(staff, trip, a, b).json()
    replaced = post(staff, f"/api/d02/weighings/{b['event_id']}/results/{b['id']}/replace", {"weight_kg": "2990", "reason": "Đọc nhầm một chữ số"})
    assert replaced.status_code == 200
    detail = staff.get(f"/api/d02/trips/{trip['id']}").json()
    assert len([w for w in detail["weighings"] if w["event_id"] == b["event_id"]]) == 2
    flagged = next(tx for tx in detail["transactions"] if tx["id"] == draft["id"])
    assert flagged["needs_review"] is True
    assert post(staff, f"/api/d02/transactions/{draft['id']}/submit", {"version": flagged["version"]}).status_code == 409
    selected = post(staff, f"/api/d02/weighings/{b['event_id']}/select/{replaced.json()['id']}")
    assert selected.status_code == 200


def test_trip_cannot_complete_without_vehicle_or_unhandled_items_and_overview_only_confirmed(data):
    manager = data["clients"]["manager"]; staff = data["clients"]["staff"]
    trip = new_trip(staff, "NO-PLATE")
    assert post(manager, f"/api/d02/trips/{trip['id']}/complete", {"version": trip["version"]}).status_code == 409
    overview = staff.get("/api/d02/overview?day=2026-05-01").json()
    assert overview["timezone"] == "Asia/Ho_Chi_Minh"
    assert Decimal(str(overview["confirmed_import_kg"])) == 0


def test_pending_manual_ack_zero_delta_mixed_types_and_cross_trip_result_guard(data):
    staff = data["clients"]["staff"]
    trip = new_trip(staff, "MIXED")
    pending = weigh(staff, trip["id"], 30000, time_minute=0, acknowledge=False)
    assert post(staff, f"/api/d02/weighings/{pending['event_id']}/select/{pending['id']}").status_code == 409
    assert post(staff, f"/api/d02/weighings/{pending['event_id']}/acknowledge").status_code == 200
    assert post(staff, f"/api/d02/weighings/{pending['event_id']}/select/{pending['id']}").status_code == 200
    b = weigh(staff, trip["id"], 20000, time_minute=1)
    c = weigh(staff, trip["id"], 23500, time_minute=2)
    # Add a second distinct goods category for this facility.
    extra_goods = post(staff, "/api/d02/goods", {"name": "Bao bì"})
    assert extra_goods.status_code == 200
    first = transaction(staff, trip, pending, b, "import")
    second = post(staff, f"/api/d02/trips/{trip['id']}/transactions", {"goods_item_id": extra_goods.json()["id"], "direction": "export", "before_result_id": b["id"], "after_result_id": c["id"]}, {"Idempotency-Key": "mixed-other-good"})
    assert second.status_code == 200
    assert Decimal(first.json()["weight_kg"]) == Decimal("10000.000")
    assert Decimal(second.json()["weight_kg"]) == Decimal("3500.000")
    equal = weigh(staff, trip["id"], 23500, time_minute=3)
    assert transaction(staff, trip, c, equal, "import").status_code == 422
    unrelated_trip = new_trip(staff, "OTHER-TRIP")
    unrelated = weigh(staff, unrelated_trip["id"], 1000, time_minute=4)
    assert transaction(staff, trip, pending, unrelated, "import").status_code == 404


def test_cancelled_confirmed_transaction_can_be_replaced_with_history(data):
    staff = data["clients"]["staff"]; manager = data["clients"]["manager"]; trip = new_trip(staff, "REPLACE-TX")
    a = weigh(staff, trip["id"], 8000, time_minute=0); b = weigh(staff, trip["id"], 5000, time_minute=1)
    old = transaction(staff, trip, a, b).json()
    sent = post(staff, f"/api/d02/transactions/{old['id']}/submit", {"version": old["version"]}).json()
    confirmed = post(manager, f"/api/d02/transactions/{old['id']}/confirm", {"version": sent["version"]})
    assert confirmed.status_code == 200
    assert post(manager, f"/api/d02/transactions/{old['id']}/cancel", {"reason": "Nhầm loại hàng"}).status_code == 200
    replacement = post(staff, f"/api/d02/trips/{trip['id']}/transactions", {"goods_item_id": 1, "direction": "import", "before_result_id": a["id"], "after_result_id": b["id"], "replacement_for_id": old["id"]}, {"Idempotency-Key": "replacement-1"})
    assert replacement.status_code == 200 and replacement.json()["replacement_for_id"] == old["id"]
    history = staff.get(f"/api/d02/trips/{trip['id']}").json()["transactions"]
    assert [x["status"] for x in history] == ["cancelled", "draft"]


def test_optimistic_version_and_parallel_confirmation_are_idempotent(data):
    staff = data["clients"]["staff"]; manager = data["clients"]["manager"]; trip = new_trip(staff, "CONCURRENT")
    a = weigh(staff, trip["id"], 7000, time_minute=0); b = weigh(staff, trip["id"], 6000, time_minute=1)
    tx = transaction(staff, trip, a, b).json()
    update = {"goods_item_id": 1, "direction": "import", "before_result_id": a["id"], "after_result_id": b["id"], "version": tx["version"]}
    assert staff.patch(f"/api/d02/transactions/{tx['id']}", json=update, headers={"X-CSRF-Token": staff.csrf}).status_code == 200
    assert staff.patch(f"/api/d02/transactions/{tx['id']}", json=update, headers={"X-CSRF-Token": staff.csrf}).status_code == 409
    refreshed = staff.get(f"/api/d02/trips/{trip['id']}").json()["transactions"][0]
    sent = post(staff, f"/api/d02/transactions/{tx['id']}/submit", {"version": refreshed["version"]}).json()
    second_manager = TestClient(app)
    token = second_manager.get("/api/auth/csrf").json()["csrf_token"]
    login_response = second_manager.post("/api/auth/login", json={"username": "d02.manager", "password": data["passwords"]["manager"]}, headers={"X-CSRF-Token": token})
    assert login_response.status_code == 200
    second_manager.csrf = login_response.json()["csrf_token"]
    clients = [manager, second_manager]
    def confirm(client): return post(client, f"/api/d02/transactions/{tx['id']}/confirm", {"version": sent["version"]})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(confirm, clients))
    assert all(r.status_code == 200 for r in responses)
    assert len([r for r in responses if r.json()["status"] == "confirmed"]) == 2


def test_local_day_boundary_is_vietnam_time_and_excludes_drafts(data):
    staff = data["clients"]["staff"]; manager = data["clients"]["manager"]
    accepted = []
    for code in ("BOUNDARY-IN", "BOUNDARY-OUT"):
        trip = new_trip(staff, code)
        a = weigh(staff, trip["id"], 9000, time_minute=0); b = weigh(staff, trip["id"], 8000, time_minute=1)
        tx = transaction(staff, trip, a, b).json()
        sent = post(staff, f"/api/d02/transactions/{tx['id']}/submit", {"version": tx["version"]}).json()
        post(manager, f"/api/d02/transactions/{tx['id']}/confirm", {"version": sent["version"]})
        accepted.append(tx["id"])
    with SessionLocal.begin() as db:
        inside = db.get(GoodsTransaction, accepted[0]); outside = db.get(GoodsTransaction, accepted[1])
        inside.created_at = datetime(2026, 4, 30, 17, 0, tzinfo=timezone.utc)
        outside.created_at = datetime(2026, 4, 30, 16, 59, 59, tzinfo=timezone.utc)
    summary = staff.get("/api/d02/overview?day=2026-05-01").json()
    assert Decimal(str(summary["confirmed_import_kg"])) == Decimal("1000.000")
