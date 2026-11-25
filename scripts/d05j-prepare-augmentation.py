#!/usr/bin/env python3
"""Phase D preparation: measured camera crop stats, seeded previews, no fitting."""
import argparse,json,subprocess,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.camera_augmentation import GROUPS,camera_stats,augment,export_fastplate_config,hevc_roundtrip
from offline_vision.dataset import sha256,safe_image,save_png,validate_labels
from offline_vision.export import write_json
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
labelpath=ROOT/'data/offline-vision/training/d05f-review-20261007/labels.confirmed.json';labels=json.loads(labelpath.read_text());root=ROOT/'data/offline-vision/runs/d05e-review-20261007/missed-frames';validate_labels(labels,root);crops=[];items=[]
for f in labels['frames']:
    if not f['reviewed']:continue
    image=cv2.imread(str(safe_image(root,f['image_path'])))
    for an in f['annotations']:
        if an['kind']!='plate':continue
        x,y,r,b=an['bbox'];crop=image[y:b,x:r];split=an.get('split_y');split=split-y if split is not None else None
        if split is not None and not 0<split<crop.shape[0]:raise ValueError('Invalid manual split')
        key=f['sample_id']+'-'+an['annotation_id'];crops.append((key,crop,split,an['readability']=='readable' and (an.get('layout')=='single-line' or split is not None)));items.append((f,an,crop,split,image))
stats=camera_stats(crops);config=stats['config'];write_json(a.output/'camera-statistics.json',stats);write_json(a.output/'augmentation.adapter.json',config)
# Measured native crops only. Labels are inherited as confirmed transcripts only;
# unreadable examples have no GT and no generated training sample is exported.
selected=sorted(items,key=lambda z:cv2.Laplacian(cv2.cvtColor(z[2],cv2.COLOR_BGR2GRAY),cv2.CV_64F).var(),reverse=True)
examples=[]
for group in GROUPS:
    pool=[x for x in selected if group!='occlusion' or x[3] is not None][:4];sheet=np.full((max(1,len(pool))*180,5*250,3),245,np.uint8)
    for j,(f,an,crop,split,full) in enumerate(pool):
        baseline=f'real/{group}-{j}.png';save_png(a.output/baseline,crop)
        for k in range(5):
            if k==0:out=crop;visible=an['plate_text'];meta={'applied':False,'source':'real native crop, not training'}
            else:out,visible,meta=augment(crop,an['plate_text'] if an['readability']=='readable' else '',split='train',config=config,sample_id=f['sample_id']+'-'+an['annotation_id'],draw=k,groups=[group],split_y=split,source_frame=full,bbox=an['bbox'])
            rel=f'previews/{group}-{j}-{k}.png';save_png(a.output/rel,out)
            # Sheet display enlargement does not replace native stored previews.
            h,w=out.shape[:2];scale=min(240/w,120/h);thumb=cv2.resize(out,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_NEAREST);sheet[j*180:j*180+thumb.shape[0],k*250:k*250+thumb.shape[1]]=thumb
            cv2.putText(sheet,'REAL' if k==0 else f'{group} seed draw {k}',(k*250+4,j*180+142),cv2.FONT_HERSHEY_SIMPLEX,.38,(0,0,0),1)
            cv2.putText(sheet,f"native {w}x{h}",(k*250+4,j*180+160),cv2.FONT_HERSHEY_SIMPLEX,.35,(0,0,0),1)
            examples.append({'source_sample_id':f['sample_id'],'annotation_id':an['annotation_id'],'source_native_crop':baseline,'output':rel,'group':group,'visible_text':visible,'manual_full_text':an['plate_text'] if an['readability']=='readable' else None,'is_training_data':False,'metadata':meta})
    save_png(a.output/f'contact-{group}.jpg',sheet)
compat=export_fastplate_config(config,a.output/'fastplate.albumentations.yaml');write_json(a.output/'fastplate-compatibility.json',compat)
# Exercise actual HEVC once even if stochastic preview selected only JPEG.
original=selected[0][2];encoded=hevc_roundtrip(original,28);save_png(a.output/'hevc-actual-roundtrip.png',encoded)
ffmpeg=subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
import importlib.metadata
(a.output/'dependencies.txt').write_text('\n'.join(f'{name}=={importlib.metadata.version(name)}' for name in ['albumentations','albucore','numpy','opencv-python-headless','scipy','pydantic','PyYAML','simsimd','stringzilla'])+'\n')
upstream={}
for name,path in [('augmentation.py','/tmp/d05j-fast-augmentation.py'),('dataset.py','/tmp/d05j-fast-dataset.py'),('train.py','/tmp/d05j-fast-train.py'),('pyproject.toml','/tmp/d05j-fast-pyproject.toml')]:
    source=Path(path)
    if source.is_file():target=a.output/'upstream'/name;target.parent.mkdir(exist_ok=True);target.write_bytes(source.read_bytes());upstream[name]={'revision':'9ce7a5b64a939aa421c243b331d42e6bc25ffd44','sha256':sha256(target),'source_url':f'https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/'+('pyproject.toml' if name=='pyproject.toml' else 'fast_plate_ocr/cli/train.py' if name=='train.py' else 'fast_plate_ocr/train/data/'+name),'license':'MIT; see edge-agent/licenses/FastPlateOCR-MIT.txt'}
manifest={'purpose':'D05j Phase D augmentation preparation; no training, not evaluated model gain','camera_labels_sha256':sha256(labelpath),'camera_plate_crops':len(crops),'config_sha256':sha256(a.output/'augmentation.adapter.json'),'code_sha256':sha256(ROOT/'edge-agent/offline_vision/camera_augmentation.py'),'upstream':upstream,'examples':examples,'ffmpeg':ffmpeg,'hevc_actual_roundtrip':{'input_size':list(original.shape),'output_size':list(encoded.shape),'codec':'libx265 CRF28 yuv420p one frame with edge padding; native size restored','limitation':'single-frame codec stress, not temporal stream HEVC camera noise calibration'},'split_policy':'All generated examples are previews, not dataset/splits. Runtime val/test return identical real pixels. No transformations of camera evaluation files. Calibration uses existing camera diagnostics; future independent test must not tune amplitudes/thresholds.'}
write_json(a.output/'manifest.json',manifest)
(a.output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>D05j augmentation</title><style>body{font:16px system-ui;margin:24px}img{max-width:100%}</style><h1>Phase D · Preview, chưa train</h1><p>Cột REAL là crop camera gốc; phóng nearest chỉ để xem. Native preview giữ riêng. Biên độ ánh sáng/contrast/chiều cao ký tự lấy proxy từ camera; thời tiết/đêm/góc là stress presets chưa có dữ liệu hiệu chỉnh.</p>'+''.join(f'<h2>{g}</h2><img src="contact-{g}.jpg">' for g in GROUPS))
print(json.dumps({'crops':len(crops),'quantiles':stats['quantiles'],'native_config':compat,'previews':len(examples),'hevc':'passed'},indent=2))
