import copy
from dataclasses import replace
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from offline_vision.benchmark import manual_lines, preprocess, run_benchmark
from offline_vision.config import CameraConfig
from offline_vision.dataset import duplicate_audit, prepare_dataset, save_png, sha256, validate_labels
from offline_vision.recognizer import PaddleTinyRecognizer, ctc_decode, paddle_input
from offline_vision.sampling import CandidatePool
from offline_vision.sessions import Session
from offline_vision.types import OcrRead
from offline_vision.video import VideoReader


def dataset(tmp_path):
    root = tmp_path / 'dataset'; root.mkdir()
    image = np.full((80,160,3),255,np.uint8)
    cv2.putText(image,'ABC123',(5,50),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,0),1)
    save_png(root/'frame.png',image)
    frame={'sample_id':'f1','source_id':'v1','media_seconds':1.0,'frame_index':1,'image_path':'frame.png',
           'image_sha256':sha256(root/'frame.png'),'width':160,'height':80,'scene_hash':123,
           'capture_group_id':'capture1','split':'unassigned','reviewed':False,'suggested_vehicles':[],'annotations':[]}
    manifest={'dataset_id':'fixture-dataset','label_origin':'manual_review_required','sources':[{'path':'synthetic-test'}],'frames':[frame],'duplicate_reviews':[]}
    (root/'manifest.template.json').write_text(json.dumps(manifest))
    return root,manifest


def labeled(manifest, text='ABC123'):
    labels=copy.deepcopy(manifest); labels['label_origin']='manual_review'; f=labels['frames'][0];f['reviewed']=True
    f['annotations']=[{'annotation_id':'plate1','kind':'plate','bbox':[0,0,160,80],'readability':'readable',
        'plate_text':text,'layout':'single-line','split_y':None,'vehicle_group_id':'vehicle1','label_origin':'manual_review'}]
    return labels


def test_missing_manual_labels_produce_pending_table_without_inference(tmp_path):
    root,manifest=dataset(tmp_path)
    result=run_benchmark(root,root/'manifest.template.json',tmp_path/'pending',Path('missing'),Path('missing'))
    assert result['status'].startswith('awaiting_manual')
    assert result['full_plate_exact_match_rate'] is None and result['metrics']==[]
    assert (tmp_path/'pending/predictions.pending.csv').exists()


def test_benchmark_exact_whole_plate_does_not_correct_characters(tmp_path):
    root,manifest=dataset(tmp_path); labels=labeled(manifest,'ABC-123')
    path=tmp_path/'manual.json';path.write_text(json.dumps(labels))
    rec={'right':(lambda x:('abc123',.8),{'name':'fake-test'}),'wrong':(lambda x:('ABC12O',.99),{'name':'fake-test'})}
    report=run_benchmark(root,path,tmp_path/'bench',Path('.'),Path('.'),recognizers=rec)
    assert len(report['metrics'])==12
    manual=[m for m in report['metrics'] if m['crop_source']=='manual']
    assert len(manual)==6
    assert all(m['full_plate_exact_match_rate']==1 for m in manual if m['model']=='right')
    assert all(m['full_plate_exact_match_rate']==0 for m in manual if m['model']=='wrong')
    assert all(m['full_plate_exact_match_rate'] is None for m in report['metrics'] if m['crop_source']=='detector')
    assert {p['raw'] for p in report['predictions']}=={'abc123','ABC12O'}
    assert all(p['strict_raw_correct'] is False for p in report['predictions'])


def test_uncertain_transcript_is_not_scored_as_ground_truth(tmp_path):
    root,m=dataset(tmp_path); labels=labeled(m);labels['frames'][0]['annotations'][0]['readability']='uncertain'
    path=tmp_path/'manual.json';path.write_text(json.dumps(labels))
    r=run_benchmark(root,path,tmp_path/'bench',Path('.'),Path('.'),recognizers={'test':(lambda x:('ABC123',.9),{})})
    assert all(p['full_plate_correct'] is None for p in r['predictions'])
    assert all(m['readable_manual_denominator']==0 and m['full_plate_exact_match_rate'] is None for m in r['metrics'])


def test_two_lines_use_manual_separator_not_aspect_or_transcription(tmp_path):
    root,m=dataset(tmp_path); labels=labeled(m);a=labels['frames'][0]['annotations'][0];a['layout']='two-line'
    with pytest.raises(ValueError,match='split_y'):validate_labels(labels,root)
    a['split_y']=25; validate_labels(labels,root)
    parts=manual_lines(np.zeros((80,160,3),np.uint8),a)
    assert [x.shape[0] for x in parts]==[25,55]


def test_detector_two_line_uses_absolute_native_separator(tmp_path):
    root,m=dataset(tmp_path);labels=labeled(m);a=labels['frames'][0]['annotations'][0]
    a.update(bbox=[0,10,160,70],layout='two-line',split_y=30)
    labels['frames'][0]['suggested_plates']=[{'bbox':[0,0,160,80],'score':.9}]
    path=tmp_path/'labels.json';path.write_text(json.dumps(labels));heights=[]
    def infer(image):heights.append(image.shape[0]);return 'ABC123',.9
    r=run_benchmark(root,path,tmp_path/'bench',Path('.'),Path('.'),recognizers={'fake':(infer,{})})
    # Original detector parts: y=0..30 and y=30..80. Proportional split would be 27.
    assert heights[6:8]==[30,50]


@pytest.mark.parametrize('field,value',[('label_origin','model_prediction'),('bbox',[-1,0,160,80])])
def test_invalid_or_model_labels_are_rejected(tmp_path,field,value):
    root,m=dataset(tmp_path);labels=labeled(m);labels['frames'][0]['annotations'][0][field]=value
    with pytest.raises(ValueError):validate_labels(labels,root)


def test_immutable_pixels_and_provenance_are_checked(tmp_path):
    root,m=dataset(tmp_path);labels=labeled(m);labels['frames'][0]['media_seconds']=9
    with pytest.raises(ValueError,match='metadata'):validate_labels(labels,root)
    labels=labeled(m);(root/'frame.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='PNG'):validate_labels(labels,root)


def test_capture_vehicle_and_duplicate_leakage_block_training(tmp_path):
    _,m=dataset(tmp_path);labels=labeled(m);a=labels['frames'][0];a['split']='train'
    b=copy.deepcopy(a);b['sample_id']='f2';b['split']='test';b['capture_group_id']='capture2';labels['frames'].append(b)
    r=duplicate_audit(labels)
    assert r['training_ready'] is False
    assert any(i['reason']=='group_crosses_splits' for i in r['issues'])
    assert any(i['reason'].startswith('cross_split_duplicate') for i in r['issues'])


def test_input_clip_cannot_be_random_split_by_renaming_capture_groups(tmp_path):
    _,m=dataset(tmp_path);labels=labeled(m);a=labels['frames'][0];a['split']='train'
    b=copy.deepcopy(a);b['sample_id']='f2';b['split']='test';b['capture_group_id']='renamed';b['annotations']=[]
    b['image_sha256']='another-image';b['scene_hash']=(1<<64)-1;labels['frames'].append(b)
    result=duplicate_audit(labels)
    assert any(i.get('group_id')=='source:v1' and i['reason']=='group_crosses_splits' for i in result['issues'])


@pytest.mark.parametrize('changes',[{'ocr_phase_seconds':(20,8)},{'max_candidates_per_phase':100},
                                   {'duplicate_hash_distance':2.5},{'repeat_crop_seconds':0}])
def test_candidate_policy_rejects_invalid_config(changes):
    with pytest.raises(ValueError):replace(CameraConfig('test',[[0,0],[1,0],[1,1],[0,1]]),**changes).validate()


def test_cpu_paddle_input_preserves_bgr_ratio_and_has_no_force_charset():
    image=np.full((20,100,3),[0,127,255],np.uint8)
    blob=paddle_input(image)
    assert blob.shape==(1,3,48,320) and blob[0,0,0,0]==-1 and blob[0,2,0,0]==1
    assert np.all(blob[0,:,:,240:]==0)
    logits=np.eye(4,dtype=np.float32)[[1,1,0,1,2,3]]
    assert ctc_decode(logits,['blank','A','0','O'])[0]=='AA0O'


def test_prepare_writes_native_pixel_png_and_never_ocr_labels(tmp_path):
    video=tmp_path/'fixture.mp4';writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),2,(160,80))
    for index in range(60):writer.write(np.full((80,160,3),index*4,np.uint8))
    writer.release()
    class Detector:
        metadata={'purpose':'scripted no-vehicle test'}
        def detect(self,image,seconds):return []
    output=tmp_path/'selected';m=prepare_dataset([video],output,Detector(),count=30,candidate_interval=1)
    decoded=next(iter(VideoReader(video,1)))
    assert len(m['frames'])==30
    assert np.array_equal(cv2.imread(str(output/m['frames'][0]['image_path'])),decoded.image)
    assert all(not f['reviewed'] and f['annotations']==[] for f in m['frames'])
    assert validate_labels(m,output)['readable_plates']==0


def textured_crop():
    image=np.full((40,100,3),245,np.uint8);cv2.putText(image,'ABC123',(3,28),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),1)
    return image


def test_pool_deferred_ocr_spans_phases_prefers_later_evidence(tmp_path):
    cfg=replace(CameraConfig('test',[[0,0],[1,0],[1,1],[0,1]]),repeat_crop_seconds=1,plate_attempt_interval_seconds=1,consistent_reads=8,max_ocr_reads=8)
    pool=CandidatePool(tmp_path,cfg);s=Session('s1',['t1'],0,0,0,(0,0,100,100))
    for stamp in [0,2,9,11,21,24]:
        o={'media_seconds':stamp,'box_in_vehicle_crop':[0,0,100,40],'used_for_ocr':False};s.plate_observations.append(o);pool.offer(s,textured_crop(),o)
    class OCR:
        calls=0
        def cost(self,c):return 1
        def read(self,c):self.calls+=1;return OcrRead('ABC123',.8,'fixture')
    ocr=OCR();assert ocr.calls==0
    output=tmp_path/'output';(output/'evidence/s1').mkdir(parents=True)
    stats={'ocr_model_calls':0,'ocr_observation_reads':0};pool.recognize(s,ocr,stats,output)
    assert s.reads[0]['phase']==2 and {r['phase'] for r in s.reads}=={0,1,2}
    assert s.ocr_calls==6 <= cfg.max_ocr_reads and s.proposed_plate is None


def test_pool_suppresses_near_duplicate_and_rejects_vertical_hardware(tmp_path):
    cfg=CameraConfig('test',[[0,0],[1,0],[1,1],[0,1]]);pool=CandidatePool(tmp_path,cfg);s=Session('s1',[],0,0,0,(0,0,100,100))
    observations=[]
    for stamp in [0,1,7]:
        o={'media_seconds':stamp};observations.append(o);pool.offer(s,textured_crop(),o)
    assert observations[1]['skipped_reason']=='near_duplicate_crop' and len(pool.pools['s1'][0])==2
    o={'media_seconds':9};pool.offer(s,np.tile(textured_crop()[:,:20],(4,1,1)),o)
    assert o['skipped_reason']=='crop_too_small'


def test_phase_gate_reserves_late_detector_budget():
    cfg=CameraConfig('test',[[0,0],[1,0],[1,1],[0,1]])
    p=CandidatePool(Path('.'),cfg);s=Session('s',[],0,0,0,(0,0,1,1));s.plate_attempts=3
    assert not p.should_attempt(s,7) and p.should_attempt(s,9)
    s.plate_attempts=6
    assert not p.should_attempt(s,19) and p.should_attempt(s,21)


def test_real_pinned_paddle_model_can_read_local_synthetic_line():
    folder=Path(__file__).resolve().parents[2]/'data/offline-vision/benchmark-models/paddle-tiny'
    if not (folder/'manifest.json').exists():pytest.skip('Explicit fetch required; tests never download')
    model=PaddleTinyRecognizer(folder);raw,score=model.line(textured_crop())
    assert isinstance(raw,str) and (score is None or 0<=score<=1)
    assert model.session.get_providers()==['CPUExecutionProvider']
