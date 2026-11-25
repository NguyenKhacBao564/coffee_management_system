from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

Box = tuple[float, float, float, float]  # pixel xyxy, original frame/crop coordinates


@dataclass
class Detection:
    box: Box
    label: str
    score: float
    model: str
    corners: list[list[float]] | None = None


@dataclass
class OcrRead:
    raw: str
    score: float | None
    model: str
    strategy: str = "single-line"
    raw_lines: list[str] = field(default_factory=list)
    inference_calls: int = 1


class Detector(Protocol):
    metadata: dict

    def detect(self, image: np.ndarray, media_seconds: float) -> list[Detection]: ...


class OCR(Protocol):
    metadata: dict

    def read(self, crop: np.ndarray) -> OcrRead: ...

    def cost(self, crop: np.ndarray) -> int: ...
