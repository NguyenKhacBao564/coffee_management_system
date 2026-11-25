"""Fixed D05i Phase 2 CPU experiment; readable human labels only, no selection."""
import csv
import html
import json
import platform
import resource
import statistics
import time
from pathlib import Path

import cv2
import psutil

from .benchmark import preprocess
from .consensus import normalize
from .crop_readability import validate_review
from .dataset import safe_image, sha256
from .export import write_json


def edit_distance(prediction, target):
    previous = list(range(len(target) + 1))
    for i, left in enumerate(prediction, 1):
        current = [i]
        for j, right in enumerate(target, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def parts_for(item, image, mode, variant):
    if mode == 'whole' or item['layout'] == 'single-line':
        parts, names = [image], ['whole' if item['layout'] == 'two-line' else 'single']
    else:
        split = item['split_y_crop']
        if type(split) is not int or not 0 < split < image.shape[0]:
            raise ValueError('Split experiment requires human native line separator')
        parts, names = [image[:split], image[split:]], ['top', 'bottom']
    if variant == 'original':
        return [preprocess(part, 'original') for part in parts], names
    if variant == 'upscale2':
        return [cv2.resize(part, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC) for part in parts], names
    raise ValueError('Unknown diagnostic variant')


def score_read(item, raw_lines, names):
    prediction = '\n'.join(raw_lines)
    results = {}
    targets = {
        'full': item['full_text'] or (item['single_text'] if item['layout'] == 'single-line' else ''),
        'top': item['top_text'], 'bottom': item['bottom_text'],
    }
    for field, target in targets.items():
        # A partial crop's supplied full_text must NEVER become whole-plate ground truth.
        permitted = item['readability'] == 'readable_full' if field == 'full' else field in item['readable_lines']
        predicted = prediction if field == 'full' else raw_lines[names.index(field)] if field in names else None
        known = bool(normalize(target)) and permitted
        scored = known and predicted is not None
        results[field] = {
            'ground_truth_available': known, 'scored': scored,
            'manual_target': target if known else None, 'raw_prediction': predicted,
            'normalized_prediction': normalize(predicted) if predicted is not None else None,
            'exact': normalize(predicted) == normalize(target) if scored else None,
            'strict_raw_exact': predicted == target if scored else None,
            'edit_errors': edit_distance(normalize(predicted), normalize(target)) if scored else None,
            'target_characters': len(normalize(target)) if scored else 0,
            'unscored_reason': None if scored else 'missing explicit human transcript/readability' if not known else 'whole recognizer output has no row boundaries',
        }
    return results


def summarize(rows):
    groups = {}
    for row in rows:
        for scope in ['all', row['crop_source']]:
            key = (row['model'], row['mode'], row['variant'], scope)
            groups.setdefault(key, []).append(row)
    results = []
    for key, group in sorted(groups.items()):
        entry = dict(zip(['model', 'mode', 'variant', 'crop_scope'], key))
        entry['crops'] = len(group)
        for field in ['full', 'top', 'bottom']:
            scores = [row['scores'][field] for row in group]
            scored = [score for score in scores if score['scored']]
            chars = sum(score['target_characters'] for score in scored)
            errors = sum(score['edit_errors'] for score in scored)
            entry[field] = {
                'correct': sum(score['exact'] for score in scored), 'denominator': len(scored),
                'ground_truth_crops': sum(score['ground_truth_available'] for score in scores),
                'unscored_known_crops': sum(score['ground_truth_available'] and not score['scored'] for score in scores),
                'edit_errors': errors, 'target_characters': chars, 'cer': errors / chars if chars else None,
            }
        entry['median_cpu_seconds_per_crop'] = statistics.median(row['cpu_seconds_median'] for row in group)
        entry['median_wall_seconds_per_crop'] = statistics.median(row['wall_seconds_median'] for row in group)
        entry['max_sampled_rss_after_bytes'] = max(row['rss_after_bytes'] for row in group)
        results.append(entry)
    return results


def worker(plan, model_name, model, output):
    review_root = Path(plan['review_root'])
    template = json.loads((review_root / 'crop-review.template.json').read_text())
    label_path = Path(plan['labels_path'])
    if sha256(label_path) != plan['labels_sha256']:
        raise ValueError('Frozen label hash changed')
    labels = json.loads(label_path.read_text())
    validate_review(template, labels)
    eligible = [item for item in labels['items'] if item['readability'] in {'readable_full', 'readable_partial'}]
    if not eligible:
        raise ValueError('No human-confirmed readable crops')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    images = {}
    for item in eligible:
        path = safe_image(review_root, item['crop_path'])
        if sha256(path) != item['crop_sha256']:
            raise ValueError('Frozen native crop hash changed')
        image = cv2.imread(str(path))
        if image is None or [image.shape[1], image.shape[0]] != [item['width'], item['height']]:
            raise ValueError('Native crop size changed')
        images[item['crop_id']] = image
    for _ in range(plan['warmup_calls']):
        model.line(images[eligible[0]['crop_id']])
    process = psutil.Process()
    rows, excluded = [], []
    started = time.perf_counter()
    for item in eligible:
        image = images[item['crop_id']]
        for mode in plan['modes']:
            for variant in plan['variants']:
                try:
                    parts_for(item, image, mode, variant)
                except ValueError as e:
                    excluded.append({'crop_id': item['crop_id'], 'mode': mode, 'variant': variant, 'reason': str(e)})
                    continue
                reads, cpu_times, wall_times, shapes, slots = [], [], [], [], []
                before = process.memory_info().rss
                for _ in range(plan['repetitions']):
                    if time.perf_counter() - started > plan['max_worker_seconds']:
                        raise TimeoutError('Diagnostic worker time bound reached')
                    cpu_start, wall_start = time.process_time(), time.perf_counter()
                    parts, names = parts_for(item, image, mode, variant)
                    text, line_shapes, raw_slots, confidences = [], [], [], []
                    for part in parts:
                        raw, confidence = model.line(part)
                        text.append(raw); confidences.append(confidence)
                        line_shapes.append(getattr(model, 'last_input_shape', None))
                        raw_slots.append(getattr(model, 'last_raw_slots', None))
                    wall_times.append(time.perf_counter() - wall_start)
                    cpu_times.append(time.process_time() - cpu_start)
                    reads.append({'raw_lines': text, 'line_scores': confidences})
                    shapes.append(line_shapes); slots.append(raw_slots)
                first = reads[0]['raw_lines']  # NEVER pick a repetition by ground truth
                rows.append({
                    'crop_id': item['crop_id'], 'sample_id': item['sample_id'], 'capture_group_id': item['capture_group_id'],
                    'media_seconds': item['media_seconds'], 'crop_source': item['crop_source'], 'source_split': item['source_split'],
                    'crop_path': item['crop_path'], 'crop_sha256': item['crop_sha256'], 'crop_pixels': [item['width'], item['height']],
                    'readability': item['readability'], 'model': model_name, 'mode': mode, 'variant': variant,
                    'raw': '\n'.join(first), 'normalized': normalize('\n'.join(first)), 'raw_repetitions': reads,
                    'repeat_predictions_equal': all(read['raw_lines'] == first for read in reads),
                    'recognizer_input_shapes': shapes[0], 'raw_model_slots': slots[0],
                    'scores': score_read(item, first, names), 'cpu_seconds': cpu_times, 'wall_seconds': wall_times,
                    'cpu_seconds_median': statistics.median(cpu_times), 'wall_seconds_median': statistics.median(wall_times),
                    'rss_before_bytes': before, 'rss_after_bytes': process.memory_info().rss,
                })
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = int(maxrss if platform.system() == 'Darwin' else maxrss * 1024)
    result = {
        'model': model_name, 'metadata': model.metadata, 'rows': rows, 'metrics': summarize(rows),
        'excluded': excluded, 'elapsed_seconds': time.perf_counter() - started,
        'peak_process_rss_bytes': peak, 'rss_scope': 'Separate CPU process per model, includes Python/native runtime, initialization/warmup; crop RSS are before/after snapshots, not per-crop peaks.',
        'memory_runtime': {'psutil': psutil.__version__, 'platform': platform.platform()},
    }
    write_json(output / 'summary.json', result)
    return result


def write_report(root, plan, models):
    rows = [row for model in models for row in model['rows']]
    report = {'plan': plan, 'models': models, 'metrics': summarize(rows),
              'status': 'diagnostic_only_phase2_stop', 'selected_variant': None,
              'limits': 'Two correlated captures/two transcripts, only one full-readable plate string. No policy/checkpoint/threshold selected with camera test. Whole two-line outputs have no row boundaries, no oracle substring scoring.'}
    write_json(root / 'summary.json', report)
    with (root / 'predictions.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['crop_id', 'sample_id', 'crop_source', 'readability', 'model', 'mode', 'variant', 'raw', 'normalized',
                  'full_target', 'full_correct', 'top_target', 'top_correct', 'bottom_target', 'bottom_correct',
                  'cpu_ms_per_crop', 'wall_ms_per_crop', 'rss_after_mib']
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in rows:
            flat = {k: row[k] for k in fields if k in row}
            for field in ['full', 'top', 'bottom']:
                flat[field + '_target'] = row['scores'][field]['manual_target']
                flat[field + '_correct'] = row['scores'][field]['exact']
            flat.update(cpu_ms_per_crop=row['cpu_seconds_median'] * 1000,
                        wall_ms_per_crop=row['wall_seconds_median'] * 1000, rss_after_mib=row['rss_after_bytes'] / 2**20)
            writer.writerow(flat)
    (root / 'predictions.csv').chmod(0o600)
    head = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>D05i Phase 2 OCR</title>',
            '<style>body{font:15px system-ui;margin:20px;background:#f4f6f4}table{border-collapse:collapse;background:white}td,th{border:1px solid #ccd;padding:9px;vertical-align:top}pre{white-space:pre-wrap}.scroll{overflow:auto}.pixel{image-rendering:pixelated}</style>',
            '<h1>D05i Phase 2 — chẩn đoán trên crop đã review</h1>',
            '<p>Giữ raw. Toàn biển chỉ chấm readable_full; partial chỉ chấm dòng được ghi chắc. Không chọn biến thể theo test; không phải accuracy xưởng. Whole output thiếu ranh giới dòng: không đoán phần đuôi để chấm.</p>',
            '<div class="scroll"><table><tr><th>Model / cách đọc / biến thể</th><th>Toàn biển</th><th>Trên</th><th>Dưới</th><th>CER toàn biển / dưới</th><th>CPU / wall ms/crop</th><th>Peak RAM model</th></tr>']
    peaks = {model['model']: model['peak_process_rss_bytes'] for model in models}
    for metric in report['metrics']:
        if metric['crop_scope'] != 'all':
            continue
        fraction = lambda key: f"{metric[key]['correct']}/{metric[key]['denominator']}" if metric[key]['denominator'] else 'N/A (0 được chấm)'
        cer = lambda key: f"{metric[key]['edit_errors']}/{metric[key]['target_characters']}" if metric[key]['target_characters'] else 'N/A'
        head.append(f"<tr><td>{html.escape(metric['model'])} / {metric['mode']} / {metric['variant']}</td><td>{fraction('full')}</td><td>{fraction('top')}</td><td>{fraction('bottom')}</td><td>{cer('full')} / {cer('bottom')}</td><td>{metric['median_cpu_seconds_per_crop']*1000:.2f} / {metric['median_wall_seconds_per_crop']*1000:.2f}</td><td>{peaks[metric['model']]/2**20:.1f} MiB (process)</td></tr>")
    head += ['</table></div><h2>Ảnh, nhãn thật và prediction</h2><div class="scroll"><table><tr><th>Crop / ảnh</th><th>Model / cách đọc</th><th>Nhãn dùng chấm</th><th>Raw prediction</th><th>Khớp full / trên / dưới</th></tr>']
    import os
    for row in rows:
        source = Path(plan['review_root']) / row['crop_path']
        relative = os.path.relpath(source, root)
        scores = row['scores']
        target = '\n'.join(f"{k}: {scores[k]['manual_target']}" for k in ['full', 'top', 'bottom'] if scores[k]['manual_target'] is not None)
        states = ' / '.join(str(scores[k]['exact']) for k in ['full', 'top', 'bottom'])
        head.append(f"<tr><td>{html.escape(row['sample_id'])} / {row['crop_source']} / {row['media_seconds']} s<br><img src='{html.escape(relative)}' width='{row['crop_pixels'][0]}' height='{row['crop_pixels'][1]}'><br><img class='pixel' src='{html.escape(relative)}' width='{row['crop_pixels'][0]*8}' height='{row['crop_pixels'][1]*8}'></td><td>{html.escape(row['model'])}<br>{row['mode']} / {row['variant']}</td><td><pre>{html.escape(target)}</pre></td><td><pre>{html.escape(row['raw'])}</pre></td><td>{states}</td></tr>")
    head += ['</table></div>']
    (root / 'review.html').write_text('\n'.join(head))
    (root / 'review.html').chmod(0o600)
    return report
