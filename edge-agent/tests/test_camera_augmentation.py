import copy
import numpy as np
import pytest
from offline_vision.camera_augmentation import augment,camera_stats,jitter_bbox,occlude_upper,seed_for


def crop():
    image=np.full((30,90,3),210,np.uint8);image[6:13,10:20]=20;image[18:27,20:25]=30;return image


def config():return camera_stats([('real',crop(),15)])['config']


@pytest.mark.parametrize('split',['val','test'])
def test_evaluation_is_bitwise_unchanged_and_label_preserved(split):
    original=crop();before=original.copy();out,text,meta=augment(original,'29K\n52755',split=split,config=config(),sample_id='real',groups=['lighting','occlusion'],split_y=15)
    assert np.array_equal(original,before) and np.array_equal(out,original) and text=='29K\n52755' and meta['applied'] is False
    assert not np.shares_memory(original,out)


def test_seed_reproducibility_and_epoch_variety_no_source_mutation():
    original=crop();before=original.copy();kwargs=dict(split='train',config=config(),sample_id='vehicle-a',groups=['lighting','weather','color'])
    a,ta,ma=augment(original,'29K52755',**kwargs);b,tb,mb=augment(original,'29K52755',**kwargs)
    c,_,_=augment(original,'29K52755',epoch=1,**kwargs)
    assert np.array_equal(a,b) and ma==mb and ta==tb
    assert not np.array_equal(a,c) and np.array_equal(original,before)
    assert seed_for(185,0,'x')!=seed_for(185,1,'x')


@pytest.mark.parametrize('fraction',[0,.01,.25,.5])
def test_upper_row_unknown_mask_keeps_known_bottom(fraction):
    image=crop();out,visible,meta=occlude_upper(image,'29K\n52755',15,fraction,(200,200,200))
    assert visible==('29K' if fraction==0 else '???')+'\n52755'
    assert np.array_equal(out[15:],image[15:])
    assert meta['known_character_mask']==([True]*8 if fraction==0 else [False]*3+[True]*5)


def test_missing_row_mapping_does_not_guess_character_positions():
    _,visible,_=occlude_upper(crop(),'29K52755',15,.2,(100,100,100))
    assert visible=='????????'
    with pytest.raises(ValueError):occlude_upper(crop(),'29K\n52755',15,.51,(0,0,0))
    with pytest.raises(ValueError):occlude_upper(crop(),'29K\n52755',0,.25,(0,0,0))


def test_augmentation_unknown_not_native_trainable():
    out,text,meta=augment(crop(),'29K\n52755',split='train',config=config(),sample_id='a',groups=['occlusion'],split_y=15)
    assert text=='???\n52755' and not meta['native_fastplate_eligible']
    out,text,meta=augment(crop(),'???\n52755',split='train',config=config(),sample_id='a',groups=['color'])
    assert not meta['native_fastplate_eligible'] and text=='???\n52755'


def test_jitter_clipped_valid_and_flag_inward_crop():
    for seed in range(100):
        box,cuts=jitter_bbox((30,90,3),[0,0,90,30],np.random.default_rng(seed),.03)
        x,y,r,b=box;assert 0<=x<r<=90 and 0<=y<b<=30
        assert cuts==(x>0 or y>0 or r<90 or b<30)
    with pytest.raises(ValueError):jitter_bbox((30,90,3),[10,10,5,5],np.random.default_rng(1),.03)


def test_color_preserves_plate_hue_white_and_yellow():
    import cv2
    for bgr in [(240,240,240),(20,210,220)]:
        original=np.full((30,90,3),bgr,np.uint8)
        out,text,meta=augment(original,'49C02655',split='train',config=config(),sample_id='yellow',groups=['color'])
        hsv0=cv2.cvtColor(original,cv2.COLOR_BGR2HSV);hsv1=cv2.cvtColor(out,cv2.COLOR_BGR2HSV)
        assert np.max(np.abs(hsv0[:,:,0].astype(int)-hsv1[:,:,0].astype(int)))<=1
        assert np.max(np.abs(hsv0[:,:,2].astype(int)-hsv1[:,:,2].astype(int)))<=1
        assert text=='49C02655'


def test_native_character_height_is_not_plate_height():
    stats=camera_stats([('real',crop(),15)])
    assert stats['quantiles']['character_height_proxy']['p50']<stats['quantiles']['height']['p50']
    out,_,meta=augment(crop(),'29K52755',split='train',config=stats['config'],sample_id='native',groups=['resolution'],character_height=40)
    assert out.shape==crop().shape and meta['groups']['resolution']['downsample_size'][1]<crop().shape[0]


def test_unknown_split_rejected():
    with pytest.raises(ValueError):augment(crop(),'49C02655',split='unassigned',config=config(),sample_id='a')


def test_no_transcript_is_not_native_training_label():
    _,visible,meta=augment(crop(),'',split='train',config=config(),sample_id='unreadable',groups=['color'])
    assert visible=='' and not meta['native_fastplate_eligible']
