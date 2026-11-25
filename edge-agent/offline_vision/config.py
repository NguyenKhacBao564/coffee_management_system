import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str
    roi: list[list[float]]
    roi_status: str = "provisional_requires_operator_confirmation"
    sample_hz: float = 2.0
    vehicle_threshold: float = 0.35
    plate_threshold: float = 0.75
    tracking_gap_seconds: float = 3.0
    session_gap_seconds: float = 5.0
    exit_grace_seconds: float = 3.0
    match_iou: float = 0.12
    match_distance: float = 0.10
    min_entry_observations: int = 2
    plate_attempt_interval_seconds: float = 3.0
    max_plate_attempts: int = 12
    max_ocr_reads: int = 8
    max_saved_plate_crops: int = 4
    consistent_reads: int = 3
    consensus_ratio: float = 0.8
    min_plate_width: int = 24
    min_plate_height: int = 8
    ocr_layout: str = "auto"
    cpu_threads: int = 2
    max_sessions: int = 500
    ocr_phase_seconds: tuple[float, float] = (8.0, 20.0)
    max_candidates_per_phase: int = 4
    repeat_crop_seconds: float = 6.0
    duplicate_hash_distance: int = 2
    min_plate_sharpness: float = 10.0
    plate_phase_backoff: float = 1.0

    def validate(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.camera_id):
            raise ValueError("camera_id must contain only letters, digits, underscore or hyphen")
        points = np.asarray(self.roi, dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 2 or not 3 <= len(points) <= 20:
            raise ValueError("ROI must have 3–20 normalized xy vertices")
        if not np.isfinite(points).all() or (points < 0).any() or (points > 1).any():
            raise ValueError("ROI coordinates must be finite and within [0,1]")
        if not cv2.isContourConvex(points) or cv2.contourArea(points) < 0.0001:
            raise ValueError("First offline version requires a convex, non-degenerate ROI")
        for name in ("sample_hz", "tracking_gap_seconds", "session_gap_seconds", "exit_grace_seconds", "plate_attempt_interval_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if self.sample_hz > 10 or self.session_gap_seconds < self.tracking_gap_seconds:
            raise ValueError("sample_hz <= 10; session gap must cover tracking gap")
        for name in ("vehicle_threshold", "plate_threshold", "match_iou", "match_distance", "consensus_ratio"):
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0,1]")
        for name in ("min_entry_observations", "max_plate_attempts", "max_ocr_reads", "max_saved_plate_crops", "consistent_reads", "min_plate_width", "min_plate_height", "cpu_threads", "max_sessions"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 10000:
                raise ValueError(f"{name} must be a positive bounded integer")
        if self.consistent_reads > self.max_ocr_reads or self.cpu_threads > 8 or self.max_saved_plate_crops > 100:
            raise ValueError("Invalid read/crop/thread budget")
        if self.ocr_layout not in {"auto", "single-line", "two-line"}:
            raise ValueError("Unsupported OCR layout")
        if len(self.ocr_phase_seconds) != 2 or not all(math.isfinite(x) and x > 0 for x in self.ocr_phase_seconds) or self.ocr_phase_seconds[0] >= self.ocr_phase_seconds[1]:
            raise ValueError("OCR phase boundaries must be two increasing positive media ages")
        if type(self.max_candidates_per_phase) is not int or not 1 <= self.max_candidates_per_phase <= 12:
            raise ValueError("Candidate pool must have 1–12 crops per phase")
        if not math.isfinite(self.repeat_crop_seconds) or self.repeat_crop_seconds <= 0 or type(self.duplicate_hash_distance) is not int or not 0 <= self.duplicate_hash_distance <= 16:
            raise ValueError("Invalid crop repetition policy")
        if not math.isfinite(self.min_plate_sharpness) or self.min_plate_sharpness < 0 or not math.isfinite(self.plate_phase_backoff) or not 0 <= self.plate_phase_backoff <= 4:
            raise ValueError("Invalid quality/backoff policy")
        return self

    def snapshot(self):
        return asdict(self)


def load_config(path: Path) -> CameraConfig:
    return CameraConfig(**json.loads(path.read_text(encoding="utf-8"))).validate()
