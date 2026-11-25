"""Mac camera worker: shared D05 pipeline, durable local outbox, existing pilot tables.

No camera loops run inside API processes. All exception output is fixed safe codes.
"""
import argparse
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import make_engine
from app.core.models import utcnow
from app.modules.accounts import models as _accounts
from app.modules.facilities.models import Facility
from app.modules.scale_ingestion.cli import _database_url_for_cli
from app.modules.vehicle_pilot.models import CameraDiagnostic, CameraEvidence, CameraRuntime, CameraVisit, VehicleAIJob, VehiclePilotAuditEvent, VehiclePrediction
from app.modules.vehicle_pilot.storage import EvidenceStorage

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "edge-agent"))


def atomic_json(path, data):
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(data, stream, default=str)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


class Outbox:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, key, payload, state=None):
        value = json.dumps(payload, sort_keys=True)
        with self.connect() as db:
            previous = db.execute("SELECT payload FROM outbox WHERE id=?", (key,)).fetchone()
            if previous and previous[0] != value:
                raise ValueError("OUTBOX_ID_CONFLICT")
            db.execute("INSERT OR IGNORE INTO outbox VALUES (?,?)", (key, value))
            if state is not None:
                db.execute("INSERT OR REPLACE INTO state VALUES ('live-state',?)", (json.dumps(state),))

    def get(self, key):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM outbox WHERE id=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def head(self):
        with self.connect() as db:
            row = db.execute("SELECT id,payload FROM outbox ORDER BY rowid LIMIT 1").fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def ack(self, key):
        with self.connect() as db:
            db.execute("DELETE FROM outbox WHERE id=?", (key,))

    def state(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))
            row = db.execute("SELECT payload FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def count(self):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM outbox").fetchone()[0]


def ingest(factory, storage, event):
    """Idempotent local worker ingress. Outbox ACK occurs only after this commit."""
    visit_id = UUID(event["visit_id"])
    now = utcnow()
    with factory.begin() as db:
        visit = db.scalar(select(CameraVisit).where(CameraVisit.id == visit_id).with_for_update())
        if visit is None:
            fingerprint = hashlib.sha256(json.dumps(event["identity"], sort_keys=True).encode()).hexdigest()
            visit = CameraVisit(id=visit_id, facility_id=event["facility_id"], camera_id=event["camera_id"],
                source_mode="live", source_ref="camera-main-live", observed_at_utc=datetime.fromisoformat(event["observed_at_utc"]),
                status="open", create_fingerprint=fingerprint, metadata_json=event["identity"], version=1)
            db.add(visit); db.flush()
        elif (visit.metadata_json.get("worker_visit_identity") != event["identity"]["worker_visit_identity"]
              or visit.facility_id != event["facility_id"] or visit.camera_id != event["camera_id"]
              or visit.observed_at_utc != datetime.fromisoformat(event["observed_at_utc"])):
            raise ValueError("LIVE_VISIT_ID_CONFLICT")
        audit_id = UUID(event["event_id"])
        payload_hash = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
        previous = db.get(VehiclePilotAuditEvent, audit_id)
        if previous:
            if previous.details.get("payload_sha256") != payload_hash:
                raise ValueError("LIVE_EVENT_ID_CONFLICT")
            return
        if event["stage"] == "finished":
            if visit.status in {"open", "interrupted"}:
                visit.status = "needs_review"  # Departure is an observation; never a D02 confirmation.
                visit.version += 1
            visit.updated_at = now
            visit.metadata_json = {**visit.metadata_json, "end_observed_at_utc": event["ended_at_utc"],
                "end_reason": event["end_reason"], "track_ids": event["track_ids"],
                "multiple_vehicle_review": event["multiple_vehicle_review"], "raw_ocr": event["reads"],
                "capture_selection": event.get('capture_selection'),
                "plate_observations": event.get("plate_observations", [])}
        if event["stage"] == "interrupted" and visit.status == "open":
            visit.status = "interrupted"; visit.version += 1; visit.updated_at = now
        if event["stage"] in {"evidence", "resumed"} and visit.status == "interrupted":
            visit.status = "open"; visit.version += 1; visit.updated_at = now
        for item in event.get("evidence", []):
            evidence_id = UUID(item["id"])
            body = Path(item["path"]).read_bytes()
            sha = storage.validate(body, "image/jpeg")
            if sha != item["sha256"]:
                raise ValueError("OUTBOX_FILE_HASH_MISMATCH")
            existing = db.get(CameraEvidence, evidence_id)
            if existing and existing.sha256 != sha:
                raise ValueError("LIVE_EVIDENCE_ID_CONFLICT")
            total = db.scalar(select(func.coalesce(func.sum(CameraEvidence.size_bytes), 0)).where(
                CameraEvidence.facility_id == event["facility_id"], CameraEvidence.storage_state.in_(["stored", "pending"])))
            if not existing and total + len(body) > get_settings().pilot_evidence_quota_per_facility_bytes:
                raise ValueError("EVIDENCE_QUOTA_EXCEEDED")
            key = "live/" + storage.object_key(event["facility_id"], visit_id, evidence_id, "image/jpeg")
            storage.write(key, body, sha)
            if not existing:
                db.add(CameraEvidence(id=evidence_id, visit_id=visit_id, facility_id=event["facility_id"],
                    kind=item["kind"], source_mode="live", observed_at_utc=datetime.fromisoformat(item["observed_at_utc"]),
                    retention_until_utc=now + timedelta(days=get_settings().pilot_evidence_retention_days),
                    content_type="image/jpeg", size_bytes=len(body), sha256=sha, object_key=key, storage_state="stored",
                    bbox_json=item.get("bbox"), transform_json=item.get("transform"), metadata_json=item.get("metadata", {})))
            else:
                existing.storage_state = "stored"
        for index, read in enumerate(event.get("reads", [])):
            prediction_id = uuid5(visit_id, f"local-read-{index}")
            if not db.get(VehiclePrediction, prediction_id):
                db.add(VehiclePrediction(id=prediction_id, visit_id=visit_id, source="local", identifier_kind="unknown",
                    raw_text=read["raw"], normalized_text=read["normalized"], visible_text=read["raw"],
                    reading_status="unknown", model_version=read["model"], score_info={"score": read["score"], "calibrated": False}, raw_result=read))
        db.add(VehiclePilotAuditEvent(id=audit_id, visit_id=visit_id, facility_id=event["facility_id"],
            event="live_visit_" + event["stage"], details={"source_mode": "live", "end_reason": event.get("end_reason"), "payload_sha256": payload_hash}))


class Worker:
    def __init__(self, config_path):
        os.umask(0o077)
        from offline_vision.config import load_config
        from offline_vision.live_source import LiveSource
        self.config = json.loads(config_path.read_text())
        if self.config.get("keychain_helper"):
            self.config["keychain_helper"] = str((ROOT / self.config["keychain_helper"]).resolve())
        self.cfg = load_config(ROOT / self.config["camera_config"])
        self.camera_id = self.cfg.camera_id
        self.folder = (ROOT / self.config["state_dir"]).resolve()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700); self.folder.chmod(0o700)
        self.lockfile = open(self.folder / "worker.lock", "a+")
        try:
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("CAMERA_WORKER_ALREADY_RUNNING") from None
        self.lockfile.seek(0); self.lockfile.truncate(); self.lockfile.write(str(os.getpid())); self.lockfile.flush()
        self.outbox = Outbox(self.folder / "outbox.sqlite3")
        self.output = self.folder / "work"
        (self.output / "evidence").mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.output / "candidates").mkdir(exist_ok=True, mode=0o700)
        self.live_root = (ROOT / self.config["live_storage_dir"]).resolve()
        self.live_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.live_root.name != "live":
            raise ValueError("LIVE_STORAGE_DIRECTORY_MUST_END_IN_LIVE")
        self.storage = EvidenceStorage(self.live_root.parent)
        self.engine = make_engine(_database_url_for_cli())
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        with self.factory() as db:
            facility = db.scalar(select(Facility).where(Facility.code == self.config["facility_code"], Facility.is_active.is_(True)))
            if not facility:
                raise ValueError("CAMERA_FACILITY_NOT_FOUND")
            self.facility_id = facility.id
        self.owner = f"mac-camera:{os.getpid()}:{uuid4().hex[:8]}"
        from offline_vision.event_gate import EventGate
        from app.modules.scale_ingestion.models import ScaleAgent
        if self.config.get('mode', 'continuous') not in {'event_driven', 'continuous'}:
            raise ValueError('CAMERA_MODE_INVALID')
        with self.factory() as db:
            agent = db.get(ScaleAgent, self.config['scale_agent_id'])
            if not agent or agent.facility_id != self.facility_id or not agent.is_active:
                raise ValueError('CAMERA_SCALE_AGENT_MAPPING_INVALID')
        self.gate = EventGate(self.config['event_policy'], self.outbox.state('event-gate'))
        self.photo_ids = set()
        self.source = LiveSource(self.config)
        self.stop = threading.Event()
        self.health = {"last_frame_processed_at": None, "last_evidence_saved_at": None, "processed_frames": 0,
            "latency_ms": None, "processing_state": "starting", "processing_error_code": None,
            "preview_key": f"live/diagnostics/{self.camera_id}/preview.jpg", "outbox_error_code": None,
            "roi_status": self.cfg.roi_status, "observed_clock": "Mac_receive_UTC_not_camera_OSD",
            "capture_policy": self.config['event_policy']}
        with self.factory() as db:
            latest_evidence = db.scalar(select(CameraEvidence.observed_at_utc).join(CameraVisit,
                CameraVisit.id == CameraEvidence.visit_id).where(CameraVisit.camera_id == self.camera_id,
                CameraEvidence.storage_state == "stored").order_by(CameraEvidence.received_at_utc.desc()).limit(1))
            if latest_evidence:
                self.health["last_evidence_saved_at"] = latest_evidence.isoformat()
        self.diag_queue = queue.Queue(maxsize=1)
        self.clip = None
        self.maintenance = threading.Thread(target=self._maintain, name="camera-persistence", daemon=True)
        self.started = time.monotonic()
        self.previous_metrics = (self.started, 0, 0)
        self.last_snapshot = self.outbox.state("last_snapshot") or 0
        self.report_path = self.folder / "health.json"
        self.active_state = self.folder / "sessions.json"

    def _snapshot(self):
        import psutil
        source = self.source.snapshot()
        now = time.monotonic()
        old_time, old_received, old_processed = self.previous_metrics
        delta = max(.001, now - old_time)
        data = {**source, **self.health, "receive_fps": round((source["received_packets"] - old_received) / delta, 2),
            "process_fps": round((self.health["processed_frames"] - old_processed) / delta, 2),
            "receive_fps_measure": "video_packets_per_wall_second", "outbox_depth": self.outbox.count(),
            "rss_bytes": psutil.Process().memory_info().rss, "cpu_seconds": sum(psutil.Process().cpu_times()[:2]),
            "uptime_seconds": round(now - self.started, 1), "ai_mode": get_settings().pilot_ai_mode,
            "model_hashes": self.config["model_hashes"], "worker_owner": self.owner}
        self.previous_metrics = (now, source["received_packets"], self.health["processed_frames"])
        return data

    def _maintain(self):
        next_health = 0; previous_stage = None
        while not self.stop.is_set():
            try:
                event = self.outbox.head()
                if event:
                    try:
                        if event[1].get("type") == "diagnostic":
                            payload = event[1]
                            self._persist_diagnostic(payload["id"], payload["kind"], Path(payload["path"]), payload["metadata"])
                        else:
                            ingest(self.factory, self.storage, event[1])
                        self.outbox.ack(event[0])
                        if event[1].get("evidence"):
                            self.health["last_evidence_saved_at"] = utcnow().isoformat()
                        if event[1].get("stage") == "finished":
                            shutil.rmtree(self.output / "evidence" / event[1]["visit_id"], ignore_errors=True)
                        self.health["outbox_error_code"] = None
                    except Exception as error:
                        allowed = {"LIVE_EVENT_ID_CONFLICT", "LIVE_VISIT_ID_CONFLICT", "LIVE_EVIDENCE_ID_CONFLICT", "OUTBOX_FILE_HASH_MISMATCH", "EVIDENCE_QUOTA_EXCEEDED"}
                        self.health["outbox_error_code"] = str(error) if isinstance(error, ValueError) and str(error) in allowed else "PERSISTENCE_UNAVAILABLE_OR_QUOTA"
                stage = (self.source.snapshot()["source_state"], self.health["processing_state"], self.health.get("preview_enabled"), self.health.get("capture_active"))
                if time.monotonic() >= next_health or stage != previous_stage:
                    previous_stage = stage
                    data = self._snapshot()
                    with self.factory.begin() as db:
                        row = db.get(CameraRuntime, self.camera_id)
                        if row and row.facility_id != self.facility_id:
                            raise ValueError("CAMERA_FACILITY_CONFLICT")
                        if row is None:
                            row = CameraRuntime(camera_id=self.camera_id, facility_id=self.facility_id, owner=self.owner,
                                updated_at=utcnow(), snapshot=data); db.add(row)
                        else:
                            row.owner = self.owner; row.updated_at = utcnow(); row.snapshot = data
                        job = db.scalar(select(VehicleAIJob).join(CameraVisit, VehicleAIJob.visit_id == CameraVisit.id).where(
                            CameraVisit.camera_id == self.camera_id).order_by(VehicleAIJob.created_at.desc()).limit(1))
                        self.health["ai_job_state"] = job.status if job else "none"
                    atomic_json(self.report_path, {**data, "reported_at_utc": utcnow().isoformat()})
                    print(json.dumps({"event": "camera_health", "camera_id": self.camera_id,
                        **{k: data[k] for k in ("source_state", "processed_frames", "decoded_frames", "queue_depth", "outbox_depth", "reconnect_count", "receive_fps", "process_fps", "rss_bytes")}}), flush=True)
                    next_health = time.monotonic() + self.config["health_seconds"]
                    self._cleanup_diagnostics()
                with self.factory.begin() as db:
                    for photo in db.scalars(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == self.camera_id,
                            CameraDiagnostic.kind == 'photo', CameraDiagnostic.status == 'saving')):
                        path = self.live_root / 'diagnostics' / self.camera_id / f'{photo.id}.jpg'
                        if path.exists() and self.outbox.get('diagnostic:' + str(photo.id)) is None:
                            self._diagnostic_saved(str(photo.id), 'snapshot', path, photo.metadata_json)
                        elif not path.exists() and photo.created_at < utcnow() - timedelta(seconds=30):
                            photo.status = 'interrupted'; photo.metadata_json = {**photo.metadata_json, 'error_code': 'PHOTO_FILE_MISSING_AFTER_RESTART'}
                    # Unfinished clips after crash become explicitly interrupted, never success.
                    db.query(CameraDiagnostic).filter(CameraDiagnostic.camera_id == self.camera_id,
                        CameraDiagnostic.kind == "clip", CameraDiagnostic.status.in_(["queued", "capturing"]), CameraDiagnostic.created_at < utcnow() - timedelta(seconds=60)).update(
                        {CameraDiagnostic.status: "interrupted"}, synchronize_session=False)
                    if self.diag_queue.empty():
                        item = db.scalar(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == self.camera_id,
                            CameraDiagnostic.kind == "clip", CameraDiagnostic.status == "queued").with_for_update(skip_locked=True).limit(1))
                        if item:
                            item.status = "capturing"
                            self.diag_queue.put_nowait(str(item.id))
            except Exception:
                self.health["outbox_error_code"] = "PERSISTENCE_UNAVAILABLE_OR_QUOTA"
                # No exception text / connection strings. Outbox remains intact on rollback.
                atomic_json(self.report_path, {**self._snapshot(), "reported_at_utc": utcnow().isoformat()})
            self.stop.wait(1)

    def _cleanup_diagnostics(self):
        folder = self.live_root / "diagnostics" / self.camera_id
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.factory.begin() as db:
            expired = list(db.scalars(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == self.camera_id,
                CameraDiagnostic.expires_at <= utcnow())))
            for item in expired:
                if item.object_key:
                    self.storage.delete(item.object_key)
                db.delete(item)
        # Recover files written before their metadata commit; allow 24h repair window.
        for path in folder.iterdir():
            if path.name != "preview.jpg" and time.time() - path.stat().st_mtime > 86400:
                path.unlink(missing_ok=True)

    def _diagnostic_space(self, additional=0):
        folder = self.live_root / "diagnostics" / self.camera_id
        size = sum(p.stat().st_size for p in folder.glob("*") if p.is_file()) if folder.exists() else 0
        if size + additional > self.config["diagnostic_quota_bytes"]:
            raise ValueError("DIAGNOSTIC_QUOTA_EXCEEDED")
        return folder

    def _diagnostic_saved(self, item_id, kind, path, metadata):
        self.outbox.put("diagnostic:" + item_id, {"type": "diagnostic", "id": item_id, "kind": kind, "path": str(path), "metadata": metadata})

    def _persist_diagnostic(self, item_id, kind, path, metadata):
        raw = path.read_bytes()
        key = str(path.relative_to(self.live_root.parent))
        with self.factory.begin() as db:
            item = db.get(CameraDiagnostic, UUID(item_id))
            if item is None:
                item = CameraDiagnostic(id=UUID(item_id), camera_id=self.camera_id, facility_id=self.facility_id,
                    kind=kind, status="stored", created_at=utcnow(), expires_at=utcnow() + timedelta(hours=24), metadata_json=metadata)
                db.add(item)
            item.object_key = key; item.status = "stored"; item.size_bytes = len(raw)
            item.sha256 = hashlib.sha256(raw).hexdigest(); item.metadata_json = {**item.metadata_json, **metadata}

    def _proof(self, image, frame_time):
        import cv2
        import numpy as np
        folder = self._diagnostic_space()
        if time.time() - self.last_snapshot >= self.config["snapshot_seconds"]:
            # Persist cadence before storage/DB handoff; failure cannot cause a snapshot storm.
            self.last_snapshot = time.time(); self.outbox.state("last_snapshot", self.last_snapshot)
            overlay = image.copy()
            points = (np.asarray(self.cfg.roi) * [image.shape[1], image.shape[0]]).astype(np.int32)
            cv2.polylines(overlay, [points], True, (0, 220, 220), 3)
            cv2.putText(overlay, "ROI provisional - operator confirmation required", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 220, 220), 2)
            item_id = str(uuid4()); path = folder / f"{item_id}.jpg"
            ok, data = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok: raise ValueError("DIAGNOSTIC_ENCODE_FAILED")
            self._diagnostic_space(len(data))
            self.storage.write(str(path.relative_to(self.live_root.parent)), data.tobytes(), hashlib.sha256(data).hexdigest())
            self._diagnostic_saved(item_id, "snapshot", path, {"observed_at_utc": frame_time, "purpose": "diagnostic_no_ai", "native_pixels": [image.shape[1], image.shape[0]]})
        if self.clip is None:
            try:
                item_id = self.diag_queue.get_nowait()
                self._diagnostic_space(20 * 1024 * 1024)  # Reserve worst-case bounded diagnostic headroom.
                import av
                path = folder / f"{item_id}.mp4"
                container = av.open(str(path), "w")
                stream = container.add_stream("libx264", rate=3)
                stream.width, stream.height = 960, 540; stream.pix_fmt = "yuv420p"
                stream.options = {"crf": "25", "preset": "ultrafast"}
                self.clip = {"id": item_id, "path": path, "container": container, "stream": stream,
                    "start": time.monotonic(), "frames": 0, "first": frame_time}
            except queue.Empty:
                pass
        if self.clip:
            import av
            clip = self.clip
            small = cv2.resize(image, (960, 540))
            for packet in clip["stream"].encode(av.VideoFrame.from_ndarray(small, format="bgr24")):
                clip["container"].mux(packet)
            clip["frames"] += 1
            if time.monotonic() - clip["start"] >= 15:
                self._finish_clip(frame_time)

    def _finish_clip(self, frame_time=None):
        clip, self.clip = self.clip, None
        if not clip: return
        for packet in clip["stream"].encode():
            clip["container"].mux(packet)
        clip["container"].close()
        clip["path"].chmod(0o600)
        duration = time.monotonic() - clip["start"]
        if frame_time and 10 <= duration <= 20 and clip["frames"] >= 25:
            self._diagnostic_saved(clip["id"], "clip", clip["path"], {"first_frame_received_at": clip["first"],
                "last_frame_received_at": frame_time, "wall_seconds": round(duration, 2), "encoded_frames": clip["frames"],
                "encoded_fps": 3, "preview_pixels": [960, 540], "purpose": "diagnostic_no_ai", "not_native_stream_copy": True})
        else:
            clip["path"].unlink(missing_ok=True)
            with self.factory.begin() as db:
                row = db.get(CameraDiagnostic, UUID(clip["id"]))
                if row: row.status = "interrupted"; row.metadata_json = {"error_code": "CLIP_FRAME_GAP_OR_SHUTDOWN"}

    def _event(self, session, stage, occurrence="state"):
        item = {"visit_id": session.session_id, "stage": stage,
            "event_id": str(uuid5(UUID(session.session_id), stage + (self.owner + occurrence if stage in {"interrupted", "resumed"} else ""))), "facility_id": self.facility_id,
            "camera_id": self.camera_id, "observed_at_utc": datetime.fromtimestamp(session.started, timezone.utc).isoformat(),
            "identity": {"worker_visit_identity": session.session_id, "model_hashes": self.config["model_hashes"],
                "observed_clock": "Mac_receive_UTC_not_camera_OSD", "roi_status": self.cfg.roi_status,
                "observation_mode": self.config.get("mode", "continuous"),
                "capture_window_not_full_entry_exit": self.config.get("mode") == "event_driven",
                "event_policy": self.config.get('event_policy'),
                "camera_config": self.cfg.snapshot()},
            "ended_at_utc": datetime.fromtimestamp(session.ended or session.last_seen, timezone.utc).isoformat(),
            "end_reason": session.end_reason, "track_ids": session.track_ids, "reads": session.reads if stage == "finished" else [],
            "multiple_vehicle_review": getattr(self, "multi_vehicle", False), "evidence": [],
            "plate_observations": session.plate_observations if stage == "finished" else []}
        if stage == 'finished':
            item['capture_selection'] = {'mode': self.config['event_policy'].get('selection_mode', 'time_spaced'),
                'qualifying_plate_count': self.gate.state.get('qualifying_plate_count', 0),
                'completion_reason': self.gate.state.get('completion_reason'), 'requires_human_review': True}
        if stage == "opened":
            for key in ("ended_at_utc", "end_reason", "track_ids", "multiple_vehicle_review"):
                item.pop(key)
        return item

    def _checkpoint(self, manager, pool):
        state = self._session_state(manager, pool)
        self.outbox.state("live-state", state)
        self.outbox.state("event-gate", self.gate.state)
        atomic_json(self.active_state, state)

    def _session_state(self, manager, pool):
        return {"sessions": [asdict(s) for s in manager.sessions if s.ended is None],
            "pools": {s.session_id: pool.pools.get(s.session_id, [[], [], []]) for s in manager.sessions if s.ended is None},
            "serial": pool.serial, "tracker_created": self.tracker.created}

    def _event_tick(self):
        from app.modules.scale_ingestion.models import ScaleAgentHeartbeat, ScaleSignal
        now = utcnow(); epoch = now.timestamp()
        with self.factory.begin() as db:
            heartbeat = db.get(ScaleAgentHeartbeat, self.config['scale_agent_id'])
            self.health['scale_contact'] = ('never_received' if heartbeat is None else
                'communicating' if (now - heartbeat.received_at_utc).total_seconds() <= 90 else
                'delayed' if (now - heartbeat.received_at_utc).total_seconds() <= 180 else 'lost_contact')
            self.health['scale_reader_status'] = heartbeat.reader_status if heartbeat else None
            if self.config.get('mode') == 'event_driven':
                item = db.scalar(select(ScaleSignal).where(ScaleSignal.agent_id == self.config['scale_agent_id'],
                    ScaleSignal.observed_at_utc >= now - timedelta(seconds=self.config['event_policy']['signal_max_age_seconds']),
                    ScaleSignal.observed_at_utc <= now + timedelta(seconds=2)).order_by(
                        ScaleSignal.observed_at_utc.desc(), ScaleSignal.sequence.desc()).limit(1))
                if item and self.gate.signal(str(item.event_id), item.observed_at_utc.timestamp(), item.weight_kg, epoch):
                    self.health['trigger_signal'] = {'event_id': str(item.event_id), 'observed_at_utc': item.observed_at_utc.isoformat(),
                        'received_at_utc': item.received_at_utc.isoformat(), 'sequence': str(item.sequence), 'not_d02_link': True}
            rows = list(db.scalars(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == self.camera_id,
                CameraDiagnostic.kind.in_(['process', 'photo', 'preview']), CameraDiagnostic.status.in_(['queued', 'capturing']))
                .order_by(CameraDiagnostic.created_at, CameraDiagnostic.id).with_for_update(skip_locked=True)))
            self.gate.state['preview_until'] = 0
            for row in rows:
                metadata = dict(row.metadata_json)
                if row.status == 'queued' and datetime.fromisoformat(metadata['deadline_at']) < now:
                    row.status = 'interrupted'; row.metadata_json = {**metadata, 'error_code': 'COMMAND_EXPIRED'}; continue
                if row.kind == 'preview':
                    until = datetime.fromisoformat(metadata['preview_until']).timestamp()
                    if until <= epoch: row.status = 'completed'
                    else:
                        row.status = 'capturing'
                        self.gate.state['preview_until'] = max(self.gate.state['preview_until'], until)
                    continue
                if row.status == 'queued':
                    if datetime.fromisoformat(metadata['deadline_at']) < now:
                        row.status = 'interrupted'; row.metadata_json = {**metadata, 'error_code': 'COMMAND_EXPIRED'}; continue
                    if row.kind == 'process':
                        if self.gate.trigger(epoch, 'manual', str(row.id)):
                            self.gate.state['request_at'] = row.created_at.timestamp()
                        metadata['capture_until'] = self.gate.state['capture_until']
                    else:
                        self.photo_ids.add(str(row.id))
                        metadata['capture_until'] = epoch + 10
                    if row.kind == 'process': metadata['capture_trigger_id'] = self.gate.state['trigger_id']
                    row.status = 'capturing'; row.metadata_json = metadata
                elif row.kind == 'photo':
                    if metadata.get('capture_until', 0) > epoch: self.photo_ids.add(str(row.id))
                    elif str(row.id) not in self.photo_ids:
                        row.status = 'interrupted'; row.metadata_json = {**metadata, 'error_code': 'PHOTO_NO_FRAME'}
                elif (metadata.get('capture_until', 0) <= epoch or
                      metadata.get('capture_trigger_id', str(row.id)) == self.gate.state.get('trigger_id') and
                      self.gate.state.get('completion_reason')):
                    row.status = 'completed' if self.gate.state.get('frame_count', 0) else 'interrupted'
                    row.metadata_json = {**metadata, 'metrics': dict(self.gate.state), 'not_proof_of_departure': True,
                        'error_code': None if self.gate.state.get('frame_count', 0) else 'CAPTURE_NO_FRAME'}
            # A photo is bounded independently and never enables inference/AI.
            self.photo_ids = {key for key in self.photo_ids if any(str(row.id) == key and row.status == 'capturing'
                and row.metadata_json.get('capture_until', 0) > epoch for row in rows)}
        self.outbox.state('event-gate', self.gate.state)
        self.health.update(mode=self.config.get('mode', 'continuous'), preview_enabled=self.gate.preview(epoch),
            preview_until_utc=datetime.fromtimestamp(self.gate.state['preview_until'], timezone.utc).isoformat() if self.gate.preview(epoch) else None,
            capture_active=self.gate.capturing(epoch), capture_metrics=dict(self.gate.state))
        active = self.config.get('mode', 'continuous') == 'continuous' or self.gate.connected(epoch) or bool(self.photo_ids) or self.clip is not None or not self.diag_queue.empty()
        self.source.enable(active)
        if not active:
            self.health['processing_state'] = 'idle'
        elif not self.gate.capturing(epoch) and self.config.get('mode') == 'event_driven':
            self.health['processing_state'] = 'preview_only'

    def _manual_photo(self, image, received, item_id=None):
        import cv2
        manual_id = item_id
        folder = self._diagnostic_space(); item_id = item_id or str(uuid4())
        metadata = {'observed_at_utc': received, 'native_pixels': [image.shape[1], image.shape[0]],
            'purpose': 'bounded_capture_no_ai', 'trigger_id': manual_id or self.gate.state.get('trigger_id'),
            'not_proof_of_vehicle_presence': True}
        if manual_id:
            with self.factory.begin() as db:
                row = db.scalar(select(CameraDiagnostic).where(CameraDiagnostic.id == UUID(item_id)).with_for_update())
                if row.status != 'capturing': return folder / f'{item_id}.jpg'
                row.status = 'saving'; metadata = {**row.metadata_json, **metadata}; row.metadata_json = metadata

        ok, data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok: raise ValueError('DIAGNOSTIC_ENCODE_FAILED')
        self._diagnostic_space(len(data))
        path = folder / f'{item_id}.jpg'
        self.storage.write(str(path.relative_to(self.live_root.parent)), data.tobytes(), hashlib.sha256(data).hexdigest())
        self._diagnostic_saved(item_id, 'snapshot', path, metadata)
        return path

    def _window_evidence(self, image, received, manager, pool=None):
        now = time.time(); state = self.gate.state; policy = self.config['event_policy']
        if policy.get('selection_mode') == 'plate_guided':
            self._capture_plate_context(image, received, manager, pool)
            return
        if state['evidence_count'] >= policy['max_evidence_frames'] or now - state.get('last_evidence_at', 0) < policy['evidence_spacing_seconds']:
            return
        index = state['evidence_count']; path = self._manual_photo(image, received)
        # A camera_visit still requires vehicle observations. No empty-yard synthetic visit.
        for session in manager.sessions:
            if session.ended is not None: continue
            pending_path = self.output / 'evidence' / session.session_id / f'window-{index:02d}.jpg'
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, pending_path); pending_path.chmod(0o600)
            event = self._event(session, 'evidence')
            event['event_id'] = str(uuid5(UUID(session.session_id), 'window:' + state['trigger_id'] + ':' + str(index)))
            event['evidence'] = [{'id': str(uuid5(UUID(session.session_id), 'window-photo:' + state['trigger_id'] + ':' + str(index))),
                'kind': 'overview', 'path': str(pending_path), 'sha256': hashlib.sha256(pending_path.read_bytes()).hexdigest(),
                'observed_at_utc': received, 'transform': {'resize_before_crop': False},
                'metadata': {'phase': 'trigger_window', 'native_pixels': [image.shape[1], image.shape[0]]}}]
            self.outbox.put(f'{session.session_id}:window:{state["trigger_id"]}:{index}', event)
        state['evidence_count'] += 1; state['last_evidence_at'] = now
        if state['first_evidence_seconds'] is None: state['first_evidence_seconds'] = now - state['trigger_at']

    def _capture_plate_context(self, image, received, manager, pool):
        """Store only bounded accepted crop candidates with their same-frame context."""
        from offline_vision.export import save_jpeg
        from offline_vision.geometry import clip_box
        from offline_vision.sampling import select_capture_candidates
        state, policy = self.gate.state, self.config['event_policy']
        timestamp = datetime.fromisoformat(received).timestamp()
        eligible = []
        for session in manager.sessions:
            pools = pool.pools.get(session.session_id, [[], [], []])
            for phase in pools:
                for candidate in phase:
                    obs = candidate['observation']
                    if candidate.get('context_files') or abs(obs['media_seconds'] - timestamp) > .001:
                        continue
                    x1, y1, x2, y2 = clip_box(session.box, image.shape)
                    car = image[y1:y2, x1:x2]
                    if not car.size: continue
                    base = Path(candidate['path']).with_suffix('')
                    overview, vehicle = Path(str(base) + '-scene.jpg'), Path(str(base) + '-vehicle.jpg')
                    save_jpeg(overview, image); save_jpeg(vehicle, car)
                    candidate['context_files'] = {'overview': str(overview), 'vehicle_crop': str(vehicle)}
                    bx1, by1, bx2, by2 = obs['box_in_vehicle_crop']
                    ox, oy = obs['vehicle_crop_origin']
                    candidate['context'] = {'native_pixels': [image.shape[1], image.shape[0]],
                        'vehicle_box_native': [x1, y1, x2, y2],
                        'plate_box_native': [ox + bx1, oy + by1, ox + bx2, oy + by2],
                        'bbox_complete': bx1 > 1 and by1 > 1 and bx2 < car.shape[1] - 1 and by2 < car.shape[0] - 1}
                    state['candidate_count'] = state.get('candidate_count', 0) + 1
            eligible += select_capture_candidates(pools, policy, for_stop=True)
        state['qualifying_plate_count'] = len(eligible)
        self.health['capture_metrics'] = dict(state)
        # Never declare success from two different/ambiguous vehicles or OCR guesses.
        if (len(state.get('capture_session_ids', [])) == 1 and not getattr(self, 'multi_vehicle', False)
                and len(eligible) >= policy['success_plate_frames']
                and time.time() - state['trigger_at'] >= policy['min_capture_seconds']):
            self.gate.finish(time.time(), 'plate_quality_target_reached_requires_review')

    def _selected_plate_evidence(self, session, pool, event):
        from offline_vision.export import save_jpeg
        from offline_vision.sampling import select_capture_candidates
        import cv2
        policy = self.config['event_policy']
        selection_policy = {**policy, 'max_evidence_frames': max(0, policy['max_evidence_frames'] -
                            self.gate.state.get('evidence_count', 0))}
        selected = select_capture_candidates(pool.pools.get(session.session_id, [[], [], []]), selection_policy)
        for index, candidate in enumerate(selected):
            obs, context = candidate['observation'], candidate['context']
            folder = self.output / 'evidence' / session.session_id
            folder.mkdir(parents=True, exist_ok=True)
            for kind in ('overview', 'vehicle_crop', 'plate_crop'):
                target = folder / f'selected-{index:02d}-{kind}.jpg'
                if kind == 'plate_crop':
                    crop = cv2.imread(candidate['path'])
                    if crop is None: raise ValueError('CANDIDATE_FILE_MISSING')
                    save_jpeg(target, crop)
                else:
                    shutil.copyfile(candidate['context_files'][kind], target); target.chmod(0o600)
                sha = hashlib.sha256(target.read_bytes()).hexdigest()
                event['evidence'].append({'id': str(uuid5(UUID(session.session_id), target.name + sha)),
                    'kind': kind, 'path': str(target), 'sha256': sha,
                    'observed_at_utc': datetime.fromtimestamp(obs['media_seconds'], timezone.utc).isoformat(),
                    'bbox': {'vehicle_box_native': context['vehicle_box_native'],
                        'plate_box_native': context['plate_box_native'],
                        'box_in_vehicle_crop': obs['box_in_vehicle_crop']},
                    'transform': {'resize_before_crop': False, 'coordinates': 'native_frame',
                        'crop_origin_native': context['plate_box_native'][:2] if kind == 'plate_crop' else
                            context['vehicle_box_native'][:2] if kind == 'vehicle_crop' else [0, 0]},
                    'metadata': {'selection': 'plate_candidate_quality_and_time_spacing', 'selection_set': index,
                        'native_pixels': context['native_pixels'], 'crop_pixels': obs['crop_pixels'],
                        'quality': obs['quality'], 'bbox_complete': context['bbox_complete'],
                        'proposal_only': True, 'not_human_readability_confirmation': True}})
                if kind == 'plate_crop':
                    obs['evidence_path'] = str(target.relative_to(self.output))
                    for read in session.reads:
                        if read.get('plate_observation_index') == session.plate_observations.index(obs):
                            read['evidence_path'] = obs['evidence_path']
        return len(selected)

    def _complete_session(self, session, pool, ocr, stats, manager):
        original_config = pool.config
        previous_calls = stats['ocr_model_calls']
        if self.config.get('mode') == 'event_driven':
            remaining = max(0, self.config['event_policy']['max_ocr_calls'] - self.gate.state.get('ocr_model_calls', 0))
            pool.config = replace(original_config, max_ocr_reads=min(original_config.max_ocr_reads, session.ocr_calls + remaining))
        try: pool.recognize(session, ocr, stats, self.output)
        finally: pool.config = original_config
        self.gate.state['ocr_model_calls'] = self.gate.state.get('ocr_model_calls', 0) + stats['ocr_model_calls'] - previous_calls
        if session.reads and self.gate.state.get('trigger_at') is not None and self.gate.state.get('suggestion_seconds') is None:
            self.gate.state['suggestion_seconds'] = time.time() - self.gate.state['trigger_at']
        event = self._event(session, "finished")
        evidence = session.evidence
        guided = (self.config.get('mode') == 'event_driven' and
                  self.config['event_policy'].get('selection_mode') == 'plate_guided')
        selected = self._selected_plate_evidence(session, pool, event) if guided else False
        # Keep one vehicle scene on failure: a detector miss is not proof no plate exists.
        links = [(evidence[k], kind, evidence["overview_media_seconds"], None) for k, kind in
            ([("overview", "overview")] if guided else [("overview", "overview"), ("annotated", "overview"), ("vehicle_crop", "vehicle_crop")])
            if evidence.get(k) and not selected]
        if not guided:
            links += [(p["path"], "plate_crop", p["media_seconds"], {"box_in_vehicle_crop": p["box_in_vehicle_crop"]}) for p in evidence["plate_crops"]]
        for relative, kind, observed, box in links:
            path = self.output / relative; sha = hashlib.sha256(path.read_bytes()).hexdigest()
            event["evidence"].append({"id": str(uuid5(UUID(session.session_id), relative + sha)), "kind": kind,
                "path": str(path), "sha256": sha, "bbox": box,
                "observed_at_utc": datetime.fromtimestamp(observed, timezone.utc).isoformat(),
                "transform": {"coordinates": "native_frame_or_vehicle_crop", "resize_before_crop": False,
                    "vehicle_box_native": evidence.get("vehicle_box_native") if kind != "plate_crop" else None},
                "metadata": {"source_pixels": evidence.get("native_pixels"), "proposal_only": True,
                    "selection": "no_plate_candidate_fallback_requires_review" if guided else "legacy_best_vehicle"}})
        self.outbox.put(f"{session.session_id}:finished", event, self._session_state(manager, pool))
        if selected:
            self.gate.state['evidence_count'] += selected
            if self.gate.state.get('first_evidence_seconds') is None:
                self.gate.state['first_evidence_seconds'] = time.time() - self.gate.state['trigger_at']
        for phase in pool.pools.pop(session.session_id, []):
            for candidate in phase:
                from offline_vision.sampling import discard_candidate
                discard_candidate(candidate)

    def run(self, duration):
        import cv2
        from offline_vision.detectors import VehicleDetector
        from offline_vision.fine_tune.detector import YoloXPlateDetector
        from offline_vision.ocr import FastPlateOCR
        from offline_vision.pipeline import process_frame
        from offline_vision.sampling import CandidatePool
        from offline_vision.sessions import Session, SessionManager
        from offline_vision.tracking import Tracker
        cv2.setNumThreads(self.cfg.cpu_threads)
        vehicle = VehicleDetector(ROOT / self.config["vehicle_model_dir"], self.cfg.vehicle_threshold)
        plate = YoloXPlateDetector(ROOT / self.config["plate_manifest"], threshold=self.cfg.plate_threshold)
        ocr = FastPlateOCR(ROOT / self.config["ocr_model_dir"])
        if any(actual != self.config["model_hashes"][kind] for kind, actual in [
                ("vehicle", vehicle.metadata["sha256"]), ("plate", plate.metadata["sha256"]), ("ocr", ocr.metadata["sha256"])]):
            raise ValueError("CAMERA_MODEL_HASH_MISMATCH")
        manager, pool = SessionManager(self.cfg), CandidatePool(self.output / "candidates", self.cfg)
        self.tracker = Tracker(self.cfg)
        saved = self.outbox.state("live-state")
        if saved is None and self.active_state.exists():
            saved = json.loads(self.active_state.read_text())
        if saved:
            manager.sessions = [Session(**s) for s in saved["sessions"]]
            pool.pools, pool.serial = saved["pools"], saved["serial"]
            for session in manager.sessions:
                for phase in pool.pools.get(session.session_id, []):
                    for candidate in phase:
                        candidate["observation"] = next(o for o in session.plate_observations if o == candidate["observation"])
            self.tracker.created = saved["tracker_created"]
            for session in manager.sessions:
                self.outbox.put(f"{session.session_id}:opened", self._event(session, "opened"))
                self.outbox.put(f"{session.session_id}:interrupted:{self.owner}", self._event(session, "interrupted", "restart"))
        # Finalized outbox items own separate copies; only active pools reference this folder.
        referenced = {Path(c['path']).resolve() for phases in pool.pools.values() for phase in phases for c in phase}
        referenced.update(Path(p).resolve() for phases in pool.pools.values() for phase in phases for c in phase
                          for p in c.get('context_files', {}).values())
        for candidate_path in (self.output / 'candidates').iterdir():
            if candidate_path.is_file() and candidate_path.resolve() not in referenced:
                candidate_path.unlink()
        stats = {"vehicle_detection_calls": 0, "vehicle_detection_boxes": 0, "frames_with_vehicle": 0,
            "plate_detection_calls": 0, "plate_detection_boxes": 0, "ocr_observation_reads": 0, "ocr_model_calls": 0}
        worker = self
        class PlateBudget:
            def detect(self, image, seconds):
                if worker.config.get('mode') == 'event_driven' and worker.gate.state.get('plate_model_calls', 0) >= worker.config['event_policy']['max_plate_calls']:
                    return []
                if worker.config.get('mode') == 'event_driven': worker.gate.state['plate_model_calls'] = worker.gate.state.get('plate_model_calls', 0) + 1
                return plate.detect(image, seconds)
        bounded_plate = PlateBudget()
        self.source.start(); self.maintenance.start()
        next_process = 0; last_frame_time = None; generation = None; last_preview = 0; next_event_poll = 0; was_capturing = bool(manager.sessions); self.window_ocr_start = 0; self.window_plate_start = 0; window_id = None
        try:
            while not self.stop.is_set() and (not duration or time.monotonic() - self.started < duration):
                capturing = self.gate.capturing(time.time())
                if was_capturing and not capturing and self.config.get('mode') == 'event_driven':
                    if (self.config['event_policy'].get('selection_mode') == 'plate_guided' and
                            not self.gate.state.get('completion_reason')):
                        self.gate.finish(time.time(), 'capture_time_limit_requires_review')
                    for session in manager.sessions:
                        if session.ended is None:
                            session.ended = time.time(); session.end_reason = (self.gate.state.get('completion_reason') or
                                'capture_window_expired_not_proof_of_departure')
                        self._complete_session(session, pool, ocr, stats, manager)
                    manager.sessions = []; self.tracker.tracks.clear(); manager.entry_hits.clear()
                    self._checkpoint(manager, pool)
                    self.outbox.state('event-gate', self.gate.state)
                    self.health['active_visits'] = 0
                    self.health['capture_metrics'] = dict(self.gate.state)
                    try:
                        with self.factory.begin() as db:
                            for command in db.scalars(select(CameraDiagnostic).where(CameraDiagnostic.camera_id == self.camera_id,
                                    CameraDiagnostic.kind == 'process', CameraDiagnostic.status == 'completed',
                                    CameraDiagnostic.created_at > utcnow() - timedelta(seconds=60))):
                                command.metadata_json = {**command.metadata_json, 'metrics': dict(self.gate.state)}
                    except Exception: self.health['outbox_error_code'] = 'CONTROL_OR_SCALE_DATABASE_UNAVAILABLE'
                if time.monotonic() >= next_event_poll:
                    try: self._event_tick()
                    except Exception: self.health['outbox_error_code'] = 'CONTROL_OR_SCALE_DATABASE_UNAVAILABLE'
                    next_event_poll = time.monotonic() + 1
                capturing = self.gate.capturing(time.time())
                if capturing and window_id != self.gate.state['trigger_id']:
                    window_id = self.gate.state['trigger_id']
                    self.multi_vehicle = False
                    self.window_ocr_start = stats['ocr_model_calls']; self.window_plate_start = stats['plate_detection_calls']
                was_capturing = capturing
                try:
                    native, received, decoded, decode_tick, current_generation = self.source.frames.get(timeout=.5)
                except queue.Empty:
                    if self.clip and time.monotonic() - self.clip["start"] > 20:
                        self._finish_clip()
                    continue
                if self.config.get('mode') == 'event_driven' and not (capturing or self.gate.preview(time.time()) or self.photo_ids or self.clip or not self.diag_queue.empty()):
                    continue
                if time.monotonic() < next_process:
                    continue
                hz = self.config["event_policy"]["capture_hz"] if self.config.get("mode") == "event_driven" and capturing else self.cfg.sample_hz
                next_process = time.monotonic() + 1 / hz
                timestamp = datetime.fromisoformat(received).timestamp()
                # Stream gaps/restarts cannot be interpreted as vehicle departure.
                if generation != current_generation or (last_frame_time and timestamp - last_frame_time > 2):
                    for session in manager.sessions:
                        shift = max(0, timestamp - session.last_seen)
                        session.last_seen += shift; session.last_inside += shift
                        if session.outside_since: session.outside_since += shift
                    self.tracker.tracks.clear(); manager.entry_hits.clear()
                generation, last_frame_time = current_generation, timestamp
                image = native.to_ndarray(format="bgr24")
                if self.gate.preview(time.time()) and time.monotonic() - last_preview >= 1:
                    preview = cv2.resize(image, (640, 360))
                    ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok:
                        target = self.storage.path(self.health["preview_key"])
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        temporary = target.with_suffix(".tmp")
                        with open(temporary, "wb") as stream: os.chmod(temporary, 0o600); stream.write(encoded.tobytes())
                        os.replace(temporary, target)
                    last_preview = time.monotonic()
                if capturing:
                    self.gate.state['frame_count'] += 1
                    if self.gate.state['first_frame_seconds'] is None:
                        self.gate.state['first_frame_seconds'] = time.time() - self.gate.state['trigger_at']
                for photo_id in list(self.photo_ids):
                    try: self._manual_photo(image, received, photo_id)
                    except Exception:
                        self.health['diagnostic_error_code'] = 'DIAGNOSTIC_STORAGE_OR_CAPTURE_ERROR'
                        try:
                            with self.factory.begin() as db:
                                row = db.get(CameraDiagnostic, UUID(photo_id))
                                if row: row.status = 'interrupted'; row.metadata_json = {**row.metadata_json, 'error_code': 'PHOTO_STORAGE_OR_QUOTA_ERROR'}
                        except Exception: pass
                    self.photo_ids.remove(photo_id)
                try:
                    self._proof(image, received)
                except Exception:
                    self.health["diagnostic_error_code"] = "DIAGNOSTIC_STORAGE_OR_CAPTURE_ERROR"
                if self.config.get('mode') == 'event_driven' and (not capturing or self.gate.state['inference_count'] >= self.config['event_policy']['max_inference_frames']):
                    continue
                try:
                    before = {s.session_id for s in manager.sessions}
                    process_frame(SimpleNamespace(image=image, seconds=timestamp, index=self.health["processed_frames"]),
                        self.output, self.cfg, vehicle, bounded_plate, self.tracker, manager, pool, stats)
                    if capturing: self.gate.state['inference_count'] += 1
                    self.multi_vehicle = getattr(self, 'multi_vehicle', False) or len([s for s in manager.sessions if s.ended is None]) > 1
                    for session in manager.sessions:
                        if session.session_id not in before:
                            old_id = session.session_id; session.session_id = str(uuid4())
                            if old_id in pool.pools: pool.pools[session.session_id] = pool.pools.pop(old_id)
                            old_folder = self.output / "evidence" / old_id
                            if old_folder.exists(): old_folder.rename(old_folder.with_name(session.session_id))
                            session.evidence = json.loads(json.dumps(session.evidence).replace(old_id, session.session_id))
                            self.gate.state.setdefault('capture_session_ids', []).append(session.session_id)
                            self.outbox.put(f"{session.session_id}:opened", self._event(session, "opened"), self._session_state(manager, pool))
                            initial = self._event(session, "evidence")
                            for key, kind in ([] if self.config.get('mode') == 'event_driven' and
                                              self.config['event_policy'].get('selection_mode') == 'plate_guided' else
                                              [("overview", "overview"), ("vehicle_crop", "vehicle_crop")]):
                                if session.evidence.get(key):
                                    original = self.output / session.evidence[key]
                                    path = original.with_name("initial-" + original.name)
                                    shutil.copyfile(original, path); path.chmod(0o600)
                                    sha = hashlib.sha256(path.read_bytes()).hexdigest()
                                    initial["evidence"].append({"id": str(uuid5(UUID(session.session_id), "initial:" + key)),
                                        "kind": kind, "path": str(path), "sha256": sha, "observed_at_utc": received,
                                        "bbox": {"vehicle_box_native": session.evidence.get("vehicle_box_native")},
                                        "transform": {"crop_origin_native": session.evidence.get("vehicle_box_native", [0, 0])[:2], "resize_before_crop": False},
                                        "metadata": {"native_pixels": session.evidence.get("native_pixels"), "phase": "entry"}})
                            if initial['evidence']:
                                self.outbox.put(f"{session.session_id}:initial-evidence", initial)
                        if session.ended is not None:
                            self._complete_session(session, pool, ocr, stats, manager)
                    if capturing:
                        self._window_evidence(image, received, manager, pool)
                    manager.sessions = [s for s in manager.sessions if s.ended is None]
                    self._checkpoint(manager, pool)
                    self.health.update(last_frame_processed_at=utcnow().isoformat(), processed_frames=self.health["processed_frames"] + 1,
                        latency_ms=round((time.monotonic() - decode_tick) * 1000, 1), processing_state="processing", processing_error_code=None,
                        latency_measure="decode_to_processing_complete_not_camera_end_to_end", active_visits=len(manager.sessions), **stats)
                    if sum(p.stat().st_size for p in self.output.rglob("*") if p.is_file()) > self.config["outbox_quota_bytes"]:
                        self.health["processing_error_code"] = "OUTBOX_QUOTA_EXCEEDED"
                        self.stop.set()  # Explicit stop with durable files, never silently discard evidence.
                except Exception:
                    self.health["processing_state"] = "error"; self.health["processing_error_code"] = "INFERENCE_OR_STATE_ERROR"
                    self.stop.wait(1)
        finally:
            self.stop.set(); self.source.close()
            self._checkpoint(manager, pool)
            for session in manager.sessions:
                self.outbox.put(f"{session.session_id}:interrupted:{self.owner}:shutdown", self._event(session, "interrupted", "shutdown"))
            try: self._finish_clip()
            except Exception: pass
            self.maintenance.join(timeout=10)
            self.health["processing_state"] = "stopped"
            final = self._snapshot()
            atomic_json(self.report_path, {**final, "reported_at_utc": utcnow().isoformat(), "shutdown": True})
            with self.factory.begin() as db:
                row = db.get(CameraRuntime, self.camera_id)
                if row and row.owner == self.owner:
                    row.snapshot = final; row.updated_at = utcnow()
            self.engine.dispose()
            print(json.dumps({"event": "camera_shutdown", "processed_frames": final["processed_frames"], "decoded_frames": final["decoded_frames"], "outbox_depth": final["outbox_depth"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Separate live camera worker (Keychain credentials only)")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=int, default=0, help="0 means continuous; SIGTERM shuts down safely")
    args = parser.parse_args()
    try:
        worker = Worker(args.config)
        signal.signal(signal.SIGTERM, lambda *_: worker.stop.set())
        signal.signal(signal.SIGINT, lambda *_: worker.stop.set())
        worker.run(args.duration_seconds)
        return 0
    except Exception as error:
        code = "CAMERA_WORKER_ALREADY_RUNNING" if str(error) == "CAMERA_WORKER_ALREADY_RUNNING" else "CAMERA_WORKER_START_OR_STOP_FAILED"
        print(json.dumps({"event": "camera_worker_error", "code": code}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
