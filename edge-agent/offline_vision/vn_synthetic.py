"""Small VN car/truck OCR generator; random strings, explicit licensed font.

Templates approximate TT79/2024 Article37/Appendix04. No government font claim,
registration identity, motorcycle/foreign/military coverage or inferred text.
"""
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .camera_augmentation import augment, seed_for
from .plate_domain import SERIES, parse_plate

PROVINCES = ('29','30','49','51','59','60','62','65')
COLORS = {'white':((235,235,235),(12,12,12)), 'yellow':((242,211,45),(12,12,12)), 'blue':((30,80,151),(240,240,240))}


def random_plate(rng, color, excluded=()):
    alphabet='ABCDEFGHKLM' if color=='blue' else SERIES
    for _ in range(1000):
        text=str(rng.choice(PROVINCES))+str(rng.choice(list(alphabet)))+f'{int(rng.integers(1,100000)):05d}'
        if text not in excluded and parse_plate(text):return text
    raise ValueError('Cannot create non-held-out synthetic string')


def render_plate(text, layout, color, font_path):
    if len(text)!=8 or not parse_plate(text) or color not in COLORS or layout not in {'single-line','two-line'}:raise ValueError('Supported ordinary car/truck five-digit template required')
    if color=='blue' and text[2] not in 'ABCDEFGHKLM':raise ValueError('Blue car series outside supported official subset')
    w,h=(1040,220) if layout=='single-line' else (660,330)
    bg,fg=COLORS[color];im=Image.new('RGB',(w,h),bg);draw=ImageDraw.Draw(im)
    draw.rounded_rectangle((4,4,w-5,h-5),radius=12,outline=fg,width=3)
    font=ImageFont.truetype(str(font_path),125 if layout=='single-line' else 120)
    if hasattr(font,'set_variation_by_name'):font.set_variation_by_name('Bold')
    lines=[text[:3]+'-'+text[3:6]+'.'+text[6:]] if layout=='single-line' else [text[:2]+'-'+text[2],text[3:6]+'.'+text[6:]]
    boxes=[]
    for row,line in enumerate(lines):
        gap=8 if layout=='single-line' else 12
        widths=[font.getlength(c) for c in line];total=sum(widths)+gap*(len(line)-1)
        x=(w-total)/2;center=h/2 if layout=='single-line' else (h*.255 if row==0 else h*.74)
        for c,advance in zip(line,widths):
            bx,by,br,bb=font.getbbox(c);y=center-(bb-by)/2-by
            draw.text((x,y),c,font=font,fill=fg)
            if c.isalnum():boxes.append({'character':c,'row':row,'bbox':[math.floor(x+bx),math.floor(y+by),math.ceil(x+br),math.ceil(y+bb)]})
            x+=advance+gap
    if ''.join(b['character'] for b in boxes)!=text:raise ValueError('Rendered glyph order differs from transcript')
    if any(not (0<=b['bbox'][0]<b['bbox'][2]<=w and 0<=b['bbox'][1]<b['bbox'][3]<=h) for b in boxes):raise ValueError('Glyph clipped')
    return cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR), boxes, (h//2 if layout=='two-line' else None)


def safe_upper_cover(image, glyphs, fraction, split_y):
    """Cover margin only, strictly <1/3; reject ANY intersection with real glyph ink."""
    if not 0<=fraction<1/3:raise ValueError('Cover must be strictly below one third')
    if split_y is None:return image.copy(),{'applied':False,'reason':'single-line'}
    height=math.ceil(split_y*fraction)
    if any(b['bbox'][1]<height for b in glyphs):raise ValueError('Cover would hide a glyph; plain FastPlate loss cannot mask it')
    out=image.copy();out[:height]=np.median(image.reshape(-1,3),axis=0).astype(np.uint8)
    return out,{'applied':height>0,'fraction':fraction,'covered_height':height,'glyph_intersections':0}


def safe_jitter(image,glyphs,rng,fraction=.025):
    h,w=image.shape[:2];delta=rng.uniform(0,fraction,4)*[w,h,w,h]
    x,y=int(delta[0]),int(delta[1]);r,b=w-int(delta[2]),h-int(delta[3])
    if any(not (x<=g['bbox'][0]<g['bbox'][2]<=r and y<=g['bbox'][1]<g['bbox'][3]<=b) for g in glyphs):raise ValueError('Jitter hides synthetic glyph')
    shifted=[{**g,'bbox':[g['bbox'][0]-x,g['bbox'][1]-y,g['bbox'][2]-x,g['bbox'][3]-y]} for g in glyphs]
    return image[y:b,x:r].copy(),shifted,{'crop_bbox':[x,y,r,b],'glyph_intersections':0}


def synthetic_augment(image,text,glyphs,split_y,config,*,sample_id,epoch=0,draw=0,groups=None):
    rng=np.random.default_rng(seed_for(config['seed'],epoch,sample_id,draw));out=image.copy();boxes=glyphs
    selected=list(groups) if groups is not None else [g for g in ('lighting','weather','sharpness','geometry','color') if rng.random()<.18]
    cover={'applied':False};jitter={'applied':False}
    if 'occlusion' in selected:
        fraction=float(rng.uniform(0,.18));out,cover=safe_upper_cover(out,boxes,fraction,split_y)
    if 'geometry' in selected:
        out,boxes,jitter=safe_jitter(out,boxes,rng);split_y=split_y-jitter['crop_bbox'][1] if split_y else None
        # Conservative displacement bound for existing adapter's rotation/perspective.
        h,w=out.shape[:2];bound=math.sin(math.radians(config['geometry_degrees']))*max(h,w)/2+config['perspective_fraction']*min(h,w)*3
        if min(min(g['bbox'][0],g['bbox'][1],w-g['bbox'][2],h-g['bbox'][3]) for g in boxes)<=bound:raise ValueError('Insufficient glyph margin for geometry')
    # Geometry on render, then native downscale BEFORE blur/weather/codec.
    char_height=float(np.median([g['bbox'][3]-g['bbox'][1] for g in boxes]))
    geometry_meta=None
    if 'geometry' in selected:
        out,_,geometry_meta=augment(out,text,split='train',config=config,sample_id=sample_id,epoch=epoch,draw=draw,groups=['geometry'])
    target=float(rng.uniform(*config['native_character_height_px']));scale=min(1,target/char_height)
    size=(max(2,round(out.shape[1]*scale)),max(2,round(out.shape[0]*scale)))
    out=cv2.resize(out,size,interpolation=cv2.INTER_AREA)
    native_split=max(1,min(size[1]-1,round(split_y*scale))) if split_y else None
    chosen=[g for g in selected if g not in {'occlusion','resolution','geometry'}]+['resolution']
    out,visible,meta=augment(out,text,split='train',config=config,sample_id=sample_id,epoch=epoch,draw=draw,groups=chosen,split_y=native_split,character_height=char_height*scale)
    if visible!=text or not meta['native_fastplate_eligible']:raise ValueError('Synthetic label would change')
    # Keep degraded native raster, not the interpolated high-resolution display copy.
    return out,{**meta,'safe_cover':cover,'safe_jitter':jitter,'render_character_height':char_height,'first_native_downscale_size':list(size),'first_target_glyph_height':target,'geometry_before_downscale':geometry_meta,'native_size':[out.shape[1],out.shape[0]],'text_preserved':True}
