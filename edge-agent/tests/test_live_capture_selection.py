import hashlib
from datetime import datetime, timezone
from uuid import uuid4

def test_plate_guided_capture_pairs_native_context_and_stops_only_on_quality(tmp_path, monkeypatch):
    import json
    import numpy as np
    from pathlib import Path
    from types import SimpleNamespace
    from app.modules.vehicle_pilot.live_worker import Worker, Outbox, ROOT
    from offline_vision.config import CameraConfig
    from offline_vision.event_gate import EventGate
    from offline_vision.sampling import CandidatePool, select_capture_candidates, discard_candidate
    from offline_vision.sessions import Session
    policy=json.loads((ROOT/'edge-agent/config/camera-185.worker.json').read_text())['event_policy']
    worker=Worker.__new__(Worker)
    worker.config={'event_policy':policy,'mode':'event_driven'}
    worker.gate=EventGate(policy); worker.gate.trigger(1000,'manual','fixture')
    worker.health={}; worker.multi_vehicle=False; worker.output=tmp_path/'work'
    worker.output.mkdir(); (worker.output/'candidates').mkdir()
    worker.outbox=Outbox(tmp_path/'outbox.sqlite3')
    cfg=CameraConfig('fixture',[[0,0],[1,0],[1,1],[0,1]],max_saved_plate_crops=8)
    pool=CandidatePool(worker.output/'candidates',cfg)
    session=Session(str(uuid4()),['t1'],1000,1000,1000,(50,50,500,350))
    worker.gate.state['capture_session_ids']=[session.session_id]
    manager=SimpleNamespace(sessions=[session])
    image=np.random.default_rng(7).integers(0,256,(400,600,3),dtype=np.uint8)
    for timestamp in (1001,1016):
        obs={'media_seconds':timestamp,'crop_pixels':[96,32], 'box_in_vehicle_crop':[100,100,196,132],
             'vehicle_crop_origin':[50,50],'score':.8,'used_for_ocr':False}
        session.plate_observations.append(obs)
        pool.offer(session,image[150:182,150:246],obs)
        monkeypatch.setattr('app.modules.vehicle_pilot.live_worker.time.time',lambda:timestamp)
        worker._window_evidence(image,datetime.fromtimestamp(timestamp,timezone.utc).isoformat(),manager,pool)
    assert not worker.gate.capturing(1017)
    assert worker.gate.state['completion_reason']=='plate_quality_target_reached_requires_review'
    worker.gate.state.update(capture_until=1120,completion_reason=None)
    worker.multi_vehicle=True
    worker._capture_plate_context(image,datetime.fromtimestamp(1016,timezone.utc).isoformat(),manager,pool)
    assert worker.gate.capturing(1017)  # Good crops are insufficient when vehicle association is ambiguous.
    worker.multi_vehicle=False
    worker.gate.state['capture_session_ids'].append('another-vehicle')
    worker._capture_plate_context(image,datetime.fromtimestamp(1016,timezone.utc).isoformat(),manager,pool)
    assert worker.gate.capturing(1017)
    saved=json.loads(json.dumps(pool.pools))  # Same durable representation used for restart.
    event={'evidence':[]}
    assert worker._selected_plate_evidence(session,SimpleNamespace(pools=saved),event)==2
    assert len(event['evidence'])==6
    for item in event['evidence']:
        assert Path(item['path']).exists()
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
        assert item['bbox']['plate_box_native']==[150,150,246,182]
        assert item['metadata']['proposal_only']
    first=saved[session.session_id][0][0]
    first['context']['bbox_complete']=False
    assert len(select_capture_candidates(saved[session.session_id],policy,for_stop=True))==1
    first['context']['bbox_complete']=True; first['observation']['crop_pixels']=[36,20]
    assert len(select_capture_candidates(saved[session.session_id],policy,for_stop=True))==1
    worker.gate.state['evidence_count']=policy['max_evidence_frames']
    assert worker._selected_plate_evidence(session,pool,{'evidence':[]})==0
    paths=[first['path'],*first['context_files'].values()]
    discard_candidate(first)
    assert all(not Path(p).exists() for p in paths)
    # Candidate cleanup cannot remove immutable selected evidence (needed by the outbox).
    assert all(Path(item['path']).exists() for item in event['evidence'])


def test_plate_guided_no_plate_or_ambiguous_vehicles_never_stop_early(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from app.modules.vehicle_pilot.live_worker import Worker, ROOT
    from offline_vision.event_gate import EventGate
    policy=json.loads((ROOT/'edge-agent/config/camera-185.worker.json').read_text())['event_policy']
    worker=Worker.__new__(Worker); worker.config={'event_policy':policy}
    worker.gate=EventGate(policy); worker.gate.trigger(1000,'manual','fixture'); worker.health={}
    worker.multi_vehicle=True
    monkeypatch.setattr('app.modules.vehicle_pilot.live_worker.time.time',lambda:1050)
    worker._capture_plate_context(None,datetime.fromtimestamp(1050,timezone.utc).isoformat(),
        SimpleNamespace(sessions=[]),SimpleNamespace(pools={}))
    assert worker.gate.capturing(1050) and worker.gate.state['qualifying_plate_count']==0
    assert not worker.gate.capturing(1120)


def test_replaced_candidate_context_is_removed_without_touching_evidence(tmp_path):
    from dataclasses import replace
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    from offline_vision.config import CameraConfig
    from offline_vision.sampling import CandidatePool
    cfg=CameraConfig('fixture',[[0,0],[1,0],[1,1],[0,1]],min_plate_sharpness=0,max_candidates_per_phase=1)
    pool=CandidatePool(tmp_path,cfg)
    session=SimpleNamespace(session_id='s',started=0)
    observation=lambda t: {'media_seconds':t,'crop_pixels':[96,32]}
    pool.offer(session,np.zeros((32,96,3),np.uint8),observation(1))
    old=pool.pools['s'][0][0]
    context=tmp_path/'old-scene.jpg';context.write_bytes(b'temporary')
    old['context_files']={'overview':str(context)}
    immutable=tmp_path/'committed-evidence.jpg';immutable.write_bytes(b'original')
    pool.offer(session,np.random.default_rng(8).integers(0,256,(32,96,3),dtype=np.uint8),observation(2))
    assert not Path(old['path']).exists() and not context.exists()
    assert immutable.read_bytes()==b'original'
    assert len(pool.pools['s'][0])==1
