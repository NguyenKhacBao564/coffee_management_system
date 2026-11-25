#!/usr/bin/env python3
"""Reuse D05b review / D05c manifest tools; never write application data."""
import argparse
import copy
import csv
import hashlib
import json
import math
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

import cv2

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.dataset import browser_manifest,validate_labels,safe_image,duplicate_audit
from offline_vision.export import write_json
from offline_vision.fine_tune.audit import file_hash,contact_sheets,perceptual_hash
from offline_vision.fine_tune.adaptation import epoch_order
from offline_vision.sampling import image_hash,hash_distance


def write_csv(path,rows,fields):
    with path.open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    path.chmod(0o600)


def review(args):
    original=json.loads((args.dataset/'manifest.template.json').read_text())
    labels=json.loads(args.labels.read_text());notes=[]
    # Explicit legacy recovery only after provenance and every other immutable field match.
    expected={f['sample_id']:f for f in original['frames']}
    if labels['dataset_id']!=original['dataset_id'] or labels['sources']!=original['sources']:raise ValueError('Different camera provenance')
    if args.recover_legacy_hash:
        for f in labels['frames']:
            b=expected[f['sample_id']]
            for key in ['source_id','media_seconds','frame_index','image_path','image_sha256','width','height']:
                if f[key]!=b[key]:raise ValueError('Legacy provenance differs')
            if str(f['scene_hash'])!=str(b['scene_hash']):notes.append({'sample_id':f['sample_id'],'field':'scene_hash','action':'restored exact immutable source hash'})
            f['scene_hash']=str(b['scene_hash'])
    labels=browser_manifest(labels);validate_labels(labels,args.dataset)
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    write_json(args.output/'labels.resume.json',labels)
    template=(ROOT/'edge-agent/offline_vision/labeling.html').read_text()
    template=template.replace('D05b ·','D05f ·')
    embedded=json.dumps(labels,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    page=template.replace('__MANIFEST_JSON__',embedded)
    # Keep page next to PNG folder; preserve prior pages and exports.
    target=args.dataset/'label.d05f.html'
    if target.exists():raise ValueError('D05f review page exists; preserve it and choose a new dataset working copy')
    target.write_text(page);target.chmod(0o600)
    rows=[];sheets=[];sizes=[]
    for f in labels['frames']:
        plates=[a for a in f['annotations'] if a['kind']=='plate']
        missing_groups=[a['annotation_id'] for a in f['annotations'] if a['kind'] in {'plate','vehicle'} and not a.get('vehicle_group_id')]
        reasons=[]
        if not f['reviewed']:reasons.append('frame_not_reviewed')
        if f.get('annotations_complete') is not True:reasons.append('completeness_not_confirmed')
        if f.get('plate_presence') not in {'plate','no_plate'}:reasons.append('presence_not_confirmed')
        if missing_groups:reasons.append('vehicle_group_missing')
        if f['split']=='unassigned':reasons.append('split_unassigned')
        rows.append({'sample_id':f['sample_id'],'source_id':f['source_id'],'media_seconds':f['media_seconds'],'reviewed':f['reviewed'],
                     'plate_boxes':len(plates),'missing_vehicle_groups':len(missing_groups),'needs':';'.join(reasons)})
        sheets.append({'sample_id':f['sample_id'],'image_path':str(safe_image(args.dataset,f['image_path'])),
                       'original_split':f['split'],'boxes':plates,'errors':reasons})
        for a in plates:
            x,y,r,b=a['bbox'];scale=640/max(f['width'],f['height'])
            containing=[v for v in f['annotations'] if v['kind']=='vehicle' and v['bbox'][0]<=x and v['bbox'][1]<=y and v['bbox'][2]>=r and v['bbox'][3]>=b]
            crop_scale=640/max(containing[0]['bbox'][2]-containing[0]['bbox'][0],containing[0]['bbox'][3]-containing[0]['bbox'][1]) if len(containing)==1 else None
            sizes.append({'sample_id':f['sample_id'],'annotation_id':a['annotation_id'],'reviewed':f['reviewed'],'native_width':r-x,'native_height':b-y,
                          'full_640_width':(r-x)*scale,'full_640_height':(b-y)*scale,
                          'manual_vehicle_640_width':(r-x)*crop_scale if crop_scale else '',
                          'manual_vehicle_640_height':(b-y)*crop_scale if crop_scale else ''})
    write_csv(args.output/'frame-review-needed.csv',rows,list(rows[0]))
    write_csv(args.output/'plate-resize.csv',sizes,list(sizes[0]))
    sheets.sort(key=lambda r:('frame_not_reviewed' not in r['errors'],r['sample_id']))
    pages=contact_sheets(sheets,args.output)
    crops=json.loads(args.crop_template.read_text())
    if args.crop_labels:
        confirmed=json.loads(args.crop_labels.read_text())
        if confirmed['dataset_id']!=crops['dataset_id'] or {i['crop_id'] for i in confirmed['items']}!={i['crop_id'] for i in crops['items']}:raise ValueError('Crop inventory differs')
        crops=confirmed
    write_csv(args.output/'crop-review-needed.csv',[{'crop_id':i['crop_id'],'video':i['video_name'],'media_seconds':i['media_seconds'],'status':i['status']} for i in crops['items']],['crop_id','video','media_seconds','status'])
    summary={'source_labels_sha256':file_hash(args.labels),'recovery':notes,'reviewed_frames':sum(f['reviewed'] for f in labels['frames']),
             'pending_frames':[f['sample_id'] for f in labels['frames'] if not f['reviewed']],
             'pending_crops':[i['crop_id'] for i in crops['items'] if i['status']=='pending'],'contact_sheets':pages,
             'confirmed_complete_frames':sum(f.get('annotations_complete') is True for f in labels['frames']),
             'manual_vehicle_groups':sorted({a['vehicle_group_id'] for f in labels['frames'] for a in f['annotations'] if a.get('vehicle_group_id')}),
             'raw_source_unchanged':True,'scene_hash_storage':'uint64 canonical decimal string','training_started':False}
    write_json(args.output/'review-status.json',summary);return summary


def prepare(args):
    public=json.loads(args.public_manifest.read_text())
    if not public['training_ready'] or public['class_names']!=['license_plate']:raise ValueError('Public data manifest not ready')
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    records=copy.deepcopy(public['records']);labels=json.loads(args.labels.read_text());validate_labels(labels,args.dataset)
    for r in records:
        p=Path(r['image_path']);p=p if p.is_absolute() else args.public_manifest.parent/p
        r['image_path']=str(p.resolve());r['annotations_complete']=False
        if file_hash(p)!=r['file_sha256']:raise ValueError('Public image hash changed')
    selected=[];excluded=[];blocked=[]
    for f in labels['frames']:
        plates=[a for a in f['annotations'] if a['kind']=='plate']
        if not f['reviewed'] or f.get('annotations_complete') is not True or f.get('plate_presence') not in {'plate','no_plate'}:
            excluded.append({'sample_id':f['sample_id'],'reason':'review/completeness/presence not confirmed'});continue
        if bool(plates)!=(f['plate_presence']=='plate'):raise ValueError('Plate presence contradicts boxes')
        if f['split'] not in {'train','test'}:blocked.append(f"{f['sample_id']}: camera must use train or held-out test; selection uses public val")
        selected.append(f)
        path=safe_image(args.dataset,f['image_path']);image=cv2.imread(str(path));h,w=image.shape[:2]
        negatives=[a for a in f['annotations'] if a['kind']=='hard_negative']
        for a in negatives:
            x,y,r,b=a['bbox']
            if any(min(r,p['bbox'][2])>max(x,p['bbox'][0]) and min(b,p['bbox'][3])>max(y,p['bbox'][1]) for p in plates):
                raise ValueError('Hard negative overlaps confirmed plate; redraw/review')
        records.append({'sample_id':f['sample_id'],'image_path':str(path),'file_sha256':file_hash(path),'width':w,'height':h,
                        'boxes':[{'bbox':a['bbox'],'class':'license_plate'} for a in plates],
                        'split':f['split'],'capture_group_id':'camera-source:'+f['source_id'],
                        'vehicle_group_ids':sorted({a['vehicle_group_id'] for a in f['annotations'] if a.get('vehicle_group_id') and a['kind'] in {'plate','vehicle'}}),
                        'source_id':f['source_id'],'media_seconds':f['media_seconds'],'label_origin':'manual_review',
                        'annotations_complete':True,'plate_presence':f['plate_presence'],'hard_negatives':negatives,
                        'vehicle_boxes':[a['bbox'] for a in f['annotations'] if a['kind']=='vehicle'],
                        'sampling_group_id':f['sample_id'],'input_scope':'full_frame'})
        if f['split']=='train':
            parent=records[-1]
            for a in f['annotations']:
                if a['kind']!='vehicle':continue
                x,y,r,b=a['bbox']
                contained=[p for p in plates if x<=p['bbox'][0] and y<=p['bbox'][1] and r>=p['bbox'][2] and b>=p['bbox'][3]]
                intersecting=[p for p in plates if min(r,p['bbox'][2])>max(x,p['bbox'][0]) and min(b,p['bbox'][3])>max(y,p['bbox'][1])]
                if len(contained)!=len(intersecting):continue
                crop=image[y:b,x:r];target=args.output/'vehicle-crops'/(hashlib.sha256(a['annotation_id'].encode()).hexdigest()+'.png')
                target.parent.mkdir(exist_ok=True,mode=0o700)
                if not cv2.imwrite(str(target),crop):raise ValueError('Cannot save native vehicle crop')
                target.chmod(0o600)
                records.append({**parent,'sample_id':'vehicle-crop-'+a['annotation_id'],'image_path':str(target.resolve()),'file_sha256':file_hash(target),
                                'width':r-x,'height':b-y,'boxes':[{'bbox':[p['bbox'][0]-x,p['bbox'][1]-y,p['bbox'][2]-x,p['bbox'][3]-y],'class':'license_plate'} for p in contained],
                                'parent_sample_id':f['sample_id'],'crop_bbox':a['bbox'],'vehicle_boxes':[],
                                'hard_negatives':[],'input_scope':'manual_vehicle_crop','plate_presence':'plate' if contained else 'no_plate'})
            for a in negatives:
                x,y,r,b=a['bbox'];crop=image[y:b,x:r]
                # Annotation IDs are labels, never filesystem paths.
                target=args.output/'hard-negatives'/(hashlib.sha256(a['annotation_id'].encode()).hexdigest()+'.png')
                target.parent.mkdir(exist_ok=True,mode=0o700)
                if not cv2.imwrite(str(target),crop):raise ValueError('Cannot save confirmed negative crop')
                target.chmod(0o600)
                records.append({'sample_id':f"negative-{a['annotation_id']}",'image_path':str(target.resolve()),'file_sha256':file_hash(target),
                                'width':r-x,'height':b-y,'boxes':[],'split':'train','capture_group_id':'camera-source:'+f['source_id'],
                                'vehicle_group_ids':records[-1].get('vehicle_group_ids',[]),'source_id':f['source_id'],'media_seconds':f['media_seconds'],
                                'label_origin':'manual_review','annotations_complete':True,'plate_presence':'no_plate','hard_negatives':[],
                                'parent_sample_id':f['sample_id'],'sampling_group_id':f['sample_id'],'crop_bbox':a['bbox'],'negative_basis':'manual hard_negative + complete parent labels + no plate intersection'})
    camera_audit=duplicate_audit({**labels,'frames':selected},training=True)
    blocked.extend(str(i) for i in camera_audit['issues'])
    if not any(r['label_origin']=='manual_review' and r['split']=='train' for r in records):blocked.append('No confirmed grouped camera train samples')
    if not any(r['label_origin']=='manual_review' and r['split']=='test' for r in records):blocked.append('No independent confirmed camera test capture')
    # Same hash methods for all sources; do not compare scene hashes from differing ROIs.
    fingerprints=[];pairs=[];groups={}
    for r in records:
        image=cv2.imread(r['image_path']);h,w=image.shape[:2]
        pixel=hashlib.sha256(f'{w}x{h}:'.encode()+image.tobytes()).hexdigest()
        fingerprints.append((r,pixel,perceptual_hash(image),image_hash(image)))
        for group in [r.get('capture_group_id','')]+r.get('vehicle_group_ids',[]):
            if group:groups.setdefault(group,set()).add(r['split'])
    for group,splits in groups.items():
        if len(splits)>1:blocked.append('Vehicle/capture crosses splits: '+group)
    similarity_exclusions=set()
    for i,(a,ap,ah,ad) in enumerate(fingerprints):
        for b,bp,bh,bd in fingerprints[i+1:]:
            exact=ap==bp;near=hash_distance(ah,bh)<=6 and hash_distance(ad,bd)<=8
            if exact or near:
                pair={'sample_ids':[a['sample_id'],b['sample_id']],'kind':'exact_pixels' if exact else 'near_duplicate_suspect','cross_split':a['split']!=b['split']};pairs.append(pair)
                if exact or pair['cross_split']:
                    removable=[r for r in [a,b] if r['split']=='train' and r['label_origin']=='manual_review']
                    if getattr(args,'exclude_cross_split_camera_suspects',False) and pair['cross_split'] and removable:
                        similarity_exclusions.update(r.get('sampling_group_id',r['sample_id']) for r in removable)
                    else:blocked.append('Duplicate/similarity requires regroup or explicit review: '+str(pair))
    if similarity_exclusions:
        for r in records:
            if r.get('sampling_group_id') in similarity_exclusions:
                excluded.append({'sample_id':r['sample_id'],'parent_frame':r['sampling_group_id'],
                                 'reason':'Conservative pre-training exclusion of camera train frame and all variants involved in cross-split hash similarity; source file preserved'})
        records=[r for r in records if r.get('sampling_group_id') not in similarity_exclusions]
        for pair in pairs:
            pair['resolved_by_train_frame_exclusion']=any(next(r for r in fingerprints if r[0]['sample_id']==sid)[0].get('sampling_group_id') in similarity_exclusions for sid in pair['sample_ids'])
    counts={s:{'images':sum(r['split']==s for r in records),'boxes':sum(len(r['boxes']) for r in records if r['split']==s),
               'negative_images':sum(not r['boxes'] for r in records if r['split']==s),
               'camera_images':sum(r['label_origin']=='manual_review' for r in records if r['split']==s)} for s in ['train','val','test']}
    policy={'camera_max_fraction':.2,'camera_repeats_per_epoch':1,'camera_variants_per_frame_per_epoch':1,'augmentation':'light_photometric_v1','selection_split':'public_val'}
    train=[r for r in records if r['split']=='train'];epoch_samples=len(epoch_order(train,20261007,0,policy))
    sampled=epoch_order(train,20261007,0,policy)
    if not any(train[i]['label_origin']=='manual_review' for i in sampled):blocked.append('Camera cap permits no camera samples in an epoch')
    result={'schema_version':1,'purpose':'reviewed_real_training','class_names':['license_plate'],'records':records,'counts':counts,
            'groups':{k:sorted(v) for k,v in groups.items()},'excluded':excluded,'blocking_issues':blocked,'training_ready':not blocked,
            'duplicate_pairs':pairs,'batch_size':2,'drop_last':False,'samples_per_epoch':epoch_samples,'batches_per_epoch':math.ceil(epoch_samples/2),
            'inputs':{'public_manifest_sha256':file_hash(args.public_manifest),'camera_labels_sha256':file_hash(args.labels)},
            'limits':'Only two captures; public vehicle identities unknown. Exact/perceptual checks do not prove absence of vehicle-level leakage. No random camera-frame split.'}
    write_json(args.output/'manifest.json',result)
    contact_sheets([{'sample_id':r['sample_id'],'image_path':r['image_path'],'original_split':r['split'],'boxes':r['boxes'],'errors':[]} for r in records if r['label_origin']=='manual_review'],args.output)
    return {k:result[k] for k in ['training_ready','counts','samples_per_epoch','batches_per_epoch','blocking_issues']}


def package(args):
    manifest=json.loads(args.manifest.read_text())
    if not manifest['training_ready'] and not args.draft:raise ValueError('Camera data unresolved; only explicitly marked draft package is allowed')
    if file_hash(args.initial)!=args.initial_sha256:raise ValueError('D05d checkpoint hash differs')
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    def cp(source,target):
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copyfile(source,target);target.chmod(0o600)
    for index,r in enumerate(manifest['records']):
        source=Path(r['image_path']);source=source if source.is_absolute() else args.manifest.parent/source
        if file_hash(source)!=r['file_sha256']:raise ValueError('Dataset image changed')
        relative=Path('images')/r['split']/(f'{index:05d}'+source.suffix.lower())
        cp(source,args.output/'dataset'/relative);r['image_path']=relative.as_posix()
    write_json(args.output/'dataset/manifest.json',manifest)
    cp(args.initial,args.output/'initial/best.pth')
    (args.output/'initial/SHA256').write_text(args.initial_sha256+'\n')
    original=ROOT/'data/offline-vision/training-packages/d05c-first-train'
    for source in (original/'model').rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts:cp(source,args.output/'model'/source.relative_to(original/'model'))
    for source in (ROOT/'edge-agent/offline_vision').rglob('*'):
        if source.suffix in {'.py','.html'}:cp(source,args.output/'code/offline_vision'/source.relative_to(ROOT/'edge-agent/offline_vision'))
    for name in ['d05d-train.py','plate-training.py','d05f-run-with-retries.sh']:cp(ROOT/'scripts'/name,args.output/'scripts'/name)
    cp(ROOT/'edge-agent/config/plate-training.d05f.yaml',args.output/'configs/train.yaml')
    cp(ROOT/'edge-agent/config/plate-training.d05f-policy.yaml',args.output/'configs/policy.yaml')
    cp(original/'requirements-training.lock.txt',args.output/'requirements-training.lock.txt')
    for source in (original/'licenses').iterdir():cp(source,args.output/'licenses'/source.name)
    baseline=ROOT/'data/offline-vision/runs/d05d-vast-54567374/final/export'
    for name in ['model.json','detector.onnx']:cp(baseline/name,args.output/'baseline'/name)
    counts=manifest['counts']
    readme=f'''# D05f {'DRAFT — CAMERA NOT READY' if not manifest['training_ready'] else 'camera adaptation package'}

training_ready={str(manifest['training_ready']).lower()}. Read dataset/manifest.json blocking_issues.
Draft packages intentionally refuse training. They contain public data and tools, not a finished camera training set.
Re-run scripts/d05f-prepare.py prepare in the original repository after user confirmation, then package without --draft.

Counts: {json.dumps(counts)}. One class license_plate. Epoch reads {manifest['samples_per_epoch']} samples / {manifest['batches_per_epoch']} batches at batch2; drop_last=false.
Public images once/epoch, camera without replacement at most20% of epoch reads. Native full-frame/vehicle-crop variants share a frame sampling group: randomly choose only one variant per parent frame per epoch. Derived variants are intentional, not extra repeated reads.
No duplicated files, infinite sampler, horizontal flip, mosaic or mixup. Light brightness(.85–1.15,p=.3), 3x3 blur(p=.15), downsample(.8–1,p=.2) preserves bbox geometry.
Seed20261007, input640, batch2, LR1e-5 unchanged from D05d, SGD/cosine. Limits6 epochs /1000 cumulative steps /7200s total /3 process attempts.
Initialization D05d best SHA256={args.initial_sha256}; strict one-class state dict, no COCO head skips, optimizer/scheduler start fresh. Resume requires same dataset/config/policy/init hashes.
Public validation selects checkpoint. Camera held-out capture only for frozen comparison; public test preserved. Unknown public vehicle IDs and two captures limit leakage assurance and generalization.

Python3.12, PyTorch2.8.0/torchvision0.23.0. YOLOX revision6ddff4824372906469a7fae2dc3206c7aa4bbaee. See lock file and licenses. For CUDA use matching torch2.8.0+cu126/torchvision0.23.0+cu126 wheels as D05d; verify driver/GPU before running. Never upload secrets.

Run from extracted package (install locked dependencies in a separate venv; PY below is that venv's Python):
```sh
export PYTHONPATH="$PWD/code"
PY=/path/to/venv/bin/python
INIT_SHA=$(cat initial/SHA256)
$PY scripts/d05d-train.py preflight --manifest dataset/manifest.json --config configs/train.yaml --policy configs/policy.yaml --assets model --init-checkpoint initial/best.pth --init-sha256 "$INIT_SHA" --output results/preflight --max-steps-this-run 1 --max-seconds 300 --validate-after
$PY scripts/d05d-train.py preflight --manifest dataset/manifest.json --config configs/train.yaml --policy configs/policy.yaml --assets model --init-checkpoint initial/best.pth --init-sha256 "$INIT_SHA" --output results/preflight --resume results/preflight/last.pth --max-steps-this-run 1 --max-seconds 300 --validate-after
# CPU smoke: add --device cpu to preflight only; it does not certify CUDA.
tmux new-session -d -s d05f "bash scripts/d05f-run-with-retries.sh '$PWD' '$PY'"
# Wrapper resumes results/train/last.pth, bounded timeout includes validation.
$PY scripts/plate-training.py export --manifest dataset/manifest.json --config configs/train.yaml --assets model --checkpoint results/train/best.pth --output results/export
```
ONNX export checks parity coordinate atol.05px/probability1e-4, no tolerance for label/hash differences.
Use existing plate-training.py compare with an evaluation plan frozen by public validation and --baseline-folder baseline/model.json (D05d).
Record exact manifest hashes, confidence.25/NMS.45/IoU.5 before sealed test. For camera comparison run both models on identical full frames or identical vehicle crops; do not compare different input scopes.
OCR uses existing benchmark-ocr/PP-OCRv6 tiny with identical layout/preprocessing; no OCR fine-tune or guessed labels. Unmatched predictions are FPs only on explicitly complete frames.
No model/ONNX parity/new camera metrics exist until actual D05f training. App DB/D02/S03 are outside this package.
'''
    (args.output/'README.md').write_text(readme)
    entries=[{'path':str(p.relative_to(args.output)),'sha256':file_hash(p),'bytes':p.stat().st_size} for p in sorted(args.output.rglob('*')) if p.is_file()]
    write_json(args.output/'package-manifest.json',{'task':'D05f','draft':not manifest['training_ready'],'files':entries,'initial_sha256':args.initial_sha256})
    archive=args.output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(args.output.rglob('*')):
            if p.is_file():bundle.write(p,args.output.name+'/'+str(p.relative_to(args.output)))
    archive.chmod(0o600)
    return {'package':str(archive),'sha256':file_hash(archive),'draft':not manifest['training_ready'],'files':len(entries)+1}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('review');p.add_argument('--recover-legacy-hash',action='store_true');p.add_argument('--crop-template',type=Path,required=True);p.add_argument('--crop-labels',type=Path)
    q=sub.add_parser('prepare');q.add_argument('--public-manifest',type=Path,required=True);q.add_argument('--exclude-cross-split-camera-suspects',action='store_true')
    r=sub.add_parser('package');r.add_argument('--manifest',type=Path,required=True);r.add_argument('--initial',type=Path,required=True);r.add_argument('--initial-sha256',required=True);r.add_argument('--output',type=Path,required=True);r.add_argument('--draft',action='store_true')
    for entry in [p,q]:
        entry.add_argument('--dataset',type=Path,required=True);entry.add_argument('--labels',type=Path,required=True);entry.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result={'review':review,'prepare':prepare,'package':package}[args.command](args)
    if args.command=='review':result={k:v for k,v in result.items() if k!='recovery'}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
