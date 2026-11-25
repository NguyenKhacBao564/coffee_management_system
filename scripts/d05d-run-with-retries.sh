#!/usr/bin/env bash
set -u

RUN_ROOT="${1:-/workspace/d05d-run}"
PACKAGE="$RUN_ROOT/source-package/d05c-first-train"
OUTPUT="$RUN_ROOT/results/pilot"
CONFIG="$PACKAGE/configs/plate-training.pilot.yaml"
MANIFEST="$PACKAGE/dataset/manifest.json"
ASSETS="$PACKAGE/model"
PYTHON="$RUN_ROOT/.venv/bin/python"
SCRIPT="$PACKAGE/scripts/d05d-train.py"
MAX_WALL_SECONDS=7200
MAX_ATTEMPTS=3

mkdir -p "$OUTPUT"
exec >>"$OUTPUT/train.log" 2>&1
export PYTHONPATH="$PACKAGE/code"
export CUDA_VISIBLE_DEVICES=0
start_seconds=$SECONDS
attempt=1

while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  remaining=$((MAX_WALL_SECONDS - (SECONDS - start_seconds)))
  if [ "$remaining" -le 0 ]; then
    echo "wall-time limit reached before attempt $attempt"
    exit 0
  fi
  echo "attempt=$attempt remaining_seconds=$remaining started=$(date -u +%FT%TZ)"
  command=("$PYTHON" "$SCRIPT" train --manifest "$MANIFEST" --config "$CONFIG"
    --assets "$ASSETS" --output "$OUTPUT" --max-seconds "$remaining")
  if [ -f "$OUTPUT/last.pth" ]; then
    command+=(--resume "$OUTPUT/last.pth")
  fi
  "${command[@]}"
  result=$?
  if [ "$result" -eq 0 ]; then
    echo "training stopped normally; see run.json for reason"
    exit 0
  fi
  echo "attempt=$attempt exited=$result"
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "restart limit reached"
    exit "$result"
  fi
  attempt=$((attempt + 1))
  sleep 10
done
