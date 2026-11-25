import copy
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from offline_vision.crop_readability import build_review, import_review, validate_review
from offline_vision.dataset import browser_manifest, sha256


@pytest.fixture
def crop_inventory(tmp_path):
    dataset = tmp_path / 'source'; dataset.mkdir()
    image = np.arange(48 * 64 * 3, dtype=np.uint16).reshape(48, 64, 3).astype(np.uint8)
    cv2.imwrite(str(dataset / 'image.png'), image)
    plate = {'annotation_id': 'plate', 'kind': 'plate', 'bbox': [10, 12, 30, 26],
             'readability': 'readable', 'plate_text': '29K52755', 'layout': 'two-line',
             'split_y': 19, 'vehicle_group_id': 'vehicle', 'label_origin': 'manual_review'}
    frame = {'sample_id': 'frame', 'source_id': 'video', 'capture_group_id': 'capture',
             'media_seconds': 2.0, 'frame_index': 50, 'image_path': 'image.png',
             'image_sha256': sha256(dataset / 'image.png'), 'width': 64, 'height': 48,
             'scene_hash': str(2**64 - 1), 'split': 'test', 'reviewed': True,
             'annotations_complete': True, 'plate_presence': 'plate', 'annotations': [plate],
             'suggested_plates': [{'bbox': [10, 12, 30, 26], 'score': .9, 'model': 'fixture'}]}
    labels = {'schema_version': 1, 'dataset_id': 'source-fixture', 'label_origin': 'manual_review',
              'sources': [], 'frames': [frame]}
    (dataset / 'manifest.template.json').write_text(json.dumps(labels))
    path = dataset / 'labels.json'; path.write_text(json.dumps(browser_manifest(labels)))
    comparison = tmp_path / 'comparison.json'
    comparison.write_text(json.dumps({'input_scope': 'manual_vehicle_crop', 'metrics': {'detector': {'rows': [{
        'sample_id': 'frame', 'ground_truth': 1, 'annotations_complete': True,
        'matches': [{'gt_index': 0, 'bbox': [10, 12, 30, 26], 'iou': 1.0}]}]}}}))
    output = tmp_path / 'review'
    summary = build_review(dataset, path, output, comparisons=[comparison])
    template = json.loads((output / 'crop-review.template.json').read_text())
    return dataset, path, output, image, summary, template


def test_native_pixels_nearest8_provenance_and_no_inherited_readability(crop_inventory):
    dataset, labels_path, output, image, summary, template = crop_inventory
    assert summary['crops'] == 2 and summary['by_crop_source'] == {'manual': 1, 'detector': 1}
    assert summary['unique_confirmed_plate_strings'] == 1 and summary['captures'] == 1
    for item in template['items']:
        crop = cv2.imread(str(output / item['crop_path']))
        assert np.array_equal(crop, image[12:26, 10:30])
        zoom = cv2.imread(str(output / item['zoom8_path']))
        assert np.array_equal(zoom, np.repeat(np.repeat(crop, 8, axis=0), 8, axis=1))
        assert item['scene_hash'] == str(2**64 - 1)
        assert item['readability'] == 'pending' and item['full_text'] == ''
        assert item['split_y_crop'] == 7
    detector = next(i for i in template['items'] if i['crop_source'] == 'detector')
    assert len(detector['references']) == 2  # one shared crop, both origins retained
    assert '29K52755' not in (output / 'review.html').read_text()
    assert 'crop-readability.js' in (output / 'review.html').read_text()
    assert json.loads(labels_path.read_text())['frames'][0]['annotations'][0]['plate_text'] == '29K52755'


def test_incomplete_and_vehicle_boxes_are_not_plate_crops(crop_inventory, tmp_path):
    dataset, labels_path, _, _, _, _ = crop_inventory
    labels = json.loads(labels_path.read_text())
    labels['frames'][0].update(annotations_complete=False)
    labels_path.write_text(json.dumps(labels))
    report = build_review(dataset, labels_path, tmp_path / 'incomplete')
    assert report['crops'] == 0 and report['excluded_incomplete_frames'] == ['frame']


@pytest.mark.parametrize('field,value', [('scene_hash', str(2**64)), ('crop_sha256', 'changed'),
                                       ('frame_bbox_xyxy', [0, 0, 20, 20]), ('annotation_id', 'other')])
def test_import_rejects_source_changes(crop_inventory, field, value):
    *_, template = crop_inventory
    edited = copy.deepcopy(template); edited['items'][0][field] = value
    with pytest.raises(ValueError, match='Immutable'):
        validate_review(template, edited)


def test_partial_requires_readable_line_and_does_not_invent_text(crop_inventory):
    *_, template = crop_inventory
    edited = copy.deepcopy(template); item = edited['items'][0]
    item['readability'] = 'readable_partial'
    with pytest.raises(ValueError, match='lines'):
        validate_review(template, edited)
    item['readable_lines'] = ['bottom']; item['bottom_text'] = '52755'
    assert validate_review(template, edited)['readable_partial'] == 1
    assert item['full_text'] == '' and item['top_text'] == ''
    item['readability'] = 'readable_full'
    with pytest.raises(ValueError, match='every line'):
        validate_review(template, edited)


def test_import_keeps_original_and_records_source_hash(crop_inventory, tmp_path):
    _, original, output, _, _, template = crop_inventory
    original_hash = sha256(original)
    labels_path = tmp_path / 'downloaded.json'; labels_path.write_text(json.dumps(template))
    imported = tmp_path / 'imported.json'
    result = import_review(output, labels_path, imported)
    assert result == {'pending': 2} and sha256(original) == original_hash
    data = json.loads(imported.read_text())
    assert data['review_provenance']['source_json_sha256'] == sha256(labels_path)
    with pytest.raises(ValueError, match='overwrite'):
        import_review(output, labels_path, imported)
    (output / template['items'][0]['crop_path']).write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='hash'):
        import_review(output, labels_path, tmp_path / 'bad-import.json')


def test_real_js_export_import_exact_uint64_and_partial_draft(crop_inventory):
    *_, template = crop_inventory
    script = Path(__file__).parents[1] / 'offline_vision/crop_readability_review.js'
    code = """
const api=require(process.argv[1]);let raw='';
process.stdin.on('data',x=>raw+=x);process.stdin.on('end',()=>{
 const base=JSON.parse(raw),data=structuredClone(base);
 data.items[0].readability='readable_partial';
 api.validateReview(base,data,true); // incomplete draft can survive browser reload
 try {api.exportReview(base,data);throw Error('incomplete export accepted')} catch(e) {
  if(e.message==='incomplete export accepted')throw e;
 }
 data.items[0].readable_lines=['bottom'];data.items[0].bottom_text='52755';
 const exported=api.exportReview(base,data,'2026-10-07T00:00:00Z');
 const restored=api.validateReview(base,JSON.parse(JSON.stringify(exported)));
 const tampered=structuredClone(restored);tampered.items[0].scene_hash='18446744073709551616';
 try {api.validateReview(base,tampered);throw Error('tampered accepted')} catch(e) {
  if(e.message==='tampered accepted')throw e;
 }
 process.stdout.write(JSON.stringify(restored));
});
"""
    result = subprocess.run(['node', '-e', code, str(script)], input=json.dumps(template),
                            text=True, capture_output=True, check=True)
    restored = json.loads(result.stdout)
    assert restored['items'][0]['scene_hash'] == str(2**64 - 1)
    assert validate_review(template, restored)['readable_partial'] == 1


def test_d05e_legacy_template_remains_a_separate_mode():
    template = (Path(__file__).parents[1] / 'offline_vision/d05e_crop_review.html').read_text()
    assert "if(initial.review_kind==='crop_readability')" in template
    assert "download('d05e-crop-labels.manual.json'" in template


def write_csv_labels(path, template):
    import csv
    fields = ['crop_id', 'sample_id', 'crop_source', 'media_seconds', 'readability', 'readable_lines',
              'layout', 'full_text', 'top_text', 'bottom_text', 'single_text', 'split_y_crop', 'notes']
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for item in template['items']:
            row = {k: item[k] for k in fields}
            row['readable_lines'] = '|'.join(item['readable_lines'])
            writer.writerow(row)


def test_csv_uses_explicit_full_or_human_line_text_without_changing_characters(crop_inventory, tmp_path):
    from offline_vision.crop_readability import csv_review
    *_, template = crop_inventory
    supplied = copy.deepcopy(template)
    first, second = supplied['items']
    first.update(readability='readable_full', full_text='29K-527.55')
    second.update(readability='readable_partial', full_text='29K-527.55', bottom_text='52755')
    path = tmp_path / 'labels.csv'; write_csv_labels(path, supplied)
    imported = csv_review(template, path)
    a, b = imported['items']
    assert a['readable_lines'] == ['top', 'bottom'] and a['full_text'] == '29K-527.55'
    assert b['readable_lines'] == ['bottom'] and b['top_text'] == ''
    assert len(imported['review_provenance']['derived_line_flags']) == 2
    assert imported['items'][0]['scene_hash'] == str(2**64 - 1)


@pytest.mark.parametrize('field,value', [('media_seconds', 99), ('sample_id', 'other'), ('crop_source', 'other')])
def test_csv_immutable_reference_checked_before_rebinding(crop_inventory, tmp_path, field, value):
    from offline_vision.crop_readability import csv_review
    *_, template = crop_inventory
    altered = copy.deepcopy(template); altered['items'][0][field] = value
    path = tmp_path / 'labels.csv'; write_csv_labels(path, altered)
    with pytest.raises(ValueError, match='changed'):
        csv_review(template, path)


def test_partial_full_text_and_whole_output_never_enable_oracle_scoring():
    from offline_vision.ocr_diagnostic import score_read
    item = {'readability': 'readable_partial', 'layout': 'two-line', 'readable_lines': ['bottom'],
            'full_text': '29K52755', 'top_text': '', 'bottom_text': '52755', 'single_text': ''}
    scores = score_read(item, ['29K52755'], ['whole'])
    assert not scores['full']['scored'] and not scores['bottom']['scored']
    assert scores['bottom']['ground_truth_available'] and scores['top']['manual_target'] is None
    split = score_read(item, ['车', '52755'], ['top', 'bottom'])
    assert split['bottom']['exact'] and not split['top']['scored']


def test_cer_preserves_wrong_characters_and_reports_missing_denominator():
    from offline_vision.ocr_diagnostic import edit_distance, score_read, summarize
    assert edit_distance('车52755', '29K52755') == 3
    item = {'readability': 'readable_full', 'layout': 'single-line', 'readable_lines': ['single'],
            'full_text': '49C-026.55', 'top_text': '', 'bottom_text': '', 'single_text': ''}
    scores = score_read(item, ['49C02655'], ['single'])
    assert scores['full']['exact'] and scores['full']['edit_errors'] == 0
    row = {'model': 'fake', 'mode': 'whole', 'variant': 'original', 'crop_source': 'manual',
           'scores': scores, 'cpu_seconds_median': .01, 'wall_seconds_median': .02, 'rss_after_bytes': 10}
    result = next(x for x in summarize([row]) if x['crop_scope'] == 'all')
    assert result['full']['denominator'] == 1 and result['full']['target_characters'] == 8
    assert result['top']['denominator'] == 0 and result['top']['cer'] is None


def test_slot_decoder_keeps_repeats_and_removes_only_trailing_pad():
    from offline_vision.plate_recognizer import slot_decode, plate_input
    cfg = {'alphabet': 'A01_', 'max_plate_slots': 10, 'pad_char': '_',
           'img_height': 64, 'img_width': 128, 'keep_aspect_ratio': False,
           'image_color_mode': 'rgb', 'interpolation': 'linear'}
    text = 'AA1100____'; probabilities = np.zeros((1, 10, 4), dtype=np.float32)
    for index, char in enumerate(text): probabilities[0, index, cfg['alphabet'].index(char)] = 1
    raw, confidence, slots = slot_decode(probabilities, cfg)
    assert raw == 'AA1100' and slots == text and confidence == 1
    image = np.zeros((2, 3, 3), dtype=np.uint8); image[:, :, 0] = 255
    blob = plate_input(image, cfg)
    assert blob.shape == (1, 64, 128, 3) and blob.dtype == np.uint8
    assert blob[0, 0, 0].tolist() == [0, 0, 255]


def test_worker_keeps_first_read_not_ground_truth_best_repetition(crop_inventory, tmp_path):
    from offline_vision.ocr_diagnostic import worker
    _, _, root, _, _, template = crop_inventory
    labels = copy.deepcopy(template)
    labels['items'][0].update(readability='readable_full', readable_lines=['top', 'bottom'], full_text='29K52755')
    path = tmp_path / 'reviewed.json'; path.write_text(json.dumps(labels))
    class Model:
        metadata = {'model': 'fixture'}
        calls = 0
        def line(self, image):
            self.calls += 1
            return ('wrong' if self.calls == 1 else '29K52755'), .8
    plan = {'review_root': str(root), 'labels_path': str(path), 'labels_sha256': sha256(path),
            'warmup_calls': 0, 'repetitions': 3, 'modes': ['whole'], 'variants': ['original'], 'max_worker_seconds': 10}
    result = worker(plan, 'fixture', Model(), tmp_path / 'worker')
    assert len(result['rows']) == 1 and result['rows'][0]['raw'] == 'wrong'
    assert result['rows'][0]['scores']['full']['exact'] is False
    assert result['rows'][0]['repeat_predictions_equal'] is False
