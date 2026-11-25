"""Export portable Keras checkpoint with TensorFlow, verify original Torch parity.

Original checkpoint, model and preprocessing stay unchanged. Export backend is
separate from the training backend; frozen Torch predictions must match ONNX.
"""
import argparse,json
from pathlib import Path
import cv2,numpy as np
from .dataset import sha256
from .export import write_json
from .ocr_training_data import load_lock
from .plate_recognizer import plate_input,slot_decode


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reference-only',action='store_true');args=parser.parse_args()
    root=args.root.resolve();output=args.output.resolve();gold=load_lock(root/'evaluation');state=json.loads((output/'state.json').read_text())
    if state['stop_reason']!='epochs_complete' or not state['best_validation']:raise ValueError('Choose checkpoint by validation after bounded training first')
    for rel,digest in json.loads((root/'package.hashes.json').read_text()).items():
        if sha256(root/rel)!=digest:raise ValueError('Executed package changed: '+rel)
    import keras,onnxruntime as ort
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml
    from fast_plate_ocr.train.model import model_builders  # Register official custom layers.
    from .ocr_finetune import prediction
    if keras.backend.backend()=='torch':
        import torch
        torch.set_num_threads(2);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    else:
        import tensorflow as tf
        tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(2)
    pc=load_plate_config_from_yaml(root/'model/plate_config.yaml');config=pc.model_dump();path=output/state['chosen_checkpoint']
    model=keras.models.load_model(path,compile=False)
    if args.reference_only:
        if keras.backend.backend()!='torch':raise ValueError('Reference must use original training backend')
        values=[prediction(model,plate_input(cv2.imread(str(root/'evaluation'/r['crop_path'])),config)) for r in gold['rows']]
        np.savez(output/'torch-reference.npz',sample_ids=np.array([r['sample_id'] for r in gold['rows']]),probabilities=np.array(values))
        write_json(output/'torch-reference.json',{'checkpoint_sha256':sha256(path),'evaluation_sha256':sha256(root/'evaluation/evaluation.lock.json'),'reference_sha256':sha256(output/'torch-reference.npz'),'torch':torch.__version__,'keras':keras.__version__})
        print('Saved original Torch/Keras reference for '+str(len(values))+' frozen inputs');return
    if keras.backend.backend()!='tensorflow':raise ValueError('Export uses TensorFlow backend; reference remains Torch')
    refmeta=json.loads((output/'torch-reference.json').read_text());reference=np.load(output/'torch-reference.npz')
    if refmeta['checkpoint_sha256']!=sha256(path) or refmeta['reference_sha256']!=sha256(output/'torch-reference.npz') or refmeta['evaluation_sha256']!=sha256(root/'evaluation/evaluation.lock.json'):raise ValueError('Reference changed')
    if list(reference['sample_ids'])!=[r['sample_id'] for r in gold['rows']]:raise ValueError('Reference order changed')
    write_json(output/'export-plan.json',{'checkpoint':state['chosen_checkpoint'],'checkpoint_sha256':sha256(path),'state_sha256':sha256(output/'state.json'),'exporter':'Keras TensorFlow ONNX exporter, fixed batch1, opset17; original Torch predictions separately locked','adapter_sha256':sha256(Path(__file__)),'code_revision':'D05k export compatibility only, no fitting/reselection','selection':'validation source macro exact/CER, earliest tie; no test choice','tensorflow':tf.__version__,'keras':keras.__version__,'torch_reference':refmeta})
    onnx=output/'detector-ocr.onnx';model.export(str(onnx),format='onnx',input_signature=[tf.TensorSpec((1,64,128,3),tf.float32)],opset_version=17,verbose=False)
    options=ort.SessionOptions();options.intra_op_num_threads=2;session=ort.InferenceSession(str(onnx),sess_options=options,providers=['CPUExecutionProvider']);name=session.get_inputs()[0].name;rows=[]
    for index,row in enumerate(gold['rows']):
        blob=plate_input(cv2.imread(str(root/'evaluation'/row['crop_path'])),config);k=prediction(model,blob);o=session.run(None,{name:blob.astype(np.float32)})[0]
        original=reference['probabilities'][index]
        rows.append({'sample_id':row['sample_id'],'max_absolute_error':float(np.max(np.abs(original-o))),'tensorflow_onnx_error':float(np.max(np.abs(k-o))),'allclose':bool(np.allclose(original,o,atol=.0001,rtol=.001) and np.allclose(k,o,atol=.0001,rtol=.001)),'raw_equal':slot_decode(original,config)[0]==slot_decode(k,config)[0]==slot_decode(o,config)[0]})
    result={'rows':rows,'passed':all(r['allclose'] and r['raw_equal'] for r in rows),'keras_backend':keras.backend.backend(),'exporter':'Keras TensorFlow ONNX, compared to original Torch/Keras; fixed batch1 NHWCfloat32; opset17','preprocess':'Pinned RGB linear128x64 whole/original; transport float320..255, embedded normalization','onnx_sha256':sha256(onnx),'input_shape':session.get_inputs()[0].shape,'output_shape':session.get_outputs()[0].shape,'atol':.0001,'rtol':.001};write_json(output/'onnx-parity.json',result)
    if not result['passed']:raise ValueError('ONNX parity failed; no runtime promotion')
    print(json.dumps({'parity':True,'inputs':len(rows),'max_absolute_error':max(r['max_absolute_error'] for r in rows),'onnx_sha256':result['onnx_sha256']},indent=2))


if __name__=='__main__':main()
