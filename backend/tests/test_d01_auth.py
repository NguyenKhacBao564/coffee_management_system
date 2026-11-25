from datetime import timedelta
import logging
import os
import secrets
import socket
import subprocess
import sys
import time

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.database import SessionLocal
from app.core.models import utcnow
from app.modules.accounts.models import AuthSession, User
from app.modules.audit.models import AccountAuditLog
from app.modules.facilities.models import Facility
from app.main import app
from app.modules.accounts.bootstrap_admin import create_first_admin
from app.modules.accounts.security import hash_password, token_hash


class TestSetup(dict):
    __test__ = False

    def __repr__(self) -> str:
        return "<isolated D01 test accounts>"


@pytest.fixture(autouse=True)
def clean_database():
    with SessionLocal.begin() as db:
        db.execute(text("TRUNCATE account_audit_logs, auth_sessions, login_attempts, user_facilities, users, facilities RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def setup_accounts():
    admin_password = secrets.token_urlsafe(18)
    manager_password = secrets.token_urlsafe(18)
    staff_password = secrets.token_urlsafe(18)
    other_site_password = secrets.token_urlsafe(18)
    with SessionLocal.begin() as db:
        site_a = Facility(code="SITE-A", name="Cơ sở A", is_active=True)
        site_b = Facility(code="SITE-B", name="Cơ sở B", is_active=True)
        db.add_all([site_a, site_b])
        db.flush()
        admin = User(username="admin.test", display_name="Quản trị thử", role="admin", password_hash=hash_password(admin_password), is_active=True)
        manager = User(username="manager.test", display_name="Quản lý thử", role="manager", password_hash=hash_password(manager_password), is_active=True, facilities=[site_a])
        staff = User(username="staff.test", display_name="Nhân viên thử", role="staff", password_hash=hash_password(staff_password), is_active=True, facilities=[site_a])
        other_site = User(username="other.site", display_name="Nhân viên cơ sở B", role="staff", password_hash=hash_password(other_site_password), is_active=True, facilities=[site_b])
        db.add_all([admin, manager, staff, other_site])
        db.flush()
        result = TestSetup(admin_id=admin.id, manager_id=manager.id, staff_id=staff.id, other_site_id=other_site.id, site_a=site_a.id, site_b=site_b.id)
    result.update(admin_password=admin_password, manager_password=manager_password, staff_password=staff_password, other_site_password=other_site_password)
    result["admin_client"] = TestClient(app)
    login(result["admin_client"], "admin.test", admin_password)
    return result


def login(client: TestClient, username: str, password: str) -> str:
    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    token = csrf.json()["csrf_token"]
    response = client.post("/api/auth/login", json={"username": username, "password": password}, headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def post_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def test_login_session_cookie_csrf_logout_and_expiry(setup_accounts, caplog):
    caplog.set_level(logging.INFO, logger="nhu_tung.accounts")
    data = setup_accounts
    client = TestClient(app)
    assert client.get("/api/auth/me").status_code == 401
    preauth = client.get("/api/auth/csrf")
    assert preauth.status_code == 200
    response = client.post("/api/auth/login", json={"username": "admin.test", "password": data["admin_password"]})
    assert response.status_code == 403
    assert client.post("/api/auth/login", json={"username": "admin.test", "password": data["admin_password"]}, headers=post_headers("wrong-token")).status_code == 403
    token = preauth.json()["csrf_token"]
    assert client.get("/api/auth/csrf").json()["csrf_token"] == token
    logged_in = client.post("/api/auth/login", json={"username": "admin.test", "password": data["admin_password"]}, headers=post_headers(token))
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["role"] == "admin"
    assert "password_hash" not in logged_in.text and "session_token_hash" not in logged_in.text
    cookie = client.cookies.get("nt_session")
    assert cookie and logged_in.headers.get("set-cookie")
    set_cookie = logged_in.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie and "path=/" in set_cookie
    assert "secure" not in set_cookie
    with SessionLocal() as db:
        stored = db.query(AuthSession).filter(AuthSession.token_hash == token_hash(cookie)).one()
        assert stored.user_id == data["admin_id"]
        assert stored.token_hash != cookie
        assert db.query(User).filter(User.id == data["admin_id"]).one().password_hash.startswith("$argon2id$")
    assert data["admin_password"] not in caplog.text and cookie not in caplog.text
    csrf = logged_in.json()["csrf_token"]
    assert client.get("/api/auth/csrf").json()["csrf_token"] == csrf
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers=post_headers(csrf)).status_code == 204
    client.cookies.set("nt_session", cookie)
    assert client.get("/api/auth/me").status_code == 401

    again = TestClient(app)
    login(again, "staff.test", data["staff_password"])
    with SessionLocal.begin() as db:
        raw_cookie = again.cookies.get("nt_session")
        session = db.query(AuthSession).filter(AuthSession.token_hash == token_hash(raw_cookie)).one()
        session.expires_at = utcnow() - timedelta(seconds=1)
    assert again.get("/api/auth/me").status_code == 401


def test_disabled_lockout_allows_retry_but_still_requires_valid_password(setup_accounts, monkeypatch):
    from app.core.config import get_settings
    from app.modules.accounts.models import LoginAttempt

    with SessionLocal.begin() as db:
        db.add(LoginAttempt(username_key="staff.test", failure_count=5,
                            window_started_at=utcnow(), blocked_until=utcnow() + timedelta(minutes=15)))
    monkeypatch.setattr(get_settings(), "login_lockout_enabled", False)
    client = TestClient(app)
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    for _ in range(6):
        assert client.post("/api/auth/login", json={"username": "staff.test", "password": "wrong"},
                           headers=post_headers(csrf)).status_code == 401
    response = client.post("/api/auth/login", json={"username": "staff.test", "password": setup_accounts["staff_password"]},
                           headers=post_headers(csrf))
    assert response.status_code == 200 and response.json()["user"]["role"] == "staff"


def test_generic_login_failures_and_rate_limit(setup_accounts):
    client = TestClient(app)
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    headers = post_headers(csrf)
    known = client.post("/api/auth/login", json={"username": "admin.test", "password": "not-the-password"}, headers=headers)
    missing = client.post("/api/auth/login", json={"username": "nobody.test", "password": "not-the-password"}, headers=headers)
    assert known.status_code == missing.status_code == 401
    assert known.json() == missing.json()
    assert "admin.test" not in known.text
    for _ in range(4):
        client.post("/api/auth/login", json={"username": "admin.test", "password": "bad-password"}, headers=headers)
    blocked = client.post("/api/auth/login", json={"username": "admin.test", "password": "bad-password"}, headers=headers)
    assert blocked.status_code == 429
    assert "admin.test" not in blocked.text


def test_manager_staff_scope_and_non_admin_forbidden(setup_accounts):
    data = setup_accounts
    manager, staff, site_b_staff = TestClient(app), TestClient(app), TestClient(app)
    manager_csrf = login(manager, "manager.test", data["manager_password"])
    login(staff, "staff.test", data["staff_password"])
    login(site_b_staff, "other.site", data["other_site_password"])
    assert [x["id"] for x in manager.get("/api/facilities").json()] == [data["site_a"]]
    assert manager.get(f"/api/facilities/{data['site_b']}").status_code == 404
    assert manager.post("/api/auth/active-facility", json={"facility_id": data["site_b"]}, headers=post_headers(manager_csrf)).status_code == 404
    assert [item["id"] for item in site_b_staff.get("/api/facilities").json()] == [data["site_b"]]
    assert site_b_staff.get(f"/api/facilities/{data['site_a']}").status_code == 404
    assert staff.get("/api/admin/accounts", headers={"X-Role": "admin", "X-Facility-Id": str(data["site_b"])}).status_code == 403
    assert staff.get("/api/admin/system/status").status_code == 403
    assert staff.get("/api/admin/audit").status_code == 403
    assert staff.get("/api/health/ready").json() == {"status": "ok"}
    assert setup_accounts["admin_client"].get("/api/facilities").json() == [
        {"id": data["site_a"], "code": "SITE-A", "name": "Cơ sở A"},
        {"id": data["site_b"], "code": "SITE-B", "name": "Cơ sở B"},
    ]


def test_role_and_facility_changes_apply_on_next_request(setup_accounts):
    data = setup_accounts
    manager = TestClient(app)
    login(manager, "manager.test", data["manager_password"])
    admin_csrf = data["admin_client"].get("/api/auth/csrf").json()["csrf_token"]
    updated = data["admin_client"].patch(
        f"/api/admin/accounts/{data['manager_id']}",
        json={"display_name": "Nhân viên chuyển vai trò", "role": "staff", "facility_ids": [data["site_b"]]},
        headers=post_headers(admin_csrf),
    )
    assert updated.status_code == 200
    profile = manager.get("/api/auth/me").json()
    assert profile["role"] == "staff"
    assert [f["id"] for f in profile["facilities"]] == [data["site_b"]]
    assert manager.get("/api/admin/accounts").status_code == 403
    assert manager.get(f"/api/facilities/{data['site_a']}").status_code == 404
    assert manager.get(f"/api/facilities/{data['site_b']}").status_code == 200


def test_disable_reactivate_does_not_restore_old_session(setup_accounts):
    data = setup_accounts
    staff = TestClient(app)
    login(staff, "staff.test", data["staff_password"])
    admin = data["admin_client"]
    csrf = admin.get("/api/auth/csrf").json()["csrf_token"]
    assert admin.patch(f"/api/admin/accounts/{data['staff_id']}/status?is_active=false", headers=post_headers(csrf)).status_code == 200
    assert staff.get("/api/auth/me").status_code == 401
    assert admin.patch(f"/api/admin/accounts/{data['staff_id']}/status?is_active=true", headers=post_headers(csrf)).status_code == 200
    assert staff.get("/api/auth/me").status_code == 401
    login(staff, "staff.test", data["staff_password"])
    assert staff.get("/api/auth/me").status_code == 200


def test_reset_and_change_password_revoke_old_sessions_and_audit_secrets(setup_accounts):
    data = setup_accounts
    target_a, target_b = TestClient(app), TestClient(app)
    login(target_a, "staff.test", data["staff_password"])
    login(target_b, "staff.test", data["staff_password"])
    new_password = secrets.token_urlsafe(18)
    admin = data["admin_client"]
    admin_csrf = admin.get("/api/auth/csrf").json()["csrf_token"]
    reset = admin.post(f"/api/admin/accounts/{data['staff_id']}/reset-password", json={"new_password": new_password}, headers=post_headers(admin_csrf))
    assert reset.status_code == 204
    assert target_a.get("/api/auth/me").status_code == target_b.get("/api/auth/me").status_code == 401
    login(target_a, "staff.test", new_password)
    assert target_a.get("/api/auth/me").status_code == 200

    other_session = TestClient(app)
    login(other_session, "manager.test", data["manager_password"])
    old_cookie = other_session.cookies.get("nt_session")
    change_csrf = other_session.get("/api/auth/csrf").json()["csrf_token"]
    replacement = secrets.token_urlsafe(18)
    changed = other_session.post("/api/auth/change-password", json={"current_password": data["manager_password"], "new_password": replacement}, headers=post_headers(change_csrf))
    assert changed.status_code == 200
    assert other_session.get("/api/auth/me").status_code == 200
    with SessionLocal() as db:
        assert db.query(AuthSession).filter(AuthSession.token_hash == token_hash(old_cookie)).one().revoked_at is not None
        log = db.query(AccountAuditLog).filter(AccountAuditLog.event.in_(["password_reset", "password_changed"])).all()
        assert len(log) == 2
        assert all(new_password not in str(item.changes) and replacement not in str(item.changes) for item in log)
    assert new_password not in reset.text and replacement not in changed.text


def test_final_active_admin_cannot_be_demoted_or_disabled(setup_accounts):
    data = setup_accounts
    client, csrf = data["admin_client"], data["admin_client"].get("/api/auth/csrf").json()["csrf_token"]
    demote = client.patch(f"/api/admin/accounts/{data['admin_id']}", json={"display_name": "Quản trị thử", "role": "staff", "facility_ids": [data['site_a']]}, headers=post_headers(csrf))
    disable = client.patch(f"/api/admin/accounts/{data['admin_id']}/status?is_active=false", headers=post_headers(csrf))
    assert demote.status_code == disable.status_code == 409
    assert client.get("/api/auth/me").json()["role"] == "admin"


def test_account_create_filter_pagination_and_audit_never_return_password(setup_accounts):
    data = setup_accounts
    client = data["admin_client"]
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    password = secrets.token_urlsafe(18)
    rejected = client.post("/api/admin/accounts", json={"username": "missing.csrf", "display_name": "Thiếu CSRF", "role": "staff", "facility_ids": [data['site_a']], "password": password})
    assert rejected.status_code == 403
    too_long_password = "x" * 300
    invalid = client.post("/api/admin/accounts", json={"username": "invalid.password", "display_name": "Mật khẩu lỗi", "role": "staff", "facility_ids": [data['site_a']], "password": too_long_password}, headers=post_headers(csrf))
    assert invalid.status_code == 422 and too_long_password not in invalid.text
    created = client.post("/api/admin/accounts", json={"username": "new.staff", "display_name": "Nhân viên mới", "role": "staff", "facility_ids": [data['site_b']], "password": password}, headers=post_headers(csrf))
    assert created.status_code == 201
    assert "password" not in created.json() and "password_hash" not in created.json()
    duplicate = client.post("/api/admin/accounts", json={"username": "NEW.STAFF", "display_name": "Trùng username", "role": "staff", "facility_ids": [data['site_b']], "password": password}, headers=post_headers(csrf))
    assert duplicate.status_code == 409
    assert client.get("/api/admin/accounts?q=new.staff&role=staff&active=true&page=1&page_size=1").json()["total"] == 1
    assert client.get("/api/admin/accounts?page=1&page_size=1").json()["page_size"] == 1
    assert client.post("/api/admin/accounts", json={"username": "no.site", "display_name": "Thiếu cơ sở", "role": "manager", "facility_ids": [], "password": password}, headers=post_headers(csrf)).status_code == 422
    audit = client.get("/api/admin/audit").json()
    assert any(item["event"] == "account_created" and item["target_username"] == "new.staff" for item in audit["items"])
    assert password not in str(audit)


def test_first_admin_bootstrap_is_non_overwriting_and_creates_demo_facility():
    password = secrets.token_urlsafe(18)
    with SessionLocal.begin() as db:
        assert create_first_admin(db, " First.Admin ", "Quản trị đầu tiên", password) is True
    with SessionLocal.begin() as db:
        assert create_first_admin(db, "second.admin", "Không được tạo", secrets.token_urlsafe(18)) is False
        assert db.query(User).filter(User.role == "admin").count() == 1
        assert db.query(Facility).filter(Facility.code == "DEMO", Facility.is_demo.is_(True)).count() == 1
    client = TestClient(app)
    login(client, "first.admin", password)


def test_cookie_secure_setting_is_environment_specific():
    local = Settings(app_env="local")
    production = Settings(app_env="production")
    assert local.session_cookie_secure is False
    assert local.session_cookie_name == "nt_session"
    assert production.session_cookie_secure is True
    assert production.session_cookie_name.startswith("__Host-")


def test_session_survives_api_process_restart(setup_accounts):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    def start_server():
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            env={**os.environ, "APP_ENV": "test"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError("Test API process stopped during startup")
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/health/ready", timeout=0.5).status_code == 200:
                    return process
            except httpx.HTTPError:
                time.sleep(0.05)
        process.terminate()
        raise AssertionError("Test API did not become ready")

    server = start_server()
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}")
    try:
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        signed_in = client.post("/api/auth/login", json={"username": "admin.test", "password": setup_accounts["admin_password"]}, headers=post_headers(csrf))
        assert signed_in.status_code == 200
        server.terminate()
        server.wait(timeout=5)
        server = start_server()
        assert client.get("/api/auth/me").status_code == 200
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        assert client.post("/api/auth/logout", headers=post_headers(csrf)).status_code == 204
        assert client.get("/api/auth/me").status_code == 401
    finally:
        client.close()
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
