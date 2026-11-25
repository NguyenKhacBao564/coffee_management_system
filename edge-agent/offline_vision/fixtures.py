"""Deterministic test adapters. Never selected for real-video inference."""
import json
from pathlib import Path

import cv2
import numpy as np

from .types import Detection, OcrRead


class FixtureVehicleDetector:
    metadata = {"name":"scripted fixture vehicle boxes", "weights":None, "purpose":"pipeline control tests, not model accuracy"}

    def __init__(self, scenario: dict):
        self.scenario = scenario

    def detect(self, image, media_seconds):
        return [Detection(tuple(item["box"]), "truck", .9, "fixture-vehicle") for item in self.scenario["vehicles"]
                if item["from"] <= media_seconds < item["to"]]


class FixturePlateDetector:
    metadata = {"name":"scripted fixture plate boxes", "weights":None, "purpose":"pipeline control tests, not model accuracy"}

    def __init__(self, scenario: dict):
        self.has_plate = scenario["plate"]

    def detect(self, image, media_seconds):
        if not self.has_plate:
            return []
        h,w = image.shape[:2]
        return [Detection((w*.3,h*.65,w*.7,h*.87), "license_plate", .95, "fixture-plate")]


class FixtureOCR:
    metadata = {"name":"scripted fixture OCR text", "weights":None, "purpose":"consensus tests, not model accuracy"}

    def __init__(self, scenario: dict):
        self.values, self.index = scenario["ocr"], 0

    def cost(self, crop): return 1

    def read(self, crop):
        value = self.values[self.index % len(self.values)]
        self.index += 1
        return OcrRead(value, .85, "fixture-ocr")


def create_fixture(output: Path, case: str):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    inside, outside = [210,80,450,315], [210,0,450,125]
    scenarios = {
        "no-vehicle": {"vehicles":[], "plate":False, "ocr":[""]},
        "outside-roi": {"vehicles":[{"from":0,"to":10,"box":outside}], "plate":True,"ocr":["51C-123.45"]},
        "enter-exit": {"vehicles":[{"from":0,"to":1,"box":outside},{"from":1,"to":6,"box":inside},{"from":6,"to":10,"box":outside}],"plate":True,"ocr":["51C-123.45"]},
        "short-dropout": {"vehicles":[{"from":0,"to":3,"box":inside},{"from":4,"to":10,"box":inside}],"plate":True,"ocr":["51C-123.45"]},
        "no-plate": {"vehicles":[{"from":0,"to":10,"box":inside}],"plate":False,"ocr":[""]},
        "conflicting-ocr": {"vehicles":[{"from":0,"to":10,"box":inside}],"plate":True,"ocr":["51C-123.45", "51C-128.45"]},
    }
    if case not in scenarios:
        raise ValueError("Unknown fixture case")
    scenario = scenarios[case]
    writer = cv2.VideoWriter(str(output / "fixture.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640,360))
    if not writer.isOpened(): raise ValueError("Cannot write fixture video")
    try:
        for index in range(100):
            image = np.full((360,640,3), 45, np.uint8)
            cv2.rectangle(image, (160,145), (512,352), (55,110,70), 2)
            cv2.putText(image, "SYNTHETIC FIXTURE", (10,350), cv2.FONT_HERSHEY_SIMPLEX,.5,(200,200,200),1)
            for detection in FixtureVehicleDetector(scenario).detect(image,index/10):
                x1,y1,x2,y2 = map(int,detection.box)
                cv2.rectangle(image,(x1,y1),(x2,y2),(110,100,60),-1)
                if scenario["plate"]:
                    px,py = x1+int((x2-x1)*.3),y1+int((y2-y1)*.65)
                    cv2.rectangle(image,(px,py),(x1+int((x2-x1)*.7),y1+int((y2-y1)*.87)),(245,245,245),-1)
                    cv2.putText(image,"51C12345",(px+3,py+24),cv2.FONT_HERSHEY_SIMPLEX,.4,(10,10,10),1)
            writer.write(image)
    finally:
        writer.release()
    (output / "scenario.json").write_text(json.dumps(scenario,indent=2)+"\n")
    return output / "fixture.mp4"
