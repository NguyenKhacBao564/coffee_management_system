import copy
import json
import subprocess
import numpy as np
import pytest
from offline_vision.dataset import browser_manifest,validate_labels
from offline_vision.fine_tune.adaptation import epoch_order,transform,initialize,load_policy
from offline_vision.fine_tune.compare import score
from offline_vision.types import Detection


@pytest.mark.parametrize('value',[0,2**53+1,2**63+7,2**64-1])
def test_hash_survives_real_javascript_export_import(value):
    manifest={'frames':[{'scene_hash':value}]}
    payload=browser_manifest(manifest)
    result=subprocess.run(['node','-e','process.stdin.on("data", x=>process.stdout.write(JSON.stringify(JSON.parse(x))))'],input=json.dumps(payload),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)['frames'][0]['scene_hash']==str(value)
    assert manifest['frames'][0]['scene_hash']==value


def test_exact_hash_import_rejects_rounded_numeric_or_string(tmp_path):
    import cv2
    from offline_vision.dataset import sha256
    cv2.imwrite(str(tmp_path/'image.png'),np.zeros((2,2,3),np.uint8))
    m={'dataset_id':'test','label_origin':'manual_review','sources':[],
       'frames':[{'sample_id':'f','source_id':'s','media_seconds':0,'frame_index':0,'image_path':'image.png','image_sha256':sha256(tmp_path/'image.png'),
                  'width':2,'height':2,'scene_hash':2**64-1,'reviewed':False,'annotations':[]}]}
    (tmp_path/'manifest.template.json').write_text(json.dumps(m))
    labels=browser_manifest(m);assert validate_labels(labels,tmp_path)['frames']==1
    for bad in [2**64,str(2**64),'018446744073709551615',True]:
        labels['frames'][0]['scene_hash']=bad
        with pytest.raises(ValueError,match='scene_hash'):validate_labels(labels,tmp_path)


def test_finite_camera_sampling_caps_fraction_and_is_resume_deterministic():
    records=[{'label_origin':'roboflow_published_annotation'}]*8+[{'label_origin':'manual_review'}]*10
    policy={'camera_max_fraction':.2,'camera_repeats_per_epoch':1}
    a=epoch_order(records,5,1,policy)
    assert len(a)==10 and len(set(a))==10 and sum(i>=8 for i in a)==2
    assert epoch_order(records,5,1,policy)==a and set(range(8))<=set(a)
    assert len(epoch_order(records,5,1))==18


def test_camera_variants_are_sampled_once_per_parent_frame():
    public = [{'sample_id': f'p{i}', 'label_origin': 'roboflow_published_annotation'} for i in range(20)]
    camera = [{'sample_id': f'f{i}-{variant}', 'sampling_group_id': f'f{i}',
               'label_origin': 'manual_review'} for i in range(4) for variant in ['full', 'crop']]
    records = public + camera
    order = epoch_order(records, 20261007, 0, {'camera_max_fraction': .2})
    chosen = [records[i] for i in order if i >= len(public)]
    assert len(order) == 24 and len(chosen) == 4
    assert len({r['sampling_group_id'] for r in chosen}) == 4
    assert order == epoch_order(records, 20261007, 0, {'camera_max_fraction': .2})


def test_light_augmentation_keeps_geometry_no_flip_and_deterministic():
    image=np.zeros((50,100,3),np.uint8);image[:,:50]=200
    a=transform(5)(image);b=transform(5)(image)
    assert np.array_equal(a,b) and a.shape==image.shape
    assert a[:,:40].mean()>a[:,60:].mean() and image[:,:40].mean()==200


def test_partial_annotations_unmatched_is_not_false_positive(monkeypatch):
    monkeypatch.setattr('cv2.imread',lambda _:np.zeros((50,100,3),np.uint8))
    class Detector:
        def detect(self,image,t):return [Detection((0,0,10,10),'license_plate',.9,'test')]
    r=score([{'sample_id':'f','image_path':'dummy','boxes':[],'annotations_complete':False}],Detector())
    assert r['unmatched_predictions']==1 and r['false_positives']==0 and r['false_positives_per_image'] is None


def test_d05d_one_class_initialization_is_strict_and_hashed(tmp_path):
    import torch
    from offline_vision.fine_tune.audit import file_hash
    model=torch.nn.Linear(2,1);p=tmp_path/'init.pth'
    torch.save({'purpose':'d05d_cuda_training','model':model.state_dict()},p)
    target=torch.nn.Linear(2,1);report=initialize(target,p,file_hash(p))
    assert report['skipped_keys']==[] and report['optimizer_scheduler_reused'] is False
    assert torch.equal(model.weight,target.weight)
    with pytest.raises(ValueError,match='hash'):initialize(target,p,'wrong')


def test_detector_honors_export_graph_optimization_and_rejects_unknown(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from offline_vision.fine_tune.audit import file_hash
    from offline_vision.fine_tune.detector import YoloXPlateDetector
    options = []
    class Options:
        def __init__(self):
            self.graph_optimization_level = 'default'
    def session(path, sess_options, providers):
        options.append(sess_options.graph_optimization_level)
        return object()
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(SessionOptions=Options,
        GraphOptimizationLevel=SimpleNamespace(ORT_DISABLE_ALL='disabled'), InferenceSession=session))
    weight = tmp_path / 'model.onnx'; weight.write_bytes(b'fixture')
    metadata = {'classes': ['license_plate'], 'decode_in_graph': True, 'path': weight.name,
                'sha256': file_hash(weight), 'onnx_graph_optimization': 'disabled'}
    path = tmp_path / 'model.json'; path.write_text(json.dumps(metadata))
    YoloXPlateDetector(path)
    assert options == ['disabled']
    metadata['onnx_graph_optimization'] = 'unknown'; path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='optimization'): YoloXPlateDetector(path)


def camera_fixture(tmp_path):
    import cv2,importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    from offline_vision.fine_tune.audit import file_hash
    spec=importlib.util.spec_from_file_location('d05f_prepare',Path(__file__).resolve().parents[2]/'scripts/d05f-prepare.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rng=np.random.default_rng(27);public=[]
    for i,split in enumerate(['train']*4+['val','test']):
        path=tmp_path/f'p{i}.png';cv2.imwrite(str(path),rng.integers(0,255,(80,100,3),np.uint8))
        public.append({'sample_id':f'p{i}','split':split,'image_path':str(path),'file_sha256':file_hash(path),'width':100,'height':80,
                       'label_origin':'roboflow_published_annotation','boxes':[{'class':'license_plate','bbox':[10,10,30,20]}]})
    pub=tmp_path/'public.json';pub.write_text(json.dumps({'training_ready':True,'class_names':['license_plate'],'records':public}))
    frames=[]
    for i,split in enumerate(['train','test']):
        path=tmp_path/f'c{i}.png';cv2.imwrite(str(path),rng.integers(0,255,(80,100,3),np.uint8))
        frames.append({'sample_id':f'c{i}','source_id':f'v{i}','media_seconds':i,'frame_index':i,'image_path':path.name,'image_sha256':file_hash(path),
                       'width':100,'height':80,'scene_hash':int(rng.integers(0,2**63)),'capture_group_id':f'capture{i}','split':split,
                       'reviewed':True,'annotations_complete':True,'plate_presence':'plate',
                       'annotations':[{'annotation_id':f'a{i}','label_origin':'manual_review','kind':'plate','bbox':[10,10,30,20],
                                       'readability':'unreadable','plate_text':'','layout':'pending','vehicle_group_id':f'vehicle{i}'}]})
    labels={'dataset_id':'fixture','sources':[],'label_origin':'manual_review','frames':frames,'duplicate_reviews':[]}
    (tmp_path/'manifest.template.json').write_text(json.dumps(labels))
    path=tmp_path/'labels.json';path.write_text(json.dumps(browser_manifest(labels)))
    args=SimpleNamespace(public_manifest=pub,dataset=tmp_path,labels=path,output=tmp_path/'prepared')
    return module,args,labels


def test_prepare_only_complete_labels_and_one_plate_class(tmp_path):
    module,args,labels=camera_fixture(tmp_path)
    labels['frames'][0]['annotations'].append({'annotation_id':'negative','label_origin':'manual_review','kind':'hard_negative','bbox':[50,40,80,60]})
    args.labels.write_text(json.dumps(browser_manifest(labels)))
    result=module.prepare(args)
    assert result['training_ready'] and result['counts']['train']['negative_images']==1
    manifest=json.loads((args.output/'manifest.json').read_text())
    assert all(a['class']=='license_plate' for r in manifest['records'] for a in r['boxes'])
    assert result['samples_per_epoch']==5 and result['batches_per_epoch']==3


def test_incomplete_frame_never_becomes_negative(tmp_path):
    module,args,labels=camera_fixture(tmp_path)
    labels['frames'][0].update(annotations=[],annotations_complete=False)
    args.labels.write_text(json.dumps(browser_manifest(labels)))
    result=module.prepare(args)
    assert not result['training_ready'] and result['counts']['train']['negative_images']==0
    assert result['counts']['train']['camera_images']==0


def test_hard_negative_intersecting_real_plate_rejected(tmp_path):
    module,args,labels=camera_fixture(tmp_path)
    labels['frames'][0]['annotations'].append({'annotation_id':'bad','label_origin':'manual_review','kind':'hard_negative','bbox':[15,12,25,18]})
    args.labels.write_text(json.dumps(browser_manifest(labels)))
    with pytest.raises(ValueError,match='overlaps'):module.prepare(args)


def test_camera_vehicle_identity_cannot_cross_train_test(tmp_path):
    module,args,labels=camera_fixture(tmp_path)
    for f in labels['frames']:f['annotations'][0]['vehicle_group_id']='same-vehicle'
    args.labels.write_text(json.dumps(browser_manifest(labels)))
    assert not module.prepare(args)['training_ready']
