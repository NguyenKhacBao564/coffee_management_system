"""Pinned official FastPlateOCR model, CPU diagnosis; no format constraints.

Pre/postprocessing adapted from ankandrew/fast-plate-ocr 9ce7a5b (MIT).
Copyright (c) 2024 ankandrew. See THIRD-PARTY-NOTICES.md.
"""
# SPDX-License-Identifier: MIT
import json
from pathlib import Path

import cv2
import numpy as np

from .dataset import sha256

REVISION = '9ce7a5b64a939aa421c243b331d42e6bc25ffd44'
WEIGHTS_SHA256 = '384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b'
CONFIG_SHA256 = '0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6'


def plate_input(image, config):
    mode = config['image_color_mode']
    if mode == 'rgb':
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    elif mode == 'grayscale':
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError('Unknown plate color mode')
    interpolation = {'linear': cv2.INTER_LINEAR, 'cubic': cv2.INTER_CUBIC,
                     'nearest': cv2.INTER_NEAREST, 'area': cv2.INTER_AREA, 'lanczos4': cv2.INTER_LANCZOS4}[config['interpolation']]
    h, w = config['img_height'], config['img_width']
    if not config['keep_aspect_ratio']:
        image = cv2.resize(image, (w, h), interpolation=interpolation)
    else:
        ratio = min(h / image.shape[0], w / image.shape[1])
        nw, nh = round(image.shape[1] * ratio), round(image.shape[0] * ratio)
        image = cv2.resize(image, (nw, nh), interpolation=interpolation)
        dw, dh = (w - nw) / 2, (h - nh) / 2
        color = config.get('padding_color', (114, 114, 114))
        if mode == 'grayscale' and isinstance(color, (list, tuple)):
            color = color[0]
        image = cv2.copyMakeBorder(image, round(dh - .1), round(dh + .1), round(dw - .1), round(dw + .1), cv2.BORDER_CONSTANT, value=color)
    if image.ndim == 2:
        image = image[:, :, None]
    return image[None].astype(np.uint8)  # normalization is embedded in the model graph


def slot_decode(probabilities, config):
    alphabet = config['alphabet']
    scores = probabilities.reshape(config['max_plate_slots'], len(alphabet))
    indices = scores.argmax(axis=1)
    slots = ''.join(alphabet[i] for i in indices)
    # Position heads are NOT CTC: do not collapse repeated letters/digits.
    raw = slots.rstrip(config['pad_char'])
    selected = scores[np.arange(len(indices)), indices]
    return raw, float(selected[:len(raw)].mean()) if raw else None, slots


class FastPlateRecognizer:
    def __init__(self, folder: Path):
        import onnxruntime as ort
        import yaml
        manifest = json.loads((folder / 'manifest.json').read_text())
        if manifest['revision'] != REVISION or manifest['license'] != 'MIT':
            raise ValueError('FastPlate recognizer provenance mismatch')
        for name, digest in [('cct_s_v2_global.onnx', WEIGHTS_SHA256), ('cct_s_v2_global_plate_config.yaml', CONFIG_SHA256)]:
            if sha256(folder / name) != digest:
                raise ValueError('Pinned FastPlate recognizer checksum mismatch')
        self.config = yaml.safe_load((folder / 'cct_s_v2_global_plate_config.yaml').read_text())
        if not set('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ') <= set(self.config['alphabet']):
            raise ValueError('FastPlate vocabulary lacks required Latin/digit characters')
        options = ort.SessionOptions(); options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(folder / 'cct_s_v2_global.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.input = self.session.get_inputs()[0].name
        outputs = self.session.get_outputs()
        slots, vocab = self.config['max_plate_slots'], len(self.config['alphabet'])
        compatible = [o.name for o in outputs if o.shape[-1] == slots * vocab or o.shape[-2:] == [slots, vocab]]
        if len(compatible) != 1:
            raise ValueError('Cannot identify official plate position-head output')
        self.output = compatible[0]
        self.metadata = {**manifest, 'runtime': 'ONNX Runtime CPU', 'runtime_version': ort.__version__,
            'preprocess': 'BGR→RGB; linear stretch 128×64; NHWC uint8; graph normalization, no external padding',
            'decoder': '10 position heads, argmax, strip trailing training pad only; not CTC',
            'score_meaning': 'Mean selected position probability, uncalibrated; not comparable with Paddle scores'}

    def line(self, image):
        blob = plate_input(image, self.config)
        self.last_input_shape = list(blob.shape)
        prediction = self.session.run([self.output], {self.input: blob})[0]
        raw, score, slots = slot_decode(prediction, self.config)
        self.last_raw_slots = slots
        return raw, score
