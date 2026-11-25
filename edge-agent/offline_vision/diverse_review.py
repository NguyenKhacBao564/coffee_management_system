"""D05j preparation using the existing D05b labeler, no OCR or inferred GT."""
import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from .dataset import sha256, save_png, browser_manifest, export_blank_csv
from .export import write_json
from .sampling import image_hash

CONDITIONS = ['plate_color', 'layout', 'vehicle_type', 'occlusion', 'lighting', 'blur', 'angle', 'pass_id', 'vehicle_group_id', 'capture_group_id']
SOURCE_URL = 'https://thigiacmaytinh.com/tai-nguyen-xu-ly-anh/tong-hop-data-xu-ly-anh/'


def render_labeler(manifest, output):
    template=(Path(__file__).parent/'labeling.html').read_text()
    needle='media ${f.media_seconds.toFixed(3)} giây · frame ${f.frame_index}'
    if needle not in template:raise ValueError('Existing labeler changed; review still-image adaptation')
    template=template.replace(needle,"${f.media_type==='still'?'Ảnh tĩnh · không có timestamp media':`media ${f.media_seconds.toFixed(3)} giây · frame ${f.frame_index}`}" )
    template=template.replace('${f.media_seconds.toFixed(3)}s',"${f.media_seconds===null?'ảnh tĩnh':f.media_seconds.toFixed(3)+'s'}")
    template=template.replace('D05b ·','D05j ·')
    template=template.replace('Vẽ bbox trên ảnh gốc.', 'Vẽ bbox trên ảnh gốc. Ghi màu biển, che khuất, ánh sáng và loại xe trong Ghi chú hoặc conditions.manual.csv; giữ split chưa chia tập.')
    embedded=json.dumps(browser_manifest(manifest),ensure_ascii=False).replace('<','\\u003c')
    (output/'label.html').write_text(template.replace('__MANIFEST_JSON__',embedded))


def prepare(incoming, output, per_source=32):
    if not 1 <= per_source <= 100:
        raise ValueError('Bounded review requires 1..100 images per source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    entries, audits, sources = [], [], []
    for name in ['CarTGMT', 'GreenParking']:
        folder=incoming/name
        if not folder.is_dir():
            audits.append({'source':name,'status':'missing'});continue
        sources.append({'source_id':name.lower(),'path':str(folder.resolve()),'media_type':'still_images',
                        'license_status':'publisher_shares_testing_samples_no_explicit_redistribution_terms',
                        'source_url':SOURCE_URL,'usage':'user_authorized_local_evaluation; no training or redistribution in this task'})
        files=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.bmp'})
        failures=[]; rows=[]
        for p in files:
            image=cv2.imread(str(p))
            if image is None:
                failures.append({'path':str(p),'reason':'image_decode_failed'});continue
            gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
            h,w=image.shape[:2]
            rows.append({'source':name,'path':str(p.resolve()),'sha256':sha256(p),'width':w,'height':h,
                         'scene_hash':str(image_hash(image)), 'brightness':float(gray.mean()),
                         'sharpness_laplacian':float(cv2.Laplacian(gray,cv2.CV_64F).var()),
                         'pixel_sha256':__import__('hashlib').sha256(image.tobytes()).hexdigest(),
                         'license_status':'unverified','transcript':None,'ground_truth_confirmed':False})
        entries.extend(rows)
        audits.append({'source':name,'image_files':len(files),'readable_images':len(rows),'decode_failures':failures,
                       'other_metadata_files':[{'path':str(p.resolve()),'sha256':sha256(p)} for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() not in {'.jpg','.jpeg','.png','.bmp'}],
                       'source_labels':'Names/report/location retained as unverified references, not imported as ground truth or visible OCR targets'})
    # Full-frame dHash flags suspicious pairs; does not prove vehicle identity.
    pairs=[]; parents=list(range(len(entries)))
    def find(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for i,left in enumerate(entries):
        for j in range(i):
            right=entries[j]
            distance=(int(left['scene_hash'])^int(right['scene_hash'])).bit_count()
            exact=left['sha256']==right['sha256'] or left['pixel_sha256']==right['pixel_sha256']
            if exact or distance<=4:
                pairs.append({'left':i,'right':j,'exact':exact,'dhash_distance':distance,'cross_source':left['source']!=right['source']})
                parents[find(i)]=find(j)
    for i,e in enumerate(entries):e['suspected_duplicate_group']=f"dup-{find(i):05d}"
    selected=[]
    for source in sources:
        candidates=[r for r in entries if r['source'].lower()==source['source_id']]
        # Balanced measured brightness strata, then dHash novelty; no OCR/GT.
        ordered=sorted(candidates,key=lambda r:(r['brightness'],r['sha256']))
        seen=set()
        buckets=min(per_source,len(ordered))
        for b in range(buckets):
            options=ordered[b*len(ordered)//buckets:(b+1)*len(ordered)//buckets]
            options=[r for r in options if r['suspected_duplicate_group'] not in seen]
            if not options:continue
            chosen=max(options,key=lambda r:(min(((int(r['scene_hash'])^int(s['scene_hash'])).bit_count() for s in selected),default=64),r['sharpness_laplacian'],r['sha256']))
            selected.append(chosen);seen.add(chosen['suspected_duplicate_group'])
    frames=[]
    for index,row in enumerate(selected):
        image=cv2.imread(row['path']);relative=f'frames/sample-{index+1:04d}.png';save_png(output/relative,image)
        frames.append({'sample_id':f"d05j-{index+1:04d}",'source_id':row['source'].lower(),'media_type':'still',
            'media_seconds':None,'frame_index':None,'image_path':relative,'image_sha256':sha256(output/relative),
            'original_path':row['path'],'original_sha256':row['sha256'],'scene_hash':row['scene_hash'],
            'width':row['width'],'height':row['height'],'capture_group_id':'','suspected_duplicate_group':row['suspected_duplicate_group'],
            'split':'unassigned','reviewed':False,'annotations_complete':False,'plate_presence':'unreviewed',
            'suggested_vehicles':[],'suggested_plates':[],'annotations':[],'notes':'',
            'condition_tags':{field:'pending' for field in CONDITIONS},'license_status':'unverified'})
    manifest={'schema_version':1,'dataset_id':str(uuid4()),'label_origin':'manual_review_required',
        'purpose':'D05j diverse review, no OCR benchmark/train approval; source license and vehicle/capture groups pending',
        'selection':{'method':'fixed brightness strata + full-frame dHash novelty, no recognizer','per_source_cap':per_source},
        'sources':sources,'frames':frames,'duplicate_reviews':[]}
    write_json(output/'manifest.template.json',browser_manifest(manifest));export_blank_csv(output/'labels.template.csv',manifest)
    render_labeler(manifest,output)
    import csv
    with (output/'conditions.manual.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['sample_id']+CONDITIONS);writer.writeheader()
        for frame in frames:writer.writerow({'sample_id':frame['sample_id'],**frame['condition_tags']})
    char_folders=[]
    for name in ['greenparking2char','greenparkingchar']:
        folder=incoming/name
        if folder.is_dir():
            char_folders.append({'source':name,'files':sum(p.is_file() for p in folder.iterdir()),'usage':'not used: isolated character images cannot evaluate whole plates; license unverified'})
    audit={'sources':audits,'total_readable_images':len(entries),'selected_frames':len(frames),
           'selected_by_source':dict(Counter(f['source_id'] for f in frames)),
           'exact_duplicate_pairs':sum(p['exact'] for p in pairs),'near_duplicate_pairs':sum(not p['exact'] for p in pairs),
           'cross_source_pairs':sum(p['cross_source'] for p in pairs),'pairs':pairs,'entries':entries,'character_folders':char_folders,
           'limits':'No manual labels/conditions/vehicle identity/license verified; splits unassigned, no OCR accuracy. Full-frame dHash is triage only; crop duplicates must be rechecked after labels. No demonstrated new yellow/occluded-container coverage.'}
    write_json(output/'audit.json',audit)
    # Native PNG contact sheets only downscale for display; original frames retained.
    for start in range(0,len(frames),16):
        sheet=np.full((4*210,4*300,3),245,np.uint8)
        for k,frame in enumerate(frames[start:start+16]):
            image=cv2.imread(str(output/frame['image_path']));h,w=image.shape[:2];scale=min(290/w,170/h)
            thumb=cv2.resize(image,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
            y,x=(k//4)*210,(k%4)*300;sheet[y:y+thumb.shape[0],x:x+thumb.shape[1]]=thumb
            cv2.putText(sheet,frame['sample_id']+' '+frame['source_id'],(x+5,y+193),cv2.FONT_HERSHEY_SIMPLEX,.38,(20,20,20),1)
        save_png(output/f'contact-{start//16+1}.jpg',sheet)
    for p in output.iterdir():
        if p.is_file():p.chmod(0o600)
    return {k:v for k,v in audit.items() if k not in {'pairs','entries','sources'}}
