"""Pinned official training sources and COCO checkpoint; explicit fetch only."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import shutil

from ..export import write_json
from .audit import extract_archive, file_hash

REVISION = "6ddff4824372906469a7fae2dc3206c7aa4bbaee"
SOURCE_SHA = "647bba7d16cc7e13feb5f2beca0296f86186c944f5a8fa9ccefc2629758bccba"
WEIGHTS_SHA = "cd28f55fbbc1829f99d9ac9b38a16d259a22889739c8728ea877610201feff7b"
SOURCE_URL = f"https://codeload.github.com/Megvii-BaseDetection/YOLOX/zip/{REVISION}"
WEIGHTS_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.pth"


def fetch_assets(folder):
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name,url,digest,bound in [("source.zip",SOURCE_URL,SOURCE_SHA,30000000),("yolox_nano.pth",WEIGHTS_URL,WEIGHTS_SHA,12000000)]:
        path=folder/name
        if not path.exists():
            tmp=folder/(name+'.download')
            if tmp.exists():raise ValueError("Previous partial model download exists; inspect before retry")
            try:
                subprocess.run(['curl','--fail','--silent','--show-error','--location','--max-time','120','--max-filesize',str(bound),url,'-o',str(tmp)],check=True)
                if file_hash(tmp)!=digest:raise ValueError("Official artifact differs from pinned SHA-256")
                tmp.rename(path)
            finally:tmp.unlink(missing_ok=True)
        if file_hash(path)!=digest:raise ValueError("Existing artifact differs; refusing overwrite")
        path.chmod(0o600)
    if not (folder/'upstream'/f'YOLOX-{REVISION}'/'yolox/models/yolo_head.py').exists():
        if (folder/'upstream').exists():
            (folder/'upstream').rename(folder/'upstream.failed-case-alias')
        # The full archive has Android Java filenames differing only in case.
        # Extract only the Python model tree and license needed on macOS.
        prefix=f'YOLOX-{REVISION}/'
        with zipfile.ZipFile(folder/'source.zip') as bundle:
            for entry in bundle.infolist():
                relative=entry.filename.removeprefix(prefix)
                if not (relative=='LICENSE' or relative.startswith('yolox/')) or entry.is_dir():continue
                destination=folder/'upstream'/entry.filename
                destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                with bundle.open(entry) as src,destination.open('xb') as dst:shutil.copyfileobj(src,dst)
                destination.chmod(0o600)
    root=folder/'upstream'/f'YOLOX-{REVISION}'
    files={str(p.relative_to(root)):file_hash(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    license_text=(root/'LICENSE').read_text()
    if 'Apache License' not in license_text:raise ValueError("Official code license differs")
    manifest={'model':'YOLOX-Nano','source_repository':'Megvii-BaseDetection/YOLOX','source_revision':REVISION,'source_url':SOURCE_URL,
        'source_zip_sha256':SOURCE_SHA,'weights_url':WEIGHTS_URL,'weights_sha256':WEIGHTS_SHA,'weights_bytes':(folder/'yolox_nano.pth').stat().st_size,
        'code_license':'Apache-2.0','weights_license_basis':'Official project checkpoint distributed under project Apache-2.0 license; no separate restriction found in official release',
        'source_file_hashes':files,'pretrained_classes':80,'new_classes':['license_plate'],'depth':.33,'width':.25,'depthwise':True,
        'preprocess':'Official current YOLOX BGR raw 0–255, top-left aspect letterbox with fill 114; no RGB/mean/std legacy preprocessing',
        'export':'Official YOLOX ONNX export path; local export fixed shape with decoded cxcywh/objectness/class scores'}
    write_json(folder/'manifest.json',manifest);return manifest


def verify_assets(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['source_revision']!=REVISION or file_hash(folder/'source.zip')!=SOURCE_SHA or file_hash(folder/'yolox_nano.pth')!=WEIGHTS_SHA:
        raise ValueError("Pinned training assets differ")
    root=folder/'upstream'/f'YOLOX-{REVISION}'
    for path,digest in manifest['source_file_hashes'].items():
        if file_hash(root/path)!=digest:raise ValueError("Upstream source file changed")
    return root,manifest


def make_model(folder, *, pretrained=True):
    import torch
    import torch.nn as nn
    root,manifest=verify_assets(folder)
    sys.path.insert(0,str(root.resolve()))
    from yolox.models import YOLOX,YOLOPAFPN,YOLOXHead
    model=YOLOX(YOLOPAFPN(.33,.25,in_channels=[256,512,1024],act='silu',depthwise=True),
                YOLOXHead(1,.25,in_channels=[256,512,1024],act='silu',depthwise=True))
    for m in model.modules():
        if isinstance(m,nn.BatchNorm2d):m.eps=1e-3;m.momentum=.03
    model.head.initialize_biases(1e-2)
    initialization={'pretrained':pretrained,'skipped_shape_keys':[],'loaded_tensors':0,'loaded_keys':[]}
    if pretrained:
        state=torch.load(folder/'yolox_nano.pth',map_location='cpu',weights_only=True)['model'];own=model.state_dict()
        compatible={k:v for k,v in state.items() if k in own and v.shape==own[k].shape}
        initialization.update(loaded_tensors=len(compatible),loaded_keys=sorted(compatible),
                              skipped_shape_keys=sorted(k for k in state if k not in compatible))
        if any('cls_preds' not in k for k in initialization['skipped_shape_keys']):
            raise ValueError("Unexpected pretrained architecture mismatch")
        model.load_state_dict(compatible,strict=False)
    return model,{**manifest,'initialization':initialization}
