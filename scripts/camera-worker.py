#!/usr/bin/env python3
"""Start/stop only the Mac camera worker; no secrets in process arguments."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'edge-agent/config/camera-185.worker.json'
STATE = ROOT / json.loads(CONFIG.read_text())['state_dir']


def running():
    lock = STATE / 'worker.lock'
    if not lock.exists(): return None
    with lock.open('a+') as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return None
        except BlockingIOError:
            file.seek(0)
            return int(file.read().strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start','stop','status','restart'])
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(STATE / 'control.lock', 'a+') as control:
        fcntl.flock(control, fcntl.LOCK_EX)
        pid = running()
        if args.action in {'stop','restart'} and pid:
            os.kill(pid, signal.SIGTERM)
            for _ in range(40):
                if running() is None: break
                time.sleep(.5)
            if running():
                print('Worker chưa dừng an toàn; không tạo worker thứ hai.'); return 1
            print(f'Worker PID {pid} đã dừng có kiểm soát.'); pid = None
        if args.action in {'start','restart'}:
            if pid: print(f'Worker đã chạy PID {pid}; không chạy trùng.'); return 0
            log = STATE / 'worker.log'
            with log.open('ab') as output:
                os.chmod(log, 0o600)
                process = subprocess.Popen([str(ROOT/'edge-agent/.venv/bin/python'), '-m', 'app.modules.vehicle_pilot.live_worker', '--config', str(CONFIG)],
                    cwd=ROOT, env={**os.environ, 'PYTHONPATH':str(ROOT/'backend')}, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=output, start_new_session=True)
            time.sleep(2)
            if process.poll() is not None: print('Worker khởi động lỗi; xem mã an toàn trong worker.log.'); return 1
            print(f'Worker camera-185 chạy riêng PID {process.pid}.')
        elif args.action == 'status':
            print(f'Worker PID {pid}' if pid else 'Worker đã dừng.')
            if (STATE/'health.json').exists():
                data=json.loads((STATE/'health.json').read_text())
                print(json.dumps({k:data.get(k) for k in ['reported_at_utc','source_state','processing_state','decoded_frames','processed_frames','queue_depth','outbox_depth','reconnect_count','last_error_code','processing_error_code','rss_bytes']}))
    return 0

if __name__ == '__main__': raise SystemExit(main())
