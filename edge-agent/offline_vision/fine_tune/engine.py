"""Bounded CPU pilot, finite sampling, checkpoint resume and ONNX parity."""
import json
import math
import os
import random
import time
from pathlib import Path

import cv2
import numpy as np
import psutil

from ..export import write_json
from .assets import make_model
from .audit import file_hash, valid_box


def preprocess(image, size):
    h,w=image.shape[:2];scale=min(size/h,size/w)
    resized=cv2.resize(image,(int(w*scale),int(h*scale)))
    canvas=np.full((size,size,3),114,np.uint8);canvas[:resized.shape[0],:resized.shape[1]]=resized
    return canvas.transpose(2,0,1).astype(np.float32),scale


def configuration(path):
    import yaml
    config=yaml.safe_load(path.read_text())
    if set(config)!={'seed','input_size','batch_size','threads','epochs','max_steps','learning_rate','mosaic','mixup','horizontal_flip'}:
        raise ValueError('Unexpected/missing training config fields')
    for k,low,high in [('input_size',320,640),('batch_size',1,4),('threads',1,4),('epochs',1,20),('max_steps',1,1000)]:
        if type(config[k]) is not int or not low<=config[k]<=high:raise ValueError(f'Invalid bound: {k}')
    if config['input_size']%32 or type(config['seed']) is not int or not 0<float(config['learning_rate'])<=.01:raise ValueError('Invalid size/seed/learning rate')
    if any(config[k] is not False for k in ['mosaic','mixup','horizontal_flip']):raise ValueError('Pilot disables augmentation and data duplication')
    return config


def load_manifest(path):
    manifest=json.loads(path.read_text())
    if manifest['class_names']!=['license_plate']:raise ValueError('Exactly one class required')
    if manifest['purpose']!='synthetic_preflight_fixture' and not manifest['training_ready']:raise ValueError('Human review/split audit not ready')
    for r in manifest['records']:
        image_path=Path(r['image_path'])
        if not image_path.is_absolute():image_path=path.parent/image_path
        r['image_path']=str(image_path.resolve())
        if file_hash(Path(r['image_path']))!=r['file_sha256']:raise ValueError('Image hash changed')
        if any(not valid_box(a['bbox'],r['width'],r['height']) for a in r['boxes']):raise ValueError('Invalid bbox')
    train=[r for r in manifest['records'] if r['split']=='train']
    if not train:raise ValueError('No train samples')
    return manifest,train


def batch(records,size,*,transform=None):
    import torch
    images=[];targets=[];pictures=[];limit=max(1,max(len(r['boxes']) for r in records))
    for r in records:
        image=cv2.imread(r['image_path'])
        if image is None or image.shape[:2]!=(r['height'],r['width']):raise ValueError('Image decode/dimensions changed')
        if transform is not None: image=transform(image)
        tensor,scale=preprocess(image,size);images.append(tensor);target=np.zeros((limit,5),np.float32)
        picture=tensor.transpose(1,2,0).astype(np.uint8)
        for i,a in enumerate(r['boxes']):
            x1,y1,x2,y2=np.array(a['bbox'])*scale;target[i]=[0,(x1+x2)/2,(y1+y2)/2,x2-x1,y2-y1]
            cv2.rectangle(picture,(round(x1),round(y1)),(round(x2),round(y2)),(0,255,0),2)
        cv2.putText(picture,r['sample_id'][:50],(8,24),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,255),1)
        pictures.append(picture);targets.append(target)
    return torch.tensor(np.stack(images)),torch.tensor(np.stack(targets)),np.hstack(pictures)


def run(manifest_path,config_path,assets,output,*,resume=None,preflight=False,steps_this_run=None):
    import torch
    config=configuration(config_path)
    if preflight and (config['max_steps']>2 or config['epochs']>2):raise ValueError('Preflight limited to two total optimizer steps / two epochs')
    if steps_this_run is not None and not 1<=steps_this_run<=config['max_steps']:raise ValueError('Invalid invocation step bound')
    manifest,train=load_manifest(manifest_path)
    if manifest['batch_size']!=config['batch_size']:raise ValueError('Manifest and config batch sizes differ')
    torch.set_num_threads(config['threads']);torch.use_deterministic_algorithms(True)
    random.seed(config['seed']);np.random.seed(config['seed']);torch.manual_seed(config['seed'])
    model,metadata=make_model(assets);optimizer=torch.optim.SGD(model.parameters(),lr=config['learning_rate'],momentum=.9)
    dataset_sha=file_hash(manifest_path);config_sha=file_hash(config_path)
    total=0;epoch=0;cursor=0
    if resume:
        saved=torch.load(resume,map_location='cpu',weights_only=True)
        if saved['dataset_sha256']!=dataset_sha or saved['config_sha256']!=config_sha:raise ValueError('Resume data/config mismatch')
        model.load_state_dict(saved['model']);optimizer.load_state_dict(saved['optimizer'])
        total,epoch,cursor=saved['steps'],saved['epoch'],saved['cursor'];torch.set_rng_state(saved['torch_rng'])
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    process=psutil.Process();start=time.perf_counter();cpu0=process.cpu_times();peak=process.memory_info().rss
    losses=[];sample_order=[];batches=math.ceil(len(train)/config['batch_size'])
    model.train()
    limit=min(config['max_steps'],total+steps_this_run) if steps_this_run else config['max_steps']
    while epoch<config['epochs'] and total<limit:
        order=list(range(len(train)));random.Random(config['seed']+epoch).shuffle(order)
        while cursor<batches and total<limit:
            chosen=[train[i] for i in order[cursor*config['batch_size']:(cursor+1)*config['batch_size']]]
            images,targets,picture=batch(chosen,config['input_size'])
            if not losses:
                if not cv2.imwrite(str(output/'batch.png'),picture):raise ValueError('Cannot save batch')
                (output/'batch.png').chmod(0o600)
            optimizer.zero_grad(set_to_none=True);loss=model(images,targets)
            if not torch.isfinite(loss['total_loss']):raise ValueError('Nonfinite loss')
            loss['total_loss'].backward();optimizer.step()
            losses.append({k:float(v.detach()) if hasattr(v,'detach') else float(v) for k,v in loss.items()})
            sample_order.append([r['sample_id'] for r in chosen]);total+=1;cursor+=1;peak=max(peak,process.memory_info().rss)
        if cursor==batches:epoch+=1;cursor=0
    checkpoint={'model':model.state_dict(),'optimizer':optimizer.state_dict(),'steps':total,'epoch':epoch,'cursor':cursor,
        'torch_rng':torch.get_rng_state(),'seed':config['seed'],'dataset_sha256':dataset_sha,'config_sha256':config_sha,
        'model_revision':metadata['source_revision'],'weights_sha256':metadata['weights_sha256'],'purpose':manifest['purpose']}
    torch.save(checkpoint,output/'checkpoint.pth');(output/'checkpoint.pth').chmod(0o600)
    # Round-trip every tensor. Resume is also exercised separately using this checkpoint.
    restored=torch.load(output/'checkpoint.pth',map_location='cpu',weights_only=True)
    if any(not torch.equal(v,restored['model'][k]) for k,v in model.state_dict().items()):raise ValueError('Checkpoint roundtrip failed')
    cpu1=process.cpu_times();elapsed=time.perf_counter()-start
    result={'purpose':manifest['purpose'],'is_quality_trained_detector':False if preflight else None,'new_steps':len(losses),'total_steps':total,
        'epochs_completed':epoch,'cursor':cursor,'train_samples':len(train),'train_boxes':sum(len(r['boxes']) for r in train),
        'batches_per_epoch':batches,'losses':losses,'sample_order':sample_order,'dataset_sha256':dataset_sha,'config_sha256':config_sha,
        'checkpoint_sha256':file_hash(output/'checkpoint.pth'),'checkpoint_roundtrip':'passed','resume_from':str(resume) if resume else None,
        'wall_seconds':elapsed,'cpu_seconds':cpu1.user+cpu1.system-cpu0.user-cpu0.system,'rss_peak_observed_bytes':peak,
        'resource_scope':'This CPU process on this MacBook; sampled RSS, not whole-machine/cloud estimates',
        'versions':{'torch':torch.__version__,'opencv':cv2.__version__,'numpy':np.__version__},'config':config,'model':metadata}
    write_json(output/'run.json',result);return result


def export(checkpoint,manifest_path,config_path,assets,output):
    import torch
    import onnx
    import onnxruntime as ort
    config=configuration(config_path);manifest,train=load_manifest(manifest_path)
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
    if saved['dataset_sha256']!=file_hash(manifest_path) or saved['config_sha256']!=file_hash(config_path):raise ValueError('Export inputs differ from checkpoint')
    torch.set_num_threads(config['threads']);model,metadata=make_model(assets,pretrained=False);model.load_state_dict(saved['model']);model.eval();model.head.decode_in_inference=True
    images,_,_=batch(train[:1],config['input_size']);output.mkdir(parents=True,exist_ok=False,mode=0o700)
    with torch.no_grad():expected=model(images).numpy()
    # Preserve BatchNorm operations for the D05f checkpoint. Folding them into
    # convolutions amplified FP32 differences in the decoded width/height exp.
    # This changes export execution, not checkpoint tensors or parity bounds.
    preserve_bn = saved.get('purpose') == 'd05f_cuda_training'
    torch.onnx.export(model,images,output/'detector.onnx',input_names=['images'],output_names=['detections'],opset_version=11,dynamo=False,
                      do_constant_folding=not preserve_bn)
    onnx.checker.check_model(onnx.load(output/'detector.onnx'))
    options=ort.SessionOptions();options.intra_op_num_threads=config['threads'];options.inter_op_num_threads=1
    if preserve_bn: options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session=ort.InferenceSession(str(output/'detector.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    actual=session.run(None,{'images':images.numpy()})[0]
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():raise ValueError('Nonfinite export output')
    # Decoded coordinates are pixels; probabilities are dimensionless. Compare
    # them separately, with absolute bounds fixed for FP32 CPU deployment.
    np.testing.assert_allclose(actual[:,:,:4],expected[:,:,:4],rtol=0,atol=.05)
    np.testing.assert_allclose(actual[:,:,4:],expected[:,:,4:],rtol=0,atol=1e-4)
    report={'family':'YOLOX-Nano','classes':['license_plate'],'input_size':config['input_size'],'sha256':file_hash(output/'detector.onnx'),
        'path':'detector.onnx','decode_in_graph':True,'preprocess':'BGR raw 0-255 top-left letterbox 114','onnx_opset':11,
        'source_revision':metadata['source_revision'],'code_license':metadata['code_license'],'checkpoint_sha256':file_hash(checkpoint),
        'purpose':saved['purpose'],'quality_accepted':False,'steps':saved['steps'],'parity_max_absolute_error':float(np.max(np.abs(actual-expected))),
        'parity':'passed','parity_tolerance':{'coordinate_pixels_absolute':.05,'probabilities_absolute':1e-4,'relative':0},
        'parity_probability_max_absolute_error':float(np.max(np.abs(actual[:,:,4:]-expected[:,:,4:]))),
        'parity_scope':'all raw outputs on the single export input; broader checks must be reported separately',
        'parity_sample_ids':[train[0]['sample_id']],
        'output_shape':list(actual.shape),'onnxruntime':ort.__version__}
    if preserve_bn:
        report['onnx_graph_optimization']='disabled'
        report['batch_norm_export']='preserved; constant folding disabled'
    (output/'detector.onnx').chmod(0o600);write_json(output/'model.json',report);return report


def fixture(output):
    """Synthetic geometry for executable preflight only; never camera ground truth."""
    output.mkdir(parents=True,exist_ok=False,mode=0o700);records=[]
    rng=np.random.default_rng(20261007)
    for i in range(4):
        image=rng.integers(10,100,(360,640,3),dtype=np.uint8);box=[180+i*10,170,320+i*10,214]
        if i!=3:
            cv2.rectangle(image,tuple(box[:2]),tuple(box[2:]),(240,240,240),-1)
            cv2.putText(image,'FIXTURE',(box[0]+3,box[1]+28),cv2.FONT_HERSHEY_SIMPLEX,.5,(10,10,10),1)
        path=output/f'fixture-{i}.png';cv2.imwrite(str(path),image);path.chmod(0o600)
        records.append({'sample_id':f'fixture-{i}','image_path':str(path.resolve()),'file_sha256':file_hash(path),'width':640,'height':360,
            'boxes':[{'bbox':box,'class':'license_plate'}] if i!=3 else [],'split':'train','label_origin':'synthetic_fixture'})
    manifest={'schema_version':1,'purpose':'synthetic_preflight_fixture','class_names':['license_plate'],'batch_size':2,'records':records,
        'training_ready':False,'not_camera_ground_truth':True}
    write_json(output/'manifest.json',manifest);return manifest
