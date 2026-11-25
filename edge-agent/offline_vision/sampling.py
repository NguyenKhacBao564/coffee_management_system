"""Bounded offline crop selection. OCR is deferred until all session phases are observed."""
from pathlib import Path
import math

import cv2
import numpy as np

from .consensus import decide, normalize
from .export import save_jpeg


def image_hash(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    return sum(int(value) << index for index, value in enumerate((small[:, 1:] > small[:, :-1]).flat))


def hash_distance(a, b):
    return (int(a) ^ int(b)).bit_count()


def crop_quality(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return {"sharpness": sharpness, "pixels": int(gray.size),
            "rank_score": math.log1p(sharpness) * math.sqrt(gray.size)}


def discard_candidate(candidate):
    """Only temporary, uncommitted candidate files; never persisted evidence."""
    Path(candidate['path']).unlink(missing_ok=True)
    for path in candidate.get('context_files', {}).values():
        Path(path).unlink(missing_ok=True)


def select_capture_candidates(pools, policy, *, for_stop=False):
    """Plate quality is a proposal, never proof of text correctness/front/rear."""
    if policy['max_evidence_frames'] <= 0:
        return []
    items = [c for phase in pools for c in phase if c.get('context_files')]
    if for_stop:
        items = [c for c in items if
                 c['observation']['crop_pixels'][0] >= policy['success_min_plate_width'] and
                 c['observation']['crop_pixels'][1] >= policy['success_min_plate_height'] and
                 c['observation']['quality']['sharpness'] >= policy['success_min_sharpness'] and
                 c['observation']['score'] >= policy['success_min_plate_score'] and
                 c['context']['bbox_complete']]
    selected = []
    for candidate in sorted(items, key=lambda c: (-c['quality'], c['observation']['media_seconds'])):
        if any(abs(candidate['observation']['media_seconds'] - c['observation']['media_seconds']) <
               policy['evidence_spacing_seconds'] for c in selected):
            continue
        selected.append(candidate)
        if len(selected) >= policy['max_evidence_frames']:
            break
    return sorted(selected, key=lambda c: c['observation']['media_seconds'])


class CandidatePool:
    def __init__(self, folder: Path, config):
        self.folder, self.config, self.pools, self.serial = folder, config, {}, 0

    def phase(self, session, timestamp):
        return sum(timestamp - session.started >= boundary for boundary in self.config.ocr_phase_seconds)

    def should_attempt(self, session, timestamp):
        phase = self.phase(session, timestamp)
        cumulative_limit = [int(self.config.max_plate_attempts * .25),
                            int(self.config.max_plate_attempts * .5), self.config.max_plate_attempts][phase]
        # Spacing grows within the late phase; later frames retain detector opportunities.
        multiplier = 1 + (min(session.attempt_phase_counts[phase], 3) * self.config.plate_phase_backoff if phase == 2 else 0)
        return (session.plate_attempts < cumulative_limit and
                timestamp - session.last_plate_attempt >= self.config.plate_attempt_interval_seconds * multiplier)

    def offer(self, session, image, observation):
        cfg = self.config
        h, w = image.shape[:2]
        observation["quality"] = crop_quality(image) if image.size else None
        if w < cfg.min_plate_width or h < cfg.min_plate_height:
            observation["skipped_reason"] = "crop_too_small"; return
        if not .9 <= w / h <= 7:
            observation["skipped_reason"] = "implausible_crop_geometry"; return
        if observation["quality"]["sharpness"] < cfg.min_plate_sharpness:
            observation["skipped_reason"] = "low_crop_sharpness"; return
        phase = self.phase(session, observation["media_seconds"])
        observation["phase"] = phase
        pool = self.pools.setdefault(session.session_id, [[], [], []])[phase]
        digest = image_hash(image)
        candidate = {"observation": observation, "hash": digest, "quality": observation["quality"]["rank_score"]}
        similar = [c for c in pool if hash_distance(c["hash"], digest) <= cfg.duplicate_hash_distance
                   and abs(c["observation"]["media_seconds"] - observation["media_seconds"]) < cfg.repeat_crop_seconds]
        if similar:
            best = max(similar, key=lambda c: c["quality"])
            if candidate["quality"] <= best["quality"] * 1.10:
                observation["skipped_reason"] = "near_duplicate_crop"; return
            pool.remove(best); discard_candidate(best)
            best["observation"]["skipped_reason"] = "replaced_by_better_crop"
        elif len(pool) >= cfg.max_candidates_per_phase:
            worst = min(pool, key=lambda c: c["quality"])
            if candidate["quality"] <= worst["quality"]:
                observation["skipped_reason"] = "phase_quality_pool_full"; return
            pool.remove(worst); discard_candidate(worst)
            worst["observation"]["skipped_reason"] = "replaced_by_better_crop"
        self.serial += 1
        path = self.folder / f"candidate-{self.serial}.png"
        if not cv2.imwrite(str(path), image): raise ValueError("Cannot save lossless candidate crop")
        path.chmod(0o600)
        candidate["path"] = str(path); pool.append(candidate)
        observation["selection"] = "queued_lossless_for_offline_quality_selection"

    def recognize(self, session, ocr, stats, output):
        pools = self.pools.get(session.session_id, [[], [], []])
        queues = [sorted(p, key=lambda c: (-c["quality"], c["observation"]["media_seconds"])) for p in pools]
        # Prefer late/middle evidence, but visit all populated phases. Quotas are neural calls.
        budget = self.config.max_ocr_reads
        quotas = [int(budget * .25), int(budget * .25), budget - 2 * int(budget * .25)]
        used = [0, 0, 0]; selected = []
        for reserved in (True, False):
            progress = True
            while progress and not session.ocr_complete:
                progress = False
                for phase in (2, 1, 0):
                    for candidate in list(queues[phase]):
                        observation = candidate["observation"]
                        if any(abs(observation["media_seconds"] - c["observation"]["media_seconds"]) < self.config.plate_attempt_interval_seconds for c in selected):
                            queues[phase].remove(candidate); observation["skipped_reason"] = "selected_media_times_too_close"; continue
                        if any(hash_distance(candidate["hash"], c["hash"]) <= self.config.duplicate_hash_distance
                               and abs(observation["media_seconds"] - c["observation"]["media_seconds"]) < self.config.repeat_crop_seconds for c in selected):
                            queues[phase].remove(candidate); observation["skipped_reason"] = "near_duplicate_selected_crop"; continue
                        image = cv2.imread(candidate["path"])
                        cost = ocr.cost(image)
                        if session.ocr_calls + cost > budget or (reserved and used[phase] + cost > quotas[phase]):
                            continue
                        queues[phase].remove(candidate); selected.append(candidate); progress = True
                        saved = session.evidence["plate_crops"]
                        if len(saved) < self.config.max_saved_plate_crops:
                            relative = f"evidence/{session.session_id}/plate-{len(saved)+1:02d}.jpg"
                            save_jpeg(output / relative, image)
                            saved.append({"path": relative, "media_seconds": observation["media_seconds"], "box_in_vehicle_crop": observation["box_in_vehicle_crop"], "phase": phase})
                            observation["evidence_path"] = relative
                        read = ocr.read(image)
                        if read.inference_calls != cost: raise ValueError("OCR adapter call accounting changed unexpectedly")
                        session.ocr_calls += cost; used[phase] += cost
                        stats["ocr_model_calls"] += cost; stats["ocr_observation_reads"] += 1
                        observation["used_for_ocr"] = True
                        session.reads.append({"read_index": len(session.reads), "media_seconds": observation["media_seconds"],
                            "raw": read.raw, "raw_lines": read.raw_lines, "normalized": normalize(read.raw), "score": read.score,
                            "model": read.model, "strategy": read.strategy, "inference_calls": cost, "phase": phase,
                            "plate_observation_index": session.plate_observations.index(observation), "evidence_path": observation.get("evidence_path")})
                        session.proposed_plate, session.decision, session.candidates = decide(session.reads, self.config.consistent_reads, self.config.consensus_ratio)
                        session.ocr_complete = session.proposed_plate is not None
                        break
                    if session.ocr_complete: break
        # Keep a useful real plate candidate even if its OCR cost exceeds the remaining budget.
        if not session.evidence["plate_crops"] and any(pools):
            best = max((c for p in pools for c in p), key=lambda c: c["quality"])
            relative = f"evidence/{session.session_id}/plate-01.jpg"
            save_jpeg(output / relative, cv2.imread(best["path"]))
            session.evidence["plate_crops"].append({"path": relative, "media_seconds": best["observation"]["media_seconds"], "box_in_vehicle_crop": best["observation"]["box_in_vehicle_crop"], "not_used_for_ocr": True})
