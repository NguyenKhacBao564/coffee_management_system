"""Seeded train-only recognizer augmentation; camera calibration is explicit.

No OCR predictions or source suggestions become labels. Unknown chars remain ?
and are excluded from native FastPlate CSV, whose alphabet lacks that token.
"""
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

GROUPS=('lighting','weather','sharpness','resolution','geometry','occlusion','color')


def seed_for(seed,epoch,sample_id,draw=0):
    return int.from_bytes(hashlib.sha256(f'{seed}:{epoch}:{sample_id}:{draw}'.encode()).digest()[:8],'little')


def char_height_proxy(image,split_y=None):
    """Connected dark components, per manually separated row; proxy, not char GT."""
    parts=[image] if split_y is None else [image[:split_y],image[split_y:]]
    heights=[]
    for part in parts:
        gray=cv2.cvtColor(part,cv2.COLOR_BGR2GRAY);mask=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        for x,y,w,h,area in stats[1:]:
            if max(2,.35*part.shape[0])<=h<=max(2,.85*part.shape[0]) and 1<=w<=.3*part.shape[1] and area>=2:heights.append(int(h))
    return float(np.median(heights)) if heights else None


def camera_stats(crops):
    rows=[]
    for entry in crops:
        key,image,split=entry[:3];measure_chars=entry[3] if len(entry)>3 else True
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        rows.append({'sample_id':key,'width':image.shape[1],'height':image.shape[0],'character_height_proxy':char_height_proxy(image,split) if measure_chars else None,'mean_luma':float(gray.mean()),'contrast_std':float(gray.std()),'laplacian_var':float(cv2.Laplacian(gray,cv2.CV_64F).var())})
    def quant(key):
        values=[r[key] for r in rows if r[key] is not None]
        return dict(zip(['p10','p50','p90'],map(float,np.quantile(values,[.1,.5,.9])))) if values else None
    stats={k:quant(k) for k in ['height','character_height_proxy','mean_luma','contrast_std','laplacian_var']}
    if stats['character_height_proxy'] is None:raise ValueError('No measurable glyph-height proxy; need manual calibration')
    lum=stats['mean_luma'];contrast=stats['contrast_std'];median=max(1,lum['p50'])
    config={'seed':185,'train_only':True,'native_character_height_px':[max(2,stats['character_height_proxy']['p10']),max(2,stats['character_height_proxy']['p90'])],
      'brightness_shift':min(.22,max(.02,(lum['p90']-lum['p10'])/510)),
      'contrast_range':[max(.75,min(1,contrast['p10']/max(1,contrast['p50']))),min(1.25,max(1,contrast['p90']/max(1,contrast['p50'])))],
      'gamma_range':[.85,1.15],'night_gain':[.4,.65],'noise_std':[1,6],'glare_strength':[.04,.18],'shadow_gain':[.7,.95],
      'weather_alpha':[.03,.12],'motion_kernel_native':[3,5],'defocus_sigma_native':[.2,.65],
      'jpeg_quality':[65,95],'hevc_crf':[23,32],'geometry_degrees':2,'perspective_fraction':.015,'bbox_jitter_fraction':.03,
      'upper_row_occlusion_fraction':[0,.5],'color_saturation_gain':[.98,1.02],
      'calibration':{'measured':['native character-height component proxy quantiles','brightness shift from luma p10–p90','contrast gain from native crop std quantiles'],
       'limits':'Components are a glyph-height proxy, not annotated character boxes. Plate height differs from character height. Daytime camera samples cannot calibrate true night/rain/fog/dust/color/pose distributions. Those ranges are conservative stress-test presets pending new camera data/manual review, not measured camera claims.',
       'provisional_stress_groups':['gamma/night/noise/glare/shadow','weather','blur kernels','JPEG/HEVC quality','geometry/jitter','occlusion','color']}}
    return {'rows':rows,'quantiles':stats,'config':config}


def jitter_bbox(shape,bbox,rng,fraction):
    h,w=shape[:2];x,y,r,b=map(int,bbox)
    if not (0<=x<r<=w and 0<=y<b<=h):raise ValueError('Invalid source bbox')
    delta=rng.uniform(-fraction,fraction,4)*[r-x,b-y,r-x,b-y]
    box=[int(np.clip(round(v+d),0,w if i%2==0 else h)) for i,(v,d) in enumerate(zip(bbox,delta))]
    if box[2]<=box[0] or box[3]<=box[1]:box=[x,y,r,b]
    # Any inward crop may hide glyphs without manual character boxes.
    cuts=box[0]>x or box[1]>y or box[2]<r or box[3]<b
    return box,cuts


def occlude_upper(image,text,split_y,fraction,fill):
    if not 0<=fraction<=.5:raise ValueError('Upper-row occlusion must be 0..50%')
    if type(split_y) is not int or not 0<split_y<image.shape[0]:raise ValueError('Manual two-line separator required')
    # Unknown row mapping masks the entire transcript conservatively, never guesses glyph positions.
    out=image.copy();height=min(split_y,math.ceil(split_y*fraction));out[:height]=fill
    lines=text.splitlines()
    if len(lines)==2:visible=('?'*len(lines[0]) if height else lines[0])+'\n'+lines[1]
    else:visible=''.join('?' if c.isalnum() else c for c in text) if height else text
    return out,visible,{'hidden_height_px':height,'mask_policy':'conservative: any upper-row cover masks all upper-row chars without character boxes','known_character_mask':[c!='?' for c in visible if c!='\n']}


def hevc_roundtrip(image,crf):
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise RuntimeError('ffmpeg with libx265 required; no JPEG fallback for HEVC')
    h,w=image.shape[:2];pad=cv2.copyMakeBorder(image,0,h%2,0,w%2,cv2.BORDER_REPLICATE)
    # Small plates are padded to codec minimum dimensions; crop back native size.
    pad=cv2.copyMakeBorder(pad,0,max(0,64-pad.shape[0]),0,max(0,64-pad.shape[1]),cv2.BORDER_REPLICATE)
    with tempfile.TemporaryDirectory(prefix='d05j-hevc-') as temp:
        root=Path(temp);cv2.imwrite(str(root/'input.png'),pad)
        subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-i',str(root/'input.png'),'-frames:v','1','-c:v','libx265','-preset','ultrafast','-x265-params','pools=1:frame-threads=1:log-level=error','-crf',str(crf),'-pix_fmt','yuv420p',str(root/'encoded.mp4')],check=True,timeout=20,capture_output=True)
        subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-i',str(root/'encoded.mp4'),'-frames:v','1',str(root/'decoded.png')],check=True,timeout=20,capture_output=True)
        out=cv2.imread(str(root/'decoded.png'))
        if out is None:raise RuntimeError('HEVC decode failed')
        return out[:h,:w].copy()


def augment(image,text,*,split,config,sample_id,epoch=0,draw=0,groups=None,split_y=None,character_height=None,source_frame=None,bbox=None):
    if split not in {'train','val','test'}:raise ValueError('Explicit train/val/test split required')
    if image is None or image.ndim!=3 or image.size==0:raise ValueError('Nonempty native BGR crop required')
    if split!='train':return image.copy(),text,{'applied':False,'split':split,'reason':'val/test unchanged real pixels'}
    rng=np.random.default_rng(seed_for(config['seed'],epoch,sample_id,draw));out=image.copy();visible=text;meta={'applied':True,'split':split,'seed':seed_for(config['seed'],epoch,sample_id,draw),'groups':{},'native_fastplate_eligible':bool(text.strip()) and '?' not in text}
    selected=list(groups) if groups is not None else [g for g in GROUPS if rng.random()<.18]
    if any(g not in GROUPS for g in selected):raise ValueError('Unknown augmentation group')
    if 'geometry' in selected and source_frame is not None and bbox is not None:
        box,cuts=jitter_bbox(source_frame.shape,bbox,rng,config['bbox_jitter_fraction']);x,y,r,b=box
        out=cv2.resize(source_frame[y:b,x:r],(image.shape[1],image.shape[0]),interpolation=cv2.INTER_LINEAR)
        meta['jitter']={'bbox':box,'may_cut_glyph':cuts};meta['native_fastplate_eligible']=meta['native_fastplate_eligible'] and not cuts
    for group in selected:
        h,w=out.shape[:2]
        if group=='lighting':
            gain=rng.uniform(*config['contrast_range']);shift=rng.uniform(-1,1)*config['brightness_shift']*255;gamma=rng.uniform(*config['gamma_range'])
            out=np.uint8(np.clip((np.clip(out.astype(float)*gain+shift,0,255)/255)**gamma*255,0,255))
            subtype=int(rng.integers(3));yy,xx=np.mgrid[:h,:w]
            if subtype==0:
                strength=rng.uniform(*config['glare_strength']);bump=np.exp(-((xx-rng.uniform(0,w))**2+(yy-rng.uniform(0,h))**2)/(max(h,w)*.3)**2);out=np.uint8(np.clip(out.astype(float)+bump[:,:,None]*255*strength,0,255));mode='glare'
            elif subtype==1:
                shadow=rng.uniform(*config['shadow_gain']);out[:,:w//2]=np.uint8(out[:,:w//2]*shadow);mode='shadow'
            else:
                night=rng.uniform(*config['night_gain']);noise=rng.uniform(*config['noise_std']);out=np.uint8(np.clip(out.astype(float)*night+rng.normal(0,noise,out.shape),0,255));mode='night_noise'
            meta['groups'][group]={'gain':float(gain),'shift':float(shift),'gamma':float(gamma),'mode':mode}
        elif group=='weather':
            alpha=rng.uniform(*config['weather_alpha']);mode=['rain','fog','dust'][int(rng.integers(3))];layer=np.full_like(out,210)
            if mode=='rain':
                layer=out.copy()
                for _ in range(max(1,w//15)):
                    x=int(rng.integers(w));y=int(rng.integers(h));cv2.line(layer,(x,y),(min(w-1,x+1),min(h-1,y+max(2,h//3))),(210,210,210),1)
            elif mode=='dust':layer[:]=[175,180,185]
            out=cv2.addWeighted(out,1-alpha,layer,alpha,0);meta['groups'][group]={'mode':mode,'alpha':float(alpha)}
        elif group=='sharpness':
            if rng.random()<.5:
                kernel=int(rng.choice(config['motion_kernel_native']));k=np.zeros((kernel,kernel));k[kernel//2,:]=1/kernel;out=cv2.filter2D(out,-1,k);meta['groups'][group]={'motion_kernel':kernel}
            else:
                sigma=rng.uniform(*config['defocus_sigma_native']);out=cv2.GaussianBlur(out,(0,0),sigma);meta['groups'][group]={'defocus_sigma':float(sigma)}
        elif group=='resolution':
            native=character_height if character_height is not None else char_height_proxy(out,split_y)
            if native is None or native<=0:raise ValueError('Measured/native character-height proxy required')
            target=rng.uniform(*config['native_character_height_px']);scale=min(1,target/native);size=(max(2,round(w*scale)),max(2,round(h*scale)))
            out=cv2.resize(cv2.resize(out,size,interpolation=cv2.INTER_AREA),(w,h),interpolation=cv2.INTER_LINEAR)
            codec='jpeg' if rng.random()<.8 else 'hevc'
            if codec=='jpeg':
                quality=int(rng.integers(config['jpeg_quality'][0],config['jpeg_quality'][1]+1));ok,buf=cv2.imencode('.jpg',out,[cv2.IMWRITE_JPEG_QUALITY,quality])
                if not ok:raise RuntimeError('JPEG encode failed')
                out=cv2.imdecode(buf,cv2.IMREAD_COLOR)
            else:quality=int(rng.integers(config['hevc_crf'][0],config['hevc_crf'][1]+1));out=hevc_roundtrip(out,quality)
            meta['groups'][group]={'native_character_height_proxy':float(native),'target_character_height':float(target),'downsample_size':size,'codec':codec,'quality_or_crf':quality}
        elif group=='geometry':
            meta['groups'][group]=meta.get('jitter',{'bbox_jitter':'not applied: original frame/bbox absent'})
            angle=rng.uniform(-config['geometry_degrees'],config['geometry_degrees']);m=cv2.getRotationMatrix2D((w/2,h/2),angle,1);out=cv2.warpAffine(out,m,(w,h),borderMode=cv2.BORDER_REPLICATE)
            delta=config['perspective_fraction']*min(w,h);src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]);dst=src+rng.uniform(-delta,delta,(4,2)).astype(np.float32);out=cv2.warpPerspective(out,cv2.getPerspectiveTransform(src,dst),(w,h),borderMode=cv2.BORDER_REPLICATE);meta['groups'][group].update({'angle':float(angle),'perspective_delta_px':float(delta)})
        elif group=='occlusion':
            if split_y is None:meta['groups'][group]={'applied':False,'reason':'needs native manual two-line split'};continue
            fraction=rng.uniform(*config['upper_row_occlusion_fraction']);fill=tuple(map(int,np.median(out.reshape(-1,3),axis=0)));out,visible,record=occlude_upper(out,text,split_y,fraction,fill);meta['groups'][group]={'fraction':float(fraction),**record};meta['native_fastplate_eligible']=meta['native_fastplate_eligible'] and '?' not in visible
        elif group=='color':
            hsv=cv2.cvtColor(out,cv2.COLOR_BGR2HSV);gain=rng.uniform(*config['color_saturation_gain']);hsv[:,:,1]=np.uint8(np.clip(hsv[:,:,1].astype(float)*gain,0,255));out=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR);meta['groups'][group]={'saturation_gain':float(gain),'hue_shift':0,'background_color_policy':'hue/value unchanged; saturation ±2% only'}
    return out,visible,meta


def export_fastplate_config(config,path):
    """Native FastPlate train --augmentation-path accepts Albumentations YAML."""
    import albumentations as A
    pipeline=A.Compose([
        A.RandomBrightnessContrast(brightness_limit=config['brightness_shift'],contrast_limit=(config['contrast_range'][0]-1,config['contrast_range'][1]-1),p=.2),
        A.RandomGamma(gamma_limit=tuple(round(x*100) for x in config['gamma_range']),p=.15),
        A.GaussianBlur(sigma_limit=tuple(config['defocus_sigma_native']),blur_limit=(3,3),p=.15),
        A.MotionBlur(blur_limit=(3,5),p=.15),
        A.ImageCompression(quality_range=tuple(config['jpeg_quality']),p=.15),
    ],seed=config['seed'])
    A.save(pipeline,str(path),data_format='yaml');loaded=A.load(str(path),data_format='yaml');loaded.set_random_seed(config['seed'])
    sample=np.random.default_rng(1).integers(0,256,(64,128,3),dtype=np.uint8)
    pipeline.set_random_seed(config['seed']);loaded.set_random_seed(config['seed'])
    if not np.array_equal(pipeline(image=sample)['image'],loaded(image=sample)['image']):raise ValueError('Native augmentation save/load transform differs')
    return {'albumentations_version':A.__version__,'native_roundtrip':'save/load + actual image transform parity passed with explicit set_random_seed', 'seed_policy':'YAML does not serialize Compose RNG seed; native CLI only calls keras.utils.set_random_seed. Future integration must explicitly call A.Compose.set_random_seed and define sample/epoch seeds. Adapter is deterministically seeded now.','native_groups':['brightness/contrast','gamma','blur','JPEG'],
       'not_native':['native-character-height downscale before recognizer resize','HEVC','bbox jitter from scene','upper-row ?/known-character mask','weather/glare/shadow/night/color from calibrated adapter'],
       'limits':'Native loader resizes before augmentation and creates y before transform(image); no label-aware masking hook. ? not in pinned FastPlate alphabet. Native YAML excludes occlusion/jitter and label-aware steps. Use adapter on native crop before official recognizer preprocess; do not train ? labels without a separately verified masked-loss/dataset integration.'}
