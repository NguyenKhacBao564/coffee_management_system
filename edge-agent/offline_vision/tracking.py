from dataclasses import dataclass

from .config import CameraConfig
from .geometry import distance, iou
from .types import Detection


@dataclass
class Track:
    track_id: str
    detection: Detection
    last_seen: float
    observations: int = 1


class Tracker:
    """Greedy one-to-one IoU/proximity association, IDs local to this run only."""

    def __init__(self, config: CameraConfig):
        self.config = config
        self.tracks: dict[str, Track] = {}
        self.created = 0

    def update(self, detections: list[Detection], timestamp: float, shape) -> list[Track]:
        self.tracks = {key: track for key, track in self.tracks.items() if timestamp - track.last_seen <= self.config.tracking_gap_seconds}
        pairs = []
        for key, track in self.tracks.items():
            for index, detection in enumerate(detections):
                overlap, separation = iou(track.detection.box, detection.box), distance(track.detection.box, detection.box, shape)
                if overlap >= self.config.match_iou or separation <= self.config.match_distance:
                    pairs.append((overlap - separation, key, index))
        assigned_tracks, assigned_detections, observed = set(), set(), []
        for _, key, index in sorted(pairs, reverse=True):
            if key in assigned_tracks or index in assigned_detections:
                continue
            track = self.tracks[key]
            track.detection = detections[index]; track.last_seen = timestamp; track.observations += 1
            assigned_tracks.add(key); assigned_detections.add(index); observed.append(track)
        for index, detection in enumerate(detections):
            if index not in assigned_detections:
                self.created += 1
                key = f"t{self.created:05d}"
                track = Track(key, detection, timestamp)
                self.tracks[key] = track; observed.append(track)
        return observed
