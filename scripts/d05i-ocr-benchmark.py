#!/usr/bin/env python3
"""D05i Phase 2 bounded benchmark, separate CPU process for each recognizer."""
import argparse
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'edge-agent'))
from offline_vision.dataset import sha256
from offline_vision.export import write_json
from offline_vision.ocr_diagnostic import worker, write_report
from offline_vision.recognizer import PaddleEnglishRecognizer, PaddleServerRecognizer
from offline_vision.plate_recognizer import FastPlateRecognizer

MODELS = {'english_mobile': ('paddle-english-v5', PaddleEnglishRecognizer),
          'paddle_server': ('paddle-server-v5', PaddleServerRecognizer),
          'fast_plate_cct_s_v2': ('fast-plate-cct-s-v2', FastPlateRecognizer)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-root', type=Path)
    parser.add_argument('--labels', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker-plan', type=Path)
    parser.add_argument('--model', choices=list(MODELS))
    args = parser.parse_args()
    if args.worker_plan:
        plan = json.loads(args.worker_plan.read_text())
        folder, constructor = MODELS[args.model]
        model_path = ROOT / 'data/offline-vision/benchmark-models' / folder
        if sha256(model_path / 'manifest.json') != plan['model_manifest_sha256'][args.model]:
            raise ValueError('Frozen model manifest changed')
        result = worker(plan, args.model, constructor(model_path), Path(plan['output_root']) / args.model)
        print(json.dumps({'model': args.model, 'rows': len(result['rows']), 'peak_rss_mib': result['peak_process_rss_bytes']/2**20, 'seconds': result['elapsed_seconds']}))
        return
    if not all([args.review_root, args.labels, args.output]):
        parser.error('--review-root, --labels and --output required')
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    plan = {'purpose': 'D05i Phase 2 fixed diagnostic; no variant selection',
        'review_root': str(args.review_root.resolve()), 'labels_path': str(args.labels.resolve()),
        'labels_sha256': sha256(args.labels), 'output_root': str(args.output.resolve()),
        'modes': ['split', 'whole'], 'variants': ['original', 'upscale2'],
        'upscale_policy': 'OpenCV cubic 2x, no extra border; each model retains official own preprocessing',
        'repetitions': 3, 'warmup_calls': 2, 'max_worker_seconds': 600,
        'providers': ['CPUExecutionProvider'], 'intra_op_threads': 2, 'inter_op_threads': 1,
        'primary_policy_before_results': {'english_mobile': 'split/original', 'paddle_server': 'split/original', 'fast_plate_cct_s_v2': 'whole/original'},
        'variant_selection_allowed': False, 'vlm': 'not approved/not used',
        'model_manifest_sha256': {name: sha256(ROOT / 'data/offline-vision/benchmark-models' / folder / 'manifest.json') for name, (folder, _) in MODELS.items()},
        'code_sha256': {str(path.relative_to(ROOT)): sha256(path) for path in [Path(__file__), ROOT/'edge-agent/offline_vision/ocr_diagnostic.py', ROOT/'edge-agent/offline_vision/recognizer.py', ROOT/'edge-agent/offline_vision/plate_recognizer.py']},
        'versions': {**{name: importlib.metadata.version(name) for name in ['onnxruntime', 'numpy', 'PyYAML', 'psutil']}, 'opencv': cv2.__version__},
    }
    write_json(args.output / 'plan.json', plan)  # immutable policy written BEFORE any model inference
    results = []
    for name in MODELS:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker-plan', str(args.output/'plan.json'), '--model', name], check=True, timeout=660)
        results.append(json.loads((args.output / name / 'summary.json').read_text()))
    report = write_report(args.output, plan, results)
    print(json.dumps({'status': report['status'], 'models': len(results), 'prediction_rows': sum(len(r['rows']) for r in results), 'selected_variant': None}, indent=2))


if __name__ == '__main__':
    main()
