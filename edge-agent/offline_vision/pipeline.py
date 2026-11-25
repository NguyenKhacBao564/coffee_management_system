from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import time
from tempfile import TemporaryDirectory
from uuid import uuid4

import cv2

from . import VERSION
from .consensus import decide
from .export import prepare_output, save_overview, write_report
from .selection import frame_quality, plate_crop, vehicle_crop
from .sessions import SessionManager
from .sampling import CandidatePool
from .tracking import Tracker
from .video import VideoReader


def run_pipeline(video: Path, output: Path, config, vehicle_detector, plate_detector, ocr,
                 *, start: float = 0, end: float | None = None, video_start_utc: datetime | None = None,
                 profile=None, fixture: bool = False):
    prepare_output(output)
    with TemporaryDirectory(prefix=".candidate-work-", dir=output) as temporary:
        return _run_pipeline(video, output, config, vehicle_detector, plate_detector, ocr,
            start=start, end=end, video_start_utc=video_start_utc, profile=profile, fixture=fixture,
            pool=CandidatePool(Path(temporary), config))


def _run_pipeline(video, output, config, vehicle_detector, plate_detector, ocr, *, start, end,
                  video_start_utc, profile, fixture, pool):
    cv2.setNumThreads(config.cpu_threads)
    reader = VideoReader(video, config.sample_hz, start, end)
    tracker, manager = Tracker(config), SessionManager(config)
    stats = {"vehicle_detection_calls":0, "vehicle_detection_boxes":0, "frames_with_vehicle":0,
             "plate_detection_calls":0, "plate_detection_boxes":0, "ocr_observation_reads":0, "ocr_model_calls":0}
    began = time.perf_counter()
    timeline = output / "sampled-detections.jsonl"
    with timeline.open("w", encoding="utf-8") as stream:
        for frame in reader:
            process_frame(frame, output, config, vehicle_detector, plate_detector, tracker, manager, pool, stats, stream)
    timeline.chmod(0o600)
    if not reader.sampled:
        raise ValueError("No sampled frames in the requested media range; cannot interpret this as no vehicles")
    manager.finish(reader.last_seconds)
    for session in manager.sessions:
        pool.recognize(session, ocr, stats, output)
    stats.update({"processing_wall_seconds_excluding_model_init":time.perf_counter()-began,
                  "decoded_frames":reader.decoded, "sampled_frames":reader.sampled, "tracks_created":tracker.created,
                  "roi_sessions":len(manager.sessions), "sessions_with_plate_detection":sum(bool(s.plate_observations) for s in manager.sessions),
                  "sessions_with_ocr_proposal":sum(s.proposed_plate is not None for s in manager.sessions),
                  "unknown_sessions":sum(s.proposed_plate is None for s in manager.sessions),
                  "fully_correct_plates":None, "accuracy":None, "accuracy_reason":"No manual ground-truth labels supplied"})
    if profile:
        stats.update(profile.finish())
    sessions = []
    for session in manager.sessions:
        session.proposed_plate, session.decision, session.candidates = decide(session.reads, config.consistent_reads, config.consensus_ratio)
        item = {"camera_id":config.camera_id, "session_id":session.session_id, "track_ids":session.track_ids,
                "start_media_seconds":session.started, "end_media_seconds":session.ended, "last_inside_media_seconds":session.last_inside,
                "end_reason":session.end_reason, "proposed_plate":session.proposed_plate, "recognition":"proposal" if session.proposed_plate else "unknown",
                "status":"needs_confirmation", "decision":session.decision, "candidates":session.candidates, "raw_ocr":session.reads,
                "plate_observations":session.plate_observations, "evidence":session.evidence,
                "limits":{"plate_attempts":session.plate_attempts, "ocr_model_calls":session.ocr_calls,
                          "ocr_stopped_after_consensus":session.ocr_complete,
                          "plate_attempts_by_phase": session.attempt_phase_counts},
                "plate_attempt_log": session.plate_attempt_log}
        if video_start_utc is not None:
            item["start_utc"] = (video_start_utc + timedelta(seconds=session.started)).isoformat()
            item["end_utc"] = (video_start_utc + timedelta(seconds=session.ended)).isoformat()
        sessions.append(item)
    report = {"schema_version":1, "pipeline_version":VERSION, "run_id":str(uuid4()), "camera_id":config.camera_id,
              "fixture":fixture, "source_video":{"path":str(video.resolve()), "sha256":hashlib.sha256(video.read_bytes()).hexdigest(),
                  "metadata":reader.metadata, "range_seconds":{"start":start,"end":end},
                  "video_start_utc":video_start_utc.isoformat() if video_start_utc else None},
              "config":config.snapshot(), "models":{"vehicle":vehicle_detector.metadata,"plate":plate_detector.metadata,"ocr":ocr.metadata},
              "runtime":{"opencv":cv2.__version__, "python":platform.python_version(), "system":platform.system(),
                         "architecture":platform.machine(), "cpu_threads_opencv":config.cpu_threads,
                         "decoder_threads":"controlled by OpenCV bundled decoder, not the DNN thread setting"},
              "confidence_policy":"Scores retained with stage/model semantics; no cross-model averaging/comparison or calibrated probability claim",
              "tracking_policy":"Greedy image association + timed ROI session grace; IDs confined to camera/run; ambiguous close/occluded vehicles require review",
              "ocr_selection_policy": "D05b: bounded lossless quality pools for early/middle/late media ages; defer OCR until clip ends; phase quotas then unused-budget backfill; near-duplicate/time suppression; raw unknown preserved",
              "statistics":stats, "sessions":sessions}
    write_report(output, report)
    return report


def process_frame(frame, output, config, vehicle_detector, plate_detector, tracker, manager, pool, stats, stream=None):
    detections = vehicle_detector.detect(frame.image, frame.seconds)
    stats["vehicle_detection_calls"] += 1; stats["vehicle_detection_boxes"] += len(detections)
    stats["frames_with_vehicle"] += bool(detections)
    tracks = tracker.update(detections, frame.seconds, frame.image.shape)
    links = manager.update(tracks, frame.seconds, frame.image.shape)
    if stream is not None: stream.write(json.dumps({"media_seconds":frame.seconds, "frame_index":frame.index,
        "tracks":[{"track_id":track.track_id, **asdict(track.detection)} for track in tracks],
        "roi_session_ids":[session.session_id for session,_ in links]}, allow_nan=False) + "\n")
    for session, track in links:
        quality = frame_quality(frame.image, track.detection.box)
        if quality > session.best_quality:
            save_overview(output, session, frame.image, track.detection.box, config.roi, frame.seconds)
            session.best_quality = quality
        if not pool.should_attempt(session, frame.seconds):
            continue
        session.plate_attempts += 1; session.last_plate_attempt = frame.seconds
        phase = pool.phase(session, frame.seconds)
        session.attempt_phase_counts[phase] += 1
        car, origin = vehicle_crop(frame.image, track.detection.box)
        if not car.size:
            continue
        plates = plate_detector.detect(car, frame.seconds)
        session.plate_attempt_log.append({"media_seconds": frame.seconds, "phase": phase,
            "vehicle_crop_pixels": [car.shape[1], car.shape[0]], "plate_boxes": len(plates)})
        stats["plate_detection_calls"] += 1; stats["plate_detection_boxes"] += len(plates)
        for plate in plates[:2]:
            crop = plate_crop(car, plate)
            observation = {"media_seconds":frame.seconds, "box_in_vehicle_crop":list(plate.box), "vehicle_crop_origin":list(origin),
                           "score":plate.score, "model":plate.model, "corners":plate.corners,
                           "crop_pixels":[crop.shape[1],crop.shape[0]], "used_for_ocr":False}
            session.plate_observations.append(observation)
            pool.offer(session, crop, observation)
    return links
