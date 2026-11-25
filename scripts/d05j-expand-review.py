#!/usr/bin/env python3
"""Keep user labels and expand D05j review; local inference only, no training."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.diverse_review_expanded import import_existing,expand_cartgmt,separate_motorcycle,prepare_camera,preserve_cartgmt_imports
from offline_vision.fine_tune.detector import YoloXPlateDetector
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--old-review',type=Path,default=ROOT/'data/offline-vision/runs/d05j-diverse-review-20261007-v2');a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
labels=import_existing(a.old_review,a.csv,a.output/'imported');print('Imported CSV',flush=True)
detector=YoloXPlateDetector(ROOT/'data/offline-vision/runs/d05f-vast-54567374/final/export/model.json')
x=expand_cartgmt(ROOT/'data/offline-vision/incoming',labels,a.output/'cartgmt',detector);print('CarTGMT',len(x['frames']),flush=True)
old=preserve_cartgmt_imports(labels,a.old_review,a.output/'cartgmt-imported',detector);print('Previous CarTGMT',len(old['frames']),flush=True)
y=separate_motorcycle(labels,a.old_review,a.output/'motorcycle',detector);print('Motorcycle',len(y['frames']),flush=True)
z=prepare_camera(ROOT/'data/offline-vision/runs/d05f-vast-54567374',ROOT/'data/offline-vision/training/d05f-review-20261007/labels.confirmed.json',a.output/'camera185',detector);print('Camera185',len(z['frames']),flush=True)
