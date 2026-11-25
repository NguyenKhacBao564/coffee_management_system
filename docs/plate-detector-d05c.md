# D05c — Chuẩn bị fine-tune detector biển số lần đầu

Ngày 07/10/2026. Đây là bước chuẩn bị offline, **chưa có detector fine-tuned
được nghiệm thu**. D02/S03, database ứng dụng, token và video gốc không đổi.
Tình trạng audit dataset và gói train mới nhất ở mục 6.

## 1. Tình trạng dữ liệu thật

| Nguồn | Thông tin đã xác minh | Đã kiểm tra nội dung thực tế |
| --- | --- | --- |
| [biển số xe / datacar, Roboflow v1](https://universe.roboflow.com/datacar-my0w7/bien-so-xe-3w699-avdfe/dataset/1) | v1 `2025-01-06 5:34pm`, export COCO đã giải nén trong `data/offline-vision/incoming/bien so xe.v1i.coco`; CC BY 4.0 | 864 ảnh đọc được; 793 bbox cấu trúc hợp lệ, 761 bbox được chọn cho gói sau khi giữ 32 mẫu đáng ngờ chờ xác nhận; 71 ảnh không nhãn vẫn chưa phân loại |
| Camera185, hai video D05b | 40 PNG native 1920×1080, 20 mỗi video; giữ timestamp media, image/video SHA, crop và provenance D05b | 0 frame reviewed, 0 bbox biển/nội dung được người dùng xác nhận |
| Fixture preflight riêng | 4 ảnh synthetic, 3 bbox biển và 1 ảnh không biển, batch2 | Chỉ kiểm tra cơ chế huấn luyện; không phải camera hoặc Roboflow |

Roboflow công bố **CC BY 4.0** trên project. [Giấy phép](https://creativecommons.org/licenses/by/4.0/)
cho phép sử dụng/chỉnh sửa kể cả thương mại với attribution, link license và
nêu thay đổi. Attribution khi dùng dữ liệu:

> biển số xe, datacar, Roboflow Universe, version 1 (2025-01-06 5:34pm), CC BY 4.0.
> Nguồn: https://universe.roboflow.com/datacar-my0w7/bien-so-xe-3w699-avdfe/dataset/1.
> Thay đổi khi thực hiện: chuẩn hóa class biensoxehoi → license_plate,
> lọc sau audit và chia tập theo nhóm đã được rà soát.

Không suy ra quyền sở hữu ảnh hay tỷ lệ xe tải/container từ tên dataset.
Để xác minh nhãn sai, bố cục một/hai dòng và loại xe cần xem ảnh gốc; công cụ
không biến aspect ratio hoặc OCR thành ground truth.

### Bước tải cần người dùng thực hiện

Trình duyệt in-app được chọn hiện nhận modal **“Login or create a free account”**
khi mở export COCO. Ảnh chụp của bạn cho thấy Chrome đã đăng nhập; phiên đó
khác phiên in-app. Trong trình duyệt đã đăng nhập:

1. Mở link v1 phía trên → **Download Dataset**.
2. Chọn **COCO JSON** → **Download ZIP**. Nếu vẫn bị yêu cầu đăng nhập, đăng
   nhập Roboflow bằng tài khoản của bạn rồi mở lại v1.
3. Lưu ZIP vào `/Users/nguyen_bao/Documents/ChatGPT/nhu-tung-demo/data/offline-vision/incoming/`.
4. Cung cấp tên file ZIP. Không gửi API key, không dán code tải có key vào Git.

Thư mục incoming đã tạo. macOS từ chối đọc Downloads trong phiên này; không
đổi quyền hệ thống để vượt hạn chế. `d05c-dataset-status.json` lưu nguồn,
license/attribution và **published_counts**, actual counts vẫn null.

## 2. Audit, nhãn và split

CLI mới: `scripts/plate-training.py`; module độc lập
`edge-agent/offline_vision/fine_tune/`. Chạy từ repository:

```bash
cd /Users/nguyen_bao/Documents/ChatGPT/nhu-tung-demo
edge-agent/.venv-training/bin/python scripts/plate-training.py import-dataset --zip data/offline-vision/incoming/FILE.zip --output data/offline-vision/datasets/roboflow-v1
edge-agent/.venv-training/bin/python scripts/plate-training.py audit --raw data/offline-vision/datasets/roboflow-v1/raw --output data/offline-vision/datasets/roboflow-v1-audit
```

Mọi output phải là thư mục mới; không ghi đè. Import giữ `original.zip`, hash,
metadata và raw files; không sửa bản gốc. ZIP bị chặn path traversal/symlink,
case alias trên Mac, vượt20.000 entries/2GiB uncompressed. Audit hỗ trợ COCO
JSON hoặc YOLO bbox txt, kiểm tra decode/dimensions, ảnh/nhãn thiếu, orphan,
class lạ, bbox NaN/ngoài ảnh/rỗng và bbox trùng. Chuẩn hóa class trong manifest;
`prepare` mới xuất COCO một class `license_plate` và tham chiếu ảnh raw.

Audit xuất `audit.json`, `summary.json`, `review.template.csv`, contact sheets
24 ảnh/page với bbox. So sánh file/pixel SHA phát hiện exact duplicate; pHash
<=6 **và** dHash<=8 đánh dấu near-duplicate suspect. Cờ này cần xem thủ công,
không tự kết luận ảnh khác xe là trùng. Report tách cross-split, phân vị kích
thước bbox native; layout/vehicle_type unknown tới khi người dùng điền.

Lưu CSV đã rà soát thành `review.manual.csv`:

- `annotation_review`: accepted / rejected / pending; chỉ accepted được chọn.
- `plate_presence`: plate / no_plate. Nhãn rỗng không tự là âm; biển thấy thật
  mà chưa định vị được phải loại khỏi train cho tới khi có bbox.
- `layout`: single-line / two-line / unknown; `vehicle_type`: car / truck /
  container / unknown. Đây là metadata người xem, không phải prediction.
- `vehicle_group_id`, `capture_group_id`, `split`: xem ảnh/nguồn để nhóm cùng
  xe/lượt quay. Không cấp nhóm ngẫu nhiên riêng cho ảnh sát nhau chỉ để qua audit.
- Nhãn hình học sai: sửa trong bản làm việc riêng, giữ raw, audit lại nguồn
  đã sửa và lưu nguồn/hash/thay đổi; không đánh dấu accepted để bỏ qua lỗi.

### Hoàn thiện 40 frame camera và hard negatives

Công cụ hiện có được dùng lại. Bản review mới ở:
`data/offline-vision/training/d05c-camera-review-v2/label.review.html`.
Mở HTML trực tiếp bằng browser; ảnh được đọc từ bộ D05b gốc. JSON/CSV tải xuống
vẫn dùng image_path/provenance gốc để validator đối chiếu.

- Vẽ **tất cả biển thật**, cả không đọc được; không cần transcript để train
  detector. Transcript/layout/split_y/readability thủ công dùng cho OCR.
- Box xanh nét đứt chỉ gợi ý xe. Ba box vàng ở frame v001 media120s là khóa/
  thanh container được chọn bằng xem ảnh, **chưa được người dùng xác nhận**.
  Crop PNG và `hard-negative.proposals.json` có `ground_truth=false`.
  Xem lại ảnh gốc, vẽ lại với kind `hard_negative` nếu đúng; không tự gắn cả
  frame là âm và không tạo class khóa/thanh riêng.
- Điền mã xe/capture, split, đánh dấu đã xem từng frame và xuất
  `labels.manual.json`. Các proposal không nằm trong `annotations`.
- Điền file `camera-review.template.csv` → `camera-review.manual.csv`:
  `plate_presence=plate/no_plate/plate_unlocatable/unreviewed`, vehicle_type,
  split giống JSON. `plate_unlocatable` bị loại, không trở thành negative.
- Hai source clip phải giữ nguyên split. Đề xuất một clip train, clip còn lại
  test; dùng validation ngoài camera để chọn checkpoint/ngưỡng. Nếu cùng xe
  xuất hiện ở hai clip, chuyển cả nhóm sang một split và giữ test camera chưa
  có hoặc thu lượt quay khác; không cố giữ test có leakage.
- D05b audit có 140 scene-dHash suspect do nền cố định, 0 exact PNG. Rà soát
  cross-split và lưu resolution `reviewed_different_observations` khi thực sự
  khác quan sát. Exact duplicates phải chủ động loại một, không copy dữ liệu.

```bash
edge-agent/.venv-training/bin/python scripts/offline-vision.py audit-labels --dataset data/offline-vision/datasets/d05b-camera185 --labels data/offline-vision/datasets/d05b-camera185/labels.manual.json --output data/offline-vision/training/camera-manual-audit.json
edge-agent/.venv-training/bin/python scripts/plate-training.py prepare --audit data/offline-vision/datasets/roboflow-v1-audit/audit.json --review data/offline-vision/datasets/roboflow-v1-audit/review.manual.csv --camera-dataset data/offline-vision/datasets/d05b-camera185 --camera-labels data/offline-vision/datasets/d05b-camera185/labels.manual.json --camera-review data/offline-vision/training/d05c-camera-review-v2/camera-review.manual.csv --output data/offline-vision/training/d05c-reviewed
```

`--duplicate-reviews FILE.json` nhận danh sách `{sample_ids:[id1,id2],
resolution:"reviewed_different_observations"}` cho các pair thực sự khác.
Prepare khóa input/image hashes, chặn group xuyên split, exact duplication,
similarity chưa xác nhận, giữ original external test khỏi train/val, xuất
manifest và train/val/test COCO. Không tự random split. Manifest hiện tại
`d05c-pending-real/manifest.json`: **0 accepted**, batches0, training_ready=false.

## 3. Detector và preflight

Chọn **YOLOX-Nano** trainable, 896.754 parameters với head một class.
[Code official Apache-2.0](https://github.com/Megvii-BaseDetection/YOLOX/blob/6ddff4824372906469a7fae2dc3206c7aa4bbaee/LICENSE),
[custom training](https://github.com/Megvii-BaseDetection/YOLOX/blob/6ddff4824372906469a7fae2dc3206c7aa4bbaee/docs/train_custom_data.md),
[export ONNX](https://github.com/Megvii-BaseDetection/YOLOX/blob/6ddff4824372906469a7fae2dc3206c7aa4bbaee/tools/export_onnx.py).
Pinned revision `6ddff4824372906469a7fae2dc3206c7aa4bbaee`.
Official pretrained release0.1.1rc0 `yolox_nano.pth`, 7.694.953bytes,
SHA256 `cd28f55fbbc1829f99d9ac9b38a16d259a22889739c8728ea877610201feff7b`.
Checksum đo local, không phải checksum upstream đã công bố.
Release weights phân phối trong dự án Apache2; không tìm thấy hạn chế riêng
trên release. License/source/checkpoint provenance được lưu cạnh model local.
636 tensor COCO được nạp, chỉ6 tensor classification80→1 được khởi tạo lại.
LPD YuNet ONNX giữ baseline; không dùng nó làm checkpoint training.

Môi trường tách biệt `.venv-training`: Python3.12.7 arm64, torch2.8.0,
torchvision0.23.0, ONNX1.19.0, ONNXRuntime1.23.2, OpenCV4.12.0. Toàn bộ package
pin trong `requirements-training.lock.txt`; không sửa runtime/backend cũ.
Tái tạo bằng Python3.12 và pip install lock. Model fetch duy nhất có network:

```bash
edge-agent/.venv-training/bin/python scripts/plate-training.py fetch-model --output data/offline-vision/training-assets/yolox-nano
```

Loader BGR raw0–255, aspect letterbox top-left640, pad114, targetclass0cxcywh.
Đây là preprocessing release hiện tại, khác adapter YOLOX-s OpenCV Zoo cũ.
Seed20261007, CPU2threads, batch2, SGDmomentum0,9, không mosaic/mixup/flip.
Mỗi epoch shuffle hữu hạn, không nhân bản ảnh; tail batch không drop/repeat.
**Batches thực = ceil(N_train_accepted/2)**. Chưa có actual N Roboflow; không
lấy606 công bố làm actual. Config pilot tối đa20epochs/**1000totalsteps**, dừng
khi chạm một giới hạn; chưa chạy. LR1e-5 chỉ là cấu hình pilot thận trọng,
chưa được chọn bằng validation hay chứng minh convergence.

Config preflight giới hạn2epochs/**2totalsteps**, LR1e-6. Resume chỉ khi data/
config hashes khớp, giữ epoch/cursor/order/RNG/optimizer và cumulative cap.
Model uses safe `torch.load(weights_only=True)`. Batch PNG có bbox đã resize;
checkpoint roundtrip kiểm tra mọi tensor bằng nhau.

### Đã chạy trên fixture

| Lần | New steps / cumulative | Wall / CPU | RSS quan sát |
| --- | --- | --- | --- |
| v2 step1 | 1 / 1 | 1,421s / 2,371s | 956MiB |
| v2 resume | 1 / 2 | 1,395s / 2,340s | 970MiB |

Thời gian/CPU đo interval forward/backward + checkpoint, không gồm import,
khởi tạo/load pretrained hoặc export. RSS là observed process sampling,
không phải RAM toàn máy hay estimate cloud.

Ảnh batch/weights/loss/hash: `data/offline-vision/training/d05c-preflight-v2-*`.
Lần đầu LR1e-3 có forward/backward hữu hạn nhưng decoded ONNX parity không đạt
(vùng tọa độ bất thường). Giữ nguyên artifact thất bại; chạy lại cấu hình LR
nhỏ hơn trên fixture, tổng cộng **hai thử nghiệm ×2 optimizersteps**, không
training dữ liệu thật hoặc dài. Đây không phải đường loss nghiệm thu model.

Export fixed640 opset11, decode trong graph, output[1,8400,6] = cxcywh,
objectness, classscore. ONNX checker và ORT CPU parity đạt: coords max0,026093
pixel, probabilities max0,00006551. Dùng bounds FP32 tuyệt đối riêng: 0,05pixel
và0,0001probability, rtol0; không dùng tolerance này cho timestamp S01.
Adapter `YoloXPlateDetector.detect(image,media_seconds)` giữ Detector interface,
score objectness×class, NMS và tọa độ ảnh gốc. Fixture adapter smoke37ms, 0box;
không có nghĩa detector tốt. Metadata quality_accepted=false. CLI D05a nhận optional `--plate-model-manifest` và yêu cầu
`--plate-model-threshold` chọn riêng bằng val. CLI từ chối checkpoint synthetic
trên camera; mặc định YuNet giữ nguyên.

Để preflight **sau khi dữ liệu thật đủ nhãn** (output mới):

```bash
edge-agent/.venv-training/bin/python scripts/plate-training.py preflight --manifest data/offline-vision/training/d05c-reviewed/manifest.json --config edge-agent/config/plate-training.preflight.yaml --assets data/offline-vision/training-assets/yolox-nano --output data/offline-vision/training/real-preflight-step1 --steps-this-run 1
edge-agent/.venv-training/bin/python scripts/plate-training.py preflight --manifest data/offline-vision/training/d05c-reviewed/manifest.json --config edge-agent/config/plate-training.preflight.yaml --assets data/offline-vision/training-assets/yolox-nano --output data/offline-vision/training/real-preflight-step2 --resume data/offline-vision/training/real-preflight-step1/checkpoint.pth --steps-this-run 1
edge-agent/.venv-training/bin/python scripts/plate-training.py export --checkpoint data/offline-vision/training/real-preflight-step2/checkpoint.pth --manifest data/offline-vision/training/d05c-reviewed/manifest.json --config edge-agent/config/plate-training.preflight.yaml --assets data/offline-vision/training-assets/yolox-nano --output data/offline-vision/training/real-preflight-onnx
```

Lệnh pilot cho bước được giao sau: `train` với cùng các argument manifest/
assets/output và config `plate-training.pilot.yaml`; có `--resume` và
`--steps-this-run` để giới hạn mỗi lần. Không dùng fixture cho `train`.

## 4. Kế hoạch so sánh và OCR

1. Chọn checkpoint và ngưỡng **chỉ trên val**; ghi hash model/data và ngưỡng
   từng detector vào bản riêng của `plate-evaluation.plan.example.json`.
2. Khóa plan trước test; không dùng test để chọn LR/checkpoint/threshold.
   CLI `compare` kiểm tra plan/data/model hashes và flag freeze khi split=test.
   Flag là xác nhận quy trình của người chạy, không tự chứng minh lịch sử chọn.
3. Trước hết so hai model trên **cùng ảnh native đầy đủ** để tách detector,
   IoU>=0,5 match một-một: recall biển thật, FP/image, FP chồng >=50% diện tích
   prediction lên region khóa/thanh thủ công, missed IDs/bbox, native crop size,
   GT area coverage và tỷ lệ crop bao >=95%GT, latency p50/p95.
4. Sau đó so trong cùng vehicle-crop/ROI/tracking pipeline D05a và sampling
   fixed; không trộn metric full-frame với vehicle-crop. Kiểm tra contact
   sheets/crop để thấy biển bị cắt chữ, xe/biển nhỏ và container FP. Không gộp
   confidence hai họ model làm cùng xác suất. Log CPU/RSS riêng cho lượt thật.
5. Test báo riêng theo capture/xe, một/hai dòng, truck/container/car và size;
   chỉhai clips không báo accuracy tổng quát. Test độc lập cần xe/lượt quay mới.

```bash
edge-agent/.venv-training/bin/python scripts/plate-training.py compare --manifest data/offline-vision/training/d05c-reviewed/manifest.json --plan data/offline-vision/training/evaluation.frozen.json --model-manifest data/offline-vision/training/pilot-export/model.json --baseline-folder data/offline-vision/models --output data/offline-vision/training/comparison-val
edge-agent/.venv-training/bin/python scripts/offline-vision.py benchmark-ocr --dataset data/offline-vision/datasets/d05b-camera185 --labels data/offline-vision/datasets/d05b-camera185/labels.manual.json --output data/offline-vision/benchmarks/d05c-manual
```

OCR hiện vẫn0 reviewed/readable nên bảng pending, metrics rỗng, accuracy null;
không chạy inference rồi gán output làm nhãn. Khi có GT, CRNN vs PaddleTiny,
3variants cố định, một/hai dòng theo nhãn, giữ raw, exact toàn biển; không sửa
O/0 hoặc dùng best-variant mỗi mẫu. Fine-tune detector trước; OCR chỉ khi GT
crop chuẩn cho thấy lỗi recognizer vẫn đáng kể.

## 5. Kiểm tra và phạm vi bàn giao

72tests offline đạt (D05a/b +22case D05c), gồm audit/geometry/missing labels,
ZIP traversal/case alias, classmap, duplicates/leakage/testseal, explicit
negative, native BGRpreprocess, finite batches/resume/cumulativecap/hash đổi,
scoring missed plate/containerFP và camera pending không biến thành âm.
Forward/backward/save/load/export kiểm tra thật bằng YOLOX trên fixture CPU;
unit resume dùng tiny fixture model riêng để kiểm tra state machine.
Browser QA: cả40 frame, ảnh1920×1080 native, frame120s box vàng/0reviewed,
không consoleerror; screenshot `data/d05c-work/review-ui.jpg`.

D05c **chưa nghiệm thu detector hoặc độ chính xác camera**. Audit/đóng gói và
CPU preflight trên dữ liệu thật được ghi trong mục 6. Không chạy cloud/GPU,
không nối database/cân/D02, không RTSP/training dài. Ảnh/data/weights/venv ignored.

## 6. Cập nhật dataset thật và gói lần train đầu (07/10/2026)

Người dùng cung cấp export COCO dạng thư mục đã giải nén, không phải ZIP. Bản
incoming được giữ nguyên. Audit thực tế:

- 864/864 ảnh decode được, kích thước khớp annotation; 0 lỗi inventory, 0 bbox
  ngoài ảnh/degenerate, 0 class ngoài danh sách được chấp nhận. COCO có hai
  category `cars` và `biensoxehoi`; category `cars` có 0 annotation được dùng,
  793 bbox `biensoxehoi` được chuẩn hóa thành `license_plate`, một bbox/ảnh.
- 71 ảnh trống annotation (train48, valid15, test8) là **chưa rõ**, không phải
  ảnh âm. 32 ảnh có bbox bị đưa vào hàng chờ xem do heuristic kích thước/diện
  tích/biên (32 ảnh: 20 bbox >20% diện tích, 7 rộng <35 px, 5 chạm biên, 1 cao
  <12 px; một ảnh có thể có nhiều cờ). Các cờ không khẳng định nhãn sai và
  không tự sửa/xóa.
- 0 exact pixel duplicate, 0 near-duplicate suspect theo ngưỡng pHash≤6 và
  dHash≤8, 0 cặp trùng giữa split theo phép kiểm này. Contact sheet ban đầu và
  9 trang ưu tiên xác nhận có bbox màu cam nằm tại
  `data/offline-vision/datasets/d05c-roboflow-v1-audit/`.
- 761 annotation còn lại qua sàng lọc hình học, giữ nguyên publisher split:
  train539, val147, test75. Cả ba split chỉ có ảnh dương, 0 ảnh âm. Test giữ
  riêng, không được dùng chọn checkpoint/ngưỡng. Không có nhãn D05b camera đã
  xác nhận hoặc hard negative đã được người dùng xác nhận nên không đưa các dữ
  liệu đó vào train.
- Public export không có vehicle/capture IDs đáng tin cậy. Đã giữ split gốc và
  xác minh không thấy ảnh trùng theo audit, nhưng không tuyên bố đã loại hết
  leakage theo xe/lượt quay. Chưa thống kê được tỷ lệ xe tải/container hoặc bố
  cục một/hai dòng bằng nhãn thủ công. Không có ground truth OCR nên chưa có
  benchmark OCR hay độ chính xác model.

Gói portable nằm tại
`data/offline-vision/training-packages/d05c-first-train/` và ZIP
`data/offline-vision/training-packages/d05c-first-train.zip` (khoảng 62 MB,
SHA-256 `921f9df5d5079c6f8464430768fcbae9e3c48285fc4fdd5e9119d02f2daf7b5d`).
Gói chứa 761 ảnh đã chọn, COCO một class, manifest và hash, review bundle riêng
cho 32+71 mẫu, danh sách 40 frame camera chưa gán nhãn, code offline tối thiểu,
YOLOX-Nano source/weights, lock dependencies, config, README và attribution.
Không chứa `.env`, token hay database. License dataset CC BY 4.0 và attribution
cùng thay đổi class/lọc ảnh được ghi trong `licenses/DATASET-ATTRIBUTION.txt`.

### Cấu hình và kiểm tra gói

- YOLOX-Nano release/code revision `6ddff4824372906469a7fae2dc3206c7aa4bbaee`,
  Apache-2.0; pretrained weight SHA-256
  `cd28f55fbbc1829f99d9ac9b38a16d259a22889739c8728ea877610201feff7b`.
  Checkpoint có 80 class; detector đổi sang một class. Loader nạp 636 tensor
  tương thích và bỏ qua 6 tensor `cls_preds` lệch shape để head mới được khởi
  tạo lại. Không dùng YuNet LPD làm checkpoint train.
- Seed20261007, input640, batch2, learning rate `1e-5`, tối đa20 epoch/1000
  bước, mosaic/mixup/flip đều tắt. Train có 539 ảnh nên 270 batch/epoch,
  `drop_last=false`, batch cuối 1 ảnh. Mỗi epoch là một permutation hữu hạn
  không hoàn lại; không oversample, không lặp dữ liệu. 1000 bước là tối đa 3
  epoch đầy đủ và 190 batch epoch thứ tư. Resume kiểm tra hash manifest/config.
- ZIP được giải nén vào thư mục tạm; README CLI chạy được từ đó. Loader đọc ảnh
  thật, vẽ `review/public-data/real-training-batch.png`; YOLOX CPU forward/
  backward 2 bước, loss hữu hạn, checkpoint round-trip và resume đạt. Sáu tensor
  phân lớp COCO được bỏ qua như trên. Probe riêng dùng optimizer stub qua đủ
  270 batch/539 ảnh thật, kết thúc epoch với cursor0 trong ~2,2 giây; probe này
  chỉ xác minh loader/kết thúc vòng lặp, không cập nhật YOLOX weights.
- Kiểm thử liên quan: `edge-agent/.venv-training/bin/python -m pytest
  edge-agent/tests/test_plate_training.py -q` → 22 passed, 1 warning do fixture
  ZIP cố ý tạo duplicate filename. Lệnh `evaluate --help` từ gói giải nén cũng
  đạt. PyTorch có FutureWarning upstream về `torch.cuda.amp.autocast`; không ảnh
  hưởng CPU preflight. CUDA preflight thực hiện sau khi có GPU thuê.

Lệnh trong README gói:

```sh
python scripts/plate-training.py train --manifest dataset/manifest.json --config configs/plate-training.pilot.yaml --assets model --output results/pilot-run
python scripts/plate-training.py train --manifest dataset/manifest.json --config configs/plate-training.pilot.yaml --assets model --output results/pilot-resume --resume results/pilot-run/checkpoint.pth
python scripts/plate-training.py evaluate --manifest dataset/manifest.json --plan evaluation-plan.json --model-manifest results/export/model.json --baseline-folder /path/to/baseline-models --output results/evaluation
python scripts/plate-training.py export --manifest dataset/manifest.json --config configs/plate-training.pilot.yaml --assets model --checkpoint results/pilot-run/checkpoint.pth --output results/export
```

Trước khi chạy thật cần xác nhận 32 bbox đáng ngờ và phân loại 71 ảnh trống.
Camera vẫn cần người dùng hoàn thiện 40 frame và xác nhận vùng khóa/thanh.
Gói này hoàn thành bước chuẩn bị/preflight D05c cho subset Roboflow; không phải
nghiệm thu fine-tune, camera công ty, OCR, hoặc độ chính xác tổng quát. D05
tổng thể vẫn đang thực hiện.
