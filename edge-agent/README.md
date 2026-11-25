# Offline vision D05a

CLI Python độc lập để chạy video/camera config và xuất JSON, CSV, ảnh, HTML
review. Không import backend, không có database/API ingestion, RTSP hoặc service.

Hướng dẫn chạy, giới hạn, đánh giá và kết quả local:
[docs/offline-vision-d05a.md](../docs/offline-vision-d05a.md).
Nguồn/giấy phép code và weights:
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

```bash
# Từ repository root; venv local hiện đã được chuẩn bị:
edge-agent/.venv/bin/python scripts/offline-vision.py --help
edge-agent/.venv/bin/python -m pytest -q edge-agent/tests
```

## D05b — chuẩn bị nhãn và benchmark

[Hướng dẫn D05b](../docs/offline-vision-d05b.md) gồm bộ 40 frame từ hai video,
biểu mẫu gán bbox/nội dung biển/layout, CRNN baseline + Paddle recognizer CPU,
audit trùng/group và kế hoạch fine-tune detector. Không có nhãn readable thì
benchmark chỉ xuất bảng chờ; không tự điền nội dung từ OCR.

Dependency bổ sung chỉ cài vào venv offline:

```bash
edge-agent/.venv/bin/python -m pip install -r edge-agent/requirements-benchmark.txt
edge-agent/.venv/bin/python scripts/offline-vision.py fetch-benchmark-model
edge-agent/.venv/bin/python scripts/offline-vision.py prepare-labels --help
edge-agent/.venv/bin/python scripts/offline-vision.py benchmark-ocr --help
```

Venv local hiện được quản lý bằng uv và đã cài các dependency trên; nếu venv
không có pip, dùng `uv pip install --python edge-agent/.venv/bin/python -r
edge-agent/requirements-benchmark.txt`. Fetch là bước mạng rõ ràng; inference
không tải model hoặc gọi API bên ngoài.

## D05c — audit dataset và preflight detector fine-tune

Hướng dẫn đầy đủ, license/pins, tải Roboflow v1, nhãn40 frame, group split,
commands và kết quả: [plate-detector-d05c.md](../docs/plate-detector-d05c.md).
CLI `scripts/plate-training.py --help`, môi trường `.venv-training` riêng,
Python3.12 và `requirements-training.lock.txt`. Có import-dataset/audit,
camera-review/prepare, fixture/preflight, train/resume, export và compare.

Chưa có ZIP thật hoặc nhãn camera xác nhận; manifest real training hiện0mẫu,
training_ready=false. Fixture preflight/ONNX không là detector nghiệm thu.
Không chạy training dài; `train` chỉ dành cho bước được giao sau và dữ liệu
reviewed. Exported one-class model dùng Detector interface; CLI offline `run`
optional `--plate-model-manifest PATH --plate-model-threshold VALUE`, default YuNet không đổi và từ chối
fixture checkpoint trên video camera. Data/models/venv không vào Git/DB.
