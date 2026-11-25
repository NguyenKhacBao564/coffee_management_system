"""Paired OCR benchmark on manually labeled native-pixel crops; no label guessing."""
import csv
import json
from pathlib import Path
import time

import cv2

from .consensus import normalize
from .dataset import safe_image, save_png, validate_labels
from .export import write_json
from .geometry import clip_box, iou
from .ocr import PlateOCR
from .recognizer import PaddleTinyRecognizer

VARIANTS = ("original", "upscale2_pad", "clahe")


def preprocess(image, variant):
    if variant == "original": return image.copy()
    if variant == "upscale2_pad":
        result = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        return cv2.copyMakeBorder(result, 4, 4, 6, 6, cv2.BORDER_REPLICATE)
    if variant == "clahe":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2, tileGridSize=(4, 4)).apply(gray)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    raise ValueError("Unsupported preprocessing variant")


def manual_lines(image, annotation):
    if annotation["layout"] == "single-line": return [image]
    if annotation["layout"] != "two-line": raise ValueError("Manual layout required; do not infer from aspect ratio or expected text")
    split = annotation["split_y"] - annotation["bbox"][1]
    if not 0 < split < image.shape[0]: raise ValueError("Manual split must be inside source crop")
    return [image[:split], image[split:]]


def _match_frame_plates(annotations, proposals, threshold):
    pairs = []
    for ai, annotation in enumerate(annotations):
        for pi, proposal in enumerate(proposals):
            score = iou(tuple(annotation["bbox"]), tuple(proposal["bbox"]))
            if score >= threshold:
                pairs.append((score, ai, pi))
    used_a, used_p, matched = set(), set(), {}
    for score, ai, pi in sorted(pairs, reverse=True):
        if ai in used_a or pi in used_p:
            continue
        used_a.add(ai); used_p.add(pi)
        matched[ai] = (proposals[pi], score)
    return matched, used_p


def run_benchmark(dataset, labels_path, output, model_dir, recognizer_dir, *, recognizers=None,
                  detector_match_iou=.5):
    labels = json.loads(labels_path.read_text())
    counts = validate_labels(labels, dataset)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    eligible, detection_rows = [], []
    for frame in labels["frames"]:
        if not frame["reviewed"]:
            continue
        manual = [a for a in frame["annotations"] if a["kind"] == "plate"]
        proposals = frame.get("suggested_plates", [])
        matches, used_proposals = _match_frame_plates(manual, proposals, detector_match_iou)
        for i, annotation in enumerate(manual):
            proposal, match_iou = matches.get(i, (None, None))
            detection_rows.append({"sample_id": frame["sample_id"], "source_id": frame["source_id"],
                "media_seconds": frame["media_seconds"], "annotation_id": annotation["annotation_id"],
                "manual_bbox": annotation["bbox"], "manual_readability": annotation["readability"],
                "manual_text": annotation["plate_text"] if annotation["readability"] == "readable" else "",
                "detector_bbox": proposal["bbox"] if proposal else None,
                "detector_score": proposal.get("score") if proposal else None,
                "detector_match_iou": match_iou, "detector_matched": proposal is not None})
            if (annotation["readability"] in {"readable", "uncertain", "unreadable"}
                and annotation["layout"] in {"single-line", "two-line"}
                and (annotation['layout'] != 'two-line' or (type(annotation.get('split_y')) is int
                     and annotation['bbox'][1] < annotation['split_y'] < annotation['bbox'][3]))):
                eligible.append((frame, annotation, proposal, match_iou))
        for i, proposal in enumerate(proposals):
            if i not in used_proposals:
                detection_rows.append({"sample_id": frame["sample_id"], "source_id": frame["source_id"],
                    "media_seconds": frame["media_seconds"], "annotation_id": "",
                    "manual_bbox": None, "manual_readability": "",
                    "manual_text": "", "detector_bbox": proposal["bbox"],
                    "detector_score": proposal.get("score"), "detector_match_iou": None,
                    "detector_matched": False, "proposal_unmatched": True})
    detection_totals = {"reviewed_frames": sum(f["reviewed"] for f in labels["frames"]),
        "manual_plate_boxes": sum(r.get("annotation_id") != "" for r in detection_rows),
        "detector_matched_boxes": sum(bool(r.get("detector_matched")) for r in detection_rows if r.get("annotation_id")),
        "manual_boxes_without_detector_match": sum(not r.get("detector_matched") for r in detection_rows if r.get("annotation_id")),
        "unmatched_detector_proposals": sum(bool(r.get("proposal_unmatched")) for r in detection_rows),
        "match_iou_threshold": detector_match_iou,
        "interpretation": "Only reviewed full frames contribute. Annotations and proposals must be checked for completeness; this is a two-video diagnostic set, not general detector accuracy."}
    if not eligible:
        with (output / "predictions.pending.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream); writer.writerow(["sample_id", "media_seconds", "image_path", "manual_bbox", "manual_plate_text", "manual_layout", "manual_readability", "raw_prediction", "full_plate_correct"])
            for f in labels["frames"]: writer.writerow([f["sample_id"], f["media_seconds"], f["image_path"], "", "", "", "pending", "", ""])
        (output / "predictions.pending.csv").chmod(0o600)
        summary = {"dataset_id": labels["dataset_id"], "dataset_purpose": labels.get("purpose"), "status": "awaiting_manual_bbox_layout_and_transcription", "manual_counts": counts,
            "detector_assessment": detection_totals, "full_plate_exact_match_rate": None, "metrics": [], "predictions": [], "detection_rows": detection_rows,
            "reason": "No manually reviewed plate with actual layout; no OCR output is promoted to ground truth"}
        write_json(output / "summary.json", summary)
        with (output / "detection-matches.pending.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            keys = ["sample_id", "source_id", "media_seconds", "annotation_id", "manual_bbox", "manual_readability", "manual_text", "detector_bbox", "detector_score", "detector_match_iou", "detector_matched", "proposal_unmatched"]
            writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader(); writer.writerows(detection_rows)
        (output / "detection-matches.pending.csv").chmod(0o600)
        return summary
    if recognizers is None:
        crnn = PlateOCR(model_dir, "single-line"); paddle = PaddleTinyRecognizer(recognizer_dir)
        recognizers = {"crnn_baseline": (crnn._line, crnn.metadata), "paddle_tiny": (paddle.line, paddle.metadata)}
    predictions, metrics, crop_id = [], [], 0
    for frame, annotation, proposal, match_iou in eligible:
        original = cv2.imread(str(safe_image(dataset, frame["image_path"])))
        gt_box = annotation["bbox"]
        crops = [("manual", original[gt_box[1]:gt_box[3], gt_box[0]:gt_box[2]], gt_box, None)]
        if proposal is not None:
            det_box = clip_box(tuple(proposal["bbox"]), original.shape)
            det_crop = original[det_box[1]:det_box[3], det_box[0]:det_box[2]]
            if det_crop.size:
                crops.append(("detector", det_crop, list(det_box), match_iou))
        for crop_source, crop, crop_box, match_score in crops:
            crop_id += 1
            crop_path = f"crops/crop-{crop_id:04d}-{crop_source}.png"
            save_png(output / crop_path, crop)
            crop_annotation = dict(annotation)
            if crop_source == "detector" and annotation["layout"] == "two-line":
                # Both crops use the SAME native frame coordinates. Moving the
                # split by bbox proportions can cut through characters.
                split_y = annotation['split_y']
                if not crop_box[1] < split_y < crop_box[3]:
                    continue  # detector crop excludes a line; no fabricated separator
                crop_annotation["bbox"] = crop_box
                crop_annotation["split_y"] = split_y
            for name, (infer, metadata) in recognizers.items():
                for variant in VARIANTS:
                    parts = [preprocess(line, variant) for line in manual_lines(crop, crop_annotation)]
                    began = time.perf_counter(); reads = [infer(line) for line in parts]
                    raw = "\n".join(text for text, _ in reads)
                    expected = annotation["plate_text"] if annotation["readability"] == "readable" else None
                    predictions.append({"sample_id": frame["sample_id"], "source_id": frame["source_id"], "annotation_id": annotation["annotation_id"],
                        "media_seconds": frame["media_seconds"], "crop_source": crop_source, "crop_path": crop_path,
                        "source_crop_pixels": [crop.shape[1], crop.shape[0]], "detector_bbox": crop_box if crop_source == "detector" else None,
                        "detector_match_iou": match_score, "model": name, "model_metadata": metadata, "variant": variant, "layout": annotation["layout"],
                        "raw": raw, "raw_lines": [x[0] for x in reads], "line_scores": [x[1] for x in reads], "normalized": normalize(raw),
                        "manual_expected": expected, "full_plate_correct": normalize(raw) == normalize(expected) if expected is not None else None,
                        "strict_raw_correct": raw == expected if expected is not None else None,
                        "wall_seconds": time.perf_counter() - began})
    for name in recognizers:
        for variant in VARIANTS:
            for crop_source in ("manual", "detector"):
                group = [p for p in predictions if p["model"] == name and p["variant"] == variant and p["crop_source"] == crop_source]
                labeled = [p for p in group if p["full_plate_correct"] is not None]
                metrics.append({"model": name, "variant": variant, "crop_source": crop_source,
                    "crops_inferred": len(group), "readable_manual_denominator": len(labeled),
                    "fully_correct_plates": sum(p["full_plate_correct"] for p in labeled),
                    "full_plate_exact_match_rate": sum(p["full_plate_correct"] for p in labeled) / len(labeled) if labeled else None,
                    "strict_raw_exact_match_rate": sum(p["strict_raw_correct"] for p in labeled) / len(labeled) if labeled else None})
    summary = {"dataset_id": labels["dataset_id"], "dataset_purpose": labels.get("purpose"), "status": "scored_manual_crops" if counts["readable_plates"] else "predictions_without_readable_ground_truth",
        "manual_counts": counts, "detector_assessment": detection_totals, "detection_rows": detection_rows,
        "metrics": metrics, "predictions": predictions,
        "preprocessing": {"variants": list(VARIANTS), "variant_order": "variant transforms apply before each recognizer's own preprocessing",
            "crnn_baseline": "split lines by manual layout; BGR to grayscale; OpenCV blob scale 1/127.5, mean 127.5; force each line to 100x32, aspect ratio not preserved",
            "paddle_tiny": "split lines by manual layout; BGR; preserve aspect at height48; width max(320,ceil(48*w/h)) capped3200; normalize (pixel/255-0.5)/0.5 and pad right with zero in normalized space"},
        "policy": "One-to-one greedy bbox matching within reviewed frame at IoU threshold; OCR paired only for matched detector boxes. Exact whole plate after uppercase/whitespace/dot/hyphen display normalization only; no character correction. Scores remain per recognizer. These crops do not represent system/vehicle accuracy."}
    write_json(output / "summary.json", summary)
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        keys = ["sample_id", "annotation_id", "media_seconds", "crop_source", "crop_path", "source_crop_pixels", "detector_bbox", "detector_match_iou", "model", "variant", "layout", "raw", "normalized", "manual_expected", "full_plate_correct", "strict_raw_correct"]
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
        for p in predictions: writer.writerow({k: p[k] for k in keys})
    (output / "predictions.csv").chmod(0o600)
    with (output / "detection-matches.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        keys = ["sample_id", "source_id", "media_seconds", "annotation_id", "manual_bbox", "manual_readability", "manual_text", "detector_bbox", "detector_score", "detector_match_iou", "detector_matched", "proposal_unmatched"]
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader(); writer.writerows(detection_rows)
    (output / "detection-matches.csv").chmod(0o600)
    return summary
