import queue
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit
import pytest
from offline_vision.live_source import LiveSource, authenticated_uri, put_latest


def test_latest_frame_queue_stays_bounded():
    frames = queue.Queue(maxsize=2)
    for i in range(1000): put_latest(frames, i)
    assert frames.qsize() == 2
    assert [frames.get(), frames.get()] == [998, 999]


def test_uri_is_in_memory_and_percent_encoded():
    uri = authenticated_uri('rtsp://192.168.1.185:554/cam/realmonitor?channel=1&subtype=0', 'user@', 'secret:@/?')
    assert urlsplit(uri).hostname == '192.168.1.185'
    assert 'secret%3A%40%2F%3F' in uri
    with pytest.raises(ValueError): authenticated_uri('rtsp://old:secret@host/path', 'x', 'y')


def test_auth_rejection_is_safe_and_not_retried(monkeypatch, capsys):
    import sys
    class Rejected(Exception): pass
    calls = []
    def open_source(*args, **kwargs):
        calls.append(1)
        raise Rejected('rtsp://user:secret@private/path')
    fake = SimpleNamespace(logging=SimpleNamespace(PANIC=0, set_level=lambda _:None), open=open_source,
        error=SimpleNamespace(HTTPUnauthorizedError=Rejected))
    monkeypatch.setitem(sys.modules, 'av', fake)
    monkeypatch.setattr('offline_vision.live_source.keychain_secret', lambda *args: 'secret')
    source = LiveSource({'rtsp_uri':'rtsp://192.168.1.185/path','username_service':'u','password_service':'p'})
    source.start(); source.thread.join(1)
    snapshot = source.snapshot()
    assert snapshot['last_error_code'] == 'RTSP_AUTH_REJECTED'
    assert len(calls) == 1
    assert 'secret' not in str(snapshot) and 'secret' not in capsys.readouterr().out
    assert source.frames.qsize() == 0


def test_event_idle_never_opens_rtsp(monkeypatch):
    import sys
    calls=[]
    fake=SimpleNamespace(logging=SimpleNamespace(set_level=lambda _:None),open=lambda *a,**k:calls.append(1))
    monkeypatch.setitem(sys.modules,'av',fake)
    monkeypatch.setattr('offline_vision.live_source.keychain_secret',lambda *args:'fixture')
    source=LiveSource({'mode':'event_driven','rtsp_uri':'rtsp://192.168.1.185/path','username_service':'u','password_service':'p'})
    source.start()
    assert source.close()
    assert calls==[] and source.snapshot()['decoded_frames']==0
    for i in range(4):put_latest(source.frames,i)
    source.enable(False)
    assert source.frames.qsize()==0
