"""Human-reviewed, finite, group-safe one-class training manifests."""
import csv
import json
import math
import os
import hashlib
from collections import Counter
from pathlib import Path

from ..dataset import validate_labels, duplicate_audit, safe_image, browser_manifest
from ..export import write_json
from .audit import file_hash, valid_box


def camera_review_template(dataset, output):
    manifest=json.loads((dataset/'manifest.template.json').read_text())
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    fields=['sample_id','plate_presence','vehicle_type','split','notes']
    with (output/'camera-review.template.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for f in manifest['frames']:
            writer.writerow(dict(sample_id=f['sample_id'],plate_presence='unreviewed',vehicle_type='unknown',split='unassigned',notes=''))
    write_json(output/'status.json',{'frames':len(manifest['frames']),'reviewed_frames':sum(f['reviewed'] for f in manifest['frames']),
        'confirmed_plate_boxes':sum(len([a for a in f['annotations'] if a['kind']=='plate']) for f in manifest['frames'] if f['reviewed']),
        'instructions':'Use existing label.html on original PNGs. Draw all real plates, even unreadable ones. Locks/rails: kind hard_negative. A full frame is negative only with explicit no_plate; visible unlocated plates: plate_unlocatable, excluded. No OCR/detection is ground truth.'})
    # Human-visible proposals only. They are separate from annotations and never
    # become training negatives without the user's explicit review/redraw.
    proposals=[]
    selected=next((f for f in manifest['frames'] if f['sample_id']=='v001-f002992'),None)
    if selected:
        import cv2
        from .audit import contact_sheets
        image=cv2.imread(str(safe_image(dataset,selected['image_path'])))
        for i,box in enumerate([[220,460,440,880],[465,475,670,980],[1050,480,1275,960]]):
            x1,y1,x2,y2=box;path=output/f'container-lock-proposal-{i+1}.png'
            cv2.imwrite(str(path),image[y1:y2,x1:x2]);path.chmod(0o600)
            proposals.append({'proposal_id':f'container-lock-{i+1}','sample_id':selected['sample_id'],
                'source_id':selected['source_id'],'media_seconds':selected['media_seconds'],'parent_image_sha256':selected['image_sha256'],
                'bbox':box,'crop_path':str(path.resolve()),'kind':'hard_negative','label_origin':'assistant_visual_proposal',
                'ground_truth':False,'confirmed':False,'instruction':'Check original frame; redraw as hard_negative. This crop does not declare the entire parent frame negative.'})
        selected['suggested_review_regions']=proposals
        contact_sheets([{'sample_id':p['proposal_id'],'image_path':p['crop_path'],'original_split':'pending','boxes':[],'errors':['NOT ground truth']} for p in proposals],output)
    write_json(output/'hard-negative.proposals.json',proposals)
    template=(Path(__file__).parents[1]/'labeling.html').read_text()
    template=template.replace('ctx.setLineDash([]);',"for(const s of (frame().suggested_review_regions??[])){const [x,y,r,b]=s.bbox;ctx.strokeStyle='#d89600';ctx.strokeRect(x,y,r-x,b-y)}ctx.setLineDash([]);",1)
    template=template.replace('img.src=f.image_path;',f'img.src={json.dumps(os.path.relpath(dataset.resolve(),output.resolve())+"/")}+f.image_path;')
    template=template.replace('Gợi ý xe/crop từ detector — không phải nhãn','Gợi ý xe từ detector, khóa/thanh màu vàng — chưa là nhãn; vẽ lại sau khi xác nhận')
    embedded=json.dumps(browser_manifest(manifest),ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    (output/'label.review.html').write_text(template.replace('__MANIFEST_JSON__',embedded));(output/'label.review.html').chmod(0o600)
    return output/'camera-review.template.csv'


def prepare(audit_path, review_path, output, *, camera_dataset=None, camera_labels=None, camera_review=None, duplicate_reviews=None, batch_size=2):
    """Reject leakage or incomplete selected labels; never silently turn missing plates into negatives."""
    records=[];pairs=[];inputs={};blocked=[];excluded=[]
    if audit_path:
        audit=json.loads(audit_path.read_text());inputs['audit_sha256']=file_hash(audit_path)
        if audit['issues']:blocked.append('External audit has inventory-level issues; resolve and re-audit')
        with review_path.open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        if len({r['sample_id'] for r in rows})!=len(rows):raise ValueError('Duplicate review sample ID')
        reviews={r['sample_id']:r for r in rows}
        if set(reviews)!={r['sample_id'] for r in audit['records']}:raise ValueError('Review inventory differs from audit')
        inputs['review_sha256']=file_hash(review_path)
        for original in audit['records']:
            r=reviews[original['sample_id']]
            if r['annotation_review']!='accepted':excluded.append({'sample_id':r['sample_id'],'reason':r['annotation_review']});continue
            if original['original_split']=='test' and r['split']!='test':blocked.append(f"{r['sample_id']}: original test cannot be used in train/val");continue
            errors=[e for e in original['errors'] if not (e=='empty_annotations_not_confirmed_negative' and r['plate_presence']=='no_plate')]
            if errors:blocked.append(f"{r['sample_id']}: structural errors {errors}");continue
            if r['plate_presence'] not in {'plate','no_plate'}:blocked.append(f"{r['sample_id']}: explicit plate presence missing");continue
            if bool(original['boxes'])!=(r['plate_presence']=='plate'):blocked.append(f"{r['sample_id']}: plate presence contradicts boxes");continue
            records.append({**original,'split':r['split'],'capture_group_id':r['capture_group_id'],'vehicle_group_ids':[r['vehicle_group_id']] if r['vehicle_group_id'] else [],
                'vehicle_type':r['vehicle_type'],'layout':r['layout'],'label_origin':'roboflow_published_annotation','hard_negatives':[],
                'plate_presence':r['plate_presence'],'vehicle_group_unknown':not bool(r['vehicle_group_id'])})
        pairs=audit['duplicate_pairs']
    if camera_dataset:
        if not camera_labels or not camera_review:raise ValueError('Camera requires manual labels and explicit presence review CSV')
        manifest=json.loads(camera_labels.read_text());validate_labels(manifest,camera_dataset)
        inputs.update(camera_labels_sha256=file_hash(camera_labels),camera_review_sha256=file_hash(camera_review))
        with camera_review.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        if len({r['sample_id'] for r in rows})!=len(rows):raise ValueError('Duplicate camera review ID')
        reviews={r['sample_id']:r for r in rows}
        if set(reviews)!={f['sample_id'] for f in manifest['frames']}:raise ValueError('Camera review inventory differs')
        selected=[]
        for f in manifest['frames']:
            r=reviews[f['sample_id']];plates=[a for a in f['annotations'] if a['kind']=='plate']
            if not f['reviewed'] or r['plate_presence'] not in {'plate','no_plate'}:
                excluded.append({'sample_id':f['sample_id'],'reason':'not reviewed or unlocated/unreviewed plate'});continue
            if bool(plates)!=(r['plate_presence']=='plate'):blocked.append(f"{f['sample_id']}: plate presence contradicts boxes");continue
            if manifest['label_origin']!='manual_review':blocked.append('Camera labels are not manually confirmed');continue
            # Source identity is immutable, keeping the entire capture together.
            if r['split']!=f['split']:blocked.append(f"{f['sample_id']}: split differs between JSON and review CSV");continue
            selected.append(f)
            path=safe_image(camera_dataset,f['image_path'])
            import cv2
            image=cv2.imread(str(path))
            pixel_sha=hashlib.sha256(f"{f['width']}x{f['height']}:".encode()+image.tobytes()).hexdigest()
            records.append({'sample_id':f['sample_id'],'image_path':str(path),'file_sha256':file_hash(path),'width':f['width'],'height':f['height'],
                'pixel_sha256':pixel_sha,
                'boxes':[{'bbox':a['bbox'],'class':'license_plate'} for a in plates],'split':f['split'],
                'capture_group_id':'camera-source:'+f['source_id'],'vehicle_group_ids':sorted({a['vehicle_group_id'] for a in f['annotations'] if a['kind'] in {'vehicle','plate'} and a.get('vehicle_group_id')}),
                'vehicle_type':r['vehicle_type'],'layout':[a['layout'] for a in plates],'plate_presence':r['plate_presence'],
                'label_origin':'manual_review','media_seconds':f['media_seconds'],'source_id':f['source_id'],
                'hard_negatives':[a for a in f['annotations'] if a['kind']=='hard_negative']})
        camera_check=duplicate_audit({**manifest,'frames':selected},training=True)
        blocked.extend(str(i) for i in camera_check['issues'])
        pairs+=camera_check['duplicate_pairs']
    if not records:blocked.append('No accepted samples; real training is blocked')
    groups={};seen_pixels={};by_id={r['sample_id']:r for r in records}
    if len(by_id)!=len(records):blocked.append('Duplicate sample IDs')
    for r in records:
        if r['split'] not in {'train','val','test'}:blocked.append(f"{r['sample_id']}: split missing")
        if not r['capture_group_id'] and r.get('label_origin')=='manual_review':blocked.append(f"{r['sample_id']}: capture group missing")
        # Public Roboflow samples have no reliable identity/capture annotation;
        # keep the publisher's split and report the limitation instead of
        # inventing one vehicle ID per image or blocking all useful positives.
        if r['boxes'] and not r['vehicle_group_ids'] and r.get('label_origin')=='manual_review':
            blocked.append(f"{r['sample_id']}: camera vehicle group missing")
        if file_hash(Path(r['image_path']))!=r['file_sha256']:blocked.append('Image changed after audit')
        for a in r['boxes']:
            if not valid_box(a['bbox'],r['width'],r['height']):blocked.append('Invalid normalized bbox')
        group_ids=(['capture:'+r['capture_group_id']] if r['capture_group_id'] else [])+['vehicle:'+v for v in r['vehicle_group_ids']]
        for group in group_ids:groups.setdefault(group,set()).add(r['split'])
        pixel=r.get('pixel_sha256',r['file_sha256'])
        if pixel in seen_pixels:blocked.append(f"Exact duplicate selected: {seen_pixels[pixel]} / {r['sample_id']}; explicitly reject one")
        seen_pixels[pixel]=r['sample_id']
    for group,splits in groups.items():
        if len(splits)>1:blocked.append(f'Group crosses splits: {group}')
    resolutions={}
    if duplicate_reviews:
        inputs['duplicate_reviews_sha256']=file_hash(duplicate_reviews)
        resolutions={tuple(sorted(r['sample_ids'])):r['resolution'] for r in json.loads(duplicate_reviews.read_text())}
    for pair in pairs:
        ids=pair['sample_ids']
        if not all(x in by_id for x in ids):continue
        if by_id[ids[0]]['split']!=by_id[ids[1]]['split'] and resolutions.get(tuple(sorted(ids)),pair.get('resolution'))!='reviewed_different_observations':
            blocked.append(f'Unresolved cross-split similarity: {ids}')
    counts={s:{'images':sum(r['split']==s for r in records),'boxes':sum(len(r['boxes']) for r in records if r['split']==s),
               'negative_images':sum(r['split']==s and not r['boxes'] for r in records)} for s in ['train','val','test']}
    if not counts['train']['images'] or not counts['val']['images']:blocked.append('Real training requires train and validation; test is sealed separately')
    result={'schema_version':1,'purpose':'reviewed_real_training','class_names':['license_plate'],'records':records,'inputs':inputs,
            'counts':counts,'batch_size':batch_size,'batches_per_epoch':math.ceil(counts['train']['images']/batch_size),
            'groups':{k:sorted(v) for k,v in groups.items()},'excluded':excluded,'blocking_issues':blocked,'training_ready':not blocked,
            'test_policy':'Test is never used for checkpoint/threshold selection; evaluate only frozen checkpoints and thresholds.',
            'split_limit':'Only two camera captures: one capture train, one sealed test; external validation required; no general camera accuracy.'}
    result['group_audit']={'known_vehicle_groups':sum(g.startswith('vehicle:') for g in groups),
        'samples_without_vehicle_identity':sum(bool(r.get('vehicle_group_unknown')) for r in records),
        'public_split_policy':'Roboflow original train/valid/test retained; individual capture and vehicle identities are unknown. Hash audit found no exact or thresholded near-duplicate pairs, but this does not establish complete vehicle leakage prevention.'}
    result['reviewed_metadata_counts']={'vehicle_type':dict(Counter(r['vehicle_type'] for r in records)),
        'layout':dict(Counter(layout for r in records for layout in (r['layout'] if isinstance(r['layout'],list) else [r['layout']]))),
        'manual_hard_negative_regions':sum(len(r['hard_negatives']) for r in records)}
    output.mkdir(parents=True,exist_ok=False,mode=0o700);write_json(output/'manifest.json',result)
    for split in ['train','val','test']:
        images=[];annotations=[]
        for r in records:
            if r['split']!=split:continue
            image_id=len(images)+1;images.append({'id':image_id,'file_name':r['image_path'],'width':r['width'],'height':r['height'],'sample_id':r['sample_id']})
            for a in r['boxes']:
                x1,y1,x2,y2=a['bbox'];annotations.append({'id':len(annotations)+1,'image_id':image_id,'category_id':1,'bbox':[x1,y1,x2-x1,y2-y1],'area':(x2-x1)*(y2-y1),'iscrowd':0})
        write_json(output/f'{split}.coco.json',{'images':images,'annotations':annotations,'categories':[{'id':1,'name':'license_plate'}]})
    return result
