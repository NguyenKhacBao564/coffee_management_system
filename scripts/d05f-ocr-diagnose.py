#!/usr/bin/env python3
"""Bounded D05f diagnosis through the existing OCR benchmark, no training."""
import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.benchmark import run_benchmark
from offline_vision.ocr import PlateOCR
from offline_vision.recognizer import PaddleTinyRecognizer,PaddleEnglishRecognizer
from offline_vision.export import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['dataset','labels','model-dir','recognizer-dir','english-dir','output']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    crnn=PlateOCR(args.model_dir,'single-line');tiny=PaddleTinyRecognizer(args.recognizer_dir);english=PaddleEnglishRecognizer(args.english_dir)
    report=run_benchmark(args.dataset,args.labels,args.output,args.model_dir,args.recognizer_dir,
        recognizers={'crnn_baseline':(crnn._line,crnn.metadata),'paddle_tiny':(tiny.line,tiny.metadata),'paddle_english_v5':(english.line,english.metadata)})
    # Quarantine inconsistent transcripts for the same vehicle, without altering source labels.
    suspect={r['annotation_id'] for r in report['predictions'] if r['source_id']=='v002' and r['manual_expected']=='29C02655'}
    groups=defaultdict(list)
    for row in report['predictions']:
        if row['manual_expected'] and row['annotation_id'] not in suspect:
            groups[(row['model'],row['crop_source'],row['variant'])].append(row)
    diagnostic={'metrics_excluding_transcripts_pending_confirmation':[
        {'model':k[0],'crop_source':k[1],'variant':k[2],'manual_samples':len(v),
         'whole_plate_exact':sum(r['full_plate_correct'] for r in v)} for k,v in groups.items()],
        'suspect_annotation_ids':sorted(suspect),'excluded_reason':'User confirmed same vehicle; transcripts switch 49C/29C and need manual recheck. No label correction inferred.',
        'raw_labels_unchanged':True,'not_accuracy_or_holdout_selection':True,
        'models':{'paddle_tiny':tiny.metadata,'paddle_english_v5':english.metadata},
        'limits':'Two correlated captures; comparison is diagnostic, not checkpoint/threshold selection. A smaller Latin vocabulary is model choice, no predicted-character replacement.'}
    write_json(args.output/'diagnostic.json',diagnostic)
    print(json.dumps({k:v for k,v in diagnostic.items() if k!='models'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
