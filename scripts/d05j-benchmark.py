#!/usr/bin/env python3
"""D05j fixed policies; confirmed manual boxes/text only; no model selection/train."""
import argparse,collections,html,json,resource,sys,time
from pathlib import Path
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.dataset import validate_labels,sha256,safe_image,save_png
from offline_vision.export import write_json
from offline_vision.consensus import normalize
from offline_vision.ocr_diagnostic import edit_distance
from offline_vision.plate_recognizer import FastPlateRecognizer
from offline_vision.recognizer import PaddleEnglishRecognizer
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--review-root',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
labels=json.loads(a.labels.read_text())
if labels['dataset_id'].startswith('d05j-ui-fixture'):raise ValueError('UI fixture cannot be human benchmark data')
counts=validate_labels(labels,a.review_root);a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
folders={'fastplate_whole_original':ROOT/'data/offline-vision/benchmark-models/fast-plate-cct-s-v2','english_split_original':ROOT/'data/offline-vision/benchmark-models/paddle-english-v5'}
plan={'policies':['FastPlate whole/original','English split/original'],'fixed_before_inference':True,'labels_sha256':sha256(a.labels),'template_sha256':sha256(a.review_root/'manifest.template.json'),'code_sha256':sha256(Path(__file__)),'model_manifest_sha256':{k:sha256(v/'manifest.json') for k,v in folders.items()},'scope':'explicitly reviewed manual annotations only; full metrics require confirmed complete transcript without ?; partial/unknown preserve visible_text + raw and excluded from full denominator; no source hint GT, no variant selection/training','counts':counts}
write_json(a.output/'plan.json',plan)
models={'fastplate_whole_original':FastPlateRecognizer(folders['fastplate_whole_original']),'english_split_original':PaddleEnglishRecognizer(folders['english_split_original'])};rows=[];skipped=[];start=time.perf_counter()
for f in labels['frames']:
    for an in f['annotations']:
        if an['kind']!='plate':continue
        if not f['reviewed'] or an['readability'] not in {'readable','uncertain','unreadable'} or an.get('layout') not in {'single-line','two-line'} or (an.get('layout')=='two-line' and not (isinstance(an.get('split_y'),int) and an['bbox'][1]<an['split_y']<an['bbox'][3])):
            skipped.append({'sample_id':f['sample_id'],'annotation_id':an['annotation_id'],'reason':'unconfirmed bbox/readability or missing manual layout/split'});continue
        image=cv2.imread(str(safe_image(a.review_root,f['image_path'])));x,y,r,b=an['bbox'];crop=image[y:b,x:r];relative=f"crops/{f['sample_id']}-{an['annotation_id']}.png";save_png(a.output/relative,crop)
        for name,model in models.items():
            parts=[crop]
            if name=='english_split_original' and an['layout']=='two-line':
                split=an['split_y']-y;parts=[crop[:split],crop[split:]]
            elapsed=time.perf_counter();process_elapsed=time.process_time();raws=[model.line(part)[0] for part in parts];elapsed=time.perf_counter()-elapsed;process_elapsed=time.process_time()-process_elapsed
            raw='\n'.join(raws);full_gt=an['readability']=='readable' and bool(an['plate_text'].strip()) and '?' not in an['plate_text'];gt=normalize(an['plate_text']) if full_gt else '';prediction=normalize(raw);conditions=an.get('condition_tags',f.get('condition_tags',{}))
            rows.append({'sample_id':f['sample_id'],'source':f['source_id'],'category':'motorcycle' if f['source_id']=='greenparking' else f['source_id'],'annotation_id':an['annotation_id'],'model':name,'crop':relative,'native_size':[crop.shape[1],crop.shape[0]],'ground_truth':an['plate_text'] if full_gt else '', 'visible_text':an.get('visible_text',''),'full_ground_truth_available':full_gt,'raw_prediction':raw,'prediction':prediction,'exact':prediction==gt if full_gt else None,'edit_errors':edit_distance(prediction,gt) if full_gt else None,'characters':len(gt),'cpu_wall_seconds':elapsed,'cpu_process_seconds':process_elapsed,'layout':an['layout'],'plate_color':conditions.get('plate_color','pending'),'occlusion':conditions.get('occlusion','pending'),'unique_plate_key':gt if full_gt else None,'preprocess':model.metadata.get('preprocess','Official Paddle BGR aspect-preserving height48; width>=320, normalized [-1,1], right zero padding; manual row split for two-line')})
        if time.perf_counter()-start>600:raise TimeoutError('Bounded 600s CPU benchmark exceeded')
metrics=[]
# Each source/category has its own denominator. No global mixed-source score.
for name in models:
    for category in sorted({r['category'] for r in rows}):
        group=[r for r in rows if r['model']==name and r['category']==category]
        for field in ['category','layout','plate_color','occlusion']:
            for value in sorted({r[field] for r in group}):
                subset=[r for r in group if r[field]==value];chars=sum(r['characters'] for r in subset)
                metrics.append({'model':name,'category':category,'stratum':field,'value':value,'correct':sum(r['exact'] is True for r in subset),'samples':sum(r['full_ground_truth_available'] for r in subset),'reviewed_crops':len(subset),'partial_or_unknown_full_gt':sum(not r['full_ground_truth_available'] for r in subset),'unique_plates':len({r['unique_plate_key'] for r in subset if r['unique_plate_key']}),'edit_errors':sum(r['edit_errors'] or 0 for r in subset),'characters':chars,'cpu_wall_seconds_per_crop':sum(r['cpu_wall_seconds'] for r in subset)/len(subset),'cpu_process_seconds_per_crop':sum(r['cpu_process_seconds'] for r in subset)/len(subset)})
summary={'metrics':metrics,'rows':rows,'skipped':skipped,'model_metadata':{k:v.metadata for k,v in models.items()},'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'rss_scope':'whole two-model process on macOS, not isolated model RAM','limits':'Manual CSV lacks color/occlusion and complete-frame flags. Pending conditions kept unknown; no general accuracy, no source hints used as GT. Unique normalized confirmed strings do not prove unique vehicles.'};write_json(a.output/'summary.json',summary)
import csv
with (a.output/'predictions.csv').open('w',encoding='utf-8-sig',newline='') as stream:
    if rows:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
esc=html.escape
cards=''.join(f"<section><h3>{esc(r['sample_id'])} · {esc(r['model'])}</h3><img src='{esc(r['crop'])}'><p>Nhãn toàn biển: {esc(r['ground_truth'])} · visible_text: {esc(r['visible_text'])} · raw: {esc(r['raw_prediction'])} · {'CHƯA CÓ GT TOÀN BIỂN' if r['exact'] is None else 'ĐÚNG' if r['exact'] else 'SAI'}</p><p>{r['native_size']} · {esc(r['layout'])} · màu {esc(r['plate_color'])} · che {esc(r['occlusion'])}</p></section>" for r in rows)
(a.output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>D05j OCR</title><style>body{font:16px system-ui;margin:24px}section{padding:12px;border-bottom:1px solid #bbb}img{max-width:95%;image-rendering:auto}</style><h1>D05j · Nhãn thủ công và raw OCR</h1><p>FastPlate whole/original; English split/original; không chọn biến thể theo kết quả. Nhóm motorcycle tách mẫu số.</p>'+cards)
print(json.dumps({'rows':len(rows),'metrics':[m for m in metrics if m['stratum'] in ['category','layout']],'peak_rss_mib':summary['peak_process_rss_bytes']/2**20},ensure_ascii=False,indent=2))
