import json
import cv2
import numpy as np
import pytest
from offline_vision.diverse_review_expanded import expand_cartgmt,render_expanded
from offline_vision.dataset import validate_labels
from offline_vision.types import Detection

class Detector:
    metadata={'sha256':'fixture','classes':['license_plate']}
    def detect(self,image,seconds):return [Detection((2,2,20,10),'license_plate',.8,'fixture')]


def test_all_source_strings_exact_deduped_not_ground_truth(tmp_path):
    incoming=tmp_path/'incoming';source=incoming/'CarTGMT';source.mkdir(parents=True)
    image=np.full((50,80,3),100,np.uint8);cv2.imwrite(str(source/'a.png'),image);cv2.imwrite(str(source/'duplicate.png'),image)
    cv2.imwrite(str(source/'other.png'),np.full((50,80,3),150,np.uint8))
    (source/'_report.csv').write_text('a.png,x,29C12345\nduplicate.png,x,29C12346\nmissing.png,x,49C00000\nother.png,,\n')
    out=tmp_path/'out';m=expand_cartgmt(incoming,{'frames':[]},out,Detector());f=m['frames'][0]
    assert len(m['frames'])==1 and len(f['source_suggestions'])==2
    assert f['annotations']==[] and not f['reviewed'] and not f['annotations_complete']
    assert f['suggested_plates'][0]['label_origin']=='model_proposal'
    assert type(f['scene_hash']) is str and validate_labels(m,out)['readable_plates']==0
    audit=json.loads((out/'audit.json').read_text());assert audit['missing_images']==['missing.png']
    page=(out/'label.html').read_text();assert 'localStorage.setItem' in page and 'KHÔNG phải nhãn' in page and '20 ảnh/trang' in page
    assert 'source_suggestions' in page and 'visible_text' in page and 'source-hint' in page
    with pytest.raises(FileExistsError):expand_cartgmt(incoming,{'frames':[]},out,Detector())


def test_real_editor_export_import_autosave_preserves_uint64_and_pending(tmp_path):
    import subprocess
    incoming=tmp_path/'incoming';folder=incoming/'CarTGMT';folder.mkdir(parents=True)
    cv2.imwrite(str(folder/'a.png'),np.full((50,80,3),120,np.uint8));(folder/'_report.csv').write_text('a.png,x,49C02655\n')
    output=tmp_path/'out';m=expand_cartgmt(incoming,{'frames':[]},output,Detector());m['frames'][0]['scene_hash']='18446744073709551615';render_expanded(m,output)
    script=(output/'label.html').read_text().split('<script>')[1].split('</script>')[0]
    stub=r"""
const vm=require('vm'),assert=require('assert');let source='';process.stdin.on('data',x=>source+=x);process.stdin.on('end',async()=>{
 const store=new Map();let download='';
 function runtime(){const els={};const context=new Proxy({},{get:()=>()=>{}});
 const element=()=>({value:'',style:{},append(o){if(this.value==='')this.value=String(o.value)},replaceChildren(){this.value=''},removeAttribute(){},getContext:()=>context,addEventListener(){},click(){},focus(){}});
 const document={getElementById:id=>els[id]??=element(),createElement:element,addEventListener(){}};
 class Image {complete=false;naturalWidth=0;}
 class Blob {constructor(parts){download=parts.join('')}}
 const scope={document,Image,Blob,structuredClone,console,localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},setTimeout:fn=>{fn();return 1},clearTimeout(){},URL:{createObjectURL:()=>'',revokeObjectURL(){}}};
 vm.runInNewContext(source,scope);return els;}
 let els=runtime();assert(els.summary.textContent.includes('Đã xem 0'));assert(els['source-hint'].textContent==='49C02655');
 els['accept-box'].onclick();els.save.onclick();let pending=JSON.parse(download);assert(!pending.frames[0].reviewed);assert(pending.frames[0].annotations[0].readability==='pending');
 els.layout.value='single-line';els.layout.oninput();els['decide-correct'].onclick();els.save.onclick();let confirmed=JSON.parse(download);
 assert(confirmed.frames[0].reviewed);assert(confirmed.frames[0].annotations[0].plate_text==='49C02655');assert(confirmed.frames[0].scene_hash==='18446744073709551615');
 els=runtime();assert(els.summary.textContent.includes('Đã xem 1'));els.load.files=[{text:async()=>download}];await els.load.onchange();els.save.onclick();assert(JSON.parse(download).frames[0].scene_hash==='18446744073709551615');
 const tampered=structuredClone(confirmed);tampered.frames[0].image_path='../wrong.png';els.load.files=[{text:async()=>JSON.stringify(tampered)}];await els.load.onchange();assert(els.message.textContent.includes('bất biến khác'));
 process.stdout.write('pending, confirmation, autosave restore, JSON export/import, uint64, tamper rejection passed');
});
"""
    result=subprocess.run(['node','-e',stub],input=script,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert 'uint64' in result.stdout


def test_report_cannot_copy_images_outside_incoming_source(tmp_path):
    incoming=tmp_path/'incoming';folder=incoming/'CarTGMT';folder.mkdir(parents=True)
    image=np.full((50,80,3),100,np.uint8);cv2.imwrite(str(folder/'good.png'),image);cv2.imwrite(str(incoming/'outside.png'),image)
    (folder/'_report.csv').write_text('good.png,x,49C02655\n../outside.png,x,49C00000\n')
    out=tmp_path/'out';m=expand_cartgmt(incoming,{'frames':[]},out,Detector())
    assert len(m['frames'])==1
    assert json.loads((out/'audit.json').read_text())['rejected_source_paths']==['../outside.png']
