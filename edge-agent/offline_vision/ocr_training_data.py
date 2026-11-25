"""D05k immutable gold evaluation and conservative silver, offline only."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import cv2

from .consensus import normalize
from .dataset import sha256, save_png, safe_image, validate_labels
from .export import write_json
from .sampling import image_hash, hash_distance


def pixel_hash(image):
    return hashlib.sha256(str(image.shape).encode() + image.tobytes()).hexdigest()


def grouped_gold_split(rows, seed=185):
    """Entire confirmed string group stays together; union exact/near crop duplicates."""
    parents = list(range(len(rows)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]; i = parents[i]
        return i
    for i, row in enumerate(rows):
        for j, other in enumerate(rows[:i]):
            if row['text'] == other['text'] or row['pixel_sha256'] == other['pixel_sha256'] or hash_distance(row['dhash'], other['dhash']) <= 4:
                parents[find(i)] = find(j)
    groups = defaultdict(list)
    for i, row in enumerate(rows): groups[find(i)].append(row)
    strata = defaultdict(list)
    for group in groups.values():
        key = tuple(sorted({(r['source'], r['layout']) for r in group}))
        group_key = '|'.join(sorted({r['text'] for r in group}))
        strata[key].append((hashlib.sha256(f'{seed}:{group_key}'.encode()).hexdigest(), group))
    for entries in strata.values():
        entries.sort(key=lambda x: x[0])
        # ~60% secondary test, remaining gold validation. Never use model scores.
        test_count = max(1, min(len(entries)-1, round(len(entries)*.6))) if len(entries)>1 else 1
        for i, (key, group) in enumerate(entries):
            for row in group:
                row['split'] = 'test' if i < test_count else 'val'
                row['group_id'] = 'public-' + key[:16]
    return rows


def lock_gold(root, output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    iroot = root/'data/offline-vision/runs/d05i-readability-20261007'
    ipath = iroot/'labels.readability.csv-imported.json'
    labels = json.loads(ipath.read_text())
    from .crop_readability import validate_review
    validate_review(json.loads((iroot/'crop-review.template.json').read_text()), labels)
    rows = []
    for item in labels['items']:
        if item['readability'] == 'pending': continue
        path = safe_image(iroot, item['crop_path'])
        if sha256(path) != item['crop_sha256']: raise ValueError('Camera crop changed')
        image = cv2.imread(str(path)); rel = f"crops/{item['crop_id']}.png"
        save_png(output/rel, image)
        rows.append({'sample_id':item['crop_id'], 'source':'camera185', 'capture':item['capture_group_id'],
            'media_seconds':item['media_seconds'], 'crop_source':item['crop_source'], 'crop_path':rel,
            'crop_sha256':sha256(output/rel), 'pixel_sha256':pixel_hash(image), 'dhash':str(image_hash(image)),
            'source_image_sha256':item['source_image_sha256'], 'frame_bbox':item['frame_bbox_xyxy'],
            'readability':item['readability'], 'layout':item['layout'], 'split_y':item['split_y_crop'],
            'text':normalize(item['full_text']) if item['readability']=='readable_full' else '',
            'known_lines':{k:item[k+'_text'] for k in ['top','bottom','single'] if item[k+'_text']},
            'label_origin':'gold', 'split':'test', 'group_id':item['capture_group_id'],
            'plate_color':'pending', 'occlusion':'pending', 'label_sha256':sha256(ipath),
            'native_size':[image.shape[1],image.shape[0]]})
    # D05i includes every D05f confirmed manual bbox; crop-specific readability wins.
    fpath = root/'data/offline-vision/training/d05f-review-20261007/labels.confirmed.json'
    frames = json.loads(fpath.read_text())['frames']
    ikeys = {(r['source_image_sha256'],tuple(r['frame_bbox'])) for r in rows if r['crop_source']=='manual'}
    fkeys = {(f['image_sha256'],tuple(a['bbox'])) for f in frames if f['reviewed'] and f['annotations_complete'] for a in f['annotations'] if a['kind']=='plate'}
    if fkeys - ikeys: raise ValueError('D05f confirmed bbox absent from D05i inventory; review explicitly')
    jroot = root/'data/offline-vision/runs/d05j-diverse-review-20261007-v2'
    jpath = root/'data/offline-vision/runs/d05j-expanded-20261007/imported/labels.imported.json'
    jlabels = json.loads(jpath.read_text()); validate_labels(jlabels,jroot)
    public=[]
    for frame in jlabels['frames']:
        for ann in frame['annotations']:
            if not frame['reviewed'] or ann['kind']!='plate' or ann['readability']!='readable' or not ann['plate_text'] or '?' in ann['plate_text']: continue
            image=cv2.imread(str(safe_image(jroot,frame['image_path'])))
            x,y,r,b=ann['bbox']; crop=image[y:b,x:r]; sample=frame['sample_id']+'-'+ann['annotation_id']
            relative=f'crops/{sample}.png';save_png(output/relative,crop)
            tags=ann.get('condition_tags',frame.get('condition_tags',{}))
            public.append({'sample_id':sample,'source':frame['source_id'], 'capture':None,
                'crop_source':'manual', 'crop_path':relative,'crop_sha256':sha256(output/relative),
                'pixel_sha256':pixel_hash(crop),'dhash':str(image_hash(crop)),
                'source_image_sha256':frame['image_sha256'],'original_sha256':frame['original_sha256'],
                'frame_bbox':ann['bbox'], 'readability':'readable_full', 'layout':ann['layout'],
                'split_y':ann['split_y']-y if ann.get('split_y') is not None else None,
                'text':normalize(ann['plate_text']), 'known_lines':{},'label_origin':'gold',
                'plate_color':tags.get('plate_color','pending'),'occlusion':tags.get('occlusion','pending'),
                'label_sha256':sha256(jpath),'native_size':[crop.shape[1],crop.shape[0]]})
    rows += grouped_gold_split(public)
    sources={str(p.relative_to(root)):sha256(p) for p in [ipath, fpath, jpath]}
    pending=json.loads((root/'data/offline-vision/runs/d05j-expanded-20261007/camera185-v3/manifest.template.json').read_text())
    if any(f['reviewed'] for f in pending['frames']): raise ValueError('New confirmed camera labels require inclusion before locking')
    frozen={'schema_version':1,'seed':185,'rows':rows,'sources_sha256':sources,
        'policy':'All confirmed camera crops test; D05i crop readability takes precedence over D05f track transcript. Public gold grouped by plate string and crop dHash<=4, ~60% secondary test/40% validation. Gold NEVER train. No test selection after lock.',
        'pending_camera_excluded':[f['sample_id'] for f in pending['frames']],
        'limits':'Camera two captures, one full-readable unique plate plus partial second plate. No independently diverse test. Public vehicle/capture identities unknown. Gold labels lack confirmed color/occlusion. Partial has no full exact/CER denominator.'}
    write_json(output/'evaluation.lock.json',frozen)
    digest=sha256(output/'evaluation.lock.json')
    (output/'evaluation.lock.sha256').write_text(digest+'\n')
    return frozen


def load_lock(folder):
    path=folder/'evaluation.lock.json'
    if sha256(path)!=(folder/'evaluation.lock.sha256').read_text().strip(): raise ValueError('Evaluation lock changed')
    d=json.loads(path.read_text())
    for row in d['rows']:
        if sha256(safe_image(folder,row['crop_path']))!=row['crop_sha256']:raise ValueError('Frozen crop changed')
    return d


def leakage_reasons(image, crop, text, gold, original_sha=None):
    reasons=[];ph=pixel_hash(crop);full=pixel_hash(image);dh=image_hash(crop)
    for row in gold:
        why=[]
        if original_sha and original_sha in {row.get('original_sha256'),row['source_image_sha256']}:why.append('source_file_hash')
        if ph==row['pixel_sha256']:why.append('exact_crop_pixels')
        if hash_distance(dh,row['dhash'])<=4:why.append('crop_dhash<=4')
        if text and text==row['text']:why.append('same_plate_string')
        if why:reasons.append({'gold_sample':row['sample_id'],'gold_split':row['split'],'reasons':why})
    return reasons


def silver_decision(proposals, fast, english, hints, leakage, threshold=.75):
    """Scores only gate detector proposals, never combine incomparable OCR scores."""
    from .plate_domain import parse_plate
    normalized = {normalize(s) for s in hints}
    if leakage: return 'excluded', 'gold_or_near_duplicate'
    if len(proposals)!=1: return 'review', 'proposal_count'
    if proposals[0]['score'] is None or proposals[0]['score'] < threshold: return 'review', 'low_detector_score'
    if len(normalized)!=1: return 'review','conflicting_source_hints'
    fast,english=normalize(fast),normalize(english)
    if not fast or not fast==english==next(iter(normalized)): return 'review','ocr_disagreement'
    if parse_plate(fast) is None: return 'review','outside_supported_vn_syntax'
    return 'silver','three_way_agreement'


def proposed_row_split(crop):
    """Image-only two-row hypothesis; not human layout, never selected using text."""
    import numpy as np
    h,w=crop.shape[:2]
    if w/h>3.2 or h<12:return None
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    mask=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]>0
    profile=mask[:,max(1,int(w*.08)):max(2,int(w*.92))].mean(axis=1)
    lo,hi=max(1,int(h*.35)),min(h-1,int(h*.65))
    y=lo+int(np.argmin(profile[lo:hi]))
    if profile[:y].max()>.12 and profile[y:].max()>.12 and profile[y]<.5*min(profile[:y].max(),profile[y:].max()):return y
    return None
