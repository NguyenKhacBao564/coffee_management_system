import json
import subprocess

import cv2
import numpy as np
import pytest

from offline_vision.diverse_review import prepare
from offline_vision.dataset import validate_labels, sha256


def test_diverse_review_preserves_pixels_and_has_no_inferred_ground_truth(tmp_path):
    incoming=tmp_path/'incoming';folder=incoming/'CarTGMT';folder.mkdir(parents=True)
    image=np.random.default_rng(12).integers(0,255,(70,130,3),dtype=np.uint8)
    original=folder/'49C02655.jpg';cv2.imwrite(str(original),image)
    before=sha256(original);expected=cv2.imread(str(original))
    (folder/'_report.csv').write_text('49C02655.jpg,x,49C02655\n')
    output=tmp_path/'review';summary=prepare(incoming,output,per_source=32)
    assert summary['selected_frames']==1 # fewer images than cap still yields one
    manifest=json.loads((output/'manifest.template.json').read_text());frame=manifest['frames'][0]
    assert frame['annotations']==[] and not frame['reviewed'] and frame['split']=='unassigned'
    assert frame['media_seconds'] is None and frame['frame_index'] is None
    assert isinstance(frame['scene_hash'],str) and int(frame['scene_hash'])<2**64
    assert np.array_equal(cv2.imread(str(output/frame['image_path'])),expected) and sha256(original)==before
    assert validate_labels(manifest,output)['reviewed_frames']==0
    page=(output/'label.html').read_text()
    assert 'Ảnh tĩnh · không có timestamp media' in page
    script=page.split('<script>')[1].split('</script>')[0]
    stub="""
const vm=require('vm');let source='';
process.stdin.on('data',v=>source+=v);process.stdin.on('end',()=>{
 const elements={};const context=new Proxy({},{get:()=>()=>{}});
 const element=()=>({style:{},append(){},replaceChildren(){},removeAttribute(){},getContext:()=>context});
 const document={getElementById:id=>elements[id]??=(element()),createElement:element};
 class Image {complete=false;naturalWidth=0;}
 vm.runInNewContext(source,{document,Image,structuredClone,console});
 process.stdout.write(JSON.stringify({summary:elements.summary.textContent,source:elements.source.textContent}));
});
"""
    result=subprocess.run(['node','-e',stub],input=script,text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    visible=json.loads(result.stdout)
    assert visible['summary'].startswith('1/1') and 'Ảnh tĩnh' in visible['source']
    audit=json.loads((output/'audit.json').read_text());assert audit['entries'][0]['transcript'] is None
    with pytest.raises(FileExistsError):prepare(incoming,output)


def test_bounded_review_rejects_unbounded_cap(tmp_path):
    with pytest.raises(ValueError):prepare(tmp_path,tmp_path/'out',per_source=1000)
