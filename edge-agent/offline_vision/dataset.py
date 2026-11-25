"""Small local diagnostic dataset. Model suggestions are never manual labels."""
import csv
import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

import cv2

from .export import write_json
from .sampling import image_hash, hash_distance
from .selection import vehicle_crop, frame_quality
from .video import VideoReader


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def browser_manifest(manifest):
    """JSON/browser boundary: uint64 hashes must never pass through JS Number."""
    result = json.loads(json.dumps(manifest))
    for frame in result['frames']:
        value = frame['scene_hash']
        if type(value) not in {int, str} or str(int(value)) != str(value) or not 0 <= int(value) < 2**64:
            raise ValueError('scene_hash must be a canonical uint64 decimal value')
        frame['scene_hash'] = str(value)
    return result


def save_png(path, image):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not cv2.imwrite(str(path), image): raise ValueError("Cannot write source-resolution PNG")
    path.chmod(0o600)


def select_frames(candidates, count):
    if len(candidates) < count: raise ValueError("Not enough candidate media frames for requested count")
    # Temporal strata guarantee clip coverage; appearance, vehicle size and sharpness rank within each stratum.
    selected = []
    for bucket in range(count):
        options = candidates[bucket * len(candidates) // count:(bucket + 1) * len(candidates) // count]
        def rank(candidate):
            novelty = min((hash_distance(candidate["scene_hash"], x["scene_hash"]) for x in selected), default=32)
            return novelty + (5 if candidate["vehicles"] else 0) + math.log1p(candidate["quality"]) * .2
        selected.append(max(options, key=lambda c: (rank(c), -c["media_seconds"])))
    return selected


def prepare_dataset(videos, output, detector, *, count=40, candidate_interval=3):
    if not 30 <= count <= 50 or not 1 <= candidate_interval <= 30 or not 1 <= len(videos) <= 5:
        raise ValueError("Select 30–50 frames, 1–5 local videos, candidate interval 1–30 seconds")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    sources, selections = [], {}
    for index, video in enumerate(videos):
        reader = VideoReader(video, 1 / candidate_interval)
        candidates = []
        for frame in reader:
            detections = detector.detect(frame.image, frame.seconds)
            candidates.append({"frame_index": frame.index, "media_seconds": frame.seconds,
                "scene_hash": image_hash(frame.image[frame.image.shape[0] // 3:]),
                "quality": max((frame_quality(frame.image, d.box) for d in detections), default=0),
                "vehicles": [{"bbox": list(map(int, d.box)), "score": d.score, "label": d.label, "model": d.model} for d in detections]})
            if len(candidates) > 2000: raise ValueError("Candidate bound exceeded; split long media first")
        source_id = f"v{index + 1:03d}"
        quota = count // len(videos) + (index < count % len(videos))
        picks = select_frames(candidates, quota)
        selections[source_id] = {x["frame_index"]: x for x in picks}
        sources.append({"source_id": source_id, "path": str(video.resolve()), "sha256": sha256(video),
            "bytes": video.stat().st_size, "metadata": reader.metadata, "candidate_count": len(candidates),
            "capture_group_id": f"capture-{source_id}", "candidate_interval_seconds": candidate_interval})
    frames = []
    for source, video in zip(sources, videos):
        for frame in VideoReader(video, 1 / candidate_interval):
            selection = selections[source["source_id"]].get(frame.index)
            if selection is None: continue
            sample_id = f"{source['source_id']}-f{frame.index:06d}"
            relative = f"frames/{sample_id}.png"
            save_png(output / relative, frame.image)
            suggestions = []
            for index, vehicle in enumerate(selection["vehicles"]):
                crop, origin = vehicle_crop(frame.image, vehicle["bbox"])
                path = f"suggestions/{sample_id}-vehicle-{index + 1}.png"
                save_png(output / path, crop)
                suggestions.append({**vehicle, "crop_path": path, "crop_origin": list(origin),
                    "crop_pixels": [crop.shape[1], crop.shape[0]], "ground_truth": False})
            frames.append({"sample_id": sample_id, "source_id": source["source_id"], "media_seconds": frame.seconds,
                "frame_index": frame.index, "image_path": relative, "image_sha256": sha256(output / relative),
                "width": frame.image.shape[1], "height": frame.image.shape[0], "scene_hash": selection["scene_hash"],
                "capture_group_id": source["capture_group_id"], "split": "unassigned", "reviewed": False,
                "suggested_vehicles": suggestions, "annotations": [], "notes": ""})
        if sha256(video) != source["sha256"]: raise ValueError("Source video changed during extraction")
    manifest = {"schema_version": 1, "dataset_id": str(uuid4()), "label_origin": "manual_review_required",
        "purpose": "D05b diagnostic set; not representative system accuracy or a training split",
        "selection": {"count": len(frames), "method": "temporal strata + dHash novelty + vehicle crop sharpness",
            "model": detector.metadata, "resize_policy": "decoded original BGR pixels saved losslessly as PNG; only feature/detector input resized"},
        "sources": sources, "frames": frames, "duplicate_reviews": []}
    write_json(output / "manifest.template.json", manifest)
    export_blank_csv(output / "labels.template.csv", manifest)
    template = (Path(__file__).parent / "labeling.html").read_text()
    embedded = json.dumps(browser_manifest(manifest), ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    (output / "label.html").write_text(template.replace("__MANIFEST_JSON__", embedded)); (output / "label.html").chmod(0o600)
    write_json(output / "duplicate-audit.initial.json", duplicate_audit(manifest, training=False))
    return manifest


CSV_FIELDS = ["sample_id", "source_id", "media_seconds", "image_path", "reviewed", "annotation_id", "kind", "x1", "y1", "x2", "y2",
              "readability", "plate_text", "layout", "split_y", "vehicle_group_id", "capture_group_id", "split", "notes"]


def export_blank_csv(path, manifest):
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS); writer.writeheader()
        for frame in manifest["frames"]:
            writer.writerow({**{k: frame[k] for k in ["sample_id", "source_id", "media_seconds", "image_path", "capture_group_id", "split"]},
                "reviewed": "false", "annotation_id": "", "kind": "plate", "readability": "pending", "layout": "pending"})
    path.chmod(0o600)


def import_csv(dataset, csv_path):
    manifest = json.loads((dataset / "manifest.template.json").read_text())
    frames = {f["sample_id"]: f for f in manifest["frames"]}
    seen = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["sample_id"] not in frames: raise ValueError("CSV sample ID does not belong to dataset")
            frame = frames[row["sample_id"]]
            frame["reviewed"] = row["reviewed"].strip().lower() == "true"
            frame["capture_group_id"], frame["split"] = row["capture_group_id"], row["split"]
            if not row["x1"].strip(): continue
            annotation_id = row["annotation_id"] or f"{frame['sample_id']}-a{len(frame['annotations']) + 1}"
            if annotation_id in seen: raise ValueError("Duplicate annotation ID in CSV")
            seen.add(annotation_id)
            frame["annotations"].append({"annotation_id": annotation_id, "kind": row["kind"],
                "bbox": [int(row[k]) for k in ["x1", "y1", "x2", "y2"]], "readability": row["readability"],
                "plate_text": row["plate_text"], "layout": row["layout"], "split_y": int(row["split_y"]) if row["split_y"].strip() else None,
                "vehicle_group_id": row["vehicle_group_id"], "label_origin": "manual_review", "notes": row["notes"]})
    manifest["label_origin"] = "manual_review"
    validate_labels(manifest, dataset)
    return manifest


def safe_image(dataset, relative):
    root = dataset.resolve(); path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise ValueError("Image path must remain within the dataset")
    return path


def validate_labels(manifest, dataset):
    original = json.loads((dataset / "manifest.template.json").read_text())
    if manifest["dataset_id"] != original["dataset_id"]: raise ValueError("Labels belong to a different dataset")
    if manifest["sources"] != original["sources"]: raise ValueError("Source video provenance must remain unchanged")
    if manifest["label_origin"] not in {"manual_review", "manual_review_required"}: raise ValueError("Unsupported label origin")
    expected = {f["sample_id"]: f for f in original["frames"]}
    if len(manifest["frames"]) != len(expected) or {f["sample_id"] for f in manifest["frames"]} != set(expected):
        raise ValueError("Label file must preserve the selected frame inventory exactly")
    seen = set(); counts = {"frames": len(expected), "reviewed_frames": 0, "readable_plates": 0, "uncertain_plates": 0, "unreadable_plates": 0, "pending_plates": 0}
    for frame in manifest["frames"]:
        base = expected[frame["sample_id"]]
        for k in ["source_id", "media_seconds", "frame_index", "image_path", "image_sha256", "width", "height", "scene_hash"]:
            same = frame[k] == base[k]
            if k == 'scene_hash':
                same = type(frame[k]) in {int, str} and str(frame[k]) == str(base[k])
            if not same: raise ValueError(f"Immutable source metadata changed: {k}")
        if sha256(safe_image(dataset, frame["image_path"])) != frame["image_sha256"]:
            raise ValueError("Source PNG differs from manifest")
        if type(frame["reviewed"]) is not bool: raise ValueError("reviewed must be boolean")
        counts["reviewed_frames"] += frame["reviewed"]
        for annotation in frame["annotations"]:
            key = annotation["annotation_id"]
            if not isinstance(key, str) or not key or key in seen: raise ValueError("Annotation IDs must be unique nonempty strings")
            seen.add(key)
            if annotation.get("label_origin") != "manual_review": raise ValueError("Annotations must be explicitly manual, not model suggestions")
            if annotation["kind"] not in {"plate", "vehicle", "hard_negative"}: raise ValueError("Invalid annotation kind")
            box = annotation["bbox"]
            if len(box) != 4 or any(type(x) is not int for x in box) or not (0 <= box[0] < box[2] <= frame["width"] and 0 <= box[1] < box[3] <= frame["height"]):
                raise ValueError("BBox must use valid original-frame integer pixel xyxy coordinates")
            if annotation["kind"] != "plate": continue
            state = annotation["readability"]
            if state not in {"pending", "readable", "uncertain", "unreadable"}: raise ValueError("Invalid plate readability")
            counts[{"pending": "pending_plates", "readable": "readable_plates", "uncertain": "uncertain_plates", "unreadable": "unreadable_plates"}[state]] += 1
            if annotation.get("layout") == "two-line" and state == 'readable':
                y = annotation.get("split_y")
                if type(y) is not int or not box[1] < y < box[3]: raise ValueError("Two-line plate requires manually placed split_y inside its bbox")
            if state == "readable":
                if not frame["reviewed"] or manifest["label_origin"] != "manual_review" or not annotation.get("plate_text", "").strip():
                    raise ValueError("Readable ground truth requires a reviewed frame and manually entered text")
                if annotation.get("layout") not in {"single-line", "two-line"}: raise ValueError("Readable plate requires actual manual layout")
    return counts


def duplicate_audit(manifest, *, training=True):
    frames = manifest["frames"]; pairs, issues = [], []
    groups = {}; readable = 0
    for f in frames:
        split = f["split"]
        if training and (not f["reviewed"] or split not in {"train", "val", "test"}): issues.append({"sample_id": f["sample_id"], "reason": "review_or_split_missing"})
        if not f.get("capture_group_id"): issues.append({"sample_id": f["sample_id"], "reason": "capture_group_missing"})
        # Keep each input clip together even if editable capture labels are inconsistent.
        group_ids = ["source:" + f["source_id"], "capture:" + f.get("capture_group_id", "")]
        for a in f["annotations"]:
            if a["kind"] in {"plate", "vehicle"}:
                if not a.get("vehicle_group_id") and training: issues.append({"sample_id": f["sample_id"], "reason": "manual_vehicle_group_missing"})
                if a.get("vehicle_group_id"): group_ids.append("vehicle:" + a["vehicle_group_id"])
                readable += a.get("readability") == "readable"
        for group in group_ids: groups.setdefault(group, set()).add(split)
    for group, splits in groups.items():
        assigned = splits - {"unassigned"}
        if len(assigned) > 1: issues.append({"group_id": group, "reason": "group_crosses_splits", "splits": sorted(assigned)})
    acknowledgments = {tuple(sorted(r["sample_ids"])): r.get("resolution") for r in manifest.get("duplicate_reviews", [])}
    for i, a in enumerate(frames):
        for b in frames[i + 1:]:
            exact = a["image_sha256"] == b["image_sha256"]
            distance = hash_distance(a["scene_hash"], b["scene_hash"])
            if exact or distance <= 4:
                ids = sorted([a["sample_id"], b["sample_id"]]); cross = a["split"] != b["split"] and "unassigned" not in {a["split"], b["split"]}
                pairs.append({"sample_ids": ids, "kind": "exact_png" if exact else "scene_dhash_suspect", "distance": distance,
                    "cross_split": cross, "resolution": acknowledgments.get(tuple(ids))})
                if cross and (exact or acknowledgments.get(tuple(ids)) != "reviewed_different_observations"):
                    issues.append({"sample_ids": ids, "reason": "cross_split_duplicate_or_unreviewed_similarity"})
    return {"training_ready": training and not issues, "frames": len(frames), "readable_annotations": readable,
        "groups": {k: sorted(v) for k, v in groups.items()}, "duplicate_pairs": pairs, "issues": issues,
        "notes": "Scene dHash includes background and can flag distinct vehicles; review suspects manually. Same vehicle/capture stays in one split; never random-split neighboring frames."}
