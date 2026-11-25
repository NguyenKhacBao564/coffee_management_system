import numpy as np

from offline_vision.ocr import FastPlateOCR
from offline_vision.types import OcrRead


def test_fastplate_pilot_adapter_preserves_whole_crop_and_raw_output(monkeypatch, tmp_path):
    seen = {}

    class StubRecognizer:
        metadata = {"revision": "pinned", "score_meaning": "uncalibrated position-head mean"}

        def __init__(self, folder):
            seen["folder"] = folder

        def line(self, image):
            seen["shape"] = image.shape
            return "49C02151", 0.73

    monkeypatch.setattr("offline_vision.plate_recognizer.FastPlateRecognizer", StubRecognizer, raising=False)
    recognizer = FastPlateOCR(tmp_path)
    crop = np.zeros((43, 101, 3), dtype=np.uint8)
    read = recognizer.read(crop)

    assert recognizer.cost(crop) == 1
    assert seen == {"folder": tmp_path, "shape": crop.shape}
    assert isinstance(read, OcrRead)
    assert (read.raw, read.score, read.model, read.strategy, read.raw_lines, read.inference_calls) == (
        "49C02151", 0.73, "FastPlate_CCT-S_v2_global", "whole-original", ["49C02151"], 1
    )
    assert recognizer.metadata["score_meaning"] == "uncalibrated position-head mean"
