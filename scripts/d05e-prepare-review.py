#!/usr/bin/env python3
"""Prepare D05e local review assets from D05d runs and the D05b frame set."""
import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-agent"))

from offline_vision.dataset import export_blank_csv, save_png, sha256, browser_manifest  # noqa: E402
from offline_vision.fine_tune.detector import YoloXPlateDetector  # noqa: E402
from offline_vision.geometry import clip_box  # noqa: E402
from offline_vision.sampling import image_hash  # noqa: E402
from offline_vision.video import VideoReader  # noqa: E402


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def frame_index_by_time(video, sample_hz, times):
    wanted = {round(float(t), 3): float(t) for t in times}
    found = {}
    for frame in VideoReader(video, sample_hz):
        key = round(frame.seconds, 3)
        target = wanted.get(key)
        if target is not None and abs(target - frame.seconds) <= 0.002:
            found[key] = frame.image.copy()
    missing = set(wanted) - set(found)
    if missing:
        raise ValueError(f"Could not reproduce D05d sampled frames at media seconds: {sorted(missing)}")
    return found


def build_crop_review(runs, output):
    items, sources = [], []
    output_crops, output_contexts = output / "crop-review" / "crops", output / "crop-review" / "contexts"
    output_crops.mkdir(parents=True, mode=0o700)
    output_contexts.mkdir(mode=0o700)
    for run_dir in runs:
        result = json.loads((run_dir / "result.json").read_text())
        video = Path(result["source_video"]["path"])
        video_sha = result["source_video"]["sha256"]
        if sha256(video) != video_sha:
            raise ValueError(f"Source video hash differs from D05d report: {video}")
        observations = []
        for session in result["sessions"]:
            for obs in session["plate_observations"]:
                observations.append((session, obs))
        times = sorted({obs["media_seconds"] for _, obs in observations})
        sample_hz = float(result["config"]["sample_hz"])
        frames = frame_index_by_time(video, sample_hz, times)
        source_id = f"source-{run_dir.name}"
        sources.append({"source_id": source_id, "path": str(video), "sha256": video_sha,
                        "duration_seconds": result["source_video"]["metadata"].get("format", {}).get("duration")})
        for ordinal, (session, obs) in enumerate(sorted(observations, key=lambda x: (x[1]["media_seconds"], x[1]["score"])), 1):
            frame = frames[round(float(obs["media_seconds"]), 3)]
            ox, oy = map(int, obs["vehicle_crop_origin"])
            bx1, by1, bx2, by2 = obs["box_in_vehicle_crop"]
            box = clip_box((ox + bx1, oy + by1, ox + bx2, oy + by2), frame.shape)
            x1, y1, x2, y2 = box
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                raise ValueError(f"Empty reconstructed detector crop {run_dir.name}/{ordinal}")
            expected = obs["crop_pixels"]
            if [crop.shape[1], crop.shape[0]] != expected:
                raise ValueError(f"Native crop size mismatch for {run_dir.name}/{ordinal}: {[crop.shape[1], crop.shape[0]]} != {expected}")
            crop_id = f"{run_dir.name}-{ordinal:03d}"
            crop_rel = f"crop-review/crops/{crop_id}.png"
            if not cv2.imwrite(str(output / crop_rel), crop):
                raise ValueError(f"Cannot write {crop_rel}")
            (output / crop_rel).chmod(0o600)
            context_rel = f"crop-review/contexts/{crop_id}.jpg"
            context = frame.copy()
            cv2.rectangle(context, (x1, y1), (x2, y2), (0, 130, 255), 3)
            cv2.putText(context, f"{crop_id} score={obs['score']:.4f} media={obs['media_seconds']:.3f}s",
                        (18, 38), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 130, 255), 2)
            if not cv2.imwrite(str(output / context_rel), context, [cv2.IMWRITE_JPEG_QUALITY, 96]):
                raise ValueError(f"Cannot write {context_rel}")
            (output / context_rel).chmod(0o600)
            items.append({"crop_id": crop_id, "video_name": video.name, "source_id": source_id,
                "source_video_sha256": video_sha, "run_name": run_dir.name, "session_id": session["session_id"],
                "track_id": session["track_ids"][0] if session["track_ids"] else None,
                "media_seconds": float(obs["media_seconds"]), "frame_width": int(frame.shape[1]),
                "frame_height": int(frame.shape[0]), "frame_bbox_xyxy": list(map(int, box)),
                "score": float(obs["score"]), "model": obs["model"], "width": int(crop.shape[1]),
                "height": int(crop.shape[0]), "crop_path": crop_rel, "annotated_path": context_rel,
                "status": "pending", "manual_text": "", "layout": "pending", "readability": "pending",
                "notes": "", "label_origin": "manual_review_required"})
    dataset = {"schema_version": 1, "dataset_id": str(uuid.uuid4()), "label_origin": "manual_review_required",
        "purpose": "D05e crop review; detector proposals are not ground truth and OCR is excluded from label form",
        "sources": sources, "items": items,
        "instructions": "Set pending/correct_plate/wrong_region/truncated by visual review. Enter text only by reading the image. OCR outputs are not ground truth."}
    write_json(output / "crop-review" / "crop-review.template.json", dataset)
    template = (ROOT / "edge-agent/offline_vision/d05e_crop_review.html").read_text(encoding="utf-8")
    embedded = json.dumps(dataset, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    page = template.replace("__REVIEW_DATA__", embedded)
    (output / "crop-review" / "review.html").write_text(page, encoding="utf-8")
    (output / "crop-review" / "review.html").chmod(0o600)
    return items, sources


def build_missed_frame_label_set(base_dataset, output, detector, runs):
    original = json.loads((base_dataset / "manifest.template.json").read_text())
    target = output / "missed-frames"
    (target / "frames").mkdir(parents=True, mode=0o700)
    frames, proposal_count, frames_with_vehicle = [], 0, 0
    by_source_time = {}
    for frame in original["frames"]:
        image_path = base_dataset / frame["image_path"]
        if sha256(image_path) != frame["image_sha256"]:
            raise ValueError(f"D05b source frame hash mismatch: {frame['sample_id']}")
        out_image = target / frame["image_path"]
        shutil.copyfile(image_path, out_image)
        out_image.chmod(0o600)
        image = cv2.imread(str(out_image))
        if image is None:
            raise ValueError(f"Cannot read D05b frame {frame['sample_id']}")
        vehicles = [{k: v for k, v in x.items() if k != "crop_path"} for x in frame.get("suggested_vehicles", [])]
        proposals = []
        if vehicles:
            frames_with_vehicle += 1
        for vehicle_index, vehicle in enumerate(vehicles):
            x1, y1, x2, y2 = vehicle["bbox"]
            vehicle_crop = image[y1:y2, x1:x2]
            for det in detector.detect(vehicle_crop, frame["media_seconds"]):
                dx1, dy1, dx2, dy2 = clip_box(det.box, vehicle_crop.shape)
                global_box = [x1 + dx1, y1 + dy1, x1 + dx2, y1 + dy2]
                proposals.append({"bbox": global_box, "score": float(det.score), "model": det.model,
                    "ground_truth": False, "vehicle_suggestion_index": vehicle_index})
                proposal_count += 1
        cloned = dict(frame)
        cloned["reviewed"] = False
        cloned["annotations"] = []
        cloned["suggested_vehicles"] = vehicles
        cloned["suggested_plates"] = proposals
        cloned["notes"] = "D05e: manually label every actual plate visible in this frame, including plates with no orange model proposal. Model proposals are not labels."
        frames.append(cloned)
        by_source_time[(frame["source_id"], round(float(frame["media_seconds"]), 3))] = cloned

    d05d_attempt_frames = d05d_zero_box_frames = d05d_boxes = d05d_vehicle_frames = 0
    source_by_path = {str(Path(s["path"]).resolve()): s for s in original["sources"]}
    for run_dir in runs:
        result = json.loads((run_dir / "result.json").read_text())
        video = Path(result["source_video"]["path"]).resolve()
        source = source_by_path.get(str(video))
        if source is None:
            raise ValueError(f"D05d video is not present in the D05b source manifest: {video}")
        timelines = {}
        with (run_dir / "sampled-detections.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line); timelines[round(float(row["media_seconds"]), 3)] = row
        attempts_by_time = {}
        observations_by_time = {}
        for session in result["sessions"]:
            for attempt in session["plate_attempt_log"]:
                attempts_by_time.setdefault(round(float(attempt["media_seconds"]), 3), []).append(attempt)
            for obs in session["plate_observations"]:
                observations_by_time.setdefault(round(float(obs["media_seconds"]), 3), []).append(obs)
        new_times = [t for t in sorted(attempts_by_time) if (source["source_id"], t) not in by_source_time]
        images = frame_index_by_time(video, float(result["config"]["sample_hz"]), new_times) if new_times else {}
        frame_index_by_key = {}
        for line in (run_dir / "sampled-detections.jsonl").read_text().splitlines():
            row = json.loads(line); frame_index_by_key[round(float(row["media_seconds"]), 3)] = int(row["frame_index"])
        for media_time, attempts in sorted(attempts_by_time.items()):
            key = (source["source_id"], media_time)
            if key in by_source_time:
                frame = by_source_time[key]
                if frame.get("d05d_attempt_frame"):
                    continue
                # Existing D05b frames are not expected to share the spaced D05d
                # plate attempts. If they do, merge proposals into the same image.
                image = cv2.imread(str(target / frame["image_path"]))
            else:
                image = images[media_time]
                frame_index = frame_index_by_key.get(media_time)
                if frame_index is None:
                    raise ValueError(f"Missing sampled timeline row at {video.name} {media_time}s")
                sample_id = f"{source['source_id']}-d05d-f{frame_index:06d}"
                relative = f"frames/{sample_id}.png"
                save_png(target / relative, image)
                tracks = timelines.get(media_time, {}).get("tracks", [])
                vehicles = [{"bbox": list(map(int, tr["box"])), "score": float(tr["score"]),
                    "label": tr["label"], "model": tr["model"], "ground_truth": False,
                    "track_id": tr["track_id"]} for tr in tracks]
                frame = {"sample_id": sample_id, "source_id": source["source_id"],
                    "media_seconds": float(media_time), "frame_index": frame_index, "image_path": relative,
                    "image_sha256": sha256(target / relative), "width": int(image.shape[1]),
                    "height": int(image.shape[0]), "scene_hash": image_hash(image),
                    "capture_group_id": source["capture_group_id"], "split": "unassigned", "reviewed": False,
                    "suggested_vehicles": vehicles, "suggested_plates": [], "annotations": [],
                    "notes": "D05d actual plate-detector attempt frame. Manually label every real plate, including zero-box frames."}
                frames.append(frame); by_source_time[key] = frame
            frame["d05d_attempt_frame"] = True
            frame["d05d_plate_attempts"] = [{"plate_boxes": int(a["plate_boxes"]), "phase": int(a["phase"])} for a in attempts]
            d05d_attempt_frames += 1
            d05d_zero_box_frames += any(int(a["plate_boxes"]) == 0 for a in attempts)
            d05d_vehicle_frames += bool(frame.get("suggested_vehicles"))
            for obs in observations_by_time.get(media_time, []):
                ox, oy = map(int, obs["vehicle_crop_origin"])
                x1, y1, x2, y2 = obs["box_in_vehicle_crop"]
                bbox = list(clip_box((ox + x1, oy + y1, ox + x2, oy + y2), image.shape))
                frame["suggested_plates"].append({"bbox": bbox, "score": float(obs["score"]),
                    "model": obs["model"], "ground_truth": False, "source": "D05d pipeline prediction"})
                d05d_boxes += 1
    manifest = dict(original)
    manifest["dataset_id"] = str(uuid.uuid4())
    manifest["label_origin"] = "manual_review_required"
    manifest["purpose"] = "D05e D05b labeler copy: manual frame-level plate boxes, including missed detector proposals; no OCR-based labels"
    manifest["frames"] = frames
    write_json(target / "manifest.template.json", manifest)
    export_blank_csv(target / "labels.template.csv", manifest)
    template = (ROOT / "edge-agent/offline_vision/labeling.html").read_text(encoding="utf-8")
    template = template.replace("<title>D05b · Gán nhãn thủ công</title>", "<title>D05e · D05b gán nhãn frame</title>")
    template = template.replace("<h1>D05b · Ảnh gốc và nhãn thủ công</h1>", "<h1>D05e · Frame bỏ sót — công cụ gán nhãn D05b</h1>")
    template = template.replace("Vẽ bbox trên ảnh gốc. Nội dung biển và khả năng đọc do người xem điền. Box nét đứt chỉ là gợi ý xe từ model. Không có OCR đề xuất trong biểu mẫu này. JSON tải xuống là nhãn riêng, ảnh gốc giữ nguyên.",
        "Vẽ bbox mọi biển thật nhìn thấy trên frame gốc, kể cả khi không có box cam. Box xanh nét đứt là gợi ý xe; box cam nét đứt là dự đoán YOLOX để đối chiếu, không phải ground truth. Không có OCR trong nhãn. Đánh dấu frame đã xem cả khi không có biển; JSON lưu riêng, ảnh gốc giữ nguyên.")
    embedded = json.dumps(browser_manifest(manifest), ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    page = template.replace("__MANIFEST_JSON__", embedded)
    (target / "label.html").write_text(page, encoding="utf-8")
    (target / "label.html").chmod(0o600)
    return {"dataset_id": manifest["dataset_id"], "frames": len(frames), "d05b_original_frames": len(original["frames"]),
            "d05d_attempt_frames": d05d_attempt_frames, "d05d_zero_box_attempt_frames": d05d_zero_box_frames,
            "d05d_plate_boxes": d05d_boxes, "d05d_attempt_frames_with_vehicle_tracks": d05d_vehicle_frames,
            "d05b_original_frames_with_vehicle_suggestions": frames_with_vehicle,
            "d05b_original_proposals": proposal_count,
            "frames_with_plate_proposals": sum(bool(x["suggested_plates"]) for x in frames),
            "plate_proposals_total": sum(len(x["suggested_plates"]) for x in frames),
            "frames_with_no_plate_proposal": sum(not x["suggested_plates"] for x in frames),
            "instructions": "User must manually draw all real plate boxes; an empty frame annotation is meaningful only after clicking reviewed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("data/offline-vision/runs/d05d-vast-54567374/camera-comparison"))
    parser.add_argument("--d05b-dataset", type=Path, default=Path("data/offline-vision/datasets/d05b-camera185"))
    parser.add_argument("--model-manifest", type=Path, default=Path("data/offline-vision/runs/d05d-vast-54567374/final/export/model.json"))
    parser.add_argument("--output", type=Path, default=Path("data/offline-vision/runs/d05e-review-20261007"))
    parser.add_argument("--threshold", type=float, default=.25)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing D05e output: {args.output}")
    cv2.setNumThreads(2)
    args.output.mkdir(parents=True, mode=0o700)
    runs = [args.runs / "video1-finetuned", args.runs / "video2-finetuned"]
    if any(not (p / "result.json").is_file() for p in runs):
        raise SystemExit("Both D05d fine-tuned result.json files are required")
    detector = YoloXPlateDetector(args.model_manifest, threshold=args.threshold)
    items, sources = build_crop_review(runs, args.output)
    base_dataset = (ROOT / args.d05b_dataset).resolve()
    frame_summary = build_missed_frame_label_set(base_dataset, args.output, detector, runs)
    summary = {"status": "awaiting_manual_review", "crop_review_items": len(items),
        "crop_counts_by_run": {name: sum(x["run_name"] == name for x in items) for name in sorted({x["run_name"] for x in items})},
        "confirmed_crop_labels": 0, "ocr_ground_truth": 0, "source_videos": sources,
        "missed_frame_review": frame_summary, "model": detector.metadata,
        "notes": ["Only full-frame labels can establish missed detections; crop-only review cannot measure recall.",
                  "OCR is deliberately not shown in either label form and has not been run on these review crops.",
                  "The 40 D05b frames are a diagnostic sample of two clips, not independent vehicles or representative accuracy."]}
    write_json(args.output / "summary.pending.json", summary)
    print(json.dumps({k: summary[k] for k in ("status", "crop_review_items", "crop_counts_by_run", "confirmed_crop_labels", "ocr_ground_truth", "missed_frame_review")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
