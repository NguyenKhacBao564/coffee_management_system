import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2


def probe_video(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("Video must be an existing local file; URLs/RTSP are not supported")
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "stream=codec_name,width,height,time_base,start_time,avg_frame_rate:format=duration,size",
                             "-of", "json", str(path.resolve())], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    if not data.get("streams"):
        raise ValueError("No video stream")
    return data


@dataclass
class MediaFrame:
    seconds: float
    index: int
    image: object


class VideoReader:
    def __init__(self, path: Path, sample_hz: float, start: float = 0, end: float | None = None):
        self.metadata = probe_video(path)
        self.capture = cv2.VideoCapture(str(path.resolve()))
        if not self.capture.isOpened():
            raise ValueError("Cannot decode video with OpenCV")
        self.metadata["decoder"] = self.capture.getBackendName()
        self.metadata["timestamp_source"] = "decoder CAP_PROP_POS_MSEC, media presentation timestamp; no filename/overlay clock inference"
        self.step, self.start, self.end = 1 / sample_hz, start, end
        self.decoded = self.sampled = 0
        self.last_seconds = 0.0

    def __iter__(self):
        due, previous = self.start, -1.0
        try:
            while self.capture.grab():
                timestamp = self.capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if timestamp < 0 or timestamp <= previous:
                    raise ValueError("Media timestamps are missing/non-monotonic; refusing to invent a frame/fps clock")
                previous = timestamp
                self.decoded += 1
                if self.end is not None and timestamp > self.end:
                    break
                self.last_seconds = timestamp
                if timestamp + 1e-8 < due:
                    continue
                success, image = self.capture.retrieve()
                if not success:
                    raise ValueError("Could not retrieve sampled frame")
                self.sampled += 1
                yield MediaFrame(timestamp, self.decoded - 1, image)
                due += self.step
                # One inference per decoded sample, even after a large media-time gap.
                if due <= timestamp:
                    due = timestamp + self.step
        finally:
            self.capture.release()
