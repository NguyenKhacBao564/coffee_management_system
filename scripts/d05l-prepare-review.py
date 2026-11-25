#!/usr/bin/env python3
"""D05l step1: reuse native D05j camera selector/editor; no training or OCR GT."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.ocr_training_data import load_lock
from offline_vision.diverse_review_expanded import prepare_camera,render_expanded
from offline_vision.fine_tune.detector import YoloXPlateDetector
from offline_vision.dataset import sha256,browser_manifest
from offline_vision.export import write_json
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
old=ROOT/'data/offline-vision/runs/d05k-20261008/evaluation';gold=load_lock(old)
labels=ROOT/'data/offline-vision/training/d05f-review-20261007/labels.confirmed.json';confirmed=json.loads(labels.read_text())
excluded={s['source_id']:sorted({r['media_seconds'] for r in gold['rows'] if r['source']=='camera185' and r['capture']==s['capture_group_id']}) for s in confirmed['sources']}
previous=ROOT/'data/offline-vision/runs/d05j-expanded-20261007/camera185-v3/manifest.template.json'
for f in json.loads(previous.read_text())['frames']:excluded[f['source_id']].append(f['media_seconds'])
for s in confirmed['sources']:
    if sha256(Path(s['path']))!=s['sha256']:raise ValueError('Source video differs from original provenance')
detector=YoloXPlateDetector(ROOT/'data/offline-vision/runs/d05f-vast-54567374/final/export/model.json')
m=prepare_camera(ROOT/'data/offline-vision/runs/d05f-vast-54567374',labels,args.output,detector,max_frames_per_track=6,candidates_per_track=32,excluded_media=excluded,reference_window_seconds=1)
m['purpose']='D05l new native camera review; ALL camera gold test only. No OCR/source transcript ground truth. Two-line geometry is only a proposal; confirm bbox, layout, text/visible_text, color and occlusion.'
for f in m['frames']:f['split']='test';f['notes']='D05l: camera test only. Layout/vehicle is a proposal, not confirmed. Use ? for hidden characters; unknown if unreadable.'
write_json(args.output/'manifest.template.json',browser_manifest(m));render_expanded(m,args.output)
page=(args.output/'label.html').read_text().replace('<title>D05b','<title>D05l').replace('labels.d05j.', 'labels.d05l.')
page=page.replace('<p id="summary">','<p><strong>D05l · Camera luôn TEST.</strong> Xác nhận bbox, một/hai dòng, đường tách dòng, nội dung đọc chắc hoặc visible_text với ?, màu và mức che. Các mục pending không phải gold. Không lấy OCR làm nhãn.</p><p id="summary">')
(args.output/'label.html').write_text(page)
write_json(args.output/'d05l-plan.json',{'old_d05k_lock_sha256':sha256(old/'evaluation.lock.json'),'excluded_old_media_seconds':excluded,'max_frames_per_temporary_track':6,'candidate_quantile_cap':32,'minimum_selected_separation_seconds':3,'pending_frames':len(m['frames']),'policy':'native PNG; best image sharpness, no OCR sorting; aspect/manual bbox references are proposals only; all camera gold evaluation only; no train/test change','limits':'Same two captures, temporary track IDs may fragment vehicles. Two-line proposal is not proof of true plate or readable text.'})
print(json.dumps({'frames':len(m['frames']),'by_source':{s['source_id']:sum(f['source_id']==s['source_id'] for f in m['frames']) for s in m['sources']},'review':str(args.output/'label.html')},indent=2))
