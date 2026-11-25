"""OpenCV CPU adapters. Decode/preprocessing adapted from pinned OpenCV Zoo.

Apache-2.0 sources and notices: ../THIRD-PARTY-NOTICES.md and licenses/.
Vehicle COCO classes are not a license-plate detector.
"""
# SPDX-License-Identifier: Apache-2.0
import hashlib
from itertools import product
from pathlib import Path

import cv2
import numpy as np

from .geometry import clip_box
from .types import Detection

MODELS = {
    "vehicle": {"repository": "opencv/object_detection_yolox", "revision": "78c368f74ce73ee28fc7a1be418a598c71b58b52",
                "filename": "object_detection_yolox_2022nov.onnx", "family": "YOLOX-s COCO", "license": "Apache-2.0",
                "sha256":"c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"},
    "plate": {"repository": "opencv/license_plate_detection_yunet", "revision": "962e8d8849878106cb84039dab61cf97bb683b31",
              "filename": "license_plate_detection_lpd_yunet_2023mar.onnx", "family": "LPD YuNet Chinese plate training", "license": "Apache-2.0",
              "sha256":"6d4978a7b6d25514d5e24811b82bfb511d166bdd8ca3b03aa63c1623d4d039c7"},
    "ocr": {"repository": "opencv/text_recognition_crnn", "revision": "6487ac545965a2c277aff293e2fdded8b0e6f9b9",
            "filename": "text_recognition_CRNN_EN_2021sep.onnx", "family": "CRNN English digits and Latin letters", "license": "Apache-2.0",
            "sha256":"a84b1f6e11a65c2d733cb0cc1f014aae3f99051e3f11447dc282faa678eee544"},
}


def model_metadata(kind: str, folder: Path):
    info = dict(MODELS[kind])
    path = folder / info["filename"]
    if not path.is_file():
        raise ValueError(f"Missing {kind} weights. Run fetch-models explicitly; inference never downloads.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = folder / "manifest.json"
    if not manifest.exists():
        raise ValueError("Missing checked model manifest; use fetch-models to verify weights")
    import json
    expected = json.loads(manifest.read_text())[kind]
    if expected["sha256"] != digest or digest != info["sha256"] or expected["revision"] != info["revision"]:
        raise ValueError(f"{kind} model checksum/revision does not match manifest")
    return path, {**info, "sha256": digest, "bytes": path.stat().st_size, "provider": "OpenCV DNN CPU"}


def cpu_net(path):
    net = cv2.dnn.readNet(str(path))
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    return net


class VehicleDetector:
    def __init__(self, folder: Path, threshold: float):
        path, self.metadata = model_metadata("vehicle", folder)
        self.net, self.threshold = cpu_net(path), threshold
        grids, strides = [], []
        for step in (8, 16, 32):
            x, y = np.meshgrid(np.arange(640 // step), np.arange(640 // step))
            grid = np.stack((x, y), 2).reshape(-1, 2)
            grids.append(grid); strides.append(np.full((len(grid), 1), step))
        self.grid, self.strides = np.concatenate(grids), np.concatenate(strides)
        self.metadata["input_size"] = [640, 640]
        self.metadata["score_meaning"] = "YOLOX objectness * class score, uncalibrated"

    def detect(self, image, media_seconds):
        h, w = image.shape[:2]
        scale = min(640 / h, 640 / w)
        padded = np.full((640, 640, 3), 114, np.float32)
        resized = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (int(w * scale), int(h * scale)))
        padded[:int(h * scale), :int(w * scale)] = resized
        self.net.setInput(padded.transpose(2, 0, 1)[None])  # RGB, 0..255 per official demo/export
        output = self.net.forward()[0]
        centers = (output[:, :2] + self.grid) * self.strides
        sizes = np.exp(output[:, 2:4]) * self.strides
        class_ids = output[:, 5:].argmax(axis=1)
        scores = output[:, 4] * output[:, 5:].max(axis=1)
        keep = np.flatnonzero(np.isin(class_ids, [2, 5, 7]) & (scores >= self.threshold))
        xyxy = np.concatenate([centers - sizes / 2, centers + sizes / 2], axis=1) / scale
        boxes = [[float(xyxy[i, 0]), float(xyxy[i, 1]), float(xyxy[i, 2]-xyxy[i, 0]), float(xyxy[i, 3]-xyxy[i, 1])] for i in keep]
        if not boxes:
            return []
        selected = cv2.dnn.NMSBoxes(boxes, scores[keep].tolist(), self.threshold, 0.5)
        labels = {2: "car", 5: "bus", 7: "truck"}
        detections = []
        for relative in np.asarray(selected).reshape(-1):
            index = keep[relative]
            box = clip_box(tuple(xyxy[index]), image.shape)
            if box[2] > box[0] and box[3] > box[1]:
                detections.append(Detection(box, labels[int(class_ids[index])], float(scores[index]), "YOLOX-s"))
        return detections


class PlateDetector:
    def __init__(self, folder: Path, threshold: float):
        path, self.metadata = model_metadata("plate", folder)
        self.net, self.threshold = cpu_net(path), threshold
        self.size = np.array([320, 240], dtype=np.float32)
        h, w = 240, 320
        second = [int(int((h + 1) / 2) / 2), int(int((w + 1) / 2) / 2)]
        third = [int(x / 2) for x in second]
        maps = [third]
        for _ in range(3):
            maps.append([int(x / 2) for x in maps[-1]])
        anchors = []
        for level, (fh, fw) in enumerate(maps):
            for y, x in product(range(fh), range(fw)):
                for minimum in [[10,16,24], [32,48], [64,96], [128,192,256]][level]:
                    step = [8,16,32,64][level]
                    anchors.append([(x + .5) * step / w, (y + .5) * step / h, minimum / w, minimum / h])
        self.priors = np.array(anchors, np.float32)
        self.metadata["input_size"] = [320, 240]
        self.metadata["score_meaning"] = "sqrt(plate class score * predicted IoU), uncalibrated"

    def detect(self, image, media_seconds):
        h, w = image.shape[:2]
        self.net.setInput(cv2.dnn.blobFromImage(cv2.resize(image, (320, 240))))
        loc, conf, overlap = self.net.forward(["loc", "conf", "iou"])
        scores = np.sqrt(np.maximum(conf[:, 1], 0) * np.clip(overlap[:, 0], 0, 1))
        indices = np.flatnonzero(scores >= self.threshold)
        corners = np.stack([(self.priors[:, :2] + loc[:, a:b] * .1 * self.priors[:, 2:]) * [w, h]
                            for a,b in [(4,6), (6,8), (10,12), (12,14)]], axis=1)
        boxes = []
        for index in indices:
            lo, hi = corners[index].min(axis=0), corners[index].max(axis=0)
            boxes.append([float(lo[0]), float(lo[1]), float(hi[0]-lo[0]), float(hi[1]-lo[1])])
        if not boxes:
            return []
        kept = cv2.dnn.NMSBoxes(boxes, scores[indices].tolist(), self.threshold, .3)
        result = []
        for offset in np.asarray(kept).reshape(-1):
            index = indices[offset]
            points = corners[index]
            box = clip_box((*points.min(axis=0), *points.max(axis=0)), image.shape)
            if box[2] > box[0] and box[3] > box[1]:
                result.append(Detection(box, "license_plate", float(scores[index]), "LPD YuNet", points.tolist()))
        return sorted(result, key=lambda d: -d.score)
