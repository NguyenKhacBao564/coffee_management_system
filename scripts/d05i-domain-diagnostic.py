#!/usr/bin/env python3
"""D05i Phase 3 offline diagnosis. Never modifies locked Phase 2 or runtime."""
import argparse
import csv
import html
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'edge-agent'))
from offline_vision.consensus import normalize, decide
from offline_vision.dataset import sha256, safe_image
from offline_vision.export import write_json
from offline_vision.ocr_diagnostic import parts_for, edit_distance
from offline_vision.plate_recognizer import FastPlateRecognizer, plate_input, slot_decode
from offline_vision.recognizer import PaddleEnglishRecognizer, paddle_input, ctc_decode
from offline_vision.plate_domain import rank_slots, ctc_beam, character_vote, unique_frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase2', type=Path, required=True)
    parser.add_argument('--d05f-labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    previous = json.loads((args.phase2/'summary.json').read_text())
    prior = previous['plan']; review = Path(prior['review_root'])
    labels_path = Path(prior['labels_path'])
    if sha256(labels_path) != prior['labels_sha256']: raise ValueError('Frozen labels changed')
    labels = json.loads(labels_path.read_text())
    items = {i['crop_id']: i for i in labels['items']}
    d05f = json.loads(args.d05f_labels.read_text())
    annotations = {(f['sample_id'], a['annotation_id']): a for f in d05f['frames'] for a in f['annotations'] if a['kind']=='plate' and f['reviewed'] and f.get('annotations_complete')}
    session_paths = {f'v00{v}': ROOT/f'data/offline-vision/runs/d05f-vast-54567374/video{v}/result.json' for v in (1,2)}
    sessions = {source: json.loads(path.read_text())['sessions'] for source,path in session_paths.items()}
    folders = {'fast_plate_cct_s_v2':ROOT/'data/offline-vision/benchmark-models/fast-plate-cct-s-v2', 'english_mobile':ROOT/'data/offline-vision/benchmark-models/paddle-english-v5'}
    policy = {'purpose':'D05i Phase3, fixed diagnosis not threshold/variant selection',
        'main':'fast_plate_cct_s_v2 whole/original','comparator':'english_mobile split/original',
        'beam_width_ctc':64,'beam_width_slots':32,'token_top_k_ctc':5,'candidate_top_k':5,
        'max_candidate_log_score_loss':3.0,'minimum_candidate_log_margin':math.log(2),
        'minimum_distinct_frames':3,'minimum_character_support':2,'vote_ratio':2/3,
        'max_wall_seconds':600,'tracks':'Frozen D05f session intervals with exactly one track; temporal association only, not spatial track validation',
        'format_scope':'Domestic one-letter, CD/RM/HC/KT, blue motorcycle letter+1..9; 5 suffix digits plus legacy 4. Province is syntax only, no current allocation validation; outside subset unknown.',
        'format_sources':['https://hue.gov.vn/Portals/0/VBPL/Nam2024/T12/79-bca.signed.pdf',
          'https://xaydungchinhsach.chinhphu.vn/mau-sac-seri-ky-hieu-bien-so-xe-cua-co-quan-to-chuc-ca-nhan-tu-01-01-2025-119241225071905346.htm',
          'https://xdcs.cdnchinhphu.vn/446259493575335936/2026/4/29/37-bca-17774475322131775956925.pdf'],
        'phase2_file_hashes':{str(p.relative_to(args.phase2)):sha256(p) for p in sorted(args.phase2.rglob('*')) if p.is_file()},
        'readability_labels_sha256':sha256(labels_path),'d05f_labels_sha256':sha256(args.d05f_labels),
        'session_hashes':{s:sha256(p) for s,p in session_paths.items()},
        'code_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in [Path(__file__),ROOT/'edge-agent/offline_vision/plate_domain.py']},
        'model_manifest_hashes':{name:sha256(path/'manifest.json') for name,path in folders.items()},
        'providers':['CPUExecutionProvider'],'runtime_config_changed':False}
    write_json(args.output/'plan.json',policy)  # before model init/inference
    old_rows = [r for m in previous['models'] for r in m['rows']]
    supplement=[]
    for old in old_rows:
        if old['model']=='fast_plate_cct_s_v2' and old['mode']=='whole' and old['variant']=='original' and old['readability']=='readable_partial':
            item=items[old['crop_id']]; ann=annotations[(item['sample_id'],item['annotation_id'])]
            target=ann['plate_text'] if ann.get('readability')=='readable' else None
            supplement.append({'crop_id':old['crop_id'],'raw':old['raw'],'normalized':old['normalized'],'d05f_transcript':target,
                'match':normalize(target)==old['normalized'] if target else None,'media_seconds':old['media_seconds']})
    write_json(args.output/'phase2-observation-d05f-transcript.json', {'label':'quan sát chẩn đoán dựa trên transcript D05f',
        'correct':sum(r['match'] is True for r in supplement),'denominator':sum(r['match'] is not None for r in supplement),
        'readability_metrics_unchanged':True,'d05f_labels_sha256':sha256(args.d05f_labels),'rows':supplement})
    rows=[]; started=time.perf_counter()
    for name,folder in folders.items():
        if sha256(folder/'manifest.json') != prior['model_manifest_sha256'][name]: raise ValueError('Model provenance changed')
        model=FastPlateRecognizer(folder) if name.startswith('fast') else PaddleEnglishRecognizer(folder)
        mode='whole' if name.startswith('fast') else 'split'
        selected=[r for r in old_rows if r['model']==name and r['mode']==mode and r['variant']=='original']
        for old in selected:
            if time.perf_counter()-started>policy['max_wall_seconds']: raise TimeoutError('Bound reached')
            item=items[old['crop_id']]; path=safe_image(review,item['crop_path'])
            if sha256(path)!=item['crop_sha256']: raise ValueError('Native crop changed')
            image=cv2.imread(str(path)); clock=time.perf_counter()
            parts,names=parts_for(item,image,mode,'original')
            if name.startswith('fast'):
                blob=plate_input(parts[0],model.config)
                probabilities=model.session.run([model.output],{model.input:blob})[0].reshape(model.config['max_plate_slots'],-1)
                raw,_,slots=slot_decode(probabilities,model.config)
                ranked=rank_slots(probabilities,model.config['alphabet'],width=policy['beam_width_slots'])
                base_score=float(np.log(np.maximum(probabilities.max(axis=1),1e-300)).sum())
                np.savez_compressed(args.output/f"{name}-{item['crop_id']}.npz",probabilities=probabilities)
            else:
                matrices=[]; lines=[]
                for part in parts:
                    blob=paddle_input(part); probs=model.session.run(None,{model.input:blob})[0][0]
                    lines.append(ctc_decode(probs,model.characters)[0]); matrices.append(probs)
                raw='\n'.join(lines)
                if len(matrices)>1:
                    blank=np.zeros((1,len(model.characters)));blank[0,0]=1
                    probabilities=np.concatenate([matrices[0],blank,matrices[1]])
                else: probabilities=matrices[0]
                unconstrained=ctc_beam(probabilities,model.characters,constrained=False)
                base_score=unconstrained[0]['log_score'] if unconstrained else -math.inf
                ranked=ctc_beam(probabilities,model.characters)
                np.savez_compressed(args.output/f"{name}-{item['crop_id']}.npz",probabilities=probabilities)
            if raw!=old['raw']: raise ValueError('Primary raw changed from Phase2; refuse silent rerun update')
            best=ranked[0] if ranked else None
            delta=best['log_score']-base_score if best else None
            margin=best['log_score']-ranked[1]['log_score'] if len(ranked)>1 else None
            proposal=best['normalized'] if best and delta>=-policy['max_candidate_log_score_loss'] and (margin is None or margin>=policy['minimum_candidate_log_margin']) else None
            association=[s for s in sessions[item['source_id']] if s['start_media_seconds']<=item['media_seconds']<=s['end_media_seconds'] and len(s['track_ids'])==1]
            track=f"{item['source_id']}/{association[0]['session_id']}/{association[0]['track_ids'][0]}" if len(association)==1 else None
            ann=annotations[(item['sample_id'],item['annotation_id'])]
            target=old['scores']['full']['manual_target']
            rows.append({'crop_id':item['crop_id'],'sample_id':item['sample_id'],'model':name,'mode':mode,'variant':'original',
                'crop_source':item['crop_source'],'media_seconds':item['media_seconds'],'track_id':track,
                'raw':raw,'normalized':normalize(raw),'ranked_format_candidates':ranked,'format_proposal':proposal,
                'format_score_loss_from_unconstrained':delta,'format_top2_log_margin':margin,'needs_confirmation':True,
                'full_target_readability':target,'before_full_correct':normalize(raw)==normalize(target) if target else None,
                'after_full_correct':proposal==normalize(target) if target else None,
                'before_edit_errors':edit_distance(normalize(raw),normalize(target)) if target else None,
                'after_edit_errors':edit_distance(proposal or '',normalize(target)) if target else None,
                'd05f_transcript_diagnostic':ann.get('plate_text') if ann.get('readability')=='readable' else None,
                'wall_seconds_with_beam':time.perf_counter()-clock})
    track_groups={}
    for row in rows:
        if row['track_id']: track_groups.setdefault((row['model'],row['crop_source'],row['track_id']),[]).append(row)
    tracks=[]
    for (model,source,track),group in sorted(track_groups.items()):
        result={'model':model,'crop_source':source,'track_id':track,'crops':len(group),'distinct_frames':len({r['media_seconds'] for r in group})}
        transcripts={normalize(r['d05f_transcript_diagnostic']) for r in group if r['d05f_transcript_diagnostic']}
        target=next(iter(transcripts)) if len(transcripts)==1 else None
        result['d05f_transcript_diagnostic']=target
        for input_kind in ['raw','format']:
            reads=[{'track_id':track,'media_seconds':r['media_seconds'],'normalized':r['normalized'] if input_kind=='raw' else r['format_proposal'] or '', 'read_index':i,'crop_id':r['crop_id']} for i,r in enumerate(group)]
            observations=unique_frames(reads)
            unique=[{'media_seconds':r['media_seconds'],'normalized':r['normalized'],'read_index':i} for i,r in enumerate(observations)]
            whole,status,candidates=decide(unique,policy['minimum_distinct_frames'],policy['vote_ratio'])
            result[input_kind]={'whole_consensus':whole,'whole_status':status,'whole_candidates':candidates,
                'character_vote':character_vote(reads,required=policy['minimum_distinct_frames'],ratio=policy['vote_ratio'],character_support=policy['minimum_character_support'])}
        tracks.append(result)
    metrics=[]
    for model in folders:
        g=[r for r in rows if r['model']==model and r['full_target_readability']]
        metrics.append({'model':model,'full_ground_truth_crops':len(g),'before_correct':sum(r['before_full_correct'] for r in g),
            'after_format_correct':sum(r['after_full_correct'] for r in g),'after_unknown':sum(r['format_proposal'] is None for r in g),
            'before_edit_errors':sum(r['before_edit_errors'] for r in g),'after_edit_errors':sum(r['after_edit_errors'] for r in g),
            'target_characters':sum(len(normalize(r['full_target_readability'])) for r in g)})
    report={'policy':policy,'rows':rows,'tracks':tracks,'metrics':metrics,'elapsed_seconds':time.perf_counter()-started,
        'limits':'Readable selected crops only, two frozen sessions, temporal association not independently verified spatial tracking; partial/D05f transcript separate from readability full metrics; no representative pass accuracy.'}
    write_json(args.output/'summary.json',report)
    with (args.output/'predictions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['crop_id','model','crop_source','track_id','raw','normalized','format_proposal','full_target_readability','before_full_correct','after_full_correct','d05f_transcript_diagnostic','wall_seconds_with_beam']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    page=['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>D05i Phase3</title><style>body{font:15px system-ui;margin:20px}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:8px}pre{white-space:pre-wrap}img{image-rendering:pixelated}</style><h1>D05i Phase3 — cần xác nhận</h1><p>Raw giữ nguyên; ứng viên đã ràng buộc định dạng. Hai phiên tương quan, không phải accuracy. Nhãn D05f chẩn đoán riêng.</p><h2>Theo track / nguồn crop</h2><pre>', html.escape(json.dumps(tracks,ensure_ascii=False,indent=2)), '</pre><h2>Theo crop</h2><table><tr><th>Ảnh/crop</th><th>Raw</th><th>Ứng viên định dạng</th><th>Nhãn readability</th><th>Transcript D05f riêng</th></tr>']
    for r in rows:
        i=items[r['crop_id']];image=f"../d05i-readability-20261007/{i['crop_path']}"
        page.append(f"<tr><td>{html.escape(r['crop_id'])}<br>{r['model']}<br><img loading='lazy' src='{html.escape(image)}' width='{i['width']*6}'></td><td><pre>{html.escape(r['raw'])}</pre></td><td>{html.escape(r['format_proposal'] or 'unknown')}<details><pre>{html.escape(json.dumps(r['ranked_format_candidates'],ensure_ascii=False,indent=2))}</pre></details></td><td>{html.escape(r['full_target_readability'] or 'không có GT toàn biển')}</td><td>{html.escape(r['d05f_transcript_diagnostic'] or 'không có')}</td></tr>")
    (args.output/'review.html').write_text('\n'.join(page)+ '</table>')
    for rel,digest in policy['phase2_file_hashes'].items():
        if sha256(args.phase2/rel)!=digest: raise ValueError('Phase2 locked file changed')
    for p in args.output.iterdir(): p.chmod(0o600)
    print(json.dumps({'metrics':metrics,'tracks':len(tracks),'supplement':f"{sum(r['match'] is True for r in supplement)}/{len(supplement)}",'elapsed_seconds':report['elapsed_seconds'],'phase2_files_unchanged':True},indent=2))


if __name__=='__main__': main()
