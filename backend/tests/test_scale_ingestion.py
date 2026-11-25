from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url

from app.core.database import SessionLocal, get_db
from app.core.models import utcnow
from app.main import app
from app.modules.facilities.models import Facility
from app.modules.goods.models import GoodsTransaction
from app.modules.scale_ingestion.models import ScaleAgent, ScaleSignal
from app.modules.scale_ingestion.schemas import ScaleSignalIn
from app.modules.trips.models import Trip
from app.modules.weighings.models import WeighEvent


@pytest.fixture(autouse=True)
def clean_database():
    with SessionLocal.begin() as db:
        db.execute(text("TRUNCATE scale_signals, scale_agents, facilities RESTART IDENTITY CASCADE"))
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def agent_data():
    token = "s01-test-token-" + uuid4().hex
    agent_id = str(uuid4())
    with SessionLocal.begin() as db:
        facility = Facility(code="S01-A", name="Scale test facility", is_active=True)
        db.add(facility); db.flush()
        agent = ScaleAgent(agent_id=agent_id, display_name="Test scale", facility_id=facility.id, scale_code="SCALE-1", is_active=True, token_hash=hashlib.sha256(token.encode()).hexdigest())
        db.add(agent)
    return {"agent_id": agent_id, "token": token}


def event(sequence=1, *, event_id=None, observed_at=None, weight="3270", vendor="3270 kg"):
    return {
        "event_id": str(event_id or uuid4()),
        "sequence": sequence,
        "observed_at_utc": (observed_at or utcnow()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "weight_kg": weight,
        "vendor_text": vendor,
        "source": "canxe2015_ui",
    }


def body(data, events):
    return {"schema_version": 1, "agent_id": data["agent_id"], "events": events}


def send(client, data, events, *, agent_id=None, token=None):
    payload = body(data, events)
    if agent_id is not None:
        payload["agent_id"] = agent_id
    headers = {"Authorization": f"Bearer {token if token is not None else data['token']}"}
    return client.post("/api/scale-ingestion/batches", json=payload, headers=headers)


def signal_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(ScaleSignal))


def test_auth_is_bearer_only_agent_bound_and_secret_is_not_logged(agent_data, caplog):
    caplog.set_level(logging.INFO)
    data = agent_data; client = TestClient(app)
    payload = body(data, [event()])
    assert client.post("/api/scale-ingestion/batches", json=payload).status_code == 401
    client.cookies.set("nt_session", "not-an-agent-token")
    assert client.post("/api/scale-ingestion/batches", json=payload).status_code == 401
    assert send(client, data, [event()], token="wrong-token").status_code == 401
    assert send(client, data, [event()], agent_id=str(uuid4())).status_code == 403
    assert data["token"] not in caplog.text
    assert data["token"] not in client.post("/api/scale-ingestion/batches", json=payload, headers={"Authorization": f"Bearer {data['token']}"}).text


def test_inactive_agent_or_facility_rejected_and_token_rotation_invalidates_old(agent_data, tmp_path, capsys):
    from app.modules.scale_ingestion import cli

    data = agent_data; client = TestClient(app)
    with SessionLocal() as db:
        facility_id = db.scalar(select(ScaleAgent.facility_id).where(ScaleAgent.agent_id == data["agent_id"]))
    token_dir = tmp_path / "tokens"
    assert cli.main(["--token-dir", str(token_dir), "create", "--facility-code", "MISSING", "--scale-code", "X", "--display-name", "Missing"]) == 2
    capsys.readouterr()
    with SessionLocal.begin() as db:
        db.get(Facility, facility_id).is_active = False
    assert send(client, data, [event()]).status_code == 403
    with SessionLocal.begin() as db:
        db.get(Facility, facility_id).is_active = True
        db.add(Facility(code="S01-C", name="CLI test facility", is_active=True))
    assert cli.main(["--token-dir", str(token_dir), "create", "--facility-code", "S01-C", "--scale-code", "SCALE-CLI", "--display-name", "CLI agent"]) == 0
    create_output = capsys.readouterr().out
    created_id = create_output.split("agent ", 1)[1].split(";", 1)[0]
    created_path = token_dir / f"{created_id}.token"
    created_token = created_path.read_text().strip()
    assert created_path.stat().st_mode & 0o777 == 0o600
    assert created_token not in create_output
    assert send(client, {"agent_id": created_id, "token": created_token}, [event()]).status_code == 200
    assert cli.main(["--token-dir", str(token_dir), "rotate-token", data["agent_id"]]) == 0
    output = capsys.readouterr().out
    path = Path(output.rsplit("File local: ", 1)[1].split(" ", 1)[0])
    new_token = path.read_text().strip()
    assert path.stat().st_mode & 0o777 == 0o600
    assert send(client, data, [event()], token=data["token"]).status_code == 401
    assert send(client, data, [event()], token=new_token).status_code == 200
    assert cli.main(["--token-dir", str(token_dir), "disable", data["agent_id"]]) == 0
    capsys.readouterr()
    assert send(client, data, [event(sequence=2)], token=new_token).status_code == 403


def test_standalone_admin_cli_creates_agent_without_printing_token(agent_data, tmp_path):
    backend = Path(__file__).resolve().parents[1]
    token_dir = tmp_path / "agent-tokens"
    result = subprocess.run(
        [sys.executable, "-m", "app.modules.scale_ingestion.cli", "--token-dir", str(token_dir), "create", "--facility-code", "S01-A", "--scale-code", "STANDALONE", "--display-name", "CLI subprocess test"],
        cwd=backend,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert agent_data["token"] not in result.stdout and len(result.stdout) < 300
    agent_id = result.stdout.split("agent ", 1)[1].split(";", 1)[0]
    token_file = token_dir / f"{agent_id}.token"
    assert token_file.stat().st_mode & 0o777 == 0o600
    token = token_file.read_text().strip()
    response = send(TestClient(app), {"agent_id": agent_id, "token": token}, [event()])
    assert response.status_code == 200


def test_cli_maps_compose_db_host_to_local_published_port(tmp_path, monkeypatch):
    from app.modules.scale_ingestion import cli

    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SCALE_ADMIN_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql+psycopg://local:fake@db:5432/nhutung\nPOSTGRES_PORT=5544\n")
    parsed = make_url(cli._database_url_for_cli())
    assert (parsed.host, parsed.port, parsed.database) == ("127.0.0.1", 5544, "nhutung")


def test_valid_batch_persists_and_acknowledges_duplicates_and_mixed_batch(agent_data):
    data = agent_data; client = TestClient(app)
    first, second = event(10, weight="3270"), event(12, weight="1600.500")
    response = send(client, data, [first, second])
    assert response.status_code == 200
    result = response.json()
    assert result["persisted"] is True and result["inserted_count"] == 2 and result["duplicate_count"] == 0
    assert result["acknowledged_event_ids"] == [first["event_id"], second["event_id"]]
    assert result["agent_id"] == data["agent_id"] and result["schema_version"] == 1
    retry = {**first, "weight_kg": "3270.000"}
    third = event(15, weight="1000")
    mixed = send(client, data, [retry, third])
    assert mixed.status_code == 200
    assert mixed.json()["inserted_count"] == 1 and mixed.json()["duplicate_count"] == 1
    assert mixed.json()["acknowledged_event_ids"] == [first["event_id"], third["event_id"]]
    assert signal_count() == 3
    with SessionLocal() as db:
        stored = db.scalar(select(ScaleSignal).where(ScaleSignal.event_id == __import__("uuid").UUID(second["event_id"])))
        assert stored.weight_kg == Decimal("1600.500")
        assert stored.observed_at_utc == datetime.fromisoformat(second["observed_at_utc"].replace("Z", "+00:00"))
        assert stored.received_at_utc is not None


@pytest.mark.parametrize("suffix", ["Z", "+00:00"])
@pytest.mark.parametrize("fraction,microseconds", [
    ("1234561", 123456),
    ("1234569", 123456),
    ("9999999", 999999),
])
def test_seven_digit_timestamp_truncates_before_postgresql_storage(agent_data, fraction, microseconds, suffix):
    original = {**event(), "observed_at_utc": f"2026-01-01T12:34:56.{fraction}{suffix}"}
    expected = datetime(2026, 1, 1, 12, 34, 56, microseconds, tzinfo=timezone.utc)
    assert ScaleSignalIn.model_validate(original).observed_at_utc == expected
    response = send(TestClient(app), agent_data, [original])
    assert response.status_code == 200 and response.json()["inserted_count"] == 1
    with SessionLocal() as db:
        stored = db.scalar(select(ScaleSignal).where(ScaleSignal.event_id == UUID(original["event_id"])))
        assert stored.observed_at_utc == expected  # .9999999 must not carry into second 57.


def test_seven_and_six_digit_timestamp_retries_acknowledge_exact_normalized_duplicate(agent_data):
    client = TestClient(app)
    original = {**event(), "observed_at_utc": "2026-01-01T12:34:56.1234561+00:00"}
    initial = send(client, agent_data, [original])
    assert initial.status_code == 200 and initial.json()["inserted_count"] == 1
    with SessionLocal() as db:
        stored = db.scalar(select(ScaleSignal).where(ScaleSignal.event_id == UUID(original["event_id"])))
        received_at = stored.received_at_utc
    for timestamp in [
        original["observed_at_utc"],
        "2026-01-01T12:34:56.1234569Z",
        "2026-01-01T12:34:56.123456Z",
        "2026-01-01T12:34:56.123456+00:00",
    ]:
        response = send(client, agent_data, [{**original, "observed_at_utc": timestamp}])
        assert response.status_code == 200
        ack = response.json()
        assert ack["persisted"] is True
        assert (ack["inserted_count"], ack["duplicate_count"]) == (0, 1)
        assert ack["acknowledged_event_ids"] == [original["event_id"]]
    with SessionLocal() as db:
        stored = db.scalar(select(ScaleSignal).where(ScaleSignal.event_id == UUID(original["event_id"])))
        assert stored.observed_at_utc == datetime(2026, 1, 1, 12, 34, 56, 123456, tzinfo=timezone.utc)
        assert stored.received_at_utc == received_at
    assert signal_count() == 1


@pytest.mark.parametrize("timestamp", [
    "2026-01-01T12:34:56.1234559Z",
    "2026-01-01T12:34:56.123457+00:00",
])
def test_timestamp_one_microsecond_difference_conflicts_atomically(agent_data, timestamp):
    client = TestClient(app)
    original = {**event(), "observed_at_utc": "2026-01-01T12:34:56.1234569+00:00"}
    assert send(client, agent_data, [original]).status_code == 200
    response = send(client, agent_data, [event(2), {**original, "observed_at_utc": timestamp}])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "event_conflict"
    assert "persisted" not in response.json()
    assert signal_count() == 1  # New event earlier in the batch must roll back.
    with SessionLocal() as db:
        stored = db.scalar(select(ScaleSignal).where(ScaleSignal.event_id == UUID(original["event_id"])))
        assert stored.observed_at_utc == datetime(2026, 1, 1, 12, 34, 56, 123456, tzinfo=timezone.utc)


def test_future_limit_uses_normalized_timestamp_and_rejects_one_microsecond_over_atomically(agent_data, monkeypatch):
    from app.modules.scale_ingestion import router as ingestion

    now = datetime(2026, 1, 1, 12, 34, 56, 123456, tzinfo=timezone.utc)
    monkeypatch.setattr(ingestion, "utcnow", lambda: now)
    limit = now + timedelta(seconds=ingestion.get_settings().scale_ingestion_max_future_seconds)
    at_limit = {**event(1), "observed_at_utc": limit.isoformat(timespec="microseconds").replace("+00:00", "9+00:00")}
    client = TestClient(app)
    assert send(client, agent_data, [at_limit]).status_code == 200
    over_limit = {**event(3), "observed_at_utc": (limit + timedelta(microseconds=1)).isoformat()}
    response = send(client, agent_data, [event(2, observed_at=now), over_limit])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "timestamp_too_far_in_future"
    assert signal_count() == 1


def test_commit_failure_rolls_back_seven_digit_event_without_ack(agent_data, monkeypatch):
    original = {**event(), "observed_at_utc": "2026-01-01T12:34:56.1234569Z"}

    def fail_commit(session):
        raise OperationalError("commit", {}, RuntimeError("test commit failure"))

    with monkeypatch.context() as patch:
        patch.setattr(SessionLocal.class_, "commit", fail_commit)
        response = send(TestClient(app), agent_data, [original])
    assert response.status_code == 503
    assert "persisted" not in response.json() and "acknowledged_event_ids" not in response.json()
    assert signal_count() == 0
    retried = send(TestClient(app), agent_data, [original])
    assert retried.status_code == 200
    assert retried.json()["persisted"] is True and retried.json()["inserted_count"] == 1
    assert signal_count() == 1


@pytest.mark.parametrize("change", [
    {"weight_kg": "3271"},
    {"vendor_text": "changed source text"},
    {"observed_at_utc": (utcnow() - timedelta(seconds=3)).isoformat()},
])
def test_same_event_id_different_content_conflicts_without_partial_write(agent_data, change):
    data = agent_data; client = TestClient(app)
    original = event(1, observed_at=utcnow() - timedelta(days=3))
    assert send(client, data, [original]).status_code == 200
    extra = event(2)
    changed = {**original, **change}
    response = send(client, data, [extra, changed])
    assert response.status_code == 409 and response.json()["detail"]["code"] == "event_conflict"
    assert signal_count() == 1


def test_same_sequence_different_event_id_conflicts(agent_data):
    data = agent_data; client = TestClient(app)
    assert send(client, data, [event(7)]).status_code == 200
    assert send(client, data, [event(7)]).status_code == 409
    assert signal_count() == 1


@pytest.mark.parametrize("bad", [
    {"weight_kg": "999.9"}, {"weight_kg": "NaN"}, {"weight_kg": "Infinity"},
    {"weight_kg": "3,270"}, {"weight_kg": "3270.1234"}, {"weight_kg": 3270},
    {"source": "scale_device"}, {"stable": True}, {"device_timestamp": "2026-01-01T00:00:00Z"},
    {"plate": "51A-12345"}, {"observed_at_utc": 1_797_000_000}, {"observed_at_utc": "2026-01-01T00:00:00+07:00"},
])
def test_invalid_contract_fields_rejected_atomically(agent_data, bad):
    data = agent_data; client = TestClient(app)
    valid, invalid = event(1), {**event(2), **bad}
    response = send(client, data, [valid, invalid])
    assert response.status_code == 422
    assert signal_count() == 0


def test_batch_limits_duplicate_ids_and_future_skew(agent_data):
    data = agent_data; client = TestClient(app)
    assert send(client, data, [event(1), event(2)] * 26).status_code == 422
    repeated = event(1)
    assert send(client, data, [repeated, repeated]).status_code == 422
    far_future = event(1, observed_at=utcnow() + timedelta(minutes=6))
    response = send(client, data, [far_future])
    assert response.status_code == 422 and response.json()["detail"]["code"] == "timestamp_too_far_in_future"
    assert signal_count() == 0


def test_body_size_limit_returns_413_before_parsing(agent_data):
    data = agent_data; client = TestClient(app)
    response = client.post(
        "/api/scale-ingestion/batches",
        content=json.dumps({**body(data, [event()]), "extra": "x" * 70_000}),
        headers={"Authorization": f"Bearer {data['token']}", "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"
    assert signal_count() == 0


def test_out_of_order_backfill_preserves_observed_time_and_d02_remains_untouched(agent_data):
    data = agent_data; client = TestClient(app)
    newer = event(20, observed_at=utcnow() - timedelta(hours=1))
    older = event(19, observed_at=utcnow() - timedelta(days=60))
    assert send(client, data, [newer]).status_code == 200
    assert send(client, data, [older]).status_code == 200
    with SessionLocal() as db:
        observed = list(db.scalars(select(ScaleSignal.observed_at_utc).order_by(ScaleSignal.sequence)))
        assert observed[0] < observed[1]
        assert db.scalar(select(func.count()).select_from(Trip)) == 0
        assert db.scalar(select(func.count()).select_from(WeighEvent)) == 0
        assert db.scalar(select(func.count()).select_from(GoodsTransaction)) == 0


def test_concurrent_identical_requests_and_lost_ack_retry_are_idempotent(agent_data):
    data = agent_data; batch = [event(1)]; barrier = Barrier(2)
    def post_once():
        with TestClient(app) as client:
            barrier.wait(timeout=5)
            return send(client, data, batch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: post_once(), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    bodies = [response.json() for response in responses]
    assert sorted(result["inserted_count"] for result in bodies) == [0, 1]
    assert sorted(result["duplicate_count"] for result in bodies) == [0, 1]
    assert signal_count() == 1
    # Simulate server commit followed by a client that discarded the response.
    resent = send(TestClient(app), data, batch)
    assert resent.status_code == 200 and resent.json()["duplicate_count"] == 1
    assert resent.json()["persisted"] is True and signal_count() == 1


def test_database_error_returns_503_without_ack(agent_data):
    def failed_db():
        raise OperationalError("connection", {}, RuntimeError("private connection details"))
        yield
    app.dependency_overrides[get_db] = failed_db
    response = send(TestClient(app), agent_data, [event(1)])
    assert response.status_code == 503
    assert "persisted" not in response.text and "private connection details" not in response.text


def test_no_raw_token_or_database_credentials_in_api_or_logs(agent_data, caplog):
    caplog.set_level(logging.INFO)
    response = send(TestClient(app), agent_data, [event(1)])
    assert response.status_code == 200
    with SessionLocal() as db:
        stored = db.scalar(select(ScaleAgent).where(ScaleAgent.agent_id == agent_data["agent_id"]))
        assert stored.token_hash == hashlib.sha256(agent_data["token"].encode()).hexdigest()
        assert agent_data["token"] not in stored.token_hash
    assert agent_data["token"] not in response.text and agent_data["token"] not in caplog.text
    assert "postgresql+psycopg" not in response.text and "postgresql+psycopg" not in caplog.text
