# D05f — fine-tune detector lần hai với camera đã xác nhận

Cập nhật 07/10/2026. Đã chạy lần train có giới hạn trên instance Vast
54567374, tải model/bằng chứng về Mac và đối chiếu hash. Chưa nghiệm thu chất
lượng camera tổng thể; model D05d vẫn là baseline. Không fine-tune OCR, không
ghi database hoặc sửa D02/S03.

**Điều chỉnh hướng tiếp theo theo phản hồi người dùng:** khảo sát nguồn ảnh,
thu nhiều lượt xe và đánh giá crop tự động/ROI + consensus theo lượt, rồi gợi
ý top-k có người xác nhận. S03b/D06/D07 được ưu tiên; kết quả 10/22 không đủ
chọn fine-tune tiếp. Kế hoạch và mẫu số trong
[camera-vehicle-evaluation-plan.md](camera-vehicle-evaluation-plan.md).

## Nhãn và nguồn dữ liệu

- Giữ nguyên `Downloads/labels.manual (1).json`, SHA-256
  `fdfe668dc83fa10740e048baf0333c6e35cb53ed14c9a402635b1122f241f792`.
- Người dùng xác nhận các frame đã xem đã vẽ đủ biển nhìn thấy, các frame
  v002 ở 152–198,52 giây là cùng xe, biển đúng là **49C02655**. Bản xử lý
  `data/offline-vision/training/d05f-review-20261007/labels.confirmed.json`
  sửa riêng 7 transcript `29C02655` thành `49C02655`, ghi provenance trong
  `user-confirmations.json`. Không suy ra chữ từ OCR.
- 60/61 frame được xác nhận đầy đủ; 47 bbox biển được sử dụng để chuẩn bị.
  `v002-f001259` ở media 51 giây vẫn pending và bị loại. Bbox xe chỉ dùng
  tạo crop/thử inference; class train duy nhất là `license_plate`.
- 22 crop D05e vẫn chưa có JSON review: `video1-finetuned-001…006` và
  `video2-finetuned-001…016`. Không dùng các proposal này làm hard negatives.
  Danh sách đầy đủ: `frame-review-needed.csv`, `crop-review-needed.csv` và
  `review-status.confirmed.json` trong thư mục nhãn D05f.
- Frame được xác nhận đầy đủ và không có bbox biển được dùng làm mẫu âm.
  Chưa có vùng khóa/thanh container được xác nhận riêng, nên chưa có số đo
  false positive chuyên biệt trên các vùng đó. Nhãn hard negative có giao
  với biển thật bị từ chối; không biến frame thiếu nhãn thành ảnh âm.
- `scene_hash` được nhúng, xuất và nhập dưới dạng chuỗi thập phân uint64.
  Các giá trị cũ bị JavaScript làm tròn được phục hồi từ manifest gốc sau
  đối chiếu provenance; không làm tròn ngược để đoán hash. Kiểm thử Node thực
  tế bao phủ 2^53+1, 2^63+7 và 2^64−1, từ chối hash bị đổi.

Review tiếp bằng công cụ hiện có:

- [Frame đã xác nhận](http://127.0.0.1:8765/missed-frames/label.d05f.confirmed.html).
  Đây là trang mới; trang đang làm việc trước đó được giữ nguyên.
- [22 crop còn pending](http://127.0.0.1:8765/crop-review/review.html).

## Split và giới hạn chống leakage

Giữ nguyên public train/val/test đã audit trong D05c. Toàn bộ v002 dùng train,
v001 giữ lại để kiểm tra. Không có camera validation: chọn checkpoint bằng
147 ảnh validation công khai. Gộp quan sát xe trong mỗi clip thành cohort
bảo thủ (`capture-cohort:v001/v002`); đây không phải tuyên bố mọi xe không đọc
được đều cùng danh tính. Hai biển đọc chắc thuộc hai capture khác nhau.

Audit hash ảnh gốc và ảnh dẫn xuất phát hiện 22 cặp nghi gần trùng qua split.
Loại bảo thủ **10 frame train v002 và toàn bộ biến thể của chúng** khỏi bản
train, giữ nguyên ảnh/nhãn nguồn và tập test. Quy tắc loại dựa trên hash trước
train, không dựa trên metric test. Danh sách và cặp nghi trùng lưu trong manifest.
Nền xưởng tĩnh có thể tạo nghi vấn perceptual hash; không tự khẳng định đó là
cùng xe. Ảnh gần nhau trong cùng capture vẫn cùng split.

Không có ID xe/lượt quay gốc của ảnh công khai; hash không chứng minh đã chống
leakage theo xe hoàn toàn. v001 đã được xem trong D05e, nên đây là nhóm không
đưa vào lần train này, **không phải test camera mù mới**. Chỉ hai capture,
chưa đủ để chia ba tập camera hoặc báo độ chính xác tổng quát.

| Split | Ảnh lưu | Bbox biển | Ảnh âm | Camera | Nhóm camera |
| --- | ---: | ---: | ---: | ---: | --- |
| Train | 581 | 575 | 6 | 42 | v002: 21 frame, ảnh gốc/crop xe |
| Validation | 147 | 147 | 0 | 0 | Không có |
| Test | 104 | 97 | 7 | 29 | v001: 29 frame, 22 biển |

Public train 539 / val 147 / test 75; camera train có 42 file dẫn xuất từ 21 frame.
Mỗi epoch chọn **một** biến thể full frame hoặc crop xe của mỗi frame, không
lặp parent: 539+21=560 lượt đọc, **280 batch**, batch 2, `drop_last=false`, batch
cuối đủ2. Camera chiếm3,75%, có cap 20% và không replacement. Ba epoch hoàn tất
đọc21 camera/epoch; phần epoch4 đọc15 camera. Tổng1.000 step/2.000 lượt đọc.
Augmentation không tăng số lần đọc.

Manifest/contact sheets:
`data/offline-vision/training/d05f-ready-20261007/`.

## Cấu hình, preflight và train thực tế

- YOLOX-Nano Apache-2.0, revision
  `6ddff4824372906469a7fae2dc3206c7aa4bbaee`; dataset Roboflow v1
  [biển số xe](https://universe.roboflow.com/datacar-my0w7/bien-so-xe-3w699-avdfe/dataset/1),
  CC-BY-4.0 theo nguồn D05c; attribution/license giữ trong gói.
- Init D05d best SHA-256:
  `a5fce8d542a0c438f6b162801f0b043a82246a89b20e2935b3ac5a8fd9d019d7`.
  Nạp642 key strict, bỏ0; không tái dùng optimizer/scheduler D05d.
- Python 3.12.3, PyTorch 2.8.0+cu126/torchvision 0.23.0+cu126, RTX 3090 Ti 24 GB,
  driver 550.163.01; venv riêng đã có từ D05d, không đổi driver.
- Seed 20261007, input 640, batch 2, LR 1e-5 giữ nguyên D05d, SGD momentum.9,
  cosine1.000 step. Không flip/mosaic/mixup. Brightness.85–1.15(p=.3),
  blur3×3(p=.15), downsample.8–1(p=.2); bbox không đổi.
- Giới hạn6 epoch /1.000 step /7.200 giây toàn wrapper /3attempt; tmux giữ job
  khi mất SSH. Lần thực tế chỉ1attempt, không cần restart. `last.pth` lưu cả
  optimizer, scheduler, RNG và cursor; resume kiểm hash data/config/policy/init.
- CPU camera smoke2 step/resume trên Mac đạt, loss hữu hạn; CUDA camera
  smoke2 step/resume và mixed smoke2 step/resume đạt. Camera smoke dùng cùng
  parent full/crop để thử hai dạng input, không phải sampler của train chính.
- Train dừng đúng1.000 step: **3 epoch đầy đủ +160 batch epoch4**, 61,61 giây;
  trung bình.05246 giây/batch, peak CUDA allocated519.184.896 byte (~495 MiB),
  không phải toàn bộ VRAM process/driver. Epoch hữu hạn đủ280 batch.
- Validation epoch 1/2/3 match145/145/146 trên147 bbox. Chọn **epoch3 step840**
  theo recall rồi số unmatched; `last` ởstep 1.000 không được chọn bằng test.
  Frozen confidence.25, NMS 0.45, matchIoU.5 ghi trước khi mở test.
- Public test sau chọn:75/75 bbox match,1unmatched theo nhãn nguồn; nhãn công
  khai chưa được rà đầy đủ nên không gọi unmatched đó là FP đã xác nhận.

## ONNX và kiểm chứng số học

Model giao là `final/export/model.json` và `detector.onnx`, FP32/opset 11,
đầu vào BGR640/top-left letterbox114, output `[1,8400,6]`; interface D05a giữ nguyên.

Export mặc định gộp BatchNorm lệch.068054 pixel và.0001443 probability trên
input xuất. Giữ BatchNorm và tắt ORT graph optimization giảm sai lệch input
đó xuống.034302 pixel/.00003955, trong giới hạn cũ.05 pixel/1e-4; detector đọc
thiết lập này từ metadata. Không sửa weights checkpoint, không nới tolerance.
Thử fuse PyTorch cũng được lưu lại nhưng không chọn vì không đạt kiểm tra.

Phải phân biệt bằng chứng:

- Tensor thô trên8 input public/camera train/val:7/8 đạt tọa độ.05 pixel;
  một anchor nền ở ảnh validation lệch.056152 pixel. Probability của8 input
  đều đạt1e-4. **Chưa đạt parity toàn tensor mở rộng.**
- Mọi anchor vượt confidence.25 trên8 input có chỉ số giống nhau và tọa độ/
  probability đạt giới hạn. Không dùng test để chọn checkpoint/ngưỡng.
- Detection thực tế sau confidence/NMS/clip ảnh: **104/104 ảnh test khớp**
  số bbox và tọa độ/score, max lệch native.001617 pixel/score.000002265.
  Đây là parity đầu ra detector đã hậu xử lý, không chứng minh toàn tensor
  raw giống nhau. Log thất bại và các phép thử vẫn giữ trong `results/`.

Khoảng khác biệt FP32 khi thay thứ tự phép toán được mô tả trong
[PyTorch numerical accuracy](https://docs.pytorch.org/docs/main/notes/numerical_accuracy.html);
thiết lập optimization dùng [ONNX Runtime](https://onnxruntime.ai/docs/performance/graph-optimizations).
Nguyên nhân cụ thể ở đây dựa trên phép thử gộp/giữ BatchNorm, không chỉ tài liệu.

## So sánh camera trên cùng input

v001:29 frame hoàn chỉnh,22 bbox biển,7 frame âm. Threshold/IoU cố định từ
public validation; không chỉnh qua kết quả camera.

| Input | Model | Match /22 | Miss | FP xác nhận | Mean GT coverage | Crop phủ≥95% GT |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full1920×1080 →640 | D05d | 0 | 22 | 1 | — | 0 |
| Full1920×1080 →640 | D05f | 0 | 22 | 1 | — | 0 |
| Cùng bbox xe thủ công | D05d | 7 | 15 | 4 | 84,54% | 1/7 |
| Cùng bbox xe thủ công | D05f | 10 | 12 | 5 | 82,82% | 0/10 |

Group report `camera-source:v001|capture-cohort:v001` chứa toàn bộ29 frame;
không coi29 frame là29xe độc lập. FP chỉ trên frame người dùng xác nhận đủ.
Coverage là proxy cho bbox/crop thiếu, không thay22 crop pending thành nhãn
“cắt thiếu” do con người xác nhận. Những GT khó/khác nhau giữa nhóm match làm
mean coverage không phải phép so sánh crop ghép cặp hoàn toàn.

Input full làm biển chỉ cao3–9,67 pixel sau resize640 (median6;36/47 bbox dưới8).
Crop xe thủ công đưa chiều cao về18,5–53,33 pixel (median33,59). Đây là thử
oracle bbox xe, chưa đánh giá độ chính xác detector xe tự động. Runtime trên
Mac: median inference ~35–36 ms/frame/crop ở các phép so sánh, không suy ra GPU
hoặc server cloud.

Chạy thêm pipeline D05a với ROI/budget hiện có trên hai video gốc, không đưa
nhãn vào runtime:

| Video | D05d plate calls / boxes | D05f calls / boxes | D05f wall | CPU process | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 103800–104015 | 9 /6 | 9 /7 | 33,96 s | 156,28 CPU-s | ~725 MiB |
| 073000–073500 | 12 /16 | 12 /15 | 74,78 s | 321,36 CPU-s | ~796 MiB |

Budget sampling/ROI không quét mọi frame. Video2 có dữ liệu train; số proposal
không phải recall/accuracy. OCR runtime cũ CRNN vẫn unknown; giữ nguyên quyết
định unknown, không nối signal/D02.

## OCR: tách lỗi nhãn, crop và recognizer

Benchmark D05b được tái dùng. Sửa lỗi tách hai dòng trên detector crop: dùng
cùng `split_y` tuyệt đối của ảnh gốc, không dịch theo tỷ lệ bbox. Biên nằm
ngoài crop thì bỏ phép OCR tương ứng, không bịa đường phân dòng.

PP-OCRv6 tiny giữ cùng weights/preprocessing ở D05d và D05f: tách dòng thủ
công, BGR, resize cao48 giữ tỷ lệ, rộng tối thiểu320/tối đa3200, normalize rồi
padding phải bằng0. Ba biến thể cố định: gốc, cubic2×+border replicate, gray
CLAHE. Không sửa O/0 hoặc ký tự để khớp nhãn. Raw/chuỗi chuẩn hóa/score giữ riêng.

Nhóm v001 giữ lại chỉ có2 frame đọc chắc, cùng biển29K52755:

- PP-OCRv6 tiny: **0/2** manual và **0/2** detector, cả ba biến thể, cả D05d/D05f.
- English PP-OCRv5 mobile chẩn đoán: manual upscale **1/2**; detector D05d
  upscale **0/2**, D05f upscale **1/2**. Gốc/CLAHE đều0/2. Không chọn detector
  checkpoint hay ngưỡng bằng kết quả OCR.

Trên toàn bộ15nhãn đã sửa theo người dùng, benchmark chẩn đoán proposal D05d
cũ: CRNN0/15manual và0/14detector; PPv6tiny tốt nhất8/15manual và8/14detector;
Englishv5 tốt nhất12/15manual và13/14detector. Các biến thể khác nhau được báo
riêng, không oracle chọn prediction theo ground truth. Hai chuỗi biển lặp,
không phải accuracy độc lập. Kết quả D05e trước sửa nhãn giữ là lịch sử.

Nguồn English:
[PaddlePaddle en_PP-OCRv5_mobile_rec_onnx](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec_onnx/tree/3fafbc3b5dcf93dd72add9f48368be8a3a2cd33b),
revision `3fafbc3b5dcf93dd72add9f48368be8a3a2cd33b`, Apache-2.0,
weights7.848.423 byte SHA-256
`b5f833dfc5d0eb71da397b4efa06ebeee9b431b690a47d6af40d77d8eabc557f`.
Preprocessing đối chiếu config và
[PaddleX chính thức](https://raw.githubusercontent.com/PaddlePaddle/PaddleX/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/text_recognition/processors.py).

Lỗi còn lại tập trung hàng trên biển hai dòng29K: crop thủ công tốt nhất vẫn
chỉ1/2 ở recognizer Latin, PPv6 hay xuất chữ ngoài Latin; source native nhỏ/mờ.
Upscale không khôi phục chi tiết đã mất. Chưa có bằng chứng để fine-tune OCR
bằng hai chuỗi lặp. Cần thêm xe/lượt quay, góc/ánh sáng và nhãn đọc chắc; crop
đủ cả hai dòng và recognizer Latin là hướng thử tiếp, không đoán chữ bị mất.

## Artifacts, hash và lệnh

Local root `data/offline-vision/runs/d05f-vast-54567374/`:

- `final/best.pth`, `last.pth`, `export/model.json`, `export/detector.onnx`,
  configs/SHA256SUMS. Best SHA
  `f0b6c1efec55aa4395c2fd81d2f9d00fba7e7ea81c53b59542352c96469d368d`;
  ONNX SHA `5233aa1b66331feeac6fb1f04e8cf7b5c5104ef1f04578798f3fd0386388794c`.
- `results/train/`: run/log/metrics/checkpoints; `results/test.json`,
  frozen selection, export/failed parity diagnostics.
- `artifact-verification.json`: 22 file kết quả và 12 file preflight từ remote
  khớp hash, tổng 34 file, thiếu 0/sai 0; kiểm tra lại sau bàn giao GPU rảnh.
- `full_native_frame/`, `manual_vehicle_crop/`: kế hoạch hash cố định,
  metrics theo group, toàn cảnh bbox và native PNG crop.
- `ocr-camera-heldout/`, `ocr-camera-heldout-latin/`: CSV/JSON/raw và trang
  ảnh-nhãn-prediction; `video1/`, `video2/` là run offline đầy đủ.
- [Review trước/sau và OCR](http://127.0.0.1:8766/review.html).

Gói thực tế upload/train: `d05f-second-train.zip`, SHA
`d72a852369c7e385c67430977af6e9b3b5a9c111952a2b752320b12e5a0dba2c`.
Manifest portable SHA
`81912565dd8704f60759f98aa0a58c2f2c58287bad4e88d2a7cd32590a38a860`.
Sửa export sau train được lưu riêng `results/export-patch.json`; không đổi
data/config/init hoặc train lại. Gói tái hiện chứa sửa export:
`data/offline-vision/training-packages/d05f-second-train-v2.zip`, SHA
`b670efc022d0e4f132053efd93ef8375a0780baeeb98bf296d20704be2c7be01`.
Gói gốc và nhãn gốc giữ nguyên; v2 không chứa secrets/dữ liệu ứng dụng.

Lệnh preflight/train/resume/export có trong README gói; wrapper dùng timeout/
tmux và không tự thuê instance. Trên Mac:

```bash
edge-agent/.venv/bin/python scripts/d05f-ocr-compare.py \
  --dataset data/offline-vision/runs/d05e-review-20261007/missed-frames \
  --labels data/offline-vision/training/d05f-review-20261007/labels.confirmed.json \
  --comparison data/offline-vision/runs/d05f-vast-54567374/manual_vehicle_crop/comparison.json \
  --recognizer-dir data/offline-vision/benchmark-models/paddle-tiny \
  --output data/offline-vision/runs/d05f-ocr-recheck
```

89 kiểm thử edge-agent đạt trên môi trường training local (một warning fixture
ZIP có tên trùng có chủ đích). Có thể dừng instance sau tải/hash artifacts;
không tự stop/destroy. Cần hoàn tất1 frame/22 crop pending và bổ sung các nhóm
camera mới, hard negatives xác nhận trước lần train sau. Bounded D05f đã chạy,
nhận dạng xưởng/OCR và toàn tensor ONNX mở rộng chưa được nghiệm thu.
