"""Run the existing D05a offline pipeline, then idempotently ingest its bundle into the pilot DB."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.models import utcnow
from app.modules.accounts import models as _account_models  # Register Facility.user relationship targets for standalone worker.
from app.modules.facilities.models import Facility
from app.modules.vehicle_pilot.models import CameraEvidence, CameraVisit, VehiclePilotAuditEvent, VehiclePrediction
from app.modules.vehicle_pilot.storage import EvidenceStorage

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
VISION_ROOT = REPOSITORY_ROOT / "edge-agent"
D05F_PLATE_MANIFEST = REPOSITORY_ROOT / "data/offline-vision/runs/d05f-vast-54567374/final/export/model.json"
FASTPLATE_DIR = REPOSITORY_ROOT / "data/offline-vision/benchmark-models/fast-plate-cct-s-v2"


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Offline run clock must include explicit timezone")
    return parsed.astimezone(timezone.utc)


def _manifest_dict(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def ingest_run(run_dir: Path, facility_code: str):
    run_dir = run_dir.resolve()
    result_path = run_dir / "result.json"
    if not result_path.is_file():
        raise ValueError(f"Missing offline result file in {run_dir}")
    report = json.loads(result_path.read_text(encoding="utf-8"))
    if report.get("fixture"):
        raise ValueError("Scripted fixtures cannot be ingested as pilot camera visits")
    source = report.get("source_video", {})
    source_hash = source.get("sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise ValueError("Offline report has no valid source video SHA-256")
    camera_id = report.get("camera_id")
    if not camera_id:
        raise ValueError("Offline report has no camera_id")
    stable_model_info = {key: value.get("sha256") or value.get("revision") or value.get("version")
                         for key, value in report.get("models", {}).items() if isinstance(value, dict)}
    config_version = hashlib.sha256(json.dumps({"pipeline": report.get("pipeline_version"), "models": stable_model_info}, sort_keys=True).encode()).hexdigest()
    video_start = _utc(source.get("video_start_utc"))
    observed_count = evidence_count = prediction_count = duplicate_count = 0
    storage = EvidenceStorage()
    settings = get_settings()
    # Replay commits each durable stage (visit, evidence metadata, file state,
    # prediction) so a retry can repair a partial file/DB handoff. Use a plain
    # session rather than a transaction context that cannot survive those commits.
    with SessionLocal() as db:
        facility = db.scalar(select(Facility).where(Facility.code == facility_code, Facility.is_active.is_(True)))
        if facility is None:
            raise ValueError("Không tìm thấy cơ sở đang hoạt động theo facility-code.")
        for session in report.get("sessions", []):
            session_key = f"{camera_id}:{source_hash}:{config_version}:{session['start_media_seconds']:.3f}:{session.get('end_media_seconds', 0):.3f}"
            visit_id = uuid5(NAMESPACE_URL, f"nhu-tung-replay:{session_key}")
            evidence_meta = {"source_video_sha256": source_hash, "pipeline_version": report.get("pipeline_version"),
                             "model_versions": stable_model_info, "offline_session_id": session.get("session_id"),
                             "track_ids": session.get("track_ids", [])}
            visit_payload = {"facility_id": facility.id, "camera_id": camera_id, "source_mode": "replay",
                "source_ref": f"video-{source_hash[:12]}", "start_media_seconds": session.get("start_media_seconds"),
                "end_media_seconds": session.get("end_media_seconds"), "observed_at_utc":
                    (video_start.timestamp() + session["start_media_seconds"]) if video_start else None,
                "status": "needs_review", "metadata_json": evidence_meta}
            fingerprint = hashlib.sha256(json.dumps(visit_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
            visit = db.get(CameraVisit, visit_id)
            if visit:
                if visit.create_fingerprint != fingerprint or visit.facility_id != facility.id:
                    raise ValueError(f"Stable replay visit id conflicts with an existing version: {visit_id}")
                duplicate_count += 1
            else:
                observed_at = datetime.fromtimestamp(visit_payload["observed_at_utc"], timezone.utc) if video_start else None
                visit = CameraVisit(id=visit_id, facility_id=facility.id, camera_id=camera_id, source_mode="replay",
                    source_ref=visit_payload["source_ref"], start_media_seconds=session.get("start_media_seconds"),
                    end_media_seconds=session.get("end_media_seconds"), observed_at_utc=observed_at,
                    received_at_utc=utcnow(), status="needs_review", create_fingerprint=fingerprint,
                    metadata_json=evidence_meta, version=1, created_at=utcnow(), updated_at=utcnow())
                db.add(visit)
                db.flush()
                db.add(VehiclePilotAuditEvent(id=uuid5(visit_id, "visit-created"), visit_id=visit_id,
                    facility_id=facility.id, actor_user_id=None, event="replay_visit_ingested",
                    details={"camera_id": camera_id, "source_mode": "replay", "source_video_sha256": source_hash}, created_at=utcnow()))
                db.commit()
            links: list[tuple[str, str, float | None, dict | None]] = []
            ev = session.get("evidence", {})
            for name, kind in [("overview", "overview"), ("annotated", "overview"), ("vehicle_crop", "vehicle_crop")]:
                if ev.get(name):
                    links.append((ev[name], kind, ev.get("overview_media_seconds"), None))
            for crop in ev.get("plate_crops", []):
                if crop.get("path"):
                    links.append((crop["path"], "plate_crop", crop.get("media_seconds"),
                                  {"box_in_vehicle_crop": crop.get("box_in_vehicle_crop")}))
            path_to_evidence = {}
            for relative, kind, media_seconds, bbox in links:
                source_path = (run_dir / relative).resolve()
                if run_dir not in source_path.parents or not source_path.is_file():
                    continue
                content_type = "image/jpeg" if source_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png" if source_path.suffix.lower() == ".png" else None
                if content_type is None:
                    continue
                raw = source_path.read_bytes()
                sha = storage.validate(raw, content_type)
                evidence_id = uuid5(visit_id, f"{relative}:{sha}")
                object_key = storage.object_key(facility.id, visit_id, evidence_id, content_type)
                existing = db.get(CameraEvidence, evidence_id)
                if existing:
                    if existing.sha256 != sha or existing.visit_id != visit_id:
                        raise ValueError(f"Stable replay evidence ID conflict: {evidence_id}")
                    if existing.storage_state != "stored":
                        storage.write(existing.object_key, raw, sha)
                        existing.storage_state = "stored"
                        db.commit()
                    duplicate_count += 1
                else:
                    reserved = db.scalar(select(func.coalesce(func.sum(CameraEvidence.size_bytes), 0)).where(
                        CameraEvidence.facility_id == facility.id, CameraEvidence.storage_state.in_(["pending", "stored"]))) or 0
                    if reserved + len(raw) > settings.pilot_evidence_quota_per_facility_bytes or storage.free_bytes() < len(raw) + 16 * 1024 * 1024:
                        raise OSError("Evidence quota/disk safety limit reached; replay bundle remains available to retry.")
                    row = CameraEvidence(id=evidence_id, visit_id=visit_id, facility_id=facility.id, kind=kind,
                        source_mode="replay", media_seconds=media_seconds, observed_at_utc=
                            datetime.fromtimestamp(video_start.timestamp() + media_seconds, timezone.utc) if video_start and media_seconds is not None else None,
                        received_at_utc=utcnow(),
                        retention_until_utc=utcnow() + timedelta(days=settings.pilot_evidence_retention_days),
                        content_type=content_type, size_bytes=len(raw), sha256=sha,
                        object_key=object_key, storage_state="pending", bbox_json=bbox,
                        transform_json=None, metadata_json={"source_relative_path": relative, "source_video_sha256": source_hash})
                    db.add(row)
                    db.add(VehiclePilotAuditEvent(id=uuid5(evidence_id, "evidence-stored"), visit_id=visit_id,
                        facility_id=facility.id, actor_user_id=None, event="replay_evidence_ingested",
                        details={"evidence_id": str(evidence_id), "kind": kind, "sha256": sha, "size_bytes": len(raw)}, created_at=utcnow()))
                    db.commit()
                    storage.write(object_key, raw, sha)
                    row.storage_state = "stored"
                    db.commit()
                path_to_evidence[relative] = evidence_id
                evidence_count += 1

            proposed = session.get("proposed_plate")
            prediction_material = session.get("raw_ocr", [])
            if proposed or prediction_material:
                proposal_id = uuid5(visit_id, f"local:{report.get('pipeline_version')}:{config_version}:proposal")
                if db.get(VehiclePrediction, proposal_id) is None:
                    source_evidence_id = next(iter(path_to_evidence.values()), None)
                    normalized = "".join(ch for ch in proposed.upper() if ch.isalnum()) if proposed else None
                    row = VehiclePrediction(id=proposal_id, visit_id=visit_id, evidence_id=source_evidence_id,
                        source="local", identifier_kind="unknown", raw_text=proposed,
                        normalized_text=normalized, visible_text=proposed,
                        reading_status="partial" if proposed else "unknown",
                        model_version=str(stable_model_info.get("ocr") or report.get("models", {}).get("ocr", {}).get("version") or "offline-pipeline"),
                        prompt_version=None, score_info={"decision": session.get("decision"), "candidate_count": len(session.get("candidates", []))},
                        raw_result={"candidates": session.get("candidates", []), "reads": prediction_material,
                                    "source": "D05a offline result; not a manual confirmation"}, created_at=utcnow())
                    db.add(row)
                    db.add(VehiclePilotAuditEvent(id=uuid5(proposal_id, "prediction-appended"), visit_id=visit_id,
                        facility_id=facility.id, actor_user_id=None, event="local_prediction_ingested",
                        details={"prediction_id": str(proposal_id), "source": "local", "identifier_kind": "unknown"}, created_at=utcnow()))
                    db.commit()
                    prediction_count += 1
                else:
                    duplicate_count += 1
            observed_count += 1
    return {"visits_seen": observed_count, "evidence_seen": evidence_count,
            "predictions_added": prediction_count, "idempotent_duplicates": duplicate_count,
            "source_video_sha256": source_hash, "mode": "replay", "d02_written": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reuse D05a offline video pipeline and ingest reviewable visits into the local pilot DB")
    parser.add_argument("--facility-code", required=True)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--camera-config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=REPOSITORY_ROOT / "data/offline-vision/models")
    parser.add_argument("--plate-model-manifest", type=Path, default=D05F_PLATE_MANIFEST)
    parser.add_argument("--plate-model-threshold", type=float, default=0.25)
    parser.add_argument("--fastplate-dir", type=Path, default=FASTPLATE_DIR)
    parser.add_argument("--vision-python", type=Path, default=VISION_ROOT / ".venv/bin/python")
    parser.add_argument("--start-seconds", type=float, default=0)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument("--video-start-utc", help="Optional absolute UTC at media time zero; never inferred")
    parser.add_argument("--ingest-only", action="store_true", help="Retry a persisted D05a output bundle without running inference again")
    args = parser.parse_args(argv)
    try:
        if args.ingest_only:
            summary = ingest_run(args.output, args.facility_code)
        else:
            if not args.video or not args.camera_config:
                parser.error("--video and --camera-config are required unless --ingest-only is set")
            if not args.vision_python.is_file():
                raise FileNotFoundError("Không tìm thấy Python environment của edge-agent; dùng --vision-python với interpreter có OpenCV và D05a dependencies.")
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            command = [str(args.vision_python), "-m", "offline_vision.cli", "run", "--video", str(args.video.resolve()),
                "--config", str(args.camera_config.resolve()), "--output", str(args.output.resolve()), "--model-dir", str(args.model_dir.resolve()),
                "--plate-model-manifest", str(args.plate_model_manifest.resolve()),
                "--plate-model-threshold", str(args.plate_model_threshold),
                "--fastplate-dir", str(args.fastplate_dir.resolve()),
                "--start-seconds", str(args.start_seconds)]
            if args.end_seconds is not None:
                command.extend(["--end-seconds", str(args.end_seconds)])
            if args.video_start_utc:
                command.extend(["--video-start-utc", args.video_start_utc])
            completed = subprocess.run(command, cwd=VISION_ROOT, check=False)
            if completed.returncode != 0:
                raise RuntimeError(f"D05a offline pipeline exited with code {completed.returncode}; output folder is retained for inspection.")
            summary = ingest_run(args.output, args.facility_code)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Replay worker stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
