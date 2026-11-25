#!/usr/bin/env python3
"""Freeze gold BEFORE new inference; same D05j whole/original FastPlate policy."""
import argparse,csv,html,json,sys,time,resource
from pathlib import Path
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.ocr_training_data import lock_gold,load_lock
from offline_vision.dataset import sha256
from offline_vision.export import write_json
from offline_vision.plate_recognizer import FastPlateRecognizer
from offline_vision.ocr_diagnostic import edit_distance
from offline_vision.consensus import normalize
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--finish-report',action='store_true',help='Recover CSV/HTML export from already frozen baseline; no inference or relabeling');a=p.parse_args()
gold=load_lock(a.output) if a.finish_report else lock_gold(ROOT,a.output)
folder=ROOT/'data/offline-vision/benchmark-models/fast-plate-cct-s-v2'
if a.finish_report:
    result=json.loads((a.output/'baseline.json').read_text());rows=result['rows'];metrics=result['metrics']
else:
    rows=None
if rows is None:
    write_json(a.output/'baseline.plan.json',{'evaluation_sha256':sha256(a.output/'evaluation.lock.json'),'model_manifest_sha256':sha256(folder/'manifest.json'),'code_sha256':sha256(Path(__file__)),'policy':'FastPlate CCT-S v2 pretrained whole/original; 128x64 RGB linear stretch embedded normalization; raw argmax only; no variant selection','fixed_before_inference':True})
    model=FastPlateRecognizer(folder);start=time.perf_counter();rows=[]
    for item in gold['rows']:
        image=cv2.imread(str(a.output/item['crop_path']));before=time.perf_counter();raw,score=model.line(image);elapsed=time.perf_counter()-before
        prediction=normalize(raw);gt=item['text'];row={**item,'raw_prediction':raw,'prediction':prediction,'score':score,'seconds':elapsed,'exact':prediction==gt if gt else None,'edit_errors':edit_distance(prediction,gt) if gt else None,'characters':len(gt)};rows.append(row)
        if time.perf_counter()-start>600:raise TimeoutError('600s bounded benchmark')
    metrics=[]
    for split in ['val','test']:
        for source in sorted({r['source'] for r in rows}):
            group=[r for r in rows if r['split']==split and r['source']==source]
            for field in ['source','readability','layout','plate_color','occlusion','crop_source']:
                for value in sorted({r[field] for r in group}):
                    sub=[r for r in group if r[field]==value]
                    metrics.append({'split':split,'source':source,'stratum':field,'value':value,'crops':len(sub),'exact_correct':sum(r['exact'] is True for r in sub),'exact_denominator':sum(bool(r['text']) for r in sub),'edit_errors':sum(r['edit_errors'] or 0 for r in sub),'characters':sum(r['characters'] for r in sub),'unique_confirmed_strings':len({r['text'] for r in sub if r['text']}),'seconds_per_crop':sum(r['seconds'] for r in sub)/len(sub)})
    write_json(a.output/'baseline.json',{'rows':rows,'metrics':metrics,'model_metadata':model.metadata,'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'partial_policy':'Full exact/CER undefined for partial or unreadable; keep raw and confirmed known lines, never promote D05f full transcript into crop GT.'})
with (a.output/'baseline.csv').open('w',newline='',encoding='utf-8-sig') as s:
    w=csv.DictWriter(s,fieldnames=sorted({k for r in rows for k in r}));w.writeheader();w.writerows(rows)
cards=''.join(f"<section><h3>{html.escape(r['sample_id'])} · {r['split']} · {r['readability']}</h3><img src='{r['crop_path']}'><p>GT: {html.escape(r['text'] or str(r['known_lines']))} · raw: {html.escape(r['raw_prediction'])}</p></section>" for r in rows)
(a.output/'baseline.html').write_text('<meta charset="utf-8"><title>D05k baseline khóa</title><style>body{font:16px system-ui;margin:20px}section{padding:12px;border-bottom:1px solid #aaa}img{max-width:95%;image-rendering:pixelated}</style><h1>D05k · FastPlate pretrained · gold khóa</h1>'+cards)
write_json(a.output/'baseline.hashes.json',{n:sha256(a.output/n) for n in ['evaluation.lock.json','baseline.plan.json','baseline.json','baseline.csv','baseline.html']})
load_lock(a.output)
print(json.dumps({'evaluation_sha256':sha256(a.output/'evaluation.lock.json'),'metrics':[m for m in metrics if m['stratum'] in ['source','readability']]},ensure_ascii=False,indent=2))
