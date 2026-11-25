#!/usr/bin/env bash
set -u
PACKAGE="${1:?Supply extracted D05f package path}"
PYTHON="${2:?Supply Python executable in the GPU venv}"
PACKAGE="$(cd "$PACKAGE" && pwd)"
OUTPUT="$PACKAGE/results/train"
mkdir -p "$OUTPUT"
exec >>"$OUTPUT/train.log" 2>&1
export PYTHONPATH="$PACKAGE/code"
export CUDA_VISIBLE_DEVICES=0
start_seconds=$SECONDS
for attempt in 1 2 3; do
  remaining=$((7200 - (SECONDS - start_seconds)))
  if [ "$remaining" -le 0 ]; then exit 0; fi
  command=("$PYTHON" "$PACKAGE/scripts/d05d-train.py" train
    --manifest "$PACKAGE/dataset/manifest.json" --config "$PACKAGE/configs/train.yaml"
    --policy "$PACKAGE/configs/policy.yaml" --assets "$PACKAGE/model"
    --init-checkpoint "$PACKAGE/initial/best.pth" --init-sha256 "$(cat "$PACKAGE/initial/SHA256")"
    --output "$OUTPUT" --max-seconds "$remaining")
  if [ -f "$OUTPUT/last.pth" ]; then command+=(--resume "$OUTPUT/last.pth"); fi
  echo "attempt=$attempt remaining_seconds=$remaining"
  timeout --signal=TERM --kill-after=30 "$remaining" "${command[@]}"
  result=$?
  if [ "$result" -eq 0 ] || [ "$result" -eq 124 ]; then exit "$result"; fi
  if [ "$attempt" -eq 3 ]; then exit "$result"; fi
  sleep 10
done
