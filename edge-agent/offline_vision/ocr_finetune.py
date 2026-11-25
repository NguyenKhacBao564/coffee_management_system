"""Bounded adapter around pinned FastPlate Keras model/loss, not a new pipeline.

Seeded finite epochs, augmentation at native crop BEFORE official preprocessing,
gold val/test only, optimizer-inclusive .keras snapshots and external time guard.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

import cv2
import numpy as np

from .camera_augmentation import augment, seed_for, char_height_proxy
from .consensus import normalize
from .dataset import sha256
from .export import write_json
from .ocr_training_data import load_lock
from .plate_recognizer import plate_input, slot_decode
from .sampling import image_hash, hash_distance
from .vn_synthetic import synthetic_augment


def finite_epoch(rows, epoch, seed, synthetic_per_silver=1):
    silver=[r for r in rows if r['label_origin']=='silver']
    synthetic=[r for r in rows if r['label_origin']=='synthetic']
    if any(r['label_origin'] not in {'silver','synthetic'} or r['split']!='train' for r in rows):raise ValueError('Gold/val/test forbidden in train')
    if not silver or not synthetic:raise ValueError('Both silver and synthetic needed')
    rng=np.random.default_rng(seed_for(seed,epoch,'finite-epoch'))
    count=min(len(synthetic),round(len(silver)*synthetic_per_silver))
    selected=silver+[synthetic[i] for i in rng.choice(len(synthetic),count,replace=False)]
    rng.shuffle(selected)
    return selected


def prediction(model, blob):
    import keras
    value=model(blob,training=False)
    if isinstance(value,dict):value=value['plate']
    return keras.ops.convert_to_numpy(value)


def validate(model, root, gold, plate_config):
    from .ocr_diagnostic import edit_distance
    rows=[]
    for item in gold['rows']:
        if item['split']!='val':continue
        im=cv2.imread(str(root/'evaluation'/item['crop_path']))
        raw,_,_=slot_decode(prediction(model,plate_input(im,plate_config)),plate_config)
        rows.append({'source':item['source'],'sample_id':item['sample_id'],'raw':raw,'exact':normalize(raw)==item['text'],'errors':edit_distance(normalize(raw),item['text']),'characters':len(item['text'])})
    sources=sorted({r['source'] for r in rows})
    if not rows:raise ValueError('Confirmed gold validation required')
    macro=sum(sum(r['exact'] for r in rows if r['source']==s)/sum(r['source']==s for r in rows) for s in sources)/len(sources)
    return {'source_macro_exact':macro,'correct':sum(r['exact'] for r in rows),'samples':len(rows),'edit_errors':sum(r['errors'] for r in rows),'characters':sum(r['characters'] for r in rows),'rows':rows}


def native_batch(root, samples, cfg, plate_config, epoch):
    from fast_plate_ocr.train.utilities.utils import target_transform
    x,y,metadata=[],[],[]
    for row in samples:
        path=root/row['crop_path'];image=cv2.imread(str(path))
        if image is None or sha256(path)!=row['crop_sha256']:raise ValueError('Training image changed')
        base=image;record={'applied':False};accepted=False
        for draw in range(4):
            try:
                if row['label_origin']=='synthetic':
                    image,record=synthetic_augment(base,row['text'],row['glyph_boxes'],row['split_y'],cfg['augmentation'],sample_id=row['sample_id'],epoch=epoch,draw=draw)
                else:
                    image,visible,record=augment(base,row['text'],split='train',config=cfg['augmentation'],sample_id=row['sample_id'],epoch=epoch,draw=draw,groups=[g for g in ('lighting','weather','sharpness','resolution','color') if np.random.default_rng(seed_for(cfg['seed'],epoch,row['sample_id']+g,draw)).random()<.12],character_height=char_height_proxy(base,row.get('split_y_hypothesis')))
                    if visible!=row['text'] or not record['native_fastplate_eligible']:raise ValueError('Training label changed')
                if any(hash_distance(image_hash(image),d)<=4 for d in cfg['heldout_crop_dhash']):continue
                accepted=True;break
            except ValueError:continue
        if not accepted:
            if row['label_origin']=='silver' and not any(hash_distance(image_hash(base),d)<=4 for d in cfg['heldout_crop_dhash']):image=base;record={'applied':False,'fallback':'unmodified leakage-checked silver'}
            else:raise ValueError('No label-safe non-leaking synthetic transform after 4 attempts')
        x.append(plate_input(image,plate_config)[0]);y.append(target_transform(row['text'],plate_config['max_plate_slots'],plate_config['alphabet'],plate_config['pad_char']))
        metadata.append({'sample_id':row['sample_id'],'origin':row['label_origin'],'native_size':[image.shape[1],image.shape[0]],'augmentation':record})
    return np.array(x),np.array(y),metadata


def save_state(model, output, state):
    temp=output/'last.tmp.keras';model.save(temp);os.replace(temp,output/'last.keras');write_json(output/'state.json',state)


def load_saved(path, loss_fn):
    import keras
    return keras.models.load_model(path,custom_objects={'cce':loss_fn},compile=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['inspect','preflight','train','export']);parser.add_argument('--root',type=Path,default=Path.cwd());parser.add_argument('--output',type=Path,required=True);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if args.mode=='export':
        import subprocess,sys
        common=[sys.executable,'-m','offline_vision.plate_export','--root',str(args.root),'--output',str(args.output)]
        subprocess.run(common+['--reference-only'],env={**os.environ,'KERAS_BACKEND':'torch'},check=True,stdin=subprocess.DEVNULL,timeout=120)
        subprocess.run(common,env={**os.environ,'KERAS_BACKEND':'tensorflow','CUDA_VISIBLE_DEVICES':'-1'},check=True,stdin=subprocess.DEVNULL,timeout=300)
        return
    root=args.root.resolve();cfg=json.loads((root/'config.json').read_text());gold=load_lock(root/'evaluation');dataset=json.loads((root/'dataset.json').read_text())
    for rel,digest in json.loads((root/'package.hashes.json').read_text()).items():
        if sha256(root/rel)!=digest:raise ValueError('Package file changed: '+rel)
    if sha256(root/'evaluation/evaluation.lock.json')!=cfg['evaluation_sha256']:raise ValueError('Wrong frozen evaluation')
    import keras,torch
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml
    from fast_plate_ocr.train.model.model_schema import load_model_config_from_yaml
    from fast_plate_ocr.train.model.model_builders import build_model
    from fast_plate_ocr.train.model.loss import cce_loss
    keras.utils.set_random_seed(cfg['seed']);torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    pc=load_plate_config_from_yaml(root/'model/plate_config.yaml');plate_cfg=pc.model_dump();mc=load_model_config_from_yaml(root/'model/model_config.yaml')
    loss_fn=cce_loss(pc.vocabulary_size,label_smoothing=.01)
    args.output.mkdir(parents=True,exist_ok=args.resume,mode=0o700)
    full=build_model(mc,pc,enable_region_head=True)
    full.load_weights(root/'model/pretrained.keras',skip_mismatch=False)
    # Strict full checkpoint load, then retain plate graph; untouched region branch excluded.
    model=keras.Model(full.inputs,full.output['plate'],name='d05k_fastplate_plate_only')
    report={'backend':keras.backend.backend(),'keras':keras.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None,'loaded_weights':len(full.weights),'loaded_elements':sum(np.prod(w.shape).item() for w in full.weights),'skip_mismatch':False,'excluded_region_branch_weights':len(full.weights)-len(model.weights),'trainable_parameters':model.count_params(),'pretrained_sha256':sha256(root/'model/pretrained.keras'),'gold_train':0,'seed':cfg['seed'],'batch_size':cfg['batch_size'],'drop_last':False,'epoch_samples':len(finite_epoch(dataset['rows'],0,cfg['seed'],cfg['synthetic_per_silver'])),'epoch_batches':math.ceil(len(finite_epoch(dataset['rows'],0,cfg['seed'],cfg['synthetic_per_silver']))/cfg['batch_size'])}
    # Confirm trainable checkpoint is the SAME pretrained teacher, on validation only.
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=2;teacher=ort.InferenceSession(str(root/'model/pretrained.onnx'),sess_options=options,providers=['CPUExecutionProvider']);tn=teacher.get_inputs()[0].name
    outputs=[o.name for o in teacher.get_outputs() if o.shape[-1]==pc.max_plate_slots*pc.vocabulary_size or o.shape[-2:]==[pc.max_plate_slots,pc.vocabulary_size]]
    if len(outputs)!=1:raise ValueError('Cannot identify official plate head')
    to=outputs[0]
    diffs=[];raw_equal=[]
    for row in gold['rows']:
        if row['split']!='val':continue
        blob=plate_input(cv2.imread(str(root/'evaluation'/row['crop_path'])),plate_cfg);actual=prediction(model,blob);expected=teacher.run([to],{tn:blob})[0];diffs.append(float(np.max(np.abs(actual-expected))));raw_equal.append(slot_decode(actual,plate_cfg)[0]==slot_decode(expected,plate_cfg)[0])
    report['pretrained_teacher_parity']={'validation_inputs':len(diffs),'max_probability_difference':max(diffs),'raw_equal':sum(raw_equal),'tolerance_atol':.0005,'passed':max(diffs)<=.0005 and all(raw_equal)}
    if not report['pretrained_teacher_parity']['passed']:raise ValueError('Trainable checkpoint differs from locked pretrained ONNX')
    write_json(args.output/'environment.json',report)
    if args.mode=='inspect':print(json.dumps(report,indent=2));return
    total_steps=report['epoch_batches']*cfg['epochs'];schedule=keras.optimizers.schedules.CosineDecay(cfg['learning_rate'],total_steps,alpha=.3)
    optimizer=keras.optimizers.AdamW(schedule,weight_decay=.0001,clipnorm=1.)
    model.compile(optimizer=optimizer,loss=loss_fn,jit_compile=False)
    if args.mode=='preflight':
        samples=finite_epoch(dataset['rows'],0,cfg['seed'],cfg['synthetic_per_silver']);losses=[];seconds=[]
        for step in range(2):
            x,y,meta=native_batch(root,samples[step*cfg['batch_size']:(step+1)*cfg['batch_size']],cfg,plate_cfg,0)
            start=time.perf_counter();loss=float(model.train_on_batch(x,y));torch.cuda.synchronize() if torch.cuda.is_available() else None;seconds.append(time.perf_counter()-start);losses.append(loss)
            if not math.isfinite(loss):raise ValueError('Nonfinite preflight loss')
            before=prediction(model,x);before_opt=[keras.ops.convert_to_numpy(v).copy() for v in model.optimizer.variables];iterations=int(model.optimizer.iterations)
            save_state(model,args.output,{'phase':'preflight','step':step+1});loaded=load_saved(args.output/'last.keras',loss_fn)
            if int(loaded.optimizer.iterations)!=iterations or any(not np.array_equal(a,keras.ops.convert_to_numpy(b)) for a,b in zip(before_opt,loaded.optimizer.variables)) or len(before_opt)!=len(loaded.optimizer.variables):raise ValueError('Optimizer resume differs')
            if not np.allclose(prediction(loaded,x),before,atol=1e-6,rtol=0):raise ValueError('Checkpoint predictions differ')
            model=loaded;write_json(args.output/f'batch-{step}.json',meta)
            # Native uint8 loader visualization, not augmented test.
            montage=np.concatenate([cv2.cvtColor(v,cv2.COLOR_RGB2BGR) for v in x],axis=1);cv2.imwrite(str(args.output/f'batch-{step}.png'),montage)
        result={'losses':losses,'seconds_per_batch':seconds,'resume_iterations':int(model.optimizer.iterations),'validation':validate(model,root,gold,plate_cfg),'peak_vram_bytes':torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None,'finite_epoch_batches':report['epoch_batches'],'preflight_only':True};write_json(args.output/'preflight.json',result);print(json.dumps(result,indent=2));return
    start=time.perf_counter();initial=validate(model,root,gold,plate_cfg);state={'next_epoch':0,'next_batch':0,'steps':0,'elapsed_seconds':0,'initial_validation':initial,'best_validation':None,'chosen_checkpoint':'initial.keras','config_sha256':sha256(root/'config.json')}
    if args.resume:
        state=json.loads((args.output/'state.json').read_text())
        if state['config_sha256']!=sha256(root/'config.json'):raise ValueError('Resume config changed')
        model=load_saved(args.output/'last.keras',loss_fn)
    else:
        model.save(args.output/'initial.keras');write_json(args.output/'initial-validation.json',initial)
    with (args.output/'iterations.jsonl').open('a') as log:
        for epoch in range(state['next_epoch'],cfg['epochs']):
            samples=finite_epoch(dataset['rows'],epoch,cfg['seed'],cfg['synthetic_per_silver']);batch_start=state['next_batch'] if epoch==state['next_epoch'] else 0
            epoch_start=time.perf_counter()
            for batch in range(batch_start,report['epoch_batches']):
                if state['steps']>=cfg['max_steps'] or time.perf_counter()-start+state['elapsed_seconds']>=cfg['max_seconds']:
                    state.update({'next_epoch':epoch,'next_batch':batch,'elapsed_seconds':state['elapsed_seconds']+time.perf_counter()-start,'stop_reason':'bounded_steps_or_time'});save_state(model,args.output,state);print('BOUNDED STOP',json.dumps(state));return
                x,y,meta=native_batch(root,samples[batch*cfg['batch_size']:(batch+1)*cfg['batch_size']],cfg,plate_cfg,epoch)
                before=time.perf_counter();loss=float(model.train_on_batch(x,y));torch.cuda.synchronize() if torch.cuda.is_available() else None
                if not math.isfinite(loss):raise ValueError('Nonfinite loss')
                state['steps']+=1;record={'epoch':epoch+1,'batch':batch+1,'batches':report['epoch_batches'],'step':state['steps'],'loss':loss,'train_seconds':time.perf_counter()-before,'optimizer_iterations':int(model.optimizer.iterations)};log.write(json.dumps(record)+'\n');log.flush();print(json.dumps(record),flush=True)
            val=validate(model,root,gold,plate_cfg);better=state['best_validation'] is None or (val['source_macro_exact'],-val['edit_errors'])>(state['best_validation']['source_macro_exact'],-state['best_validation']['edit_errors'])
            if better:model.save(args.output/'best.keras');state['best_validation']=val;state['chosen_checkpoint']='best.keras'
            write_json(args.output/f'validation-epoch-{epoch+1}.json',val)
            state.update({'next_epoch':epoch+1,'next_batch':0});snapshot={**state,'elapsed_seconds':state['elapsed_seconds']+time.perf_counter()-start};save_state(model,args.output,snapshot)
            print('EPOCH COMPLETE',epoch+1,'seconds',time.perf_counter()-epoch_start,'validation',val['correct'],val['samples'],'chosen',state['chosen_checkpoint'],flush=True)
        state.update({'elapsed_seconds':state['elapsed_seconds']+time.perf_counter()-start,'stop_reason':'epochs_complete'});save_state(model,args.output,state)
    print('TRAIN COMPLETE',json.dumps(state),flush=True)


if __name__=='__main__':main()
