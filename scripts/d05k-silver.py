#!/usr/bin/env python3
"""Three-way silver labels; gold excluded; D05j editor for disagreements."""
import argparse,collections,copy,json,sys,time,uuid,shutil
from pathlib import Path
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.ocr_training_data import load_lock,leakage_reasons,silver_decision,proposed_row_split,pixel_hash
from offline_vision.dataset import sha256,save_png,safe_image,browser_manifest
from offline_vision.export import write_json
from offline_vision.consensus import normalize
from offline_vision.ocr_diagnostic import edit_distance
from offline_vision.plate_recognizer import FastPlateRecognizer
from offline_vision.recognizer import PaddleEnglishRecognizer
from offline_vision.diverse_review_expanded import render_expanded
from offline_vision.sampling import image_hash,hash_distance
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
gold=load_lock(a.evaluation);a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
source=ROOT/'data/offline-vision/runs/d05j-expanded-20261007/cartgmt';manifest=json.loads((source/'manifest.template.json').read_text())
if manifest['detector']['sha256']!='5233aa1b66331feeac6fb1f04e8cf7b5c5104ef1f04578798f3fd0386388794c':raise ValueError('Expected D05f bbox proposals')
write_json(a.output/'plan.json',{'evaluation_sha256':sha256(a.evaluation/'evaluation.lock.json'),'source_manifest_sha256':sha256(source/'manifest.template.json'),'detector_hash':manifest['detector']['sha256'],'detector_gate':.75,'bbox_policy':'exactly one proposal; integer rounded, clipped native crop','english_policy':'original crop; image-only row-projection split if two clear rows, otherwise whole; hypothesis never GT; no OCR variant selection','silver_rule':'normalize raw FastPlate == raw English == every source hint; supported VN syntax; no substitutions or format-ranking','dedupe':'Exclude gold val AND test by original/source SHA, native pixel crop hash, crop dHash<=4, known plate string; camera full transcript from D05f additionally held out; silver exact/near crop duplicates collapsed','fixed_before_inference':True})
models={'fast':FastPlateRecognizer(ROOT/'data/offline-vision/benchmark-models/fast-plate-cct-s-v2'),'english':PaddleEnglishRecognizer(ROOT/'data/offline-vision/benchmark-models/paddle-english-v5')}
# Freeze existing confirmed camera track strings as holdout identities too, including partial.
fp=ROOT/'data/offline-vision/training/d05f-review-20261007/labels.confirmed.json'
held_strings={normalize(x['plate_text']) for f in json.loads(fp.read_text())['frames'] if f['reviewed'] for x in f['annotations'] if x['kind']=='plate' and x['plate_text']}
rows=[];silver=[];queue=[];start=time.perf_counter()
for f in manifest['frames']:
    path=safe_image(source,f['image_path'])
    if sha256(path)!=f['image_sha256']:raise ValueError('Source native image changed')
    image=cv2.imread(str(path));props=f['suggested_plates'];hints=[s['text'] for s in f['source_suggestions']]
    row={'sample_id':f['sample_id'],'source':'cartgmt','source_image_sha256':f['image_sha256'],'original_sha256':f['original_sha256'],'source_hints':hints,'proposal_count':len(props),'detector_score':props[0]['score'] if len(props)==1 else None,'raw_fast':'','raw_english':'','english_raw_lines':[],'split_y_hypothesis':None,'label_origin':None}
    leakage=[]
    if f['original_sha256'] in {r.get('original_sha256') for r in gold['rows']}:leakage.append({'reason':'gold_original_file'})
    if any(normalize(s) in held_strings for s in hints):leakage.append({'reason':'camera_confirmed_plate_identity'})
    crop=None
    if len(props)==1:
        box=[max(0,min(image.shape[1] if k%2==0 else image.shape[0],round(v))) for k,v in enumerate(props[0]['bbox'])];x,y,r,b=box
        if r<=x or b<=y:raise ValueError('Invalid proposal crop')
        crop=image[y:b,x:r];row.update({'bbox':box,'pixel_sha256':pixel_hash(crop),'dhash':str(image_hash(crop)),'native_size':[r-x,b-y]})
        for hint in hints:leakage+=leakage_reasons(image,crop,normalize(hint),gold['rows'],f['original_sha256'])
        # File hashes are checked independently of transcript/crop matching.
        if any(f['image_sha256']==g['source_image_sha256'] for g in gold['rows']):leakage.append({'reason':'gold_native_frame_hash'})
        if not leakage and props[0]['score']>=.75:
            fast,fs=models['fast'].line(crop);split=proposed_row_split(crop);parts=[crop] if split is None else [crop[:split],crop[split:]]
            reads=[models['english'].line(part) for part in parts];eraws=[r[0] for r in reads]
            row.update({'raw_fast':fast,'raw_english':'\n'.join(eraws),'english_raw_lines':eraws,'split_y_hypothesis':split,'fast_uncalibrated_score':fs,'english_uncalibrated_scores':[r[1] for r in reads]})
    status,reason=silver_decision(props,row['raw_fast'],row['raw_english'],hints,leakage)
    row.update({'status':status,'reason':reason,'leakage_evidence':leakage,'normalized_fast':normalize(row['raw_fast']),'normalized_english':normalize(row['raw_english'])})
    row['disagreement']=max([edit_distance(row['normalized_fast'],normalize(h)) for h in hints]+[edit_distance(row['normalized_english'],normalize(h)) for h in hints]+[edit_distance(row['normalized_fast'],row['normalized_english'])])
    if status=='silver':
        near=[s for s in silver if s['pixel_sha256']==row['pixel_sha256'] or hash_distance(s['dhash'],row['dhash'])<=4]
        if near:row.update({'status':'excluded','reason':'silver_near_duplicate','duplicate_of':near[0]['sample_id']})
        else:
            rel='crops/'+f['sample_id']+'.png';save_png(a.output/rel,crop)
            row.update({'label_origin':'silver','split':'train','text':row['normalized_fast'],'crop_path':rel,'crop_sha256':sha256(a.output/rel),'group_id':'plate:'+row['normalized_fast'],'layout':'two-line-hypothesis' if row['split_y_hypothesis'] else 'unknown_or_single-hypothesis'})
            silver.append(copy.deepcopy(row))
    if row['status']=='review':
        frame=copy.deepcopy(f);frame.update({'reviewed':False,'annotations_complete':False,'annotations':[],'plate_presence':'unreviewed','source_decision':'pending','d05k_triage':{'reason':reason,'disagreement':row['disagreement'],'raw_fast':row['raw_fast'],'raw_english':row['raw_english'],'label_origin':'model_proposal'}});queue.append(frame)
    rows.append(row)
    if time.perf_counter()-start>900:raise TimeoutError('900s bounded silver inference exceeded')
queue.sort(key=lambda f:(-f['d05k_triage']['disagreement'],f['sample_id']))
review=a.output/'review';review.mkdir(mode=0o700)
for f in queue:shutil.copy2(safe_image(source,f['image_path']),review/f['image_path']) if (review/f['image_path']).parent.exists() else ( (review/f['image_path']).parent.mkdir(parents=True,exist_ok=True),shutil.copy2(safe_image(source,f['image_path']),review/f['image_path']) )
qm={**manifest,'dataset_id':'d05k-review-'+str(uuid.uuid4()),'purpose':'D05k disagreement only, proposals never gold; human export stays gold val/test for FUTURE evaluation, current frozen evaluation cannot change','frames':queue}
write_json(review/'manifest.template.json',browser_manifest(qm))
if queue:
    render_expanded(qm,review)
    page=(review/'label.html').read_text();controls='<p>D05k · Bất đồng xếp giảm dần; nhãn xác nhận mới không tự thêm vào train/test đã khóa.</p><label>Lọc <select id="queue-filter"><option value="all">Tất cả</option><option value="ocr_disagreement">Bất đồng OCR</option><option value="proposal">BBox thiếu/nhiều/score thấp</option><option value="format">Gợi ý/định dạng</option></select></label><p id="teacher-raw"></p>'
    js=(ROOT/'edge-agent/offline_vision/silver_review_controls.js').read_text()
    page=page.replace('<p id="summary">',controls+'<p id="summary">').replace('</script>',js+'\n</script>');(review/'label.html').write_text(page)
write_json(a.output/'silver.labels.json',{'label_origin':'silver','split':'train','rows':silver,'gold_training_rows':0,'policy_sha256':sha256(a.output/'plan.json')})
write_json(a.output/'audit.json',{'rows':rows,'counts':dict(collections.Counter(r['status'] for r in rows)),'reasons':dict(collections.Counter(r['reason'] for r in rows)),'silver_unique_strings':len({r['text'] for r in silver}),'scope':'Teacher agreement is silver, NOT measured label accuracy. Near hash filtering heuristic; public vehicle identities unknown. No negative images/train without transcript.'})
print(json.dumps({'counts':dict(collections.Counter(r['status'] for r in rows)),'reasons':dict(collections.Counter(r['reason'] for r in rows)),'unique_strings':len({r['text'] for r in silver})},ensure_ascii=False,indent=2))
