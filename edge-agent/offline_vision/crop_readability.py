"""D05i native crop inventory and separate human readability labels, no OCR."""
import hashlib
import json
import copy
import csv
from decimal import Decimal
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2

from .benchmark import _match_frame_plates
from .consensus import normalize
from .dataset import browser_manifest, safe_image, save_png, sha256, validate_labels
from .export import write_json
from .geometry import clip_box

REVIEW_FIELDS = {
    'readability', 'readable_lines', 'layout', 'split_y_crop', 'full_text',
    'top_text', 'bottom_text', 'single_text', 'notes', 'reviewed_at',
}


def validate_item(item):
    state = item.get('readability')
    if state not in {'pending', 'readable_full', 'readable_partial', 'unreadable'}:
        raise ValueError('Unsupported readability')
    layout = item.get('layout')
    if layout not in {'pending', 'single-line', 'two-line'}:
        raise ValueError('Unsupported layout')
    lines = item.get('readable_lines')
    if not isinstance(lines, list) or len(lines) != len(set(lines)) or any(
            line not in {'top', 'bottom', 'single'} for line in lines):
        raise ValueError('Unsupported readable lines')
    if state in {'readable_full', 'readable_partial'}:
        if layout == 'pending':
            raise ValueError('Readable crop needs a confirmed layout')
        allowed = {'top', 'bottom'} if layout == 'two-line' else {'single'}
        if not lines or not set(lines) <= allowed:
            raise ValueError('Mark which lines are readable')
        if state == 'readable_full' and set(lines) != allowed:
            raise ValueError('Full readability requires every line')
    if state == 'unreadable' and lines:
        raise ValueError('Unreadable crop cannot have readable lines')
    split = item.get('split_y_crop')
    if split is not None and (type(split) is not int or not 0 < split < item['height']):
        raise ValueError('Line split must be inside native crop')
    for key in ['full_text', 'top_text', 'bottom_text', 'single_text', 'notes', 'reviewed_at']:
        if not isinstance(item.get(key), str):
            raise ValueError(f'{key} must be a string')


def validate_review(template, labels):
    """Allow only human label edits; source identity, geometry and hashes are immutable."""
    if labels.get('dataset_id') != template['dataset_id'] or labels.get('schema_version') != template['schema_version']:
        raise ValueError('Labels belong to a different crop inventory')
    if set(labels) != set(template):
        raise ValueError('Unexpected or missing review fields')
    for key, value in template.items():
        if key not in {'items', 'label_origin', 'review_provenance'} and labels.get(key) != value:
            raise ValueError(f'Immutable review metadata changed: {key}')
    if labels.get('label_origin') not in {'manual_review', 'manual_review_required'}:
        raise ValueError('Unsupported label origin')
    expected = {item['crop_id']: item for item in template['items']}
    received = labels.get('items', [])
    if len(received) != len(expected) or {item.get('crop_id') for item in received} != set(expected):
        raise ValueError('Crop inventory must be preserved exactly')
    for item in received:
        base = expected[item['crop_id']]
        if set(item) != set(base):
            raise ValueError('Unexpected or missing crop fields')
        for key, value in base.items():
            if key not in REVIEW_FIELDS and item[key] != value:
                raise ValueError(f'Immutable crop metadata changed: {key}')
        validate_item(item)
    return Counter(item['readability'] for item in received)


def csv_review(template, path):
    """CSV omits source hashes; rebind only after exact crop ID/source/time checks."""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = ['crop_id', 'sample_id', 'crop_source', 'media_seconds', 'readability',
                    'readable_lines', 'layout', 'full_text', 'top_text', 'bottom_text',
                    'single_text', 'split_y_crop', 'notes']
        if reader.fieldnames != required:
            raise ValueError('CSV columns differ from D05i review export')
        rows = list(reader)
    expected = {item['crop_id']: item for item in template['items']}
    if len(rows) != len(expected) or {r['crop_id'] for r in rows} != set(expected):
        raise ValueError('CSV crop inventory must be preserved exactly')
    labels = copy.deepcopy(template)
    labels['label_origin'] = 'manual_review'
    by_id = {item['crop_id']: item for item in labels['items']}
    derived = []
    for row in rows:
        item = by_id[row['crop_id']]
        if row['sample_id'] != item['sample_id'] or row['crop_source'] != item['crop_source']:
            raise ValueError('CSV immutable crop source changed')
        if Decimal(row['media_seconds']) != Decimal(str(item['media_seconds'])):
            raise ValueError('CSV media timestamp changed')
        for key in ['readability', 'layout', 'full_text', 'top_text', 'bottom_text', 'single_text', 'notes']:
            if not isinstance(row[key], str):
                raise ValueError('Missing CSV value')
            item[key] = row[key]
        item['split_y_crop'] = int(row['split_y_crop']) if row['split_y_crop'] else None
        item['readable_lines'] = row['readable_lines'].split('|') if row['readable_lines'] else []
        if not item['readable_lines'] and item['readability'] == 'readable_full':
            item['readable_lines'] = ['top', 'bottom'] if item['layout'] == 'two-line' else ['single'] if item['layout'] == 'single-line' else []
            derived.append({'crop_id': item['crop_id'], 'rule': 'explicit readable_full + manual layout implies all lines', 'lines': item['readable_lines']})
        elif not item['readable_lines'] and item['readability'] == 'readable_partial':
            allowed = ['top', 'bottom'] if item['layout'] == 'two-line' else ['single']
            item['readable_lines'] = [line for line in allowed if item[line + '_text'].strip()]
            derived.append({'crop_id': item['crop_id'], 'rule': 'nonempty human per-line transcript; no full_text inference', 'lines': item['readable_lines']})
    validate_review(template, labels)
    labels['review_provenance'] = {
        'format': 'D05i CSV export', 'derived_line_flags': derived,
        'limits': 'CSV lacks dataset fingerprint/image hashes/review timestamps; exact IDs/source/time checked, immutable metadata rebound from local template. No transcript/character changes.',
    }
    return labels


def import_review(review_root, labels_path, output):
    template = json.loads((review_root / 'crop-review.template.json').read_text())
    labels = csv_review(template, labels_path) if labels_path.suffix.lower() == '.csv' else json.loads(labels_path.read_text())
    counts = validate_review(template, labels)
    for item in template['items']:
        if sha256(safe_image(review_root, item['crop_path'])) != item['crop_sha256']:
            raise ValueError('Native crop hash changed')
    if output.exists():
        raise ValueError('Refusing to overwrite existing imported labels')
    labels['review_provenance'] = {
        'browser': labels.get('review_provenance'), 'imported_from': str(labels_path.resolve()),
        'source_file_sha256': sha256(labels_path),
        'source_json_sha256': sha256(labels_path) if labels_path.suffix.lower() == '.json' else None,
        'template_sha256': sha256(review_root / 'crop-review.template.json'),
        'imported_at_utc': datetime.now(timezone.utc).isoformat(),
        'origin': 'human_crop_review; no OCR-derived labels',
    }
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(output, labels)
    return dict(counts)


def build_review(dataset, labels_path, output, *, comparisons=(), pending_path=None):
    labels = json.loads(labels_path.read_text())
    validate_labels(labels, dataset)
    labels = browser_manifest(labels)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    inputs = [{'kind': 'confirmed_manual_labels', 'path': str(labels_path.resolve()), 'sha256': sha256(labels_path)}]
    items, keys, frames = [], {}, {}
    skipped = []
    for frame in labels['frames']:
        if not frame['reviewed'] or not frame.get('annotations_complete'):
            skipped.append(frame['sample_id'])
            continue
        plates = [a for a in frame['annotations'] if a['kind'] == 'plate' and a['label_origin'] == 'manual_review']
        if plates:
            frames[frame['sample_id']] = (frame, plates)
    images = {}

    def add(frame, annotation, bbox, source, reference):
        sample_id = frame['sample_id']
        if sample_id not in images:
            path = safe_image(dataset, frame['image_path'])
            if sha256(path) != frame['image_sha256']:
                raise ValueError('Native frame hash changed')
            image = cv2.imread(str(path))
            if image is None or [image.shape[1], image.shape[0]] != [frame['width'], frame['height']]:
                raise ValueError('Native frame cannot be read at recorded dimensions')
            images[sample_id] = image
        image = images[sample_id]
        box = list(clip_box(tuple(bbox), image.shape))
        key = (sample_id, annotation['annotation_id'], source, *box)
        if key in keys:
            keys[key]['references'].append(reference)
            return
        x1, y1, x2, y2 = box
        crop = image[y1:y2, x1:x2]
        if not crop.size:
            raise ValueError('Empty native crop')
        digest = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
        crop_id = f'{sample_id}-{source}-{digest}'
        crop_path, context_path, zoom_path = (f'{folder}/{crop_id}.png' for folder in ['crops', 'contexts', 'zoom8'])
        save_png(output / crop_path, crop)
        save_png(output / zoom_path, cv2.resize(crop, (crop.shape[1] * 8, crop.shape[0] * 8), interpolation=cv2.INTER_NEAREST))
        context = image.copy()
        gx1, gy1, gx2, gy2 = annotation['bbox']
        cv2.rectangle(context, (gx1, gy1), (gx2, gy2), (35, 180, 35), 2)
        cv2.rectangle(context, (x1, y1), (x2, y2), (0, 130, 255), 1)
        save_png(output / context_path, context)
        split = annotation.get('split_y')
        relative_split = split - y1 if type(split) is int and y1 < split < y2 else None
        item = {
            'crop_id': crop_id, 'sample_id': sample_id, 'annotation_id': annotation['annotation_id'],
            'crop_source': source, 'source_id': frame['source_id'], 'capture_group_id': frame['capture_group_id'],
            'vehicle_group_id': annotation.get('vehicle_group_id'), 'media_seconds': frame['media_seconds'],
            'frame_index': frame['frame_index'], 'scene_hash': frame['scene_hash'],
            'source_image_path': str(safe_image(dataset, frame['image_path'])), 'source_image_sha256': frame['image_sha256'],
            'frame_width': frame['width'], 'frame_height': frame['height'], 'frame_bbox_xyxy': box,
            'manual_bbox_xyxy': annotation['bbox'], 'source_split': frame.get('split', 'unassigned'),
            'source_annotation_layout': annotation.get('layout'), 'source_split_y': split,
            'width': crop.shape[1], 'height': crop.shape[0], 'crop_path': crop_path,
            'crop_sha256': sha256(output / crop_path), 'annotated_path': context_path, 'zoom8_path': zoom_path,
            'zoom8_sha256': sha256(output / zoom_path), 'references': [reference],
            'readability': 'pending', 'readable_lines': [],
            'layout': annotation['layout'] if annotation['layout'] in {'single-line', 'two-line'} else 'pending',
            'split_y_crop': relative_split, 'full_text': '', 'top_text': '', 'bottom_text': '',
            'single_text': '', 'notes': '', 'reviewed_at': '',
        }
        keys[key] = item
        items.append(item)

    for frame, plates in frames.values():
        matches, _ = _match_frame_plates(plates, frame.get('suggested_plates', []), .5)
        for index, annotation in enumerate(plates):
            add(frame, annotation, annotation['bbox'], 'manual', {
                'kind': 'confirmed_manual_bbox', 'labels_sha256': sha256(labels_path)})
            if index in matches:
                proposal, overlap = matches[index]
                add(frame, annotation, proposal['bbox'], 'detector', {
                    'kind': 'D05e_detector_proposal_matched_to_confirmed_bbox', 'model': proposal.get('model'),
                    'score': proposal.get('score'), 'bbox_iou': overlap, 'bbox_xyxy_float': proposal['bbox'],
                    'labels_sha256': sha256(labels_path)})
    for path in comparisons:
        comparison = json.loads(path.read_text())
        inputs.append({'kind': 'frozen_D05f_comparison', 'path': str(path.resolve()), 'sha256': sha256(path)})
        for model, metric in comparison['metrics'].items():
            for row in metric['rows']:
                if not row.get('annotations_complete') or row['sample_id'] not in frames:
                    continue
                frame, plates = frames[row['sample_id']]
                if row['ground_truth'] != len(plates):
                    raise ValueError('Comparison ground truth inventory differs from confirmed labels')
                for match in row['matches']:
                    annotation = plates[match['gt_index']]
                    add(frame, annotation, match['bbox'], 'detector', {
                        'kind': 'D05f_detector_matched_to_confirmed_bbox', 'model': model,
                        'input_scope': comparison['input_scope'], 'bbox_iou': match['iou'],
                        'bbox_xyxy_float': match['bbox'], 'comparison_sha256': sha256(path),
                        'score': match.get('score')})
    pending = json.loads(pending_path.read_text()) if pending_path else {}
    if pending_path:
        inputs.append({'kind': 'pending_inventory', 'path': str(pending_path.resolve()), 'sha256': sha256(pending_path)})
    items.sort(key=lambda i: (i['source_id'], i['media_seconds'], i['annotation_id'], i['crop_source'], i['crop_id']))
    transcripts = {normalize(a['plate_text']) for _, plates in frames.values() for a in plates
                   if a['readability'] == 'readable' and a['plate_text']}
    summary = {
        'crops': len(items), 'by_crop_source': dict(Counter(i['crop_source'] for i in items)),
        'manual_plate_annotations': sum(len(plates) for _, plates in frames.values()),
        'frames': len(frames), 'captures': len({i['capture_group_id'] for i in items}),
        'unique_confirmed_plate_strings': len(transcripts),
        'annotations_without_certain_transcript': sum(a['readability'] != 'readable' for _, plates in frames.values() for a in plates),
        'excluded_incomplete_frames': skipped, 'excluded_pending_detector_crops': pending.get('pending_crops', []),
        'readability_counts': {'pending': len(items)},
        'deduplication': 'Same frame/annotation/crop type/native bbox merged, references retained; correlated crops are not independent passes.',
        'limits': 'Confirmed bbox establishes plate location, not full/readable detector crop. Distinct plate count only counts existing confirmed transcripts; unknown plates are not assumed unique.',
    }
    dataset_id = hashlib.sha256(json.dumps({'inputs': inputs, 'crop_ids': [i['crop_id'] for i in items]}, sort_keys=True).encode()).hexdigest()
    template = {
        'schema_version': 1, 'review_kind': 'crop_readability', 'dataset_id': dataset_id,
        'label_origin': 'manual_review_required', 'inputs': inputs, 'sources': labels['sources'],
        'summary': summary, 'items': items, 'review_provenance': None,
        'policy': 'Judge only information visible in this crop. Native PNG + exact nearest-neighbor 8x. No OCR or historical transcript displayed; readability is not inherited from full-frame labels.',
    }
    write_json(output / 'crop-review.template.json', template)
    write_json(output / 'summary.json', summary)
    html = (Path(__file__).parent / 'd05e_crop_review.html').read_text()
    embedded = json.dumps(template, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    (output / 'review.html').write_text(html.replace('__REVIEW_DATA__', embedded))
    (output / 'review.html').chmod(0o600)
    helper = Path(__file__).parent / 'crop_readability_review.js'
    (output / 'crop-readability.js').write_bytes(helper.read_bytes())
    (output / 'crop-readability.js').chmod(0o600)
    return summary
