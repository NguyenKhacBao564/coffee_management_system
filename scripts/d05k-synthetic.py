#!/usr/bin/env python3
"""Bounded synthetic pool/contact sheet; online augmentation remains seeded."""
import argparse,copy,html,json,sys,collections
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge-agent'))
from offline_vision.vn_synthetic import random_plate,render_plate,synthetic_augment
from offline_vision.dataset import save_png,sha256
from offline_vision.export import write_json
from offline_vision.ocr_training_data import load_lock,leakage_reasons,pixel_hash
from offline_vision.sampling import image_hash
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--count',type=int,default=1024);a=p.parse_args()
if not 1<=a.count<=4096:raise ValueError('Bounded 1..4096 synthetic render pool')
gold=load_lock(a.evaluation);a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
font=ROOT/'data/offline-vision/fonts/RobotoCondensed.ttf';license=ROOT/'data/offline-vision/fonts/RobotoCondensed-OFL.txt'
if 'SIL OPEN FONT LICENSE Version 1.1' not in license.read_text():raise ValueError('OFL license required')
config=json.loads((ROOT/'data/offline-vision/runs/d05j-expanded-20261007/augmentation-v3/augmentation.adapter.json').read_text());config['upper_row_occlusion_fraction']=[0,.18]
write_json(a.output/'augmentation.json',config)
rng=np.random.default_rng(185);held={r['text'] for r in gold['rows'] if r['text']}|{'29K52755','49C02655'};rows=[];preview=[];rejected=[]
groups=[[],['lighting'],['weather'],['sharpness'],['geometry'],['color'],['occlusion'],['lighting','sharpness']]
for n in range(a.count):
    color=('white','yellow','blue')[n%3];layout=('single-line','two-line')[(n//3)%2];text=random_plate(rng,color,held);held.add(text);sample=f'synthetic-{n+1:05d}'
    image,boxes,split=render_plate(text,layout,color,font);rel='renders/'+sample+'.png';save_png(a.output/rel,image)
    rows.append({'sample_id':sample,'text':text,'label_origin':'synthetic','split':'train','group_id':'synthetic:'+text,'crop_path':rel,'crop_sha256':sha256(a.output/rel),'layout':layout,'plate_color':color,'glyph_boxes':boxes,'split_y':split,'native_size':[image.shape[1],image.shape[0]],'font_sha256':sha256(font)})
    if n<48:
        try:crop,meta=synthetic_augment(image,text,boxes,split,config,sample_id=sample,groups=groups[n%len(groups)])
        except ValueError as e:rejected.append({'sample_id':sample,'reason':str(e)});continue
        leaks=leakage_reasons(crop,crop,text,gold['rows'])
        if leaks:rejected.append({'sample_id':sample,'reason':'near-gold preview','evidence':leaks});continue
        dest='previews/'+sample+'.png';save_png(a.output/dest,crop);preview.append({'sample_id':sample,'text':text,'layout':layout,'color':color,'crop_path':dest,'metadata':meta})
# Build display at integer nearest-neighbor zoom alongside actual frozen camera crops.
sheet=Image.new('RGB',(1100,math_rows:=((len(preview)+3)//4+1)*155),'#f4f6f5');draw=ImageDraw.Draw(sheet)
camera=[r for r in gold['rows'] if r['source']=='camera185' and r['readability'] in {'readable_full','readable_partial'}]
for i,row in enumerate(camera[:4]):
    im=Image.open(a.evaluation/row['crop_path']).convert('RGB');im=im.resize((im.width*3,im.height*3),Image.Resampling.NEAREST);sheet.paste(im,(i*275+8,30));draw.text((i*275+8,5),'CAMERA REAL / TEST '+row['readability'],fill='black')
for i,row in enumerate(preview):
    x,y=(i%4)*275+8,(i//4+1)*155+8;im=Image.open(a.output/row['crop_path']).convert('RGB');scale=max(1,min(3,250//im.width));im=im.resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST);sheet.paste(im,(x,y+30));draw.text((x,y),row['text']+' / '+row['color']+' / '+row['layout'],fill='black')
sheet.save(a.output/'contact-sheet.png')
write_json(a.output/'manifest.json',{'rows':rows,'preview_rows':preview,'rejected_preview':rejected,'label_origin':'synthetic','evaluation_sha256':sha256(a.evaluation/'evaluation.lock.json'),'font':{'source':'https://github.com/google/fonts/tree/69d0549e8fc7ad72e1531734c81237be401ec4fd/ofl/robotocondensed','license':'SIL-OFL-1.1','font_sha256':sha256(font),'license_sha256':sha256(license),'limits':'Roboto Condensed Bold is an approximation, not the prescribed official plate font.'},'rules_sources':['https://vanban.chinhphu.vn/?pageid=27160&docid=211945','https://bocongan.gov.vn/bai-viet/nhan-dien-mau-sac-seri-ky-hieu-bien-so-xe-cua-co-quan-to-chuc-ca-nhan-tu-01012025-d1-t1617'],'scope':'Ordinary car/truck 5-digit, known province-code subset, no claim actual registered identities. Camera values reused from D05j frozen calibration, not tuned to OCR test scores. Resolution always native rendered glyph height 9-11 px; heavier weather/night presets not empirically calibrated. Test/val unchanged real images.'})
(a.output/'review.html').write_text('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>D05k synthetic</title><style>body{font:16px system-ui;margin:20px}img{max-width:100%}p{max-width:900px}</style><h1>D05k · Biển tổng hợp cạnh camera thật</h1><p>Hàng đầu: camera 185 test nguyên vẹn. Các hàng sau: synthetic TRAIN, native glyph 9–11 px. Font OFL gần đúng; che chỉ ở mép không giao ký tự, không nhãn ?. Night/weather là stress presets. Không phải bằng chứng cải thiện OCR.</p><a href="contact-sheet.png"><img src="contact-sheet.png"></a>')
print(json.dumps({'synthetic_pool':len(rows),'contact_previews':len(preview),'rejected_previews':rejected,'color_counts':dict(collections.Counter(r['plate_color'] for r in rows))},indent=2))
