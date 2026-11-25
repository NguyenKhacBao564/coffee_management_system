"""Decoded YOLOX-Nano ONNX implements the existing offline Detector protocol."""
import json
from pathlib import Path
import cv2
import numpy as np
from ..types import Detection
from .audit import file_hash
from .engine import preprocess

class YoloXPlateDetector:
    def __init__(self, manifest_path, *, threshold=.25, nms=.45):
        import onnxruntime as ort
        self.metadata=json.loads(manifest_path.read_text());self.threshold=threshold;self.nms=nms
        if self.metadata['classes']!=['license_plate'] or not self.metadata['decode_in_graph']:raise ValueError('Unsupported class/output contract')
        path=manifest_path.parent/self.metadata['path']
        if file_hash(path)!=self.metadata['sha256']:raise ValueError('Model hash differs')
        if not 0<threshold<1 or not 0<nms<1:raise ValueError('Invalid threshold')
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        if self.metadata.get('onnx_graph_optimization') == 'disabled':
            options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        elif self.metadata.get('onnx_graph_optimization') not in {None,'default'}:
            raise ValueError('Unsupported ONNX graph optimization setting')
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    def detect(self,image,media_seconds):
        tensor,scale=preprocess(image,self.metadata['input_size'])
        rows=self.session.run(None,{'images':tensor[None]})[0][0];rows=rows[np.isfinite(rows).all(axis=1)]
        scores=rows[:,4]*rows[:,5];rows=rows[scores>=self.threshold];scores=scores[scores>=self.threshold]
        h,w=image.shape[:2];boxes=[];kept_scores=[]
        for row,score in zip(rows,scores):
            cx,cy,bw,bh=row[:4]/scale;x1,y1=max(0,float(cx-bw/2)),max(0,float(cy-bh/2));x2,y2=min(w,float(cx+bw/2)),min(h,float(cy+bh/2))
            if x2>x1 and y2>y1:boxes.append([x1,y1,x2-x1,y2-y1]);kept_scores.append(float(score))
        indices=cv2.dnn.NMSBoxes(boxes,kept_scores,self.threshold,self.nms)
        result=[]
        for index in np.array(indices).reshape(-1):
            x,y,bw,bh=boxes[index];result.append(Detection((x,y,x+bw,y+bh),'license_plate',kept_scores[index],'YOLOX-Nano one-class'))
        return result
