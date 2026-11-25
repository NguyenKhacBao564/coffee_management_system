#!/usr/bin/env python3
"""Reuse D05b OCR benchmark on the frozen D05f camera comparison."""
import argparse
import copy
import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'edge-agent'))
from offline_vision.benchmark import run_benchmark
from offline_vision.dataset import safe_image
from offline_vision.export import write_json
from offline_vision.recognizer import PaddleTinyRecognizer, PaddleEnglishRecognizer
from offline_vision.fine_tune.audit import file_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['dataset', 'labels', 'comparison', 'recognizer-dir', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--english-dir', type=Path, help='Optional pinned Latin diagnosis, same model for both detectors')
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text())
    if comparison['split'] != 'test':
        raise ValueError('This paired report requires the frozen camera test comparison')
    labels = json.loads(args.labels.read_text())
    ids = {r['sample_id'] for m in comparison['metrics'].values() for r in m['rows']}
    labels['frames'] = [f for f in labels['frames'] if f['sample_id'] in ids]
    if {f['sample_id'] for f in labels['frames']} != ids:
        raise ValueError('Comparison frame inventory differs from manual labels')
    if any(not f.get('annotations_complete') for f in labels['frames']):
        raise ValueError('Only confirmed complete frames are allowed')
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    data = args.output / 'frames'
    data.mkdir(mode=0o700)
    for f in labels['frames']:
        source = safe_image(args.dataset, f['image_path'])
        destination = data / f['image_path']
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.link(source, destination)
        f['suggested_plates'] = []
    write_json(data / 'manifest.template.json', labels)
    recognizer = PaddleTinyRecognizer(args.recognizer_dir)
    recognizers = {'paddle_tiny': (recognizer.line, recognizer.metadata)}
    if args.english_dir:
        english = PaddleEnglishRecognizer(args.english_dir)
        recognizers['paddle_english_v5'] = (english.line, english.metadata)
    summaries = {}
    for name, metric in comparison['metrics'].items():
        working = copy.deepcopy(labels)
        rows = {r['sample_id']: r for r in metric['rows']}
        for f in working['frames']:
            row = rows[f['sample_id']]
            boxes = [m['bbox'] for m in row['matches']] + row['unmatched_prediction_boxes']
            f['suggested_plates'] = [{'bbox': box, 'score': None} for box in boxes]
        path = args.output / (name + '.labels.json')
        write_json(path, working)
        summaries[name] = run_benchmark(data, path, args.output / name, ROOT / 'data/offline-vision/models',
            args.recognizer_dir, recognizers=recognizers)
    report = {'comparison_sha256': file_hash(args.comparison), 'labels_sha256': file_hash(args.labels),
              'input_scope': comparison['input_scope'], 'same_recognizer': recognizer.metadata,
              'recognizers': {k: metadata for k, (_, metadata) in recognizers.items()},
              'metrics': {k: v['metrics'] for k, v in summaries.items()},
              'limits': 'One held-out capture, two readable frames of one plate. Manual vehicle crops are oracle geometry. No checkpoint or threshold is selected with OCR.'}
    write_json(args.output / 'paired-summary.json', report)
    sections = ['<!doctype html><meta charset="utf-8"><title>D05f paired OCR</title>',
                '<style>body{font:16px system-ui;margin:24px;background:#f8fafc}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:10px}img{display:block;max-width:400px}pre{white-space:pre-wrap}</style>',
                '<h1>OCR so sánh — cùng recognizer và tiền xử lý cho hai detector</h1>',
                '<p>Raw prediction giữ nguyên. Gợi ý cần xác nhận; một lượt quay giữ lại, không phải accuracy toàn hệ thống.</p>']
    for name, summary in summaries.items():
        sections += [f'<h2>{html.escape(name)}</h2><table><tr><th>Frame / giây</th><th>Crop / biến thể</th><th>Ảnh gốc</th><th>Nhãn xác nhận</th><th>Raw prediction</th><th>Khớp toàn biển</th></tr>']
        for row in summary['predictions']:
            if row['manual_expected'] is None:
                continue
            crop = name + '/' + row['crop_path']
            sections.append(f'<tr><td>{html.escape(row["sample_id"])}<br>{row["media_seconds"]}</td><td>{row["model"]} / {row["crop_source"]} / {row["variant"]}</td><td><img src="{html.escape(crop)}"><img style="width:{row["source_crop_pixels"][0]*4}px" src="{html.escape(crop)}"></td><td>{html.escape(row["manual_expected"])}</td><td><pre>{html.escape(row["raw"])}</pre></td><td>{row["full_plate_correct"]}</td></tr>')
        sections.append('</table>')
    (args.output / 'review.html').write_text('\n'.join(sections))
    print(json.dumps(report['metrics'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
