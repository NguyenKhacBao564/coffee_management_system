#!/usr/bin/env python3
"""Allowlisted offline OCR training package, no app DB/config/secrets."""
import argparse,copy,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.dataset import sha256
from offline_vision.export import write_json
from offline_vision.ocr_training_data import load_lock
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
gold=load_lock(a.run/'evaluation');silver=json.loads((a.run/'silver/silver.labels.json').read_text());syn=json.loads((a.run/'synthetic-v2/manifest.json').read_text());rows=[]
for name,source in [('silver',silver),('synthetic-v2',syn)]:
    for original in source['rows']:
        row=copy.deepcopy(original);rel=name+'/'+row['crop_path'];dest=a.output/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.run/name/row['crop_path'],dest);row['crop_path']=rel;rows.append(row)
shutil.copytree(a.run/'evaluation',a.output/'evaluation')
write_json(a.output/'dataset.json',{'rows':rows,'silver_count':len(silver['rows']),'synthetic_pool_count':len(syn['rows']),'gold_train':0,'gold_policy':'only validation/test; camera185 all test'})
model=a.output/'model';model.mkdir();cache=ROOT/'data/offline-vision/benchmark-models/fast-plate-train-9ce7a5b';inference=ROOT/'data/offline-vision/benchmark-models/fast-plate-cct-s-v2'
assets=[(cache/'cct_s_v2_global.keras','pretrained.keras','dc6db494714d88e1fb0a21b4e4e96089842dd5440418262abfc382454453c2c8'),(cache/'cct_s_v2_global_model_config.yaml','model_config.yaml','244c3c712205750e9747bca4707cd553a84005f41959745bff676b0fca8faba3'),(inference/'cct_s_v2_global_plate_config.yaml','plate_config.yaml','0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6'),(inference/'cct_s_v2_global.onnx','pretrained.onnx','384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b')]
for path,name,digest in assets:
    if sha256(path)!=digest:raise ValueError('Official model hash mismatch')
    shutil.copy2(path,model/name)
upstream=next((cache/'source').glob('fast-plate-ocr-*'));shutil.copytree(upstream/'fast_plate_ocr',a.output/'fast_plate_ocr',ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT/'edge-agent/offline_vision',a.output/'offline_vision',ignore=shutil.ignore_patterns('__pycache__','*.js','*.html','*.svg'))
licenses=a.output/'licenses';licenses.mkdir();shutil.copy2(upstream/'LICENSE',licenses/'FastPlate-MIT.txt');shutil.copy2(ROOT/'data/offline-vision/fonts/RobotoCondensed-OFL.txt',licenses/'RobotoCondensed-OFL.txt')
write_json(a.output/'provenance.json',{'fastplate_revision':'9ce7a5b64a939aa421c243b331d42e6bc25ffd44','code_license':'MIT','weights_release':'https://github.com/ankandrew/fast-plate-ocr/releases/tag/arg-plates','weights_release_digests':{name:digest for _,name,digest in assets},'font':syn['font'],'data':'CarTGMT/GreenParking source https://thigiacmaytinh.com/tai-nguyen-xu-ly-anh/tong-hop-data-xu-ly-anh/, user authorized local use, no blanket redistribution license assumed. Private camera clips cropped only. No app data.','authorization':'User 2026-10-08 allows preparation and bounded training on supplied existing Vast; no instance rental/destroy.'})
cfg={'seed':185,'epochs':8,'batch_size':16,'synthetic_per_silver':1,'learning_rate':1e-5,'max_steps':240,'max_seconds':1200,'automatic_restarts':0,'drop_last':False,'evaluation_sha256':sha256(a.run/'evaluation/evaluation.lock.json'),'augmentation':json.loads((a.run/'synthetic-v2/augmentation.json').read_text()),'heldout_crop_dhash':[r['dhash'] for r in gold['rows']],'selection':'Fine-tuned checkpoint by source-macro exact on gold validation only, CER error tie-breaker; earliest tie retained. Pretrained initial saved as comparator, never auto-promote candidate. Test run only after choice. Gold training count zero.','sampler':'Every silver crop once/epoch; equally many synthetic draws without replacement from finite pool, shuffled seed/epoch. 300 samples, ceil(300/16)=19 batches; final batch12 retained. No infinite sampler.'};write_json(a.output/'config.json',cfg)
(a.output/'requirements.txt').write_text('keras==3.13.2\nnumpy==2.2.6\nopencv-python-headless==4.12.0.88\npydantic==2.9.2\npandas==2.2.3\nPillow==11.3.0\nPyYAML==6.0.2\nonnx==1.19.0\nonnxruntime==1.23.2\nonnxscript==0.7.2\ntensorflow-cpu==2.20.0\ntf2onnx==1.17.0\nscipy==1.15.2\nrich==14.1.0\n# PyTorch backend must be separately installed/verified: measured Vast torch2.14.0+cu126.\n')
shutil.copy2(ROOT/'scripts/d05k-run-bounded.sh',a.output/'run-bounded.sh')
(a.output/'README.md').write_text('''# D05k bounded FastPlate fine-tune

Private offline package, no application database. FastPlate upstream MIT pinned
9ce7a5b64a939aa421c243b331d42e6bc25ffd44, Keras checkpoint official hash verified.
Roboto Condensed OFL is approximate plate typography; no official-font claim.
Public source rights: local use authorized by user; do not redistribute publicly.

Install requirements in a dedicated venv with verified PyTorch CPU/CUDA backend.
`ffmpeg` with libx265 is required; no fake HEVC/JPEG substitution.
Always run from package root. Existing Vast /workspace/d05k-venv, torch2.14.0+cu126.

```bash
exec </dev/null
export KERAS_BACKEND=torch
python -m offline_vision.ocr_finetune inspect --root . --output inspect
timeout 240s python -m offline_vision.ocr_finetune preflight --root . --output preflight
timeout --signal=TERM --kill-after=30 1260s python -m offline_vision.ocr_finetune train --root . --output results
# Resume same model+optimizer+schedule/epoch; no new warm restart or changed limits.
timeout --signal=TERM --kill-after=30 1260s python -m offline_vision.ocr_finetune train --root . --output results --resume
python -m offline_vision.ocr_finetune export --root . --output results --resume
```

Use tmux; outer timeout protects total runaway process. Config additionally bounds
8 epochs/240 updates/1200 elapsed seconds across resumed state. No automatic restart.
150 silver +150 synthetic per epoch, 19 batches (drop_last=false); no gold train.
Synthetic pool1024, sample without replacement/epoch; augmentation online seed185.
Native downscale from actual rendered glyph boxes to9–11px before blur/codec.
Synthetic cover only margin, no glyph intersection; no ? tokens/horizontal flip.
Gold validation20, test camera88 +Car17 +motorcycle12, immutable lock/hash.
Teacher Keras-vs-official ONNX checked on validation only before optimizer updates.
Preflight2steps validates loss/checkpoint/optimizer resume, discarded before train.
Fine-tuned checkpoint chosen by val source-macro exact +CER error tie-breaker;
earliest tie retained; pretrained initial kept as separate comparator. Test unused
for choice. No automatic runtime promotion, even if validation improves.
Export uses TensorFlow CPU backend on the unchanged portable .keras checkpoint,
then checks TensorFlow/Keras and ONNX against saved original Torch/Keras predictions
on all 137 frozen native inputs. PyTorch2.14 Dynamo and legacy convolution exports
failed, so this uses the official Keras TensorFlow ONNX exporter instead. No retrain.
Use `bash run-bounded.sh "$PWD"` in tmux; stdin is detached to prevent FFmpeg
SIGTTIN when GNU timeout creates a background process group. No automatic retries.
Read environment.json, preflight.json, iterations.jsonl, state.json and parity.
Never claim camera accuracy from two captures/one full-readable plate. Fine-tune
runtime promotion requires camera improvement AND no secondary-test regression.
''')
files={str(path.relative_to(a.output)):sha256(path) for path in sorted(a.output.rglob('*')) if path.is_file()};write_json(a.output/'package.hashes.json',files)
archive=a.output.with_suffix('.zip')
if archive.exists():raise ValueError('Refuse overwrite package')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(a.output.rglob('*')):
        if path.is_file():z.write(path,path.relative_to(a.output))
print(json.dumps({'package':str(archive),'sha256':sha256(archive),'images':len(rows),'silver':len(silver['rows']),'synthetic':len(syn['rows']),'files':len(files),'config':cfg},ensure_ascii=False,indent=2))
