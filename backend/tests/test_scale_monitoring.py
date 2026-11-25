import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from starlette.requests import Request

from app.core.database import SessionLocal, engine
from app.main import app
from app.modules.accounts.models import User
from app.modules.accounts.security import create_session
from app.modules.facilities.models import Facility
from app.modules.goods.models import GoodsTransaction
from app.modules.scale_ingestion.models import ScaleAgent, ScaleSignal
from app.modules.scale_ingestion.provenance import S03A_AGENT_ID, S03A_EVENT_IDS
from app.modules.scale_ingestion.router import _agent_from_bearer
from app.modules.trips.models import Trip
from app.modules.weighings.models import WeighEvent

BASE = "/api/scale-monitoring"
NOW = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_database():
    assert engine.url.database.startswith("nhutung_d02_test_"), "Monitoring tests require the disposable DB runner"
    with SessionLocal.begin() as db:
        db.execute(text("TRUNCATE facilities, users, auth_sessions, account_audit_logs, login_attempts RESTART IDENTITY CASCADE"))


class Setup(dict):
    def __repr__(self):
        return "<isolated monitoring fixture>"


@pytest.fixture
def data():
    with SessionLocal.begin() as db:
        a = Facility(code="A", name="Cơ sở A", is_active=True)
        b = Facility(code="B", name="Cơ sở B", is_active=True)
        inactive = Facility(code="C", name="Cơ sở tắt", is_active=False)
        db.add_all([a, b, inactive]); db.flush()
        agent = ScaleAgent(agent_id=S03A_AGENT_ID, display_name="Cân A", facility_id=a.id, scale_code="A1", is_active=True, token_hash="a" * 64)
        other = ScaleAgent(agent_id=str(uuid4()), display_name="Cân B", facility_id=b.id, scale_code="B1", is_active=True, token_hash="b" * 64)
        empty = ScaleAgent(agent_id=str(uuid4()), display_name="Cân chưa có mẫu", facility_id=a.id, scale_code="A2", is_active=False, token_hash="c" * 64)
        hidden = ScaleAgent(agent_id=str(uuid4()), display_name="Cân C", facility_id=inactive.id, scale_code="C1", is_active=True, token_hash="d" * 64)
        db.add_all([agent, other, empty, hidden]); db.flush()
        clients, users = {}, {}
        for role in ["staff", "manager", "other", "admin"]:
            user = User(username=f"monitor.{role}", display_name=role, role="staff" if role == "other" else role,
                        password_hash="unused-test-session-password", is_active=True,
                        facilities=[] if role == "admin" else [b] if role == "other" else [a])
            db.add(user); db.flush()
            _, cookie, _ = create_session(db, user, a.id if role != "other" else b.id)
            client = TestClient(app)
            client.cookies.set("nt_session", cookie)
            clients[role] = client; users[role] = user.id
        return Setup(a=a.id, b=b.id, inactive=inactive.id, agent=agent.agent_id,
                     other=other.agent_id, empty=empty.agent_id, hidden=hidden.agent_id, clients=clients, users=users)


def insert_signal(db, agent, sequence, observed, received, *, event_id=None, weight=Decimal("1500.250")):
    row = ScaleSignal(agent_id=agent, event_id=event_id or uuid4(), sequence=sequence,
                      observed_at_utc=observed, received_at_utc=received, weight_kg=weight,
                      vendor_text="Monitoring test fixture", source="canxe2015_ui", schema_version=1)
    db.add(row); db.flush()
    return str(row.event_id)


@pytest.mark.parametrize("role", ["staff", "manager", "other", "admin"])
def test_session_scope_for_catalog_history_and_direct_latest(data, role):
    with SessionLocal.begin() as db:
        a_id = insert_signal(db, data["agent"], 1, NOW, NOW)
        b_id = insert_signal(db, data["other"], 1, NOW, NOW)
        insert_signal(db, data["hidden"], 1, NOW, NOW)
    client = data["clients"][role]
    expected_agents = {data["other"]} if role == "other" else {data["agent"], data["empty"]}
    expected_ids = {b_id} if role == "other" else {a_id}
    if role == "admin":
        expected_agents.add(data["other"]); expected_ids.add(b_id)
    catalog = client.get(f"{BASE}/agents")
    assert catalog.status_code == 200
    assert {item["agent_id"] for item in catalog.json()["items"]} == expected_agents
    history = client.get(f"{BASE}/signals")
    assert {item["event_id"] for item in history.json()["items"]} == expected_ids
    unauthorized = data["agent"] if role == "other" else data["other"]
    if role != "admin":
        assert client.get(f"{BASE}/agents/{unauthorized}/latest").status_code == 404
        assert client.get(f"{BASE}/signals", params={"agent_id": unauthorized}).status_code == 404
        fid = data["a"] if role == "other" else data["b"]
        assert client.get(f"{BASE}/agents", params={"facility_id": fid}).status_code == 404
        assert client.get(f"{BASE}/signals", params={"facility_id": fid}).status_code == 404
    assert client.get(f"{BASE}/agents/{data['hidden']}/latest").status_code == 404
    assert client.get(f"{BASE}/signals", params={"facility_id": data["inactive"]}).status_code == 404
    assert data["hidden"] not in catalog.text
    assert "token_hash" not in catalog.text and "token_hash" not in history.text
    assert "a" * 64 not in catalog.text


def test_agent_bearer_cannot_access_user_monitoring_api(data):
    # A credential that really authenticates S01 still cannot become a user session.
    with SessionLocal.begin() as db:
        agent = db.get(ScaleAgent, data["agent"])
        agent.token_hash = hashlib.sha256(b"scale-token").hexdigest()
    with SessionLocal() as db:
        request = Request({"type": "http", "headers": [(b"authorization", b"Bearer scale-token")]})
        assert _agent_from_bearer(request, db).agent_id == data["agent"]
    client = TestClient(app)
    for path in ["/agents", "/signals", f"/agents/{data['agent']}/latest"]:
        assert client.get(BASE + path, headers={"Authorization": "Bearer scale-token"}).status_code == 401
    client.cookies.set("nt_session", "scale-token")
    assert client.get(f"{BASE}/signals").status_code == 401


def test_scope_revocation_and_inactive_facility_apply_to_existing_session(data):
    client = data["clients"]["staff"]
    assert client.get(f"{BASE}/agents/{data['agent']}/latest").status_code == 200
    with SessionLocal.begin() as db:
        db.get(User, data["users"]["staff"]).facilities = []
    assert client.get(f"{BASE}/agents/{data['agent']}/latest").status_code == 404
    assert client.get(f"{BASE}/signals").json()["total"] == 0
    with SessionLocal.begin() as db:
        db.get(Facility, data["a"]).is_active = False
    assert data["clients"]["admin"].get(f"{BASE}/agents/{data['agent']}/latest").status_code == 404
    with SessionLocal.begin() as db:
        db.get(User, data["users"]["manager"]).is_active = False
    assert data["clients"]["manager"].get(f"{BASE}/signals").status_code == 401


def test_latest_uses_observation_time_with_stable_tie_breaker(data):
    with SessionLocal.begin() as db:
        late_backfill = insert_signal(db, data["agent"], 1, NOW - timedelta(days=1), NOW + timedelta(minutes=3))
        insert_signal(db, data["agent"], 2, NOW, NOW)
        newest_tied = insert_signal(db, data["agent"], 3, NOW, NOW + timedelta(seconds=1))
    client = data["clients"]["staff"]
    latest = client.get(f"{BASE}/agents/{data['agent']}/latest").json()["latest"]
    assert latest["event_id"] == newest_tied and latest["event_id"] != late_backfill
    assert latest["sequence"] == "3" and latest["weight_kg"] == "1500.250"
    assert datetime.fromisoformat(latest["observed_at_utc"]) == NOW
    catalog = client.get(f"{BASE}/agents").json()["items"]
    assert next(a for a in catalog if a["agent_id"] == data["agent"])["latest"] == latest
    assert client.get(f"{BASE}/agents/{data['empty']}/latest").json()["latest"] is None


def test_history_pagination_filters_and_bounds(data):
    with SessionLocal.begin() as db:
        event_ids = [insert_signal(db, data["agent"], i, NOW + timedelta(seconds=i), NOW) for i in range(1, 6)]
        insert_signal(db, data["other"], 1, NOW, NOW)
    client = data["clients"]["admin"]
    params = {"facility_id": data["a"], "agent_id": data["agent"], "page_size": 2}
    first = client.get(f"{BASE}/signals", params=params).json()
    second = client.get(f"{BASE}/signals", params={**params, "page": 2}).json()
    third = client.get(f"{BASE}/signals", params={**params, "page": 3}).json()
    assert first["total"] == second["total"] == third["total"] == 5
    assert [s["event_id"] for page in [first, second, third] for s in page["items"]] == list(reversed(event_ids))
    assert first == client.get(f"{BASE}/signals", params=params).json()
    filtered = client.get(f"{BASE}/signals", params={**params, "page_size": 100, "observed_from": (NOW + timedelta(seconds=2)).isoformat(), "observed_to": (NOW + timedelta(seconds=4)).isoformat()}).json()
    assert [s["sequence"] for s in filtered["items"]] == ["4", "3", "2"]
    assert client.get(f"{BASE}/signals", params={**params, "page": 99}).json()["items"] == []
    assert client.get(f"{BASE}/signals", params={"facility_id": data["a"], "agent_id": data["other"]}).status_code == 404
    for invalid in [{"page": 0}, {"page_size": 101}, {"observed_from": "2026-01-01T00:00:00"}, {"observed_to": "2026-01-01T00:00:00+07:00"}, {"observed_from": "2026-02-01T00:00:00Z", "observed_to": "2026-01-01T00:00:00Z"}]:
        assert client.get(f"{BASE}/signals", params=invalid).status_code == 422
    assert client.get(f"{BASE}/agents", params={"page_size": 101}).status_code == 422
    pages = [client.get(f"{BASE}/agents", params={"page_size": 1, "page": i}).json()["items"][0]["agent_id"] for i in range(1, 4)]
    assert pages == [data["agent"], data["empty"], data["other"]]


def test_synthetic_provenance_is_per_verified_agent_event_pair_and_reads_do_not_write_d02(data):
    test_id = UUID(sorted(S03A_EVENT_IDS)[0])
    with SessionLocal.begin() as db:
        insert_signal(db, data["agent"], 1, NOW, NOW, event_id=test_id)
        future_id = insert_signal(db, data["agent"], 2, NOW + timedelta(seconds=1), NOW)
        other_id = insert_signal(db, data["other"], 1, NOW, NOW, event_id=test_id)
    client = data["clients"]["admin"]
    rows = client.get(f"{BASE}/signals").json()["items"]
    assert next(s for s in rows if s["agent_id"] == data["agent"] and s["event_id"] == str(test_id))["is_acceptance_test"] is True
    assert next(s for s in rows if s["event_id"] == future_id)["is_acceptance_test"] is False
    assert next(s for s in rows if s["agent_id"] == data["other"] and s["event_id"] == other_id)["is_acceptance_test"] is False
    assert all(s["source"] == "canxe2015_ui" for s in rows)
    client.get(f"{BASE}/agents")
    client.get(f"{BASE}/agents/{data['agent']}/latest")
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ScaleSignal)) == 3
        for model in [Trip, WeighEvent, GoodsTransaction]:
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_empty_scope_unknown_agent_and_no_write_routes(data):
    client = data["clients"]["staff"]
    assert client.get(f"{BASE}/signals").json()["items"] == []
    assert client.get(f"{BASE}/agents/{uuid4()}/latest").status_code == 404
    for path in ["/agents", "/signals", f"/agents/{data['agent']}/latest"]:
        assert client.post(BASE + path, json={}).status_code == 405


def test_chart_series_uses_entire_filter_independent_of_history_page_and_keeps_backfill_time(data):
    with SessionLocal.begin() as db:
        event_ids = [insert_signal(db, data["agent"], i, NOW + timedelta(seconds=i), NOW + timedelta(hours=2)) for i in range(1, 9)]
        insert_signal(db, data["other"], 1, NOW + timedelta(seconds=1), NOW)
    client = data["clients"]["staff"]
    params = {"facility_id": data["a"], "agent_id": data["agent"],
              "observed_from": NOW.isoformat(), "observed_to": (NOW + timedelta(seconds=20)).isoformat()}
    page = client.get(f"{BASE}/signals", params={**params, "page_size": 2}).json()
    chart = client.get(f"{BASE}/signals/chart", params=params).json()
    assert len(page["items"]) == 2 and page["total"] == 8
    assert chart["total"] == chart["returned"] == 8 and not chart["downsampled"]
    assert [row["event_id"] for row in chart["items"]] == event_ids
    assert all(row["gap_before"] is False for row in chart["items"])
    assert chart["items"][0]["received_at_utc"] > chart["items"][0]["observed_at_utc"]
    assert client.get(f"{BASE}/signals/chart", params={**params, "agent_id": data["other"]}).status_code == 404


def test_chart_downsampling_is_bounded_and_preserves_bucket_extrema(data):
    with SessionLocal.begin() as db:
        for sequence in range(1, 402):
            value = Decimal("1000") + Decimal((sequence * 37) % 997)
            insert_signal(db, data["agent"], sequence, NOW + timedelta(seconds=sequence), NOW, weight=value)
    chart = data["clients"]["manager"].get(f"{BASE}/signals/chart", params={
        "facility_id": data["a"], "agent_id": data["agent"], "max_points": 100,
    }).json()
    weights = [Decimal(row["weight_kg"]) for row in chart["items"]]
    assert chart["total"] == 401 and chart["downsampled"] is True
    assert chart["returned"] <= 100
    assert min(weights) == Decimal("1002.000")
    assert max(weights) == Decimal("1988.000")
    assert chart["items"] == sorted(chart["items"], key=lambda row: (row["observed_at_utc"], row["sequence"]))


def test_downsampling_does_not_invent_gaps_in_a_continuous_raw_series(data):
    # Sampled points can be minutes apart even though the source sent every 30s.
    with SessionLocal.begin() as db:
        for sequence in range(1, 402):
            insert_signal(db, data["agent"], sequence, NOW + timedelta(seconds=sequence * 30), NOW,
                          weight=Decimal(1000 + sequence))
    chart = data["clients"]["manager"].get(f"{BASE}/signals/chart", params={
        "facility_id": data["a"], "agent_id": data["agent"], "max_points": 100,
    }).json()
    assert chart["returned"] <= 100 and chart["downsampled"]
    assert len({s["series_key"] for s in chart["items"]}) == 1
    assert not any(s["gap_before"] for s in chart["items"])
    assert any((datetime.fromisoformat(b["observed_at_utc"]) - datetime.fromisoformat(a["observed_at_utc"])).total_seconds() > 60
               for a, b in zip(chart["items"], chart["items"][1:]))


def test_raw_gap_survives_sampling_and_agents_do_not_share_a_line(data):
    with SessionLocal.begin() as db:
        for sequence in range(1, 402):
            extra = 120 if sequence > 200 else 0
            insert_signal(db, data["agent"], sequence, NOW + timedelta(seconds=sequence * 30 + extra), NOW,
                          weight=Decimal(1000 + sequence))
        insert_signal(db, data["other"], 1, NOW + timedelta(seconds=6000), NOW)
    chart = data["clients"]["admin"].get(f"{BASE}/signals/chart", params={"max_points": 100}).json()
    keys = {s["series_key"] for s in chart["items"] if s["agent_id"] == data["agent"]}
    assert chart["returned"] <= 100 and len(keys) == 2
    assert chart["gap_basis"] == "raw_observations"
    own = [s for s in chart["items"] if s["agent_id"] == data["agent"]]
    assert any(a["series_key"] != b["series_key"] for a, b in zip(own, own[1:]))
    others = [s for s in chart["items"] if s["agent_id"] == data["other"]]
    assert others and all(s["series_key"] not in keys for s in others)


def test_overview_has_one_actual_representative_per_segment_without_creating_weighings(data):
    with SessionLocal.begin() as db:
        first_ids = [insert_signal(db, data["agent"], i + 1, NOW + timedelta(seconds=i), NOW + timedelta(hours=4), weight=Decimal(w))
                     for i, w in enumerate([1000, 3000, 3000, 3000, 3000, 8000, 1000])]
        for i, w in enumerate([1100, 7000, 7000, 1200]):
            insert_signal(db, data["agent"], i + 8, NOW + timedelta(seconds=180 + i), NOW + timedelta(hours=4), weight=Decimal(w))
        insert_signal(db, data["other"], 1, NOW, NOW, weight=Decimal("99000"))
    client = data["clients"]["manager"]
    params = {"agent_id": data["agent"], "facility_id": data["a"], "view": "overview"}
    body = client.get(f"{BASE}/signals/chart", params=params).json()
    assert body["chart_view"] == "overview" and body["total"] == 11
    assert body["total_segments"] == body["returned"] == 2 and not body["downsampled"]
    assert [s["weight_kg"] for s in body["items"]] == ["3000.000", "7000.000"]
    assert body["items"][0]["event_id"] == first_ids[3]
    assert body["items"][0]["segment_sample_count"] == 7
    assert datetime.fromisoformat(body["items"][0]["segment_started_at_utc"]) == NOW
    assert datetime.fromisoformat(body["items"][0]["segment_ended_at_utc"]) == NOW + timedelta(seconds=6)
    assert datetime.fromisoformat(body["items"][0]["received_at_utc"]) == NOW + timedelta(hours=4)
    assert client.get(f"{BASE}/signals/chart", params={**params, "agent_id": data["other"]}).status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ScaleSignal).where(ScaleSignal.agent_id == data["agent"])) == 11
        assert db.scalar(select(func.count()).select_from(WeighEvent)) == 0
    assert client.get(f"{BASE}/summary", params={"agent_id": data["agent"]}).json()["observed_weighings"] is None


def test_overview_is_bounded_and_keeps_extreme_representatives(data):
    with SessionLocal.begin() as db:
        for sequence in range(1, 402):
            insert_signal(db, data["agent"], sequence, NOW + timedelta(seconds=sequence * 120), NOW,
                          weight=Decimal(1000 + ((sequence * 37) % 997)))
    body = data["clients"]["staff"].get(f"{BASE}/signals/chart", params={
        "agent_id": data["agent"], "view": "overview", "max_points": 100,
    }).json()
    assert body["total_segments"] == 401 and body["returned"] <= 100 and body["downsampled"]
    assert min(Decimal(s["weight_kg"]) for s in body["items"]) == Decimal("1002")
    assert max(Decimal(s["weight_kg"]) for s in body["items"]) == Decimal("1988")
    assert all(s["segment_sample_count"] == 1 for s in body["items"])


def test_auto_view_switches_by_filter_span_and_empty_overview_has_no_zero_point(data):
    with SessionLocal.begin() as db:
        for i in range(5):
            insert_signal(db, data["agent"], i + 1, NOW + timedelta(seconds=i), NOW, weight=Decimal(1000 + i))
    client = data["clients"]["staff"]
    params = {"agent_id": data["agent"], "view": "auto", "observed_from": NOW.isoformat()}
    short = client.get(f"{BASE}/signals/chart", params={**params, "observed_to": (NOW + timedelta(hours=1)).isoformat()}).json()
    long = client.get(f"{BASE}/signals/chart", params={**params, "observed_to": (NOW + timedelta(hours=24)).isoformat()}).json()
    assert short["chart_view"] == "raw" and short["returned"] == 5
    assert long["chart_view"] == "overview" and long["returned"] == 1
    # All weights tie: choose a real sample nearest the segment midpoint, not a computed weight.
    assert long["items"][0]["sequence"] == "3" and long["items"][0]["weight_kg"] == "1002.000"
    empty = client.get(f"{BASE}/signals/chart", params={"agent_id": data["empty"], "view": "overview"}).json()
    assert empty["items"] == [] and empty["total"] == empty["total_segments"] == 0


def test_summary_counts_by_observed_vietnam_day_and_marks_weighing_kpis_unavailable(data):
    now_local = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    start = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=now_local.tzinfo).astimezone(timezone.utc)
    next_day = start + timedelta(days=1)
    before_boundary = start + timedelta(hours=23, minutes=59, seconds=59)
    after_boundary = next_day
    with SessionLocal.begin() as db:
        insert_signal(db, data["agent"], 1, before_boundary, before_boundary + timedelta(hours=3))
        insert_signal(db, data["agent"], 2, after_boundary, after_boundary)
        insert_signal(db, data["other"], 1, before_boundary, before_boundary)
    params = {"facility_id": data["a"], "agent_id": data["agent"],
              "observed_from": start.isoformat(), "observed_to": (next_day + timedelta(seconds=1)).isoformat()}
    body = data["clients"]["manager"].get(f"{BASE}/summary", params=params).json()
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert body["range_sample_count"] == 2
    assert body["delayed_over_60s_sample_count"] == 1
    assert body["daily_observed_sample_counts"] == [
        {"date": now_local.date().isoformat(), "sample_count": 1},
        {"date": (now_local.date() + timedelta(days=1)).isoformat(), "sample_count": 1},
    ]
    assert body["observed_weighings"] is None and body["confirmed_weighings"] is None
    assert body["needs_review_weighings"] is None and body["weight_totals"] is None
    assert body["weighing_status"] == "not_implemented"


def test_empty_signal_window_does_not_claim_zero_weight_or_a_weighing(data):
    body = data["clients"]["manager"].get(f"{BASE}/summary", params={
        "facility_id": data["a"], "agent_id": data["agent"],
        "observed_from": NOW.isoformat(), "observed_to": (NOW + timedelta(hours=1)).isoformat(),
    }).json()
    assert body["range_sample_count"] == 0
    assert body["observed_weighings"] is None
    assert body["confirmed_weighings"] is None
    assert body["needs_review_weighings"] is None
    assert body["weight_totals"] is None
    assert body["weighing_status"] == "not_implemented"
