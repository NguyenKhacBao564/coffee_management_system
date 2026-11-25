import copy
from pathlib import Path
import numpy as np
import pytest

from offline_vision.ocr_training_data import grouped_gold_split,silver_decision,leakage_reasons,pixel_hash,proposed_row_split
from offline_vision.ocr_finetune import finite_epoch
from offline_vision.sampling import image_hash
from offline_vision.vn_synthetic import random_plate,safe_upper_cover,safe_jitter,render_plate,synthetic_augment


def row(text,n,dhash):
    return {'text':text,'source':'cartgmt','layout':'single-line','pixel_sha256':str(n),'dhash':str(dhash)}


def test_gold_groups_same_string_and_near_crop():
    rows=[row('29A12345',1,0),row('29A12345',2,2**64-1),row('30A23456',3,3),row('51C34567',4,0xaaaaaaaaaaaaaaaa),row('49C45678',5,0x5555555555555555)]
    result=grouped_gold_split(copy.deepcopy(rows))
    assert result[0]['split']==result[1]['split']==result[2]['split']
    assert result==grouped_gold_split(copy.deepcopy(rows))
    assert {r['split'] for r in result}=={'val','test'}


@pytest.mark.parametrize('fast,english,hints,status',[
    ('29A-123.45','29A12345',['29A12345'],'silver'),
    ('29A12345','29A12346',['29A12345'],'review'),
    ('29A12345','29A12345',['29A12346'],'review'),
    ('29A12345','29A12345',['29A12345','29A12346'],'review'),
    ('29O12345','29O12345',['29O12345'],'review'),
    ('','',[''],'review')])
def test_silver_conservative_raw_agreement(fast,english,hints,status):
    assert silver_decision([{'score':.8}],fast,english,hints,[])[0]==status


def test_silver_no_uncertain_boxes_or_holdout():
    assert silver_decision([{'score':.8},{'score':.8}],'29A12345','29A12345',['29A12345'],[])[0]=='review'
    assert silver_decision([{'score':.74}],'29A12345','29A12345',['29A12345'],[])[0]=='review'
    assert silver_decision([{'score':.8}],'29A12345','29A12345',['29A12345'],[{'reason':'test'}])[0]=='excluded'


def test_crop_hash_filter_and_gold_string():
    im=np.random.default_rng(1).integers(0,255,(20,60,3),dtype=np.uint8)
    gold=[{'sample_id':'g','split':'test','text':'29A12345','pixel_sha256':pixel_hash(im),'dhash':str(image_hash(im)),'source_image_sha256':'source'}]
    evidence=leakage_reasons(im,im,'29A12345',gold)
    assert set(evidence[0]['reasons'])=={'exact_crop_pixels','crop_dhash<=4','same_plate_string'}


def test_finite_sampler_seed_count_caps_and_no_gold():
    rows=[{'sample_id':str(n),'label_origin':'silver','split':'train'} for n in range(5)]+[{'sample_id':'s'+str(n),'label_origin':'synthetic','split':'train'} for n in range(30)]
    epoch=finite_epoch(rows,0,185)
    assert epoch==finite_epoch(rows,0,185) and epoch!=finite_epoch(rows,1,185)
    assert len(epoch)==10 and len({r['sample_id'] for r in epoch})==10
    with pytest.raises(ValueError):finite_epoch(rows+[{'label_origin':'gold','split':'val'}],0,185)


def test_native_row_hypothesis_not_text_based():
    assert proposed_row_split(np.full((10,80,3),255,np.uint8)) is None
    im=np.full((40,80,3),255,np.uint8);im[5:15,12:68]=0;im[25:35,12:68]=0
    assert 14<=proposed_row_split(im)<=26


def test_random_supported_strings_exclude_gold_and_repeatable():
    a=np.random.default_rng(185);b=np.random.default_rng(185)
    from offline_vision.plate_domain import parse_plate
    for color in ['white','yellow','blue']:
        left=random_plate(a,color,{'49C02655','29K52755'});right=random_plate(b,color,{'49C02655','29K52755'})
        assert left==right and parse_plate(left) and left not in {'49C02655','29K52755'}
        if color=='blue':assert left[2] in 'ABCDEFGHKLM'


def test_safe_cover_never_truncates_characters():
    im=np.full((40,80,3),255,np.uint8);boxes=[{'bbox':[5,5,12,18]}]
    covered,meta=safe_upper_cover(im,boxes,.2,20)
    assert meta['glyph_intersections']==0 and meta['covered_height']==4
    with pytest.raises(ValueError):safe_upper_cover(im,boxes,.3,20)
    with pytest.raises(ValueError):safe_upper_cover(im,boxes,1/3,20)


def test_synthetic_jitter_preserves_all_glyph_boxes():
    im=np.zeros((100,200,3),np.uint8);boxes=[{'character':'A','bbox':[40,30,50,60]}]
    out,shifted,meta=safe_jitter(im,boxes,np.random.default_rng(185))
    x,y,r,b=meta['crop_bbox'];assert out.shape[:2]==(b-y,r-x)
    assert shifted[0]['bbox']==[40-x,30-y,50-x,60-y]


def test_synthetic_real_font_label_safe_native_downscale():
    root=Path(__file__).resolve().parents[2];font=root/'data/offline-vision/fonts/RobotoCondensed.ttf'
    if not font.exists():pytest.skip('Optional local OFL font not in Git')
    import json
    cfg=json.loads((root/'data/offline-vision/runs/d05j-expanded-20261007/augmentation-v3/augmentation.adapter.json').read_text())
    im,glyphs,split=render_plate('49C12345','two-line','yellow',font)
    out,meta=synthetic_augment(im,'49C12345',glyphs,split,cfg,sample_id='fixture',groups=['occlusion'])
    out2,meta2=synthetic_augment(im,'49C12345',glyphs,split,cfg,sample_id='fixture',groups=['occlusion'])
    assert np.array_equal(out,out2) and meta==meta2
    assert 9<=meta['first_target_glyph_height']<=11 and out.shape[0]<im.shape[0]
    assert meta['safe_cover']['glyph_intersections']==0 and meta['text_preserved']
