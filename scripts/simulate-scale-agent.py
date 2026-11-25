#!/usr/bin/env python3
"""Small durable-outbox simulator for the S01 batch API (test data only)."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "scale-simulator-state.json"


def write_state(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent == DATA_DIR:
        path.parent.chmod(0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def make_batch(agent_id: str, first_sequence: int) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "agent_id": agent_id,
        "events": [
            {"event_id": str(uuid4()), "sequence": first_sequence, "observed_at_utc": now, "weight_kg": "3270", "vendor_text": "S01 simulator test reading A", "source": "canxe2015_ui"},
            {"event_id": str(uuid4()), "sequence": first_sequence + 1, "observed_at_utc": now, "weight_kg": "3269.5", "vendor_text": "S01 simulator test reading B", "source": "canxe2015_ui"},
        ],
    }


def request_batch(url: str, token: str, batch: dict) -> tuple[int, dict | None]:
    encoded = json.dumps(batch, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/api/scale-ingestion/batches",
        data=encoded,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        # Do not print response headers or request details; the bearer token stays private.
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = None
        return exc.code, detail
    except (urllib.error.URLError, TimeoutError):
        return 0, None


def valid_ack(response: dict | None, agent_id: str, batch: dict) -> bool:
    if not isinstance(response, dict):
        return False
    wanted = [event["event_id"] for event in batch["events"]]
    got = response.get("acknowledged_event_ids")
    return (
        response.get("schema_version") == 1
        and response.get("agent_id") == agent_id
        and response.get("persisted") is True
        and isinstance(got, list)
        and len(got) == len(wanted)
        and set(got) == set(wanted)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mô phỏng batch S01 bằng dữ liệu test, không in token.")
    parser.add_argument("--mode", choices=("valid", "resend", "drop-ack"), default="valid")
    parser.add_argument("--state-file", type=Path, default=STATE_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args()
    agent_id = os.environ.get("SCALE_AGENT_ID", "")
    token = os.environ.get("SCALE_AGENT_TOKEN", "")
    token_file = os.environ.get("SCALE_AGENT_TOKEN_FILE", "")
    if not token and token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    base_url = os.environ.get("SCALE_API_URL", "http://localhost:8001")
    if not agent_id or not token:
        print("Set SCALE_AGENT_ID and SCALE_AGENT_TOKEN_FILE (or SCALE_AGENT_TOKEN) in the environment.", file=sys.stderr)
        return 2

    try:
        state = json.loads(args.state_file.read_text(encoding="utf-8")) if args.state_file.exists() else {"agent_id": agent_id, "next_sequence": 1, "checkpoint": 0, "pending": None, "last_batch": None}
    except (OSError, json.JSONDecodeError):
        print("Simulator state file is unreadable; preserve it and inspect locally.", file=sys.stderr)
        return 2
    if state.get("agent_id") != agent_id:
        print("Simulator state belongs to another agent; use a separate local state file.", file=sys.stderr)
        return 2

    if args.mode == "resend":
        batch = state.get("pending") or state.get("last_batch")
        if not batch:
            print("Chưa có batch để gửi lại; chạy --mode valid trước.", file=sys.stderr)
            return 2
    else:
        batch = state.get("pending")
        if not batch:
            batch = make_batch(agent_id, int(state.get("next_sequence", 1)))
            state["pending"] = batch
            state["next_sequence"] = batch["events"][-1]["sequence"] + 1
            write_state(args.state_file, state)  # Persist the outbox before network I/O.

    status, response = request_batch(base_url, token, batch)
    if status == 0:
        print("Không kết nối được API; batch vẫn nằm trong outbox local.", file=sys.stderr)
        return 1
    if status != 200:
        detail = response.get("detail") if isinstance(response, dict) else None
        if isinstance(detail, dict):
            message = str(detail.get("message", detail.get("code", "request rejected")))[:240]
        elif isinstance(detail, str):
            message = detail[:240]
        else:
            message = "request rejected"
        print(f"API trả HTTP {status}: {message}; outbox được giữ nguyên.", file=sys.stderr)
        return 1
    if args.mode == "drop-ack":
        print(f"Đã gửi HTTP 200 nhưng mô phỏng bỏ qua ACK; giữ {len(batch['events'])} event trong outbox.")
        return 0
    if not valid_ack(response, agent_id, batch):
        print("Response không đạt điều kiện ACK; outbox được giữ nguyên.", file=sys.stderr)
        return 1

    state["checkpoint"] = max(int(state.get("checkpoint", 0)), max(event["sequence"] for event in batch["events"]))
    state["last_batch"] = batch
    state["pending"] = None
    write_state(args.state_file, state)
    print(f"ACK hợp lệ cho {len(batch['events'])} event; inserted={response['inserted_count']}, duplicate={response['duplicate_count']}, checkpoint={state['checkpoint']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
