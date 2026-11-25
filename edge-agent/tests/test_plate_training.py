import csv
import json
import zipfile
from pathlib import Path
import cv2
import numpy as np
import pytest
from offline_vision.export import write_json
from offline_vision.fine_tune.audit import audit_dataset,extract_archive,file_hash,valid_box
from offline_vision.fine_tune.prepare import prepare,camera_review_template
from offline_vision.fine_tune.engine import configuration,fixture,preprocess,load_manifest,run


def coco(root, *, duplicate=False, invalid=False, missing=False, empty=False):
    rng=np.random.default_rng(10)
    first=None
    for i,split in enumerate(['train','valid','test']):
        folder=root/split;folder.mkdir(parents=True)
        image=rng.integers(0,255,(60,100,3),dtype=np.uint8)
        if i==0:first=image.copy()
        if duplicate and i==1:image=first.copy()
        cv2.imwrite(str(folder/'image.png'),image)
        anns=[] if empty and i==0 else [{'id':1,'image_id':1,'category_id':0,'bbox':[-1,10,30,15] if invalid and i==0 else [20,10,30,15]}]
        write_json(folder/'_annotations.coco.json',{'images':[{'id':1,'file_name':'absent.png' if missing and i==0 else 'image.png','width':100,'height':60}],
            'annotations':anns,'categories':[{'id':0,'name':'biensoxehoi'}]})
    return audit_dataset(root,root.parent/'audit',source='synthetic QA',version='fixture',license_name='fixture')


def reviews(path, audit, *, accepted=True):
    template=path/'review.template.csv'
    with template.open(encoding='utf-8-sig') as stream:reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
    for i,row in enumerate(rows):
        row.update(annotation_review='accepted' if accepted else 'pending',plate_presence='plate',vehicle_group_id=f'vehicle-{i}',capture_group_id=f'capture-{i}')
    target=path/'review.manual.csv'
    def save():
        with target.open('w',newline='',encoding='utf-8-sig') as stream:writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    save();return target,rows,save


def test_audit_class_mapping_native_sizes_and_contact_sheet(tmp_path):
    a=coco(tmp_path/'raw');assert len(a['records'])==3
    assert a['counts']['train']['boxes']==1 and a['records'][0]['boxes'][0]['class']=='license_plate'
    summary=json.loads((tmp_path/'audit/summary.json').read_text())
    assert summary['plate_width_percentiles']==[30]*5 and summary['one_two_line_and_vehicle_type_counts'] is None
    assert (tmp_path/'audit/contact-001.jpg').is_file() and not a['training_ready']

@pytest.mark.parametrize('option,reason',[('invalid','bbox_outside_or_degenerate'),('missing','image_decode_failed'),('empty','empty_annotations_not_confirmed_negative')])
def test_audit_invalid_missing_and_empty_are_not_training_ready(tmp_path,option,reason):
    a=coco(tmp_path/'raw',**{option:True});assert reason in next(r for r in a['records'] if r['original_split']=='train')['errors'];assert not a['training_ready']


def test_cross_split_exact_pixels_detected_and_rejected(tmp_path):
    a=coco(tmp_path/'raw',duplicate=True);assert any(p['kind']=='exact_pixels' and p['cross_split'] for p in a['duplicate_pairs'])
    r,_,_=reviews(tmp_path/'audit',a);p=prepare(tmp_path/'audit/audit.json',r,tmp_path/'prepared')
    assert not p['training_ready'] and any('Exact duplicate' in b for b in p['blocking_issues'])


def test_manual_review_group_safe_finite_batches_and_test_seal(tmp_path):
    a=coco(tmp_path/'raw');r,rows,save=reviews(tmp_path/'audit',a)
    p=prepare(tmp_path/'audit/audit.json',r,tmp_path/'ready')
    assert p['training_ready'] and p['counts']['train']=={'images':1,'boxes':1,'negative_images':0} and p['batches_per_epoch']==1
    assert p['records'][0]['label_origin']=='roboflow_published_annotation'
    next(r for r in rows if r['original_split']=='test')['split']='train';save();p=prepare(tmp_path/'audit/audit.json',r,tmp_path/'bad')
    assert not p['training_ready'] and any('original test' in b for b in p['blocking_issues'])


def test_shared_vehicle_cannot_cross_splits(tmp_path):
    a=coco(tmp_path/'raw');r,rows,save=reviews(tmp_path/'audit',a)
    rows[0]['vehicle_group_id']=rows[1]['vehicle_group_id']='same';save()
    p=prepare(tmp_path/'audit/audit.json',r,tmp_path/'bad');assert any('vehicle:same' in b for b in p['blocking_issues'])


def test_missing_boxes_are_negative_only_after_explicit_presence_review(tmp_path):
    a=coco(tmp_path/'raw',empty=True);r,rows,save=reviews(tmp_path/'audit',a)
    assert not prepare(tmp_path/'audit/audit.json',r,tmp_path/'blocked')['training_ready']
    next(r for r in rows if r['original_split']=='train')['plate_presence']='no_plate';save()
    p=prepare(tmp_path/'audit/audit.json',r,tmp_path/'ready');assert p['training_ready'] and p['counts']['train']['negative_images']==1

@pytest.mark.parametrize('name',['../escape.txt','same.txt','SAME.txt'])
def test_zip_paths_and_case_aliases_are_rejected_before_extraction(tmp_path,name):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('same.txt','first');z.writestr(name,'second')
    with pytest.raises(ValueError):extract_archive(archive,tmp_path/'raw')
    assert not (tmp_path/'raw').exists()


def test_zip_preserves_original_and_bounds_geometry(tmp_path):
    archive=tmp_path/'good.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('train/labels.txt','original')
    before=file_hash(archive);r=extract_archive(archive,tmp_path/'raw')
    assert file_hash(archive)==before==r['archive_sha256'] and (tmp_path/'raw/train/labels.txt').read_text()=='original'
    assert not valid_box([0,0,float('nan'),1],10,10) and not valid_box([0,0,11,1],10,10)


def test_preprocess_bgr_raw_letterbox_and_no_input_mutation():
    image=np.full((100,200,3),[10,20,30],np.uint8);tensor,scale=preprocess(image,320)
    assert scale==1.6 and list(tensor[:,0,0])==[10,20,30] and list(tensor[:,200,0])==[114]*3
    assert list(image[0,0])==[10,20,30]


def test_changed_fixture_hash_blocked(tmp_path):
    fixture(tmp_path/'fixture');p=tmp_path/'fixture/fixture-0.png';p.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):load_manifest(tmp_path/'fixture/manifest.json')


def test_resume_is_bounded_without_repeating_consumed_batch(tmp_path,monkeypatch):
    import torch
    import offline_vision.fine_tune.engine as engine
    class Tiny(torch.nn.Module):
        def __init__(self):super().__init__();self.scalar=torch.nn.Parameter(torch.tensor(.5))
        def forward(self,images,targets):return {'total_loss':self.scalar**2+images.mean()*0}
    monkeypatch.setattr(engine,'make_model',lambda _: (Tiny(),{'source_revision':'test','weights_sha256':'test'}))
    fixture(tmp_path/'fixture');config=tmp_path/'config.yaml'
    config.write_text('seed: 5\ninput_size: 320\nbatch_size: 2\nthreads: 1\nepochs: 2\nmax_steps: 2\nlearning_rate: 0.000001\nmosaic: false\nmixup: false\nhorizontal_flip: false\n')
    args=(tmp_path/'fixture/manifest.json',config,tmp_path/'unused-assets')
    one=run(*args,tmp_path/'one',preflight=True,steps_this_run=1)
    two=run(*args,tmp_path/'two',preflight=True,resume=tmp_path/'one/checkpoint.pth',steps_this_run=1)
    three=run(*args,tmp_path/'three',preflight=True,resume=tmp_path/'two/checkpoint.pth')
    assert one['total_steps']==1 and two['total_steps']==2 and three['new_steps']==0
    assert not set(one['sample_order'][0])&set(two['sample_order'][0]) and two['epochs_completed']==1
    config.write_text(config.read_text().replace('seed: 5','seed: 6'))
    with pytest.raises(ValueError,match='mismatch'):run(*args,tmp_path/'bad',resume=tmp_path/'two/checkpoint.pth')


def test_preflight_refuses_long_run_config(tmp_path):
    fixture(tmp_path/'fixture');config=tmp_path/'config.yaml';config.write_text('seed: 5\ninput_size: 320\nbatch_size: 2\nthreads: 1\nepochs: 20\nmax_steps: 1000\nlearning_rate: 0.000001\nmosaic: false\nmixup: false\nhorizontal_flip: false\n')
    with pytest.raises(ValueError,match='two total'):run(tmp_path/'fixture/manifest.json',config,tmp_path/'unused',tmp_path/'no',preflight=True)


def test_detector_score_counts_missed_plate_and_container_false_positive():
    from offline_vision.fine_tune.compare import score
    from offline_vision.types import Detection
    # Reader is patched with a synthetic image, never a workshop label.
    import unittest.mock
    records=[{'sample_id':'fake','image_path':'fake','boxes':[{'bbox':[10,10,40,25]},{'bbox':[50,10,80,25]}],
              'hard_negatives':[{'bbox':[10,40,40,60]}],'annotations_complete':True}]
    class Fake:
        def detect(self,image,seconds):return [Detection((10,10,40,25),'license_plate',.8,'fake'),Detection((12,42,38,58),'license_plate',.7,'fake')]
    with unittest.mock.patch('cv2.imread',return_value=np.zeros((80,100,3),np.uint8)):result=score(records,Fake())
    assert result['recall']==.5 and result['false_positives']==1 and result['container_region_false_positives']==1
    assert result['crop_gt_area_coverage_mean']==1 and result['rows'][0]['missed_gt_indices']==[1]


def test_d05d_validation_iou_and_fixed_threshold_policy():
    from offline_vision.fine_tune.d05d import iou, CONFIDENCE, NMS_IOU, MATCH_IOU
    assert iou([0,0,10,10],[0,0,10,10])==1
    assert iou([0,0,10,10],[10,0,20,10])==0
    assert (CONFIDENCE,NMS_IOU,MATCH_IOU)==(.25,.45,.50)


def test_pending_camera_labels_are_excluded_not_negative(tmp_path):
    root=tmp_path/'camera';root.mkdir();image=np.zeros((60,100,3),np.uint8);cv2.imwrite(str(root/'image.png'),image)
    frame={'sample_id':'camera-f1','source_id':'v1','media_seconds':0.,'frame_index':0,'image_path':'image.png','image_sha256':file_hash(root/'image.png'),
           'width':100,'height':60,'scene_hash':0,'capture_group_id':'clip1','split':'unassigned','reviewed':False,'suggested_vehicles':[],'annotations':[]}
    manifest={'dataset_id':'fake-camera','label_origin':'manual_review_required','sources':[{'source_id':'v1','path':'fake'}],'frames':[frame],'duplicate_reviews':[]}
    write_json(root/'manifest.template.json',manifest)
    path=camera_review_template(root,tmp_path/'review')
    prepared=prepare(None,None,tmp_path/'prepared',camera_dataset=root,camera_labels=root/'manifest.template.json',camera_review=path)
    assert not prepared['training_ready'] and prepared['records']==[] and prepared['counts']['train']['negative_images']==0


def test_yolo_missing_label_and_unknown_class_audited(tmp_path):
    root=tmp_path/'yolo';folder=root/'train/images';folder.mkdir(parents=True);(root/'train/labels').mkdir()
    (root/'data.yaml').write_text('names: [biensoxehoi, wrong_class]\n')
    for name in ['missing','wrong']:cv2.imwrite(str(folder/f'{name}.png'),np.zeros((60,100,3),np.uint8))
    (root/'train/labels/wrong.txt').write_text('1 0.5 0.5 0.2 0.1\n')
    a=audit_dataset(root,tmp_path/'audit',source='fixture',version='fixture',license_name='fixture')
    assert any('missing_label_file' in r['errors'] for r in a['records']) and any('unexpected_class' in r['errors'] for r in a['records'])


def test_onnx_adapter_maps_xyxy_to_native_coordinates_and_applies_nms(tmp_path,monkeypatch):
    import onnxruntime as ort
    from offline_vision.fine_tune.detector import YoloXPlateDetector
    (tmp_path/'fake.onnx').write_bytes(b'fixture model')
    write_json(tmp_path/'model.json',{'classes':['license_plate'],'decode_in_graph':True,'input_size':320,'path':'fake.onnx','sha256':file_hash(tmp_path/'fake.onnx')})
    class FakeSession:
        def __init__(self,*args,**kwargs):pass
        def run(self,names,inputs):
            assert inputs['images'].shape==(1,3,320,320) and list(inputs['images'][0,:,0,0])==[10,20,30]
            return [np.array([[[160,80,40,20,.8,.9],[160,80,40,20,.7,.9],[160,80,40,20,.1,.9]]],np.float32)]
    monkeypatch.setattr(ort,'InferenceSession',FakeSession)
    model=YoloXPlateDetector(tmp_path/'model.json');result=model.detect(np.full((100,200,3),[10,20,30],np.uint8),4)
    assert len(result)==1 and result[0].box==pytest.approx((87.5,43.75,112.5,56.25))
    assert result[0].label=='license_plate' and result[0].score==pytest.approx(.72)


def test_coco_duplicate_annotation_id_is_inventory_issue(tmp_path):
    a=coco(tmp_path/'raw');p=tmp_path/'raw/train/_annotations.coco.json';data=json.loads(p.read_text());data['annotations'].append(dict(data['annotations'][0]));write_json(p,data)
    a=audit_dataset(tmp_path/'raw',tmp_path/'audit-v2',source='fixture',version='fixture',license_name='fixture')
    assert any(i['reason']=='duplicate_coco_annotation_id' for i in a['issues'])


def test_corrupt_image_is_reported_without_claiming_it_usable(tmp_path):
    coco(tmp_path/'raw');(tmp_path/'raw/train/image.png').write_bytes(b'not an image')
    a=audit_dataset(tmp_path/'raw',tmp_path/'audit-v2',source='fixture',version='fixture',license_name='fixture')
    assert a['counts']['train']['structurally_usable']==0 and any('image_decode_failed' in r['errors'] for r in a['records'])
