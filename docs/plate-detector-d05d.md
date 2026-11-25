# D05d — Fine-tune detector biển số trên GPU Vast

Cập nhật 07/10/2026. Đây là lần fine-tune bounded đầu tiên của detector
YOLOX-Nano từ gói D05c. D05d hoàn tất quy trình chạy và bàn giao artifacts;
D05 tổng thể vẫn đang thực hiện vì chưa có nhãn camera được xác nhận.

## Máy và gói

- Instance Vast `54567374`, NVIDIA RTX 3090 Ti 24 GB, driver `550.163.01`,
  compute capability 8.6. CUDA tensor operation chạy được với runtime
  PyTorch CUDA 12.6 qua minor-version compatibility. Workspace Vast là
  ephemeral, vì vậy đã tải kết quả về Mac trước khi kết thúc.
- Dùng môi trường cô lập `/workspace/d05d-run/.venv`, Python 3.12.3,
  PyTorch 2.8.0+cu126, torchvision 0.23.0+cu126, OpenCV 4.12.0,
  ONNX 1.19.0, ONNX Runtime 1.23.2. Không thay driver hệ thống.
- Gói nguồn SHA-256
  `921f9df5d5079c6f8464430768fcbae9e3c48285fc4fdd5e9119d02f2daf7b5d`;
  khớp trên Mac và Vast. Dataset trong gói có 539 train, 147 validation,
  75 test; một class `license_plate`, mỗi ảnh trong ba split có một bbox dương.
  Không có ảnh âm đã xác nhận. Pretrained `yolox_nano.pth` SHA-256
  `cd28f55fbbc1829f99d9ac9b38a16d259a22889739c8728ea877610201feff7b`;
  636 tensors được nạp, sáu tensor `head.cls_preds.*` COCO có shape class
  không khớp được khởi tạo lại cho một class.

## Preflight và train

- CUDA preflight dùng ảnh thật của gói: forward/backward, loss hữu hạn,
  validation trên 147 ảnh, save/load checkpoint và optimizer/scheduler resume
  đều đạt. Hai lần chạy một batch chứng minh resume đi tiếp; mỗi epoch có
  270 batch hữu hạn. `drop_last=false`; batch cuối có một ảnh.
- Cấu hình pilot: input 640, batch 2, seed 20261007, LR `1e-5`, SGD với cosine
  scheduler, không mosaic/mixup/flip, tối đa 20 epoch, 1.000 optimizer step,
  7200 giây tổng và tối đa ba lần thử tiến trình. Wrapper chạy trong tmux,
  ghi `last.pth`/optimizer/scheduler/RNG và `best.pth` nguyên tử để resume.
  Không cần restart tự động.
- Hoàn thành đúng 1.000 bước trong 65,17 giây: ba epoch đủ 270 batch, cộng 190
  batch của epoch 4 trước giới hạn step. Validation chỉ đánh giá ở cuối epoch;
  phần epoch 4 không dùng để chọn model. Bước đầu warm-up 4,02 giây; tổng thời
  gian optimizer batch của epoch 1 là 21,28 giây (không gồm validation/setup),
  nên dự báo theo batch không đại diện thời gian epoch hoàn chỉnh.
  Batch trung bình của toàn lượt 0,0578 giây; peak allocated CUDA 519 MB.
  Tập rất nhỏ và model Nano nên VRAM 24 GB không phải giới hạn.
- Checkpoint chọn từ validation: epoch 3, step 810. Validation cố định
  confidence 0,25, NMS 0,45, match IoU 0,5: 145/147 annotation matched
  (98,64%), unmatched prediction 0,0204/ảnh, mean IoU 0,8567. Chỉ số là
  annotation-relative: publisher labels chưa được xác minh và split không có
  ảnh âm được xác nhận; unmatched predictions không được gọi là false positives.
- Chỉ sau khi chọn checkpoint mới mở test một lần: 75/75 annotation matched
  tại IoU 0,5, unmatched prediction 0,0133/ảnh, mean IoU 0,8461. Đây không phải
  accuracy tổng quát: nhãn chưa kiểm tra, test toàn ảnh dương và chưa chứng minh
  chia độc lập theo xe/lượt quay.
- ONNX fixed 640/opset 11, output `[1,8400,6]`, decode trong graph. ONNX
  checker và CPU parity đạt: sai khác tọa độ lớn nhất 0,04895 pixel, xác suất
  0,00005765, trong bounds riêng 0,05 pixel/0,0001. Hash ONNX
  `03fe0db1f9a77108d166a246770efff2dca0dfb4af3c2102bfe9057a012d932b`.
  Metadata chủ ý giữ `quality_accepted=false`.

## Hai video camera — kết quả kiểm tra định tính

Chạy cùng pipeline D05a trên Mac, cùng detector xe/ROI/tracking/OCR và media
sampling. Dùng confidence 0,25 cho YOLOX; YuNet baseline giữ threshold riêng
của nó. ROI hiện tại còn provisional. Không cung cấp manual ground truth.

| Video | Model | Sampled frames | Plate calls / boxes | OCR reads | Thời gian wall | Peak RSS | OCR kết quả |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `073000-073500` | YuNet baseline | 601 | 12 / 0 | 0 | 72,18 s | 766 MiB | unknown |
| `073000-073500` | YOLOX fine-tuned | 601 | 12 / 16 | 8 | 73,73 s | 826 MiB | unknown |
| `103800-104015` | YuNet baseline | 265 | 9 / 0 | 0 | 32,02 s | 727 MiB | unknown |
| `103800-104015` | YOLOX fine-tuned | 265 | 9 / 6 | 5 | 33,06 s | 840 MiB | unknown |

Fine-tuned detector tạo crop để xem lại; một số crop không phải biển (ví dụ
chi tiết lưới/grille trên xe), và OCR không đạt đồng thuận đủ để đề xuất biển.
Không tính các box là recall/precision. Ảnh `plate-*.jpg`, overview, annotated,
raw OCR và chi tiết phiên nằm trong thư mục camera-comparison dưới artifacts.
Không báo độ chính xác tại xưởng. Pipeline không ghi vào database, S03 hay D02.

## Artifacts trên Mac

Thư mục: `data/offline-vision/runs/d05d-vast-54567374/` (gitignored).

- `pilot/`: `best.pth`, `last.pth`, config snapshot, batch visualization,
  `run.json`, log, metrics JSONL.
- `cuda-preflight/`: checkpoint, resume logs, validation và batch visualization.
- `final/test` (JSON content), `final/export/detector.onnx`, `model.json`,
  export/test logs.
- `camera-comparison/`: bốn lượt đầy đủ, annotated/overview/crops/review HTML,
  raw OCR, run JSON và logs.
- `SHA256SUMS.local`: hash của artifacts local để kiểm tra tính toàn vẹn.

Gói training nguyên gốc không sửa. Không đưa secret vào gói; không thay database,
migration, dữ liệu D02, S03, token hay volume.

## Chạy lại có giới hạn

Lệnh ban đầu và đầy đủ dependency/code nằm trong README của gói D05c. Các bước
remote thực tế và supplemental runner đã dùng:

```bash
PYTHONPATH=source-package/d05c-first-train/code .venv/bin/python \
  source-package/d05c-first-train/scripts/d05d-train.py preflight \
  --manifest source-package/d05c-first-train/dataset/manifest.json \
  --config source-package/d05c-first-train/configs/plate-training.pilot.yaml \
  --assets source-package/d05c-first-train/model --output results/preflight \
  --max-steps-this-run 1 --validate-after

PYTHONPATH=source-package/d05c-first-train/code .venv/bin/python \
  source-package/d05c-first-train/scripts/d05d-train.py train \
  --manifest source-package/d05c-first-train/dataset/manifest.json \
  --config source-package/d05c-first-train/configs/plate-training.pilot.yaml \
  --assets source-package/d05c-first-train/model --output results/pilot \
  --max-seconds 7200
```

Actual run used `run-with-retries.sh` under tmux; config capped the run at 1.000
optimizer steps, and the wrapper capped wall time at 7200 giây and max three
process attempts, resuming from `last.pth`. No further training was started. Instance may be stopped to
end hourly GPU charges; it was not destroyed.

## Limits and next step

This run verifies the training/export path and gives a model for human review.
It does not establish Vietnam plate recall, container-lock false-positive rate,
camera accuracy or production threshold. Next, manually label camera positives
and hard negatives with confirmed container locks/bars, group by vehicle/capture,
freeze a new independent test set, then compare baseline and fine-tuned models
on native frames and pipeline crops. Revisit OCR only with checked plate crops
and manual transcripts. No CUDA preflight after this run is pending; only a
future CUDA check for a new config/model or expanded data package may be useful.
