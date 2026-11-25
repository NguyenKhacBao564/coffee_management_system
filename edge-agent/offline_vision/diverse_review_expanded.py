"""Expand D05j using the D05b editor, D05f detector and native camera reader."""
import copy
import csv
import hashlib
import json
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from .dataset import browser_manifest, import_csv, save_png, sha256, validate_labels
from .diverse_review import render_labeler, SOURCE_URL, CONDITIONS
from .export import write_json
from .sampling import image_hash
from .selection import frame_quality, vehicle_crop


def import_existing(root, csv_path, output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    shutil.copy2(csv_path, output/'labels.original.csv')
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader=csv.DictReader(stream); fields=reader.fieldnames;rows=list(reader)
    inventory={f['sample_id']:f for f in json.loads((root/'manifest.template.json').read_text())['frames']}
    downgraded=[]
    for r in rows:
        original=inventory.get(r['sample_id'])
        if original is None or any(r[k]!=str(original[k]) for k in ['source_id','image_path']):raise ValueError('CSV source/image inventory mismatch')
        if r['reviewed'].strip().lower()!='true' and r['readability']=='readable':
            downgraded.append(r['sample_id']);r['readability']='pending'
    # Compatibility CSV only changes eligibility, never the archived user file.
    with (output/'labels.eligibility.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    labels=import_csv(root,output/'labels.eligibility.csv')
    for f in labels['frames']:
        f['frame_completeness_from_csv']='unknown: CSV does not export completeness'
        for a in f['annotations']:a['visible_text']=a['plate_text'] if a['readability']=='readable' and f['reviewed'] else ''
    write_json(output/'labels.imported.json',labels)
    counts=validate_labels(labels,root)
    write_json(output/'import-report.json',{'original_sha256':sha256(csv_path),'template_sha256':sha256(root/'manifest.template.json'),'counts':counts,'unreviewed_readable_retained_pending':downgraded,'by_source':dict(Counter((f['source_id']+':'+a['readability']) for f in labels['frames'] for a in f['annotations'])),'limits':'CSV has no color/occlusion/complete-frame metadata. No inference of those fields.'})
    return labels


def render_expanded(manifest, output):
    render_labeler(manifest,output)
    html=(output/'label.html').read_text()
    controls='''<section><p class="notice">Gợi ý của nguồn — KHÔNG phải nhãn xác nhận: <strong id="source-hint"></strong></p><p id="source-status"></p>
<div class="row"><select id="proposal"></select><button id="accept-box">B · Xác nhận bbox đề xuất</button><button id="decide-correct">1 · Đúng / xác nhận bản sửa</button><button id="decide-edit">2 · Sửa chuỗi</button><button id="decide-unreadable">3 · Không đọc được</button><button id="decide-no_plate">4 · Không có biển</button></div>
<p>Crop đề xuất (chỉ để xem, không phải nhãn):</p><img id="proposal-crop" alt="Crop đề xuất từ detector/tham chiếu, chưa xác nhận"><p id="proposal-size"></p>
<div class="row"><label>visible_text (ký tự bị che dùng ?)<input id="visible-text"></label><label>Màu biển<select id="plate_color"><option value="pending">Chưa xác nhận</option><option>white</option><option>yellow</option><option>blue</option><option>other</option></select></label><label>Mức che<select id="occlusion"><option value="pending">Chưa xác nhận</option><option>none</option><option>partial</option><option>heavy</option></select></label><label>Loại xe<select id="vehicle_type"><option value="pending">Chưa xác nhận</option><option>car</option><option>truck</option><option>container</option><option>motorcycle</option><option>other</option></select></label></div>
<div class="row"><button id="page-prev">Trang trước</button><input id="page" type="number" min="1" style="width:70px"><span id="page-total"></span><button id="page-next">Trang sau</button></div><p id="autosave" role="status">Tự lưu localStorage; cần xuất JSON để chuyển nhãn sang công cụ benchmark.</p><p>←/→ đổi ảnh · 1/2/3/4 quyết định · B nhận bbox · S xuất JSON. Sửa bbox bằng xóa/vẽ lại trên ảnh gốc. “Đúng” chỉ dùng cho biển đọc chắc; màu/mức che chưa rõ vẫn pending. Nhãn CSV cũ được giữ.</p></section>'''
    html=html.replace('</style>', '#proposal{max-width:100%}nav select{max-width:100%}.form input,.form select,.form textarea{box-sizing:border-box;width:100%;min-width:0}.row label{max-width:100%}#source-hint{overflow-wrap:anywhere}</style>')
    html=html.replace('Ghi màu biển, che khuất, ánh sáng và loại xe trong Ghi chú hoặc conditions.manual.csv;', 'Dùng ô màu biển, mức che, loại xe và ghi chú;')
    html=html.replace('<p id="summary">',controls+'<p id="summary">')
    html=html.replace('Không có OCR đề xuất trong biểu mẫu này.', 'Chuỗi nguồn và bbox model là đề xuất riêng; chưa xác nhận không được dùng làm ground truth. Xuất JSON để giữ visible_text/màu/mức che; CSV cũ không chứa các trường này.')
    js=(Path(__file__).parent/'diverse_review_controls.js').read_text()
    html=html.replace('</script>', '\n'+js+'\n</script>')
    (output/'label.html').write_text(html)


def _frame(image, output, sample, source, original, **extra):
    relative=f'frames/{sample}.png';save_png(output/relative,image);h,w=image.shape[:2]
    return {'sample_id':sample,'source_id':source,'media_type':'still','media_seconds':None,'frame_index':None,'image_path':relative,'image_sha256':sha256(output/relative),'original_path':str(original),'original_sha256':sha256(original),'scene_hash':str(image_hash(image)),'width':w,'height':h,'capture_group_id':'','split':'unassigned','reviewed':False,'annotations_complete':False,'plate_presence':'unreviewed','suggested_vehicles':[],'suggested_plates':[],'source_suggestions':[],'annotations':[],'notes':'','condition_tags':{k:'pending' for k in CONDITIONS},**extra}


def _proposals(detector,image,seconds=0,offset=(0,0)):
    return [{'bbox':[float(v+offset[k%2]) for k,v in enumerate(d.box)],'score':d.score,'label_origin':'model_proposal','model':'D05f YOLOX-Nano'} for d in detector.detect(image,seconds)]


def _finish(frames,sources,output,audit,detector):
    if not frames:raise ValueError('No eligible source frames')
    manifest={'schema_version':1,'dataset_id':str(uuid4()),'label_origin':'manual_review','purpose':'D05j local human review; no training; proposals separated from ground truth','sources':sources,'frames':frames,'duplicate_reviews':[],'detector':detector.metadata}
    write_json(output/'manifest.template.json',browser_manifest(manifest));render_expanded(manifest,output);write_json(output/'audit.json',audit)
    return manifest


def expand_cartgmt(incoming, old_labels, output, detector):
    output.mkdir(parents=True,exist_ok=False,mode=0o700);folder=incoming/'CarTGMT';report=folder/'_report.csv'
    refs=defaultdict(list)
    for row in csv.reader(report.open(encoding='utf-8-sig')):
        if len(row)>=3 and row[2].strip():refs[row[0]].append({'text':row[2].strip(),'report_flag':row[1],'label_origin':'unconfirmed_source_suggestion'})
    frames=[];pixels={};missing=[];failed=[];duplicate=[];rejected=[];old={f['original_sha256']:f for f in old_labels['frames'] if f['source_id']=='cartgmt'}
    for name,suggestions in sorted(refs.items()):
        path=folder/name
        if Path(name).name!=name or not path.resolve().is_relative_to(folder.resolve()) or path.suffix.lower() not in {'.jpg','.jpeg','.png','.bmp'}:
            rejected.append(name);continue
        if not path.is_file():missing.append(name);continue
        image=cv2.imread(str(path))
        if image is None:failed.append(name);continue
        pixel=hashlib.sha256(image.tobytes()).hexdigest()
        if pixel in pixels:
            f=pixels[pixel];f['source_suggestions'].extend(s for s in suggestions if s not in f['source_suggestions']);f.setdefault('exact_duplicate_sources',[]).append({'path':str(path.resolve()),'sha256':sha256(path)});duplicate.append(name);continue
        f=_frame(image,output,f'cartgmt-{len(frames)+1:04d}','cartgmt',path.resolve(),source_suggestions=suggestions)
        f['suggested_plates']=_proposals(detector,image)
        if f['original_sha256'] in old:
            previous=old[f['original_sha256']]
            for key in ['annotations','reviewed','annotations_complete','plate_presence','capture_group_id','split','notes']:
                f[key]=copy.deepcopy(previous[key])
            f['import_provenance']={'old_sample_id':previous['sample_id'],'method':'exact original file sha256; human CSV only'}
        frames.append(f);pixels[pixel]=f
    pairs=[]
    for i,f in enumerate(frames):
        for other in frames[:i]:
            distance=(int(f['scene_hash'])^int(other['scene_hash'])).bit_count()
            if distance<=4:pairs.append({'left':f['sample_id'],'right':other['sample_id'],'dhash_distance':distance,'resolution':'pending; retained, not automatically deleted'})
    audit={'report_sha256':sha256(report),'report_rows_with_text':sum(len(v) for v in refs.values()),'report_unique_filenames_with_text':len(refs),'missing_images':missing,'rejected_source_paths':rejected,'decode_failures':failed,'exact_duplicates_collapsed':duplicate,'review_images':len(frames),'near_duplicate_pairs':pairs,'transferred_frames':sum('import_provenance' in f for f in frames),'confirmed_readable':sum(f['reviewed'] and a['readability']=='readable' for f in frames for a in f['annotations']),'limits':'Source suggestion is not GT; public vehicle/capture identities unknown. No split or train; near duplicates remain for review.'}
    return _finish(frames,[{'source_id':'cartgmt','path':str(folder.resolve()),'source_url':SOURCE_URL,'category':'main_cartgmt_review','usage':'user_authorized_local_evaluation'}],output,audit,detector)


def separate_motorcycle(old_labels,old_root,output,detector):
    output.mkdir(parents=True,exist_ok=False,mode=0o700);frames=[]
    for old in old_labels['frames']:
        if old['source_id']!='greenparking':continue
        f=copy.deepcopy(old);f['source_suggestions']=[];f['condition_tags']['vehicle_type']='motorcycle';f['source_category']='motorcycle';save_png(output/f['image_path'],cv2.imread(str(old_root/f['image_path'])));frames.append(f)
    return _finish(frames,[s for s in old_labels['sources'] if s['source_id']=='greenparking'],output,{'frames':len(frames),'denominator_policy':'separate motorcycle; never pooled with CarTGMT/camera','priority':'secondary'},detector)


def rank_camera_candidates(group, *, count=1, minimum_seconds=3, excluded_seconds=()):
    """Pick native-frame evidence by image quality, never by OCR or transcript."""
    if not 1 <= count <= 8 or minimum_seconds < 0:raise ValueError('Bounded camera selection required')
    candidates=[g for g in group if all(abs(g[1]-t)>.1 for t in excluded_seconds)]
    if count==1:
        manual=[g for g in candidates if g[4].get('reference_sample_id')]
        candidates=manual or candidates
    selected=[]
    for item in sorted(candidates,key=lambda g:(not bool(g[4].get('reference_sample_id')),-g[0],g[1])):
        if all(abs(item[1]-g[1])>=minimum_seconds for g in selected):selected.append(item)
        if len(selected)==count:break
    return selected


def prepare_camera(run_root,labels_path,output,detector, *, max_frames_per_track=1, candidates_per_track=16, excluded_media=None, reference_window_seconds=0):
    if not 1<=candidates_per_track<=64:raise ValueError('Camera candidate bound exceeded')
    if not 0<=reference_window_seconds<=1:raise ValueError('Nearby bbox reference window must be <=1s')
    excluded_media=excluded_media or {}
    output.mkdir(parents=True,exist_ok=False,mode=0o700);labels=json.loads(labels_path.read_text());frames=[];sources=[];audits=[]
    for num,source in enumerate(labels['sources'],1):
        video=Path(source['path']);records=[json.loads(s) for s in (run_root/f'video{num}'/'sampled-detections.jsonl').read_text().splitlines()];tracks=defaultdict(list)
        for record in records:
            for t in record['tracks']:
                if t['label']=='truck':tracks[t['track_id']].append((record,t))
        cap=cv2.VideoCapture(str(video));candidates=[]
        try:
            for track,rows in tracks.items():
                # Fixed bounded quantiles plus known two-line neighborhoods, no OCR.
                chosen=set(np.linspace(0,len(rows)-1,min(candidates_per_track,len(rows))).round().astype(int))
                for mf in labels['frames']:
                    if mf['source_id']==source['source_id'] and any(an['kind']=='plate' and an.get('layout')=='two-line' for an in mf['annotations']):
                        nearest=min(range(len(rows)),key=lambda j:abs(rows[j][0]['media_seconds']-mf['media_seconds']))
                        if abs(rows[nearest][0]['media_seconds']-mf['media_seconds'])<.05:chosen.add(nearest)
                        if reference_window_seconds:
                            chosen.update(j for j,row in enumerate(rows) if abs(row[0]['media_seconds']-mf['media_seconds'])<=reference_window_seconds)
                chosen=sorted(chosen)
                group=[]
                for pos in chosen:
                    record,t=rows[pos];cap.set(cv2.CAP_PROP_POS_MSEC,record['media_seconds']*1000);ok,image=cap.read()
                    if not ok:continue
                    actual=cap.get(cv2.CAP_PROP_POS_MSEC)/1000;record=copy.deepcopy(record);record['actual_frame_index']=int(cap.get(cv2.CAP_PROP_POS_FRAMES))-1;vcrop,origin=vehicle_crop(image,t['box'])
                    proposals=_proposals(detector,vcrop,actual,origin)
                    two=[p for p in proposals if (p['bbox'][2]-p['bbox'][0])/(p['bbox'][3]-p['bbox'][1])<=3.2 and (p['bbox'][2]-p['bbox'][0])/(p['bbox'][3]-p['bbox'][1])>=1.2]
                    for mf in labels['frames']:
                        if mf['source_id']!=source['source_id'] or abs(mf['media_seconds']-actual)>max(.001,reference_window_seconds) or not mf['reviewed']:continue
                        for an in mf['annotations']:
                            if an['kind']!='plate' or an.get('layout')!='two-line':continue
                            x,y,r,b=an['bbox'];cx,cy=(x+r)/2,(y+b)/2
                            if t['box'][0]<=cx<=t['box'][2] and t['box'][1]<=cy<=t['box'][3]:
                                two.append({'bbox':an['bbox'],'score':None,'label_origin':'reference_from_existing_confirmed_manual_bbox; nearby frame coordinates are ONLY proposals, review native selected frame again','reference_sample_id':mf['sample_id'],'reference_media_seconds':mf['media_seconds'],'model':None})
                    for p in two:
                        q=frame_quality(image,p['bbox']);group.append((q,actual,image,t,p,record))
                # Sharpest 2-line-shaped proposal per temporary track. Layout remains pending.
                picks=rank_camera_candidates(group,count=max_frames_per_track,excluded_seconds=excluded_media.get(source['source_id'],()))
                for pick in picks:
                    q,seconds,image,t,p,record=pick
                    suffix='' if max_frames_per_track==1 else f"-f{record['actual_frame_index']:06d}"
                    sample=f"camera185-{source['source_id']}-{track}{suffix}";f=_frame(image,output,sample,source['source_id'],video,media_type='video',media_seconds=seconds,frame_index=record['actual_frame_index'],capture_group_id=source['capture_group_id'],suggested_vehicles=[{'bbox':t['box'],'score':t['score'],'track_id':track}],suggested_plates=[p],selection={'method':f'best native plate Laplacian variance × sqrt(area) among <={candidates_per_track} quantile media frames plus existing manually labeled 2-line frame times / temporary truck track; >=3s between selected frames','quality':q,'track_id':track,'sampled_media_seconds':record['media_seconds'],'layout_hint':'manual two-line reference if available, otherwise aspect ratio proposal; current review pending','vehicle_hint':'truck/container model proposal; not GT'})
                    f['condition_tags']['vehicle_type']='pending';frames.append(f)
                audits.append({'source':source['source_id'],'track':track,'candidate_frames':len(chosen), 'quantile_cap':candidates_per_track, 'additional_candidates':'existing manual 2-line annotation times, no OCR scoring','two_line_proposals':len(group),'selected':bool(picks),'selected_frames':len(picks)})
        finally:cap.release()
        sources.append(copy.deepcopy(source))
    return _finish(frames,sources,output,{'tracks':audits,'frames':len(frames),'label_source_sha256':sha256(labels_path),'limits':'Temporary vehicle tracks can fragment or include different cars; no long-term vehicle identity. Aspect ratio is proposal only, not confirmed two-line. Native media PTS, no wall-clock inference. visible_text remains pending, no OCR GT.'},detector)


def preserve_cartgmt_imports(old_labels,old_root,output,detector):
    """Expose all old CarTGMT labels, including images without source transcript."""
    output.mkdir(parents=True,exist_ok=False,mode=0o700);frames=[]
    for old in old_labels['frames']:
        if old['source_id']!='cartgmt':continue
        f=copy.deepcopy(old);f['source_suggestions']=[];image=cv2.imread(str(old_root/f['image_path']));save_png(output/f['image_path'],image)
        f['suggested_plates']=_proposals(detector,image);f['import_provenance']={'old_sample_id':old['sample_id'],'method':'validated human CSV; exact native image inventory'};frames.append(f)
    return _finish(frames,[s for s in old_labels['sources'] if s['source_id']=='cartgmt'],output,{'frames':len(frames),'purpose':'Keep all 32 old CarTGMT records reviewable; some lack source report strings and are outside the main419 scope. Exact overlap with main419 must be deduped by pixels before pooling any future benchmark. No pooled metric.'},detector)
