"""CRNN CTC decoding adapted from OpenCV Zoo (Apache-2.0).

Copyright (C) 2021, Shenzhen Institute of Artificial Intelligence and Robotics
for Society. Third-party copyrights remain with their respective owners.
"""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import cv2
import numpy as np

from .detectors import cpu_net, model_metadata
from .types import OcrRead


class PlateOCR:
    def __init__(self, folder: Path, layout: str):
        path, self.metadata = model_metadata("ocr", folder)
        self.net, self.layout = cpu_net(path), layout
        self.metadata["score_meaning"] = "mean CTC softmax scores of emitted characters, uncalibrated; not detector scores"
        self.metadata["input_size"] = [100, 32]

    def cost(self, crop):
        return 2 if self.layout == "two-line" or (self.layout == "auto" and crop.shape[1] / crop.shape[0] < 2.4) else 1

    def _line(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.net.setInput(cv2.dnn.blobFromImage(gray, 1 / 127.5, (100, 32), 127.5))
        logits = self.net.forward().reshape(-1, 37)
        shifted = logits - logits.max(axis=1, keepdims=True)
        probabilities = np.exp(shifted); probabilities /= probabilities.sum(axis=1, keepdims=True)
        labels = logits.argmax(axis=1)
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        text, scores, previous = [], [], 0
        for index, label in enumerate(labels):
            if label and label != previous:
                text.append(alphabet[label - 1]); scores.append(float(probabilities[index, label]))
            previous = label
        return "".join(text), float(np.mean(scores)) if scores else None

    def read(self, crop):
        count = self.cost(crop)
        if count == 2:
            middle = crop.shape[0] // 2
            parts = [crop[:middle], crop[middle:]]
        else:
            parts = [crop]
        outputs = [self._line(part) for part in parts]
        scores = [score for _, score in outputs if score is not None]
        return OcrRead("\n".join(raw for raw, _ in outputs), float(np.mean(scores)) if scores else None,
                       "CRNN_EN_2021sep", "two-line" if count == 2 else "single-line", [raw for raw,_ in outputs], count)


class FastPlateOCR:
    """Pinned FastPlate position-head recognizer applied to the whole original crop."""

    def __init__(self, folder: Path):
        from .plate_recognizer import FastPlateRecognizer

        self.recognizer = FastPlateRecognizer(folder)
        self.metadata = {
            **self.recognizer.metadata,
            "name": "FastPlate CCT-S v2 global",
            "layout_policy": "whole crop; one inference call; no line split or plate-format correction",
        }

    def cost(self, crop):
        return 1

    def read(self, crop):
        raw, score = self.recognizer.line(crop)
        return OcrRead(raw, score, "FastPlate_CCT-S_v2_global", "whole-original", [raw], 1)
