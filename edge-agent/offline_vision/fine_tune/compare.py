"""Fixed-plan detector comparison; manual geometry, never OCR text as truth."""
import json
import time
from pathlib import Path
import cv2
import numpy as np
from ..export import write_json
from .audit import file_hash
from .engine import load_manifest


def intersection(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))

def area(a):return max(0,a[2]-a[0])*max(0,a[3]-a[1])

def iou(a,b):
    overlap=intersection(a,b);denominator=area(a)+area(b)-overlap
    return overlap/denominator if denominator else 0


def score(records,detector,*,match_iou=.5,evidence=None):
    rows=[];tp=fp=truth=container_fp=container_images=0;latencies=[];coverages=[];extra_count=0;complete_images=0
    for r in records:
        image=cv2.imread(r['image_path']);began=time.perf_counter();predicted=detector.detect(image,r.get('media_seconds',0));seconds=time.perf_counter()-began;latencies.append(seconds)
        gt=[a['bbox'] for a in r['boxes']];truth+=len(gt);unmatched=set(range(len(gt)));matches=[];false=[]
        # Confidence ranks detections inside this model only; scores are never pooled across models.
        for detection in sorted(predicted,key=lambda d:d.score,reverse=True):
            best=max(unmatched,key=lambda i:iou(detection.box,gt[i]),default=None)
            if best is not None and iou(detection.box,gt[best])>=match_iou:
                unmatched.remove(best);tp+=1;coverage=intersection(detection.box,gt[best])/area(gt[best]);coverages.append(coverage)
                matches.append({'gt_index':best,'bbox':list(detection.box),'iou':iou(detection.box,gt[best]),'gt_area_coverage':coverage,
                    'crop_pixels':[detection.box[2]-detection.box[0],detection.box[3]-detection.box[1]]})
            else:false.append(list(detection.box))
        complete=r.get('annotations_complete') is True
        extra_count+=len(false);fp+=len(false) if complete else 0;complete_images+=complete
        on_container=0
        for box in false:
            if any(intersection(box,a['bbox'])/max(area(box),1)>=.5 for a in r.get('hard_negatives',[])):on_container+=1
        container_fp+=on_container if complete else 0;container_images+=bool(r.get('hard_negatives'))
        rows.append({'sample_id':r['sample_id'],'media_seconds':r.get('media_seconds'),'matches':matches,'missed_gt_indices':sorted(unmatched),
                     'capture_group_id':r.get('capture_group_id'),'vehicle_group_ids':r.get('vehicle_group_ids',[]),'ground_truth':len(gt),
                     'annotations_complete':complete,'unmatched_prediction_boxes':false,
                     'false_positive_boxes':false if complete else [],'false_positives_on_manual_container_regions':on_container if complete else None,'inference_seconds':seconds})
        if evidence is not None and r.get('label_origin')=='manual_review':
            import hashlib
            stem=hashlib.sha256(r['sample_id'].encode()).hexdigest()[:16];folder=evidence/stem;folder.mkdir(parents=True,exist_ok=False,mode=0o700)
            annotated=image.copy();crops=[]
            for j,detection in enumerate(predicted):
                x,y,b,c=map(round,detection.box);x=max(0,x);y=max(0,y);b=min(image.shape[1],b);c=min(image.shape[0],c)
                if b<=x or c<=y:continue
                crop=folder/f'prediction-{j+1}.png';cv2.imwrite(str(crop),image[y:c,x:b]);crop.chmod(0o600);crops.append(str(crop))
                cv2.rectangle(annotated,(x,y),(b,c),(0,130,255),2)
            for box in gt:
                x,y,b,c=map(round,box);cv2.rectangle(annotated,(x,y),(b,c),(0,220,0),1)
            path=folder/'annotated.jpg';cv2.imwrite(str(path),annotated,[cv2.IMWRITE_JPEG_QUALITY,96]);path.chmod(0o600)
            rows[-1]['evidence']={'annotated_path':str(path),'native_prediction_crops':crops,'green':'manual GT','orange':'model prediction'}
    return {'true_plates':truth,'true_positive_plates_iou_05':tp,'recall':tp/truth if truth else None,'false_positives':fp,
        'false_positives_per_image':fp/complete_images if complete_images else None,'confirmed_complete_images':complete_images,
        'unmatched_predictions':extra_count,'container_region_false_positives':container_fp,'images_with_manual_container_regions':container_images,
        'crop_gt_area_coverage_mean':float(np.mean(coverages)) if coverages else None,'crop_covers_95pct_of_gt':sum(c>=.95 for c in coverages),
        'latency_p50_p95_seconds':np.percentile(latencies,[50,95]).tolist() if latencies else [],'rows':rows}


def compare(manifest_path,plan_path,model_manifest,baseline_folder,output,*,detectors=None):
    manifest,_=load_manifest(manifest_path);plan=json.loads(plan_path.read_text())
    if manifest['purpose']!='reviewed_real_training':raise ValueError('Synthetic preflight is not recognition evidence')
    if plan['dataset_sha256']!=file_hash(manifest_path) or plan['model_manifest_sha256']!=file_hash(model_manifest):raise ValueError('Frozen evaluation plan differs from data/model')
    if plan['selection_split']!='val' or plan['input_scope'] not in {'full_native_frame','manual_vehicle_crop'} or plan['match_iou']!=.5:raise ValueError('Unsupported plan; selection must use val')
    split=plan['evaluate_split']
    if split not in {'val','test'}:raise ValueError('Only validation or sealed test may be evaluated')
    if split=='test' and not plan.get('thresholds_and_checkpoint_frozen_before_test'):raise ValueError('Test requires a frozen checkpoint and thresholds')
    model=json.loads(model_manifest.read_text())
    if model['purpose']=='synthetic_preflight_fixture':raise ValueError('Fixture-trained model cannot be evaluated as fine-tuned detector')
    if detectors is None:
        from ..detectors import PlateDetector
        from .detector import YoloXPlateDetector
        baseline=YoloXPlateDetector(baseline_folder,threshold=plan['baseline_threshold'],nms=plan['pilot_nms']) if baseline_folder.is_file() else PlateDetector(baseline_folder,plan['baseline_threshold'])
        if baseline_folder.is_file() and file_hash(baseline_folder)!=plan.get('baseline_model_manifest_sha256'):raise ValueError('D05d baseline manifest differs')
        detectors={'d05d_baseline' if baseline_folder.is_file() else 'yunet_baseline':baseline,
                   'yolox_nano_pilot':YoloXPlateDetector(model_manifest,threshold=plan['pilot_threshold'],nms=plan['pilot_nms'])}
    records=[r for r in manifest['records'] if r['split']==split]
    if plan.get('camera_only'):records=[r for r in records if r['label_origin']=='manual_review']
    if plan['input_scope']=='manual_vehicle_crop':
        from ..types import Detection
        class VehicleInput:
            def __init__(self,detector):self.detector=detector;self.boxes=[]
            def detect(self,image,t):
                detections=[]
                for x,y,b,c in self.boxes:
                    for d in self.detector.detect(image[y:c,x:b],t):
                        detections.append(Detection((d.box[0]+x,d.box[1]+y,d.box[2]+x,d.box[3]+y),d.label,d.score,d.model))
                return detections
        # Each call uses the exact same manually confirmed vehicle bbox for both models.
        wrapped={name:VehicleInput(d) for name,d in detectors.items()}
        class RecordInput:
            def __init__(self,wrapped):self.wrapped=wrapped;self.index=0
            def detect(self,image,t):
                self.wrapped.boxes=records[self.index].get('vehicle_boxes',[]);self.index+=1
                return self.wrapped.detect(image,t)
        detectors={name:RecordInput(d) for name,d in wrapped.items()}
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'input_scope':plan['input_scope'],'split':split,
        'dataset_sha256':file_hash(manifest_path),'plan_sha256':file_hash(plan_path),'images':len(records),
        'metrics':{name:score(records,detector,evidence=output/name) for name,detector in detectors.items()},
        'limits':'Two workshop captures are not representative system accuracy. No OCR correctness is inferred from detector recall.'}
    for metric in report['metrics'].values():
        groups={}
        for row in metric['rows']:
            key=str(row['capture_group_id'])+'|'+','.join(row['vehicle_group_ids'])
            g=groups.setdefault(key,{'frames':0,'plates':0,'matched':0,'missed':0,'unmatched':0,'confirmed_false_positives':0})
            g['frames']+=1;g['plates']+=row['ground_truth'];g['matched']+=len(row['matches']);g['missed']+=len(row['missed_gt_indices'])
            g['unmatched']+=len(row['unmatched_prediction_boxes']);g['confirmed_false_positives']+=len(row['false_positive_boxes'])
        metric['per_capture_vehicle_group']=groups
    write_json(output/'comparison.json',report);return report
