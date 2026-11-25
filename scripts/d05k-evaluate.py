#!/usr/bin/env python3
"""One locked test evaluation AFTER validation selection; no runtime replacement."""
import argparse,csv,html,json,sys,time
from pathlib import Path
import cv2,numpy as np,onnxruntime as ort,yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.ocr_training_data import load_lock
from offline_vision.dataset import sha256
from offline_vision.export import write_json
from offline_vision.plate_recognizer import plate_input,slot_decode,CONFIG_SHA256
from offline_vision.ocr_diagnostic import edit_distance
from offline_vision.consensus import normalize
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();gold=load_lock(a.evaluation)
state=json.loads((a.results/'state.json').read_text());parity=json.loads((a.results/'onnx-parity.json').read_text())
if not parity['passed'] or not state['best_validation'] or state['stop_reason']!='epochs_complete':raise ValueError('Require completed bounded training, val choice, passed ONNX parity first')
config=ROOT/'data/offline-vision/benchmark-models/fast-plate-cct-s-v2/cct_s_v2_global_plate_config.yaml'
if sha256(config)!=CONFIG_SHA256:raise ValueError('Pinned preprocess config changed')
pc=yaml.safe_load(config.read_text());model=a.results/'detector-ocr.onnx'
if sha256(model)!=parity['onnx_sha256']:raise ValueError('Downloaded ONNX hash differs')
baseline=json.loads((a.evaluation/'baseline.json').read_text());before={r['sample_id']:r for r in baseline['rows']}
for name,digest in json.loads((a.evaluation/'baseline.hashes.json').read_text()).items():
    if sha256(a.evaluation/name)!=digest:raise ValueError('Locked baseline changed')
a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
write_json(a.output/'plan.json',{'evaluation_sha256':sha256(a.evaluation/'evaluation.lock.json'),'onnx_sha256':sha256(model),'checkpoint':state['chosen_checkpoint'],'checkpoint_sha256':sha256(a.results/state['chosen_checkpoint']),'selection':'gold val source macro exact/CER only; earliest tie. Test never selects threshold/preprocess/epoch.','preprocess':'same pinned whole/original RGB linear stretch128x64; float32 transport0..255, embedded normalization','code_sha256':sha256(Path(__file__))})
options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1;sess=ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider']);name=sess.get_inputs()[0].name;rows=[]
for item in gold['rows']:
    image=cv2.imread(str(a.evaluation/item['crop_path']));blob=plate_input(image,pc);start=time.perf_counter();raw,score,_=slot_decode(sess.run(None,{name:blob.astype(np.float32)})[0],pc);elapsed=time.perf_counter()-start;pred=normalize(raw);gt=item['text']
    old=before[item['sample_id']]
    rows.append({**item,'pretrained_raw':old['raw_prediction'],'pretrained_exact':old['exact'],'fine_tuned_raw':raw,'fine_tuned_exact':pred==gt if gt else None,'fine_tuned_errors':edit_distance(pred,gt) if gt else None,'pretrained_errors':old['edit_errors'],'characters':len(gt),'cpu_wall_seconds':elapsed,'uncalibrated_score':score})
metrics=[]
for split in ['val','test']:
    for source in sorted({r['source'] for r in rows}):
        group=[r for r in rows if r['split']==split and r['source']==source]
        for field in ['source','readability','layout','plate_color','occlusion','crop_source']:
            for value in sorted({r[field] for r in group}):
                sub=[r for r in group if r[field]==value];metrics.append({'split':split,'source':source,'stratum':field,'value':value,'crops':len(sub),'denominator':sum(bool(r['text']) for r in sub),'unique_full_strings':len({r['text'] for r in sub if r['text']}),'pretrained_correct':sum(r['pretrained_exact'] is True for r in sub),'fine_tuned_correct':sum(r['fine_tuned_exact'] is True for r in sub),'pretrained_errors':sum(r['pretrained_errors'] or 0 for r in sub),'fine_tuned_errors':sum(r['fine_tuned_errors'] or 0 for r in sub),'characters':sum(r['characters'] for r in sub)})
main=next(m for m in metrics if m['split']=='test' and m['source']=='camera185' and m['stratum']=='source')
secondary=[m for m in metrics if m['split']=='test' and m['source']!='camera185' and m['stratum']=='source']
improved=main['fine_tuned_correct']>main['pretrained_correct'] or (main['fine_tuned_correct']==main['pretrained_correct'] and main['fine_tuned_errors']<main['pretrained_errors'])
not_worse=all(m['fine_tuned_correct']>=m['pretrained_correct'] and m['fine_tuned_errors']<=m['pretrained_errors'] for m in secondary)
summary={'rows':rows,'metrics':metrics,'runtime_replacement_proposed':improved and not_worse,'runtime_changed':False,'primary_improved':improved,'secondary_not_worse':not_worse,'partial_policy':'Partial/unreadable: no full exact/CER; known human lines retained, raw suggestions never GT. No row metrics from whole model without row boundaries.','limits':'Camera only two captures, one full-readable plate repeated26crops; public capture/vehicle and pretrained-training overlap unknown. Color/occlusion pending: no confirmed yellow/occluded metric. No test-tuned retry.'};write_json(a.output/'comparison.json',summary)
with (a.output/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as s:
    w=csv.DictWriter(s,fieldnames=sorted({k for r in rows for k in r}));w.writeheader();w.writerows(rows)
cards=''.join(f"<section><h3>{html.escape(r['sample_id'])} · {r['source']} · {r['split']} · {r['readability']}</h3><img src='../evaluation/{r['crop_path']}'><p>GT: {html.escape(r['text'] or str(r['known_lines']))}<br>Pretrained: {html.escape(r['pretrained_raw'])} · fine-tuned: {html.escape(r['fine_tuned_raw'])}</p></section>" for r in rows)
(a.output/'review.html').write_text('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>D05k trước/sau</title><style>body{font:16px system-ui;margin:24px}section{padding:12px;border-bottom:1px solid #aaa}img{max-width:95%;image-rendering:pixelated}</style><h1>D05k · Pretrained / fine-tuned trên gold khóa</h1><p>Chọn checkpoint bằng val; partial không có GT toàn biển. Giữ raw, không ép ký tự/đổi preprocess.</p>'+cards)
write_json(a.output/'hashes.json',{name:sha256(a.output/name) for name in ['plan.json','comparison.json','comparison.csv','review.html']})
print(json.dumps({'metrics':[m for m in metrics if m['stratum'] in ['source','readability']],'runtime_replacement_proposed':summary['runtime_replacement_proposed']},ensure_ascii=False,indent=2))
