"""D05f policy for the existing finite trainer; no replacement or horizontal flip."""
import math
import random
import cv2
import numpy as np
import yaml


def load_policy(path):
    if path is None: return None
    value=yaml.safe_load(path.read_text())
    if value != {'camera_max_fraction':0.2,'camera_repeats_per_epoch':1,'camera_variants_per_frame_per_epoch':1,
                 'augmentation':'light_photometric_v1','selection_split':'public_val'}:
        raise ValueError('Unsupported D05f policy')
    return value


def epoch_order(records, seed, epoch, policy=None):
    rng=random.Random(seed+epoch)
    if policy is None:
        order=list(range(len(records)));rng.shuffle(order);return order
    public=[i for i,r in enumerate(records) if r['label_origin']=='roboflow_published_annotation']
    camera=[i for i,r in enumerate(records) if r['label_origin']=='manual_review']
    if len(public)+len(camera)!=len(records) or not public: raise ValueError('D05f requires public + manual camera provenance')
    by_frame={}
    for index in camera:
        by_frame.setdefault(records[index].get('sampling_group_id',records[index].get('sample_id',str(index))),[]).append(index)
    camera=[rng.choice(options) for options in by_frame.values()]
    rng.shuffle(camera)
    limit=math.floor(len(public)*policy['camera_max_fraction']/(1-policy['camera_max_fraction']))
    order=public+camera[:limit];rng.shuffle(order)
    return order


def transform(seed):
    rng=np.random.default_rng(seed)
    def apply(image):
        result=image.copy()
        if rng.random()<.3:
            result=np.clip(result.astype(np.float32)*rng.uniform(.85,1.15),0,255).astype(np.uint8)
        if rng.random()<.15: result=cv2.GaussianBlur(result,(3,3),0)
        if rng.random()<.2:
            h,w=result.shape[:2];ratio=rng.uniform(.8,1)
            result=cv2.resize(cv2.resize(result,(max(1,round(w*ratio)),max(1,round(h*ratio)))),(w,h))
        return result
    return apply


def initialize(model, checkpoint, digest):
    import torch
    from .audit import file_hash
    if file_hash(checkpoint)!=digest: raise ValueError('D05d initialization checkpoint hash differs')
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
    if saved.get('purpose')!='d05d_cuda_training': raise ValueError('Initialization must be D05d checkpoint')
    state=saved['model'];model.load_state_dict(state,strict=True)
    return {'origin':'D05d one-class best checkpoint','sha256':digest,'loaded_keys':sorted(state),
            'skipped_keys':[],'optimizer_scheduler_reused':False}
