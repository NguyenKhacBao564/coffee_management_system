#!/bin/bash
# Run from the private package root, inside tmux. No automatic retries.
set -euo pipefail
cd "$1"
# FFmpeg probes stdin; GNU timeout creates a background process group in tmux.
# Prevent SIGTTIN stopping Python/FFmpeg and let bounded subprocess timeouts work.
exec </dev/null
export KERAS_BACKEND=torch OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
PYTHON_BIN="${D05K_PYTHON_BIN:-/workspace/d05k-venv/bin/python}"
exit_code=0
timeout --signal=TERM --kill-after=15 240s "$PYTHON_BIN" -m offline_vision.ocr_finetune preflight --root . --output preflight > preflight.log 2>&1 || exit_code=$?
printf '%s\n' "$exit_code" > preflight.exit
if [ "$exit_code" -ne 0 ]; then exit "$exit_code"; fi
"$PYTHON_BIN" - <<'PY'
import json,math
d=json.load(open('preflight/preflight.json'));env=json.load(open('preflight/environment.json'))
assert env['gpu'] and env['pretrained_teacher_parity']['passed']
assert d['resume_iterations']==2 and all(math.isfinite(x) for x in d['losses'])
PY
timeout --signal=TERM --kill-after=30 1260s "$PYTHON_BIN" -m offline_vision.ocr_finetune train --root . --output results > train.log 2>&1 || exit_code=$?
printf '%s\n' "$exit_code" > train.exit
if [ "$exit_code" -ne 0 ]; then exit "$exit_code"; fi
timeout --signal=TERM --kill-after=15 480s "$PYTHON_BIN" -m offline_vision.ocr_finetune export --root . --output results --resume > export.log 2>&1 || exit_code=$?
printf '%s\n' "$exit_code" > export.exit
exit "$exit_code"
