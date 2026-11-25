"""Official PaddlePaddle tiny recognizer, CPU only, without the Paddle runtime.

Preprocess/CTC semantics adapted from PaddleX c50f5da (Apache-2.0).
Copyright (c) 2024 PaddlePaddle Authors. See THIRD-PARTY-NOTICES.md.
"""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import math
from pathlib import Path
import subprocess

import cv2
import numpy as np

from .export import write_json

MODEL = {"repository": "PaddlePaddle/PP-OCRv6_tiny_rec_onnx",
         "revision": "2612ab37152ae0a677521bae4e1e3d4fb4cf7c30", "license": "Apache-2.0",
         "filename": "inference.onnx", "sha256": "9ef676d6ed3c88256a2d92c640c44f25b0c40947e111b14b8be8f594091563e6",
         "config_sha256": "66170210bad538e83fff3c4a3867e547d6bf20b50d64b20347c4b913f3034ea1",
         "model_card_sha256": "e83dd03e515a2d064eaba8ec82248f21dbf6a0813550bafe4c70ee2f6e8fdf2a",
         "preprocess_source_revision": "c50f5da858020db473a2285f089bb8c7bbd6afdc",
         "purpose": "General text-line recognizer with Latin/digits vocabulary; not a validated Vietnamese plate model"}

ENGLISH_MODEL = {"repository":"PaddlePaddle/en_PP-OCRv5_mobile_rec_onnx",
    "revision":"3fafbc3b5dcf93dd72add9f48368be8a3a2cd33b","license":"Apache-2.0",
    "filename":"inference.onnx","sha256":"b5f833dfc5d0eb71da397b4efa06ebeee9b431b690a47d6af40d77d8eabc557f",
    "config_sha256":"27e91d0582f40168aa218303c76e184bc78fa7a5d105aad0cfbad8458b441067",
    "model_card_sha256":"98b45ea81164d1e1a1dd82255207053b15cd6c69d922a1c5cf3387ce604d4b74",
    "preprocess_source_revision":MODEL['preprocess_source_revision'],
    "purpose":"Official English/Latin text-line recognizer diagnostic; not fine-tuned or validated for Vietnam plates"}

SERVER_MODEL = {"repository": "PaddlePaddle/PP-OCRv5_server_rec_onnx",
    "revision": "b70df217f4fd99d14f970bad092cebe7d74cc4d1", "license": "Apache-2.0",
    "filename": "inference.onnx", "max_weights_bytes": 100000000,
    "sha256": "d9dc333c9c7b042c6dffb8e33d72b6f65c9c1d463d0a3c2f78174fea55e94752",
    "config_sha256": "2c719dba044c4e2228aef8ff92f5f575394d75d24c16de096a33b7cfd902f66d",
    "model_card_sha256": "806a481f4c15a38feb7103a64ec0e14f83f6a211abb4b0a345bdc3b13145c821",
    "preprocess_source_revision": MODEL['preprocess_source_revision'],
    "purpose": "General multilingual text-line recognizer diagnosis, not Vietnam plate validated"}


def fetch_recognizer(folder: Path, *, specification=None):
    spec=specification or MODEL
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, digest in [("inference.onnx", spec["sha256"]), ("inference.yml", spec["config_sha256"]), ("README.md", spec["model_card_sha256"])]:
        path = folder / name
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".download")
            try:
                subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "180", "--max-filesize", str(spec.get('max_weights_bytes', 10000000)),
                    f"https://huggingface.co/{spec['repository']}/resolve/{spec['revision']}/{name}", "-o", str(temporary)], check=True)
                if digest and hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                    raise ValueError("Recognizer artifact checksum does not match official pinned metadata")
                temporary.rename(path)
            finally:
                temporary.unlink(missing_ok=True)
        if digest and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Existing recognizer artifact differs; refusing overwrite")
        path.chmod(0o600)
    if "license: apache-2.0" not in (folder / "README.md").read_text():
        raise ValueError("Pinned model card does not declare the expected weights license")
    write_json(folder / "manifest.json", {**spec, "weights_bytes": (folder / "inference.onnx").stat().st_size,
        "model_card_sha256": hashlib.sha256((folder / "README.md").read_bytes()).hexdigest()})


def paddle_input(image):
    h, w = image.shape[:2]
    if not h or not w: raise ValueError("Empty recognition image")
    width = min(3200, int(48 * max(320 / 48, w / h)))
    resized_width = min(width, math.ceil(48 * w / h))
    resized = cv2.resize(image, (resized_width, 48)).astype(np.float32)
    blob = np.zeros((1, 3, 48, width), np.float32)
    blob[0, :, :, :resized_width] = (resized.transpose(2, 0, 1) / 255 - .5) / .5
    return blob  # BGR as official DecodeImage; ratio preserved, right pad zero in normalized space.


def ctc_decode(probabilities, characters):
    if probabilities.ndim != 2 or probabilities.shape[1] != len(characters):
        raise ValueError("Model output/vocabulary mismatch")
    labels = probabilities.argmax(axis=1)
    raw, scores, previous = [], [], -1
    for index, label in enumerate(labels):
        if label != 0 and label != previous:
            raw.append(characters[label]); scores.append(float(probabilities[index, label]))
        previous = label
    return "".join(raw), float(np.mean(scores)) if scores else None


class PaddleTinyRecognizer:
    def __init__(self, folder: Path, *, specification=None):
        spec=specification or MODEL
        import onnxruntime as ort
        import yaml
        manifest = json.loads((folder / "manifest.json").read_text())
        for name, digest in [("inference.onnx", spec["sha256"]), ("inference.yml", spec["config_sha256"])]:
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Pinned recognizer checksum mismatch")
        if manifest["revision"] != spec["revision"] or manifest['repository']!=spec['repository']: raise ValueError("Recognizer revision mismatch")
        cfg = yaml.safe_load((folder / "inference.yml").read_text())
        self.characters = ["blank"] + cfg["PostProcess"]["character_dict"] + [" "]
        if not set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ").issubset(set(self.characters)):
            raise ValueError("Recognizer vocabulary lacks required Latin/digit characters")
        options = ort.SessionOptions(); options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(folder / "inference.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        self.metadata = {**manifest, "runtime": "ONNX Runtime CPU", "runtime_version": ort.__version__,
            "input": self.session.get_inputs()[0].shape, "score_meaning": "Mean emitted CTC probabilities, uncalibrated; separate from CRNN scores"}

    def line(self, image):
        blob = paddle_input(image)
        self.last_input_shape = list(blob.shape)
        prediction = self.session.run(None, {self.input: blob})[0]
        return ctc_decode(prediction[0], self.characters)


class PaddleEnglishRecognizer(PaddleTinyRecognizer):
    def __init__(self, folder):
        super().__init__(folder,specification=ENGLISH_MODEL)


class PaddleServerRecognizer(PaddleTinyRecognizer):
    def __init__(self, folder):
        super().__init__(folder, specification=SERVER_MODEL)
