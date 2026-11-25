from dataclasses import dataclass, field

from .config import CameraConfig
from .geometry import distance, inside_roi, iou
from .tracking import Track


@dataclass
class Session:
    session_id: str
    track_ids: list[str]
    started: float
    last_seen: float
    last_inside: float
    box: tuple
    ended: float | None = None
    end_reason: str | None = None
    outside_since: float | None = None
    observations: int = 0
    plate_attempts: int = 0
    ocr_calls: int = 0
    last_plate_attempt: float = -1e9
    best_quality: float = -1
    evidence: dict = field(default_factory=lambda: {"plate_crops":[]})
    plate_observations: list[dict] = field(default_factory=list)
    reads: list[dict] = field(default_factory=list)
    proposed_plate: str | None = None
    decision: str = "no_readable_text"
    candidates: list[dict] = field(default_factory=list)
    ocr_complete: bool = False
    attempt_phase_counts: list[int] = field(default_factory=lambda: [0, 0, 0])
    plate_attempt_log: list[dict] = field(default_factory=list)


class SessionManager:
    """Short dropout grace belongs to the ROI session, independently of track IDs."""

    def __init__(self, config: CameraConfig):
        self.config = config
        self.sessions: list[Session] = []
        self.entry_hits = {}

    def _close(self, session, timestamp, reason):
        session.ended, session.end_reason = timestamp, reason

    def update(self, tracks: list[Track], timestamp: float, shape) -> list[tuple[Session, Track]]:
        active = [s for s in self.sessions if s.ended is None]
        for session in active:
            if timestamp - session.last_seen > self.config.session_gap_seconds:
                self._close(session, session.last_seen + self.config.session_gap_seconds, "detection_gap_expired")
        active = [s for s in active if s.ended is None]
        links, claimed = [], set()
        active_track_ids = {t.track_id for t in tracks}
        self.entry_hits = {key:value for key,value in self.entry_hits.items() if key in active_track_ids}
        for track in tracks:
            inside = inside_roi(track.detection.box, self.config.roi, shape)
            session = next((s for s in active if track.track_id in s.track_ids and s.session_id not in claimed), None)
            if session is None and inside:
                # Reattach only a missing session whose former track is not also observed.
                nearby = [s for s in active if s.session_id not in claimed and not set(s.track_ids) & active_track_ids
                          and timestamp - s.last_seen <= self.config.session_gap_seconds
                          and (iou(s.box, track.detection.box) >= self.config.match_iou or distance(s.box, track.detection.box, shape) <= self.config.match_distance)]
                nearby.sort(key=lambda s: (-iou(s.box, track.detection.box), s.session_id))
                if nearby:
                    session = nearby[0]; session.track_ids.append(track.track_id)
            if session is None:
                if not inside:
                    self.entry_hits.pop(track.track_id, None)
                    continue
                count, first = self.entry_hits.get(track.track_id, (0, timestamp))
                self.entry_hits[track.track_id] = (count + 1, first)
                if count + 1 < self.config.min_entry_observations:
                    continue
                if len(self.sessions) >= self.config.max_sessions:
                    raise ValueError("Session limit reached; split video or explicitly raise the configured bound")
                session = Session(f"s{len(self.sessions)+1:05d}", [track.track_id], first, timestamp, timestamp, track.detection.box)
                self.sessions.append(session); active.append(session)
                self.entry_hits.pop(track.track_id, None)
            claimed.add(session.session_id)
            session.last_seen, session.box = timestamp, track.detection.box
            if inside:
                session.last_inside = timestamp; session.outside_since = None; session.observations += 1
                links.append((session, track))
            else:
                if session.outside_since is None:
                    session.outside_since = timestamp
                if timestamp - session.outside_since >= self.config.exit_grace_seconds:
                    self._close(session, timestamp, "roi_exit")
        return links

    def finish(self, timestamp: float):
        for session in self.sessions:
            if session.ended is None:
                self._close(session, timestamp, "end_of_clip_not_proof_of_vehicle_departure")
