import math

import cv2
import numpy as np

from .types import Box


def iou(a: Box, b: Box) -> float:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda box: max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    return intersection / max(1e-9, area(a) + area(b) - intersection)


def distance(a: Box, b: Box, shape) -> float:
    return math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2) / math.hypot(shape[0], shape[1])


def inside_roi(box: Box, roi, shape) -> bool:
    # Bottom-center is an image anchor, not proof the entire vehicle is on the scale.
    h, w = shape[:2]
    point = ((box[0] + box[2]) / (2 * w), box[3] / h)
    return cv2.pointPolygonTest(np.asarray(roi, np.float32), point, False) >= 0


def clip_box(box: Box, shape) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    x1, y1, x2, y2 = box
    return max(0, min(w, int(x1))), max(0, min(h, int(y1))), max(0, min(w, math.ceil(x2))), max(0, min(h, math.ceil(y2)))
