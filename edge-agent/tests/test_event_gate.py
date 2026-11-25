from offline_vision.event_gate import EventGate

POLICY = {'capture_seconds':20,'max_inference_frames':30,'max_evidence_frames':4,
          'signal_max_age_seconds':10,'signal_rearm_gap_seconds':120}


def test_fresh_observed_time_not_received_or_backlog():
    gate=EventGate(POLICY)
    assert not gate.signal('old',900,2000,1000)
    assert not gate.signal('future',1003,2000,1000)
    assert not gate.signal('low',1000,999,1000)
    assert gate.signal('live',999,1000,1000)
    assert gate.state['capture_until']==1020


def test_signal_chain_single_window_restart_and_no_departure_inference():
    gate=EventGate(POLICY)
    assert gate.signal('a',1000,5000,1000)
    for t in range(1001,1050):
        assert not gate.signal(str(t),t,5000,t)
    assert gate.state['capture_until']==1020
    assert not gate.capturing(1050)
    recovered=EventGate(POLICY,dict(gate.state))
    assert not recovered.signal('backlog',1001,5000,1050)
    assert not recovered.signal('new-in-chain',1051,5000,1051)
    assert recovered.signal('new-observation-window',1180,5000,1180)
    assert 'departure' not in recovered.state


def test_preview_expires_and_manual_no_extension():
    gate=EventGate(POLICY)
    gate.state['preview_until']=1120
    assert gate.connected(1100) and not gate.capturing(1100)
    assert not gate.connected(1120)
    assert gate.trigger(1130,'manual','a')
    assert not gate.trigger(1131,'manual','b')
    assert gate.state['capture_until']==1150


def test_plate_guided_deadline_stop_and_resume_are_bounded():
    import json
    from pathlib import Path
    policy=json.loads((Path(__file__).parents[1]/'config/camera-185.worker.json').read_text())['event_policy']
    gate=EventGate(policy)
    assert gate.trigger(1000,'manual','photo')
    assert gate.capturing(1119) and not gate.capturing(1120)
    gate.finish(1016,'plate_quality_target_reached_requires_review')
    recovered=EventGate(policy,dict(gate.state))
    assert not recovered.capturing(1017)
    assert recovered.state['completion_reason']=='plate_quality_target_reached_requires_review'
    assert recovered.trigger(1020,'manual','new')
    assert recovered.state['completed_at'] is None and recovered.state['qualifying_plate_count']==0


def test_plate_guided_rejects_budget_that_stops_search_before_deadline():
    import json
    from pathlib import Path
    import pytest
    policy=json.loads((Path(__file__).parents[1]/'config/camera-185.worker.json').read_text())['event_policy']
    with pytest.raises(ValueError):
        EventGate({**policy,'max_inference_frames':10})
