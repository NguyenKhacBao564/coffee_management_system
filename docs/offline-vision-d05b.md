# D05b — chẩn đoán và chuẩn bị nhãn thủ công

Ngày 06/10/2026. Công cụ/data preparation hoàn tất; **D05 nhận dạng camera
công ty chưa nghiệm thu**. Không training, thuê GPU, ghi database hoặc đổi
D02/S03. Kết quả camera chưa có ground truth, không có accuracy.

## 1. Video gốc và crop cũ

Hai file đã xác minh trên máy, đều HEVC **1920×1080**:

| Video trong `Video_camera/` | Thời lượng / frame decode | SHA-256 |
| --- | --- | --- |
| `camera_185_20261004_103800-104015.mp4` | 132,281s / 3.300 | `108f1af04ea7a6189323a9ffe4e7543b9388e1e5f3a719d3aca5f204c29dcc0d` |
| `camera_185_20261004_073000-073500.mp4` | 300,681s / 7.493 | `f570db1517f82ebc58079e29a222ac774c21e32ef3cb31b2bc1fd9b175c86eb6` |

Pixel decode giữ nguyên kích thước. PNG giữ nguyên các pixel này; không khôi
phục thông tin đã mất do HEVC/camera. Timestamp lấy media PTS, không suy ra giờ
thực từ tên file/overlay. Chưa có anchor UTC do người vận hành cung cấp.

| Bước | Resize thực tế | Ảnh dùng để crop/OCR |
| --- | --- | --- |
| Xe YOLOX-s | RGB letterbox 640×640 | Bbox đổi về ảnh gốc, crop từ ảnh gốc |
| Biển LPD YuNet | Crop xe ép tỷ lệ vào 320×240 | Bbox đổi về crop xe gốc; resize này có thể làm biển nhỏ/méo ở detector |
| CRNN baseline | Gray, ép mỗi dòng về 100×32 | Crop gốc đi trực tiếp vào adapter, nhưng input model giảm độ phân giải/đổi tỷ lệ |
| Paddle so sánh | BGR cao 48, giữ tỷ lệ, pad phải tối thiểu 320, tối đa 3200px | Không sửa ký tự hoặc ép alphabet |

Crop **130×41** cũ là bbox `[886,603,1016,644]` trên ảnh gốc. Trong lần thử
trước, OCR nhận array slice trực tiếp, không đọc lại JPEG. JPEG cùng kích thước
chỉ để xem; ảnh phóng 4× không đi vào OCR. Với CRNN, 130×41 trở thành 100×32,
và crop chứa cả vùng ngoài biển; chia đôi theo midpoint cũng không bảo đảm hai
dòng thực tế. Đây là nguồn lỗi có thể kiểm tra, chưa đủ để kết luận cần train OCR.

Đối chiếu mới ở `data/offline-vision/diagnostics/crop130x41/`: frame/crop PNG,
ảnh input model và `diagnostic.json`. Seek yêu cầu 104,760s trả frame PTS
**104,720s**; lần thử cũ đã gọi theo mốc yêu cầu, không phải PTS thực. JPEG cũ
so với crop decode cùng frame có PSNR 35,06dB, nhưng không đi qua JPEG trước
inference. Thử single-line chưa có layout thủ công trả CRNN `cuiles`, Paddle
`G`; đây là raw diagnostic, không phải nội dung biển/benchmark có ground truth.

## 2. Bộ 40 frame và gán nhãn

Bộ local: `data/offline-vision/datasets/d05b-camera185/`.

- 20 frame/video; từ 45 + 101 candidate lấy mỗi ~3 giây, chọn theo strata thời
  gian + khác biệt scene dHash + sharpness. Có gần/xa, hướng trước/sau, xe ngoài/
  trong vùng cân và frame bàn cân trống. Đây là mẫu chẩn đoán từ một camera,
  không phải 40 xe độc lập hoặc dataset đại diện toàn hệ thống.
- `frames/*.png`: toàn ảnh gốc 1920×1080; `suggestions/*.png`: crop xe gốc cùng
  origin/bbox. Gợi ý model có `ground_truth:false`. Không chạy OCR để điền nhãn.
- `manifest.template.json`: source SHA/path, PTS/frame index, SHA ảnh, bbox/crop
  gợi ý, camera/model metadata; annotation rỗng. `labels.template.csv`: bảng
  UTF-8 BOM chờ người dùng điền. `v001-contact.jpg` / `v002-contact.jpg` chỉ
  là thumbnail tổng quan, không dùng làm ảnh gán nhãn hoặc input benchmark.
- `label.html`: mở trực tiếp bằng trình duyệt local, giữ cạnh `frames/`.
  Vẽ bbox biển/xe/hard negative; chọn 100%/200% pixel gốc để xem biển nhỏ và
  cuộn trong ảnh. Tọa độ lưu luôn là pixel ảnh gốc `xyxy`, góc phải/dưới exclusive.
- Gán `readable` chỉ khi đọc chắc **toàn biển**; nhập đúng nội dung nhìn được.
  `uncertain`/`unreadable` không làm mẫu accuracy. Chọn layout một/hai dòng;
  với hai dòng, bấm đường tách **giữa hai hàng chữ thực tế** hoặc nhập `split_y`
  tuyệt đối trong ảnh gốc. Không tự chia đôi crop hoặc chép OCR làm ground truth.
- Gán `vehicle_group_id` bằng quan sát thủ công; cùng xe ở nhiều frame/video
  cùng mã. `capture_group_id` là lượt quay, không phải track ID. Sau khi kiểm
  tra đầy đủ, đánh dấu frame đã xem. Không có biển thì để annotation rỗng và
  đánh dấu đã xem. Bbox sai xóa/vẽ lại. Lưu JSON thường xuyên; trang không tự
  lưu khi đóng/reload. “Nạp JSON đã lưu” để tiếp tục.

Tạo bộ mới (CLI không ghi đè output có sẵn):

```bash
edge-agent/.venv/bin/python scripts/offline-vision.py prepare-labels \
  --video Video_camera/camera_185_20261004_103800-104015.mp4 \
  --video Video_camera/camera_185_20261004_073000-073500.mp4 \
  --count 40 --candidate-interval 3 \
  --output data/offline-vision/datasets/camera185-review-v2
```

Lưu `labels.manual.json` tải từ biểu mẫu vào folder bộ ảnh. Hoặc điền CSV
(nhân một dòng nếu một frame có nhiều bbox), rồi import:

```bash
edge-agent/.venv/bin/python scripts/offline-vision.py import-labels \
  --dataset data/offline-vision/datasets/d05b-camera185 \
  --csv data/offline-vision/datasets/d05b-camera185/labels.manual.csv \
  --output data/offline-vision/datasets/d05b-camera185/labels.manual.json
```

## 3. Benchmark OCR

CRNN_EN hiện có giữ làm baseline. Recognizer so sánh là
[PP-OCRv6 tiny ONNX chính thức](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_rec_onnx/blob/2612ab37152ae0a677521bae4e1e3d4fb4cf7c30/README.md),
revision `2612ab37152ae0a677521bae4e1e3d4fb4cf7c30`; weights 4.462.639 byte,
model card khai báo Apache-2.0. Config/vocab/input shape/checksum đã kiểm tra,
có Latin/số/Đ. CPU ONNX Runtime 1.23.2, PyYAML 6.0.3; adapter preprocess/CTC
tham khảo PaddleX pin riêng. Đây là recognizer văn bản, chưa xác nhận chất
lượng biển Việt Nam. Code/weights/version và attribution trong
`edge-agent/THIRD-PARTY-NOTICES.md`; không dùng giấy phép wrapper thay weights.

```bash
# Chỉ cần ở máy chưa có: venv offline, không cài vào backend.
uv pip install --python edge-agent/.venv/bin/python -r edge-agent/requirements-benchmark.txt
edge-agent/.venv/bin/python scripts/offline-vision.py fetch-benchmark-model

edge-agent/.venv/bin/python scripts/offline-vision.py benchmark-ocr \
  --dataset data/offline-vision/datasets/d05b-camera185 \
  --labels data/offline-vision/datasets/d05b-camera185/labels.manual.json \
  --output data/offline-vision/benchmarks/d05b-manual-v1
```

Ba biến thể cố định: crop gốc, cubic 2× + padding nhỏ, gray CLAHE clip 2/grid
4×4. Tách dòng theo nhãn thực trước preprocessing, chạy từng dòng rồi ghép raw
bằng newline. Cả hai model dùng cùng crop/biến thể. Giữ raw/raw_lines/score,
crop PNG, expected thủ công, thời gian và metadata trong JSON/CSV. Confidence
giữ riêng theo model; không dùng để cộng/so như một thang đo chung.

Metric là **đúng toàn biển** trên những crop `readable` đã xem, sau chuẩn hóa
trình bày uppercase + bỏ whitespace/dấu chấm/gạch ngang; có thêm strict raw
exact match. Không đổi O/0, I/1, B/8, đoán phần thiếu, chọn biến thể tốt nhất
từng ảnh hoặc tính độ chính xác end-to-end từ crop thủ công. Báo từng model/
biến thể và mẫu số; đây chỉ là bộ chẩn đoán nhỏ, cùng xe nhiều ảnh không độc lập.

**Hiện tại:** 0 frame reviewed, 0 readable ground truth. Đã chạy với template,
output `data/offline-vision/benchmarks/d05b-pending-final/`: bảng chờ điền,
`metrics:[]`, accuracy null, không chạy inference. Test fixture riêng kiểm tra
đường gán nhãn → CSV import → hai model/ba biến thể; không đưa vào kết quả camera.

## 4. Chọn crop và ngân sách OCR phiên

Pipeline v0.2.0 dùng `sampling.py`, giữ tối đa 4 PNG candidate/giai đoạn/phiên
(config giới hạn 1–12). Các giai đoạn mặc định là tuổi phiên **[0,8), [8,20),
[20,∞) giây media**; đây không phải suy luận xe đang vào/đứng/rời cân.

- Detector giữ cumulative budget 25%/50%/100%; thời gian giữa các lần thử
  muộn tăng dần đến 4× khoảng gốc. Với 12 attempts/3s, còn lượt cho frame muộn.
- Crop có đủ kích thước, geometry hợp lý, sharpness và điểm chất lượng được
  giữ theo pool; gần nhau <6s và dHash distance ≤2 giảm lặp, có thể thay bằng
  crop tốt hơn >10%. Geometry/sharpness là heuristic, có thể bỏ nhầm biển thật;
  log giữ bbox/reason để kiểm tra, không dùng chúng làm nhãn.
- **Đọc hết clip rồi mới OCR** từ pool lossless: quota neural calls 25%/25%/
  phần còn lại; luân phiên ưu tiên muộn/giữa/sớm, sau đó dùng quota thừa.
  Giữ khoảng cách media tối thiểu và giảm crop gần giống nhau. Hai dòng vẫn
  tính 2 calls, tối đa 8 calls/4 crop evidence theo config hiện có.
- Consensus vẫn cần ít nhất 3 thời điểm nhất quán và ratio ≥0,8. Không đủ thì
  unknown, giữ raw/candidates/ảnh. OCR auto trong `run` còn heuristic midpoint;
  benchmark dùng layout thủ công. Pool dọn sau run, không resize/JPEG roundtrip
  trước OCR. Chính sách deferred này chỉ dành offline; RTSP cần thiết kế riêng.

Lượt chẩn đoán hạ **plate threshold 0,25** ở file local riêng
`data/d05b-work/camera-185-diagnostic.json`; config camera đã có vẫn 0,75.
Hạ threshold giúp kiểm tra lỗi, không coi tất cả box là biển thật.

| Video / output `data/offline-vision/runs/` | Xe: frame có box / tổng box / track | Plate calls / box ứng viên | OCR observations / neural calls | ROI / proposal / unknown |
| --- | --- | --- | --- | --- |
| `camera-185-d05b-video1` | 184 / 195 / 6 | 9 / 9 | 3 / 6 | 1 / 0 / 1 |
| `camera-185-d05b-video2` | 511 / 523 / 6 | 12 / 8 | 7 / 8 | 1 / 0 / 1 |

Video 1 OCR đã lấy cả media 104,000s, thay vì hết lượt ở ~69–74s như thử cũ;
crop còn hẹp, raw mâu thuẫn. Video 2 thử OCR từ 140,000 đến 186,520s, không chỉ
đầu phiên; proposal vẫn null. “Box ứng viên” chưa được đối chiếu bbox thủ công,
6 track không phải 6 xe, gap/EOF không tự chứng minh xe rời. Đọc đúng toàn biển
và accuracy cả hai run vẫn null. Ảnh/HTML/raw giúp người dùng xác nhận.

## 5. Khảo sát dữ liệu Việt Nam — chưa tải archive

Chỉ khảo sát VNLP và **một nguồn bổ sung**; kiểm tra ngày 06/10/2026:

| Nguồn / phiên bản | Ảnh và nhãn | Dung lượng xác minh | Mức phù hợp / điều khoản |
| --- | --- | --- | --- |
| [VNLP của fict-labs](https://github.com/fict-labs/VNLP), commit `d0b38df15c961393a7a1189912476c3d8d1edbfc` | Khoảng 37.300 ảnh, nhãn bbox biển + ký tự; 19.086 một dòng / 18.211 hai dòng. Biển kích thước đa dạng, có cả nhỏ/biến dạng. Cần kiểm tra cấu trúc archive và annotation thực trước chuyển đổi. | Metadata [Drive công khai](https://drive.google.com/drive/folders/19OnlE0gFXEMPyngxRZ980d4z0fGQ-C7T) hiển thị `VNLP_detection.zip` **3,45 GB**; mục storage used 6,48 GB không phải kích thước tải zip. Không xác nhận đủ archive OCR từ listing này. | Có layout Việt Nam phù hợp kiểm tra một/hai dòng; chưa có breakdown xe tải/container hoặc camera bàn cân. README cho tải miễn phí, yêu cầu trích dẫn; không thấy LICENSE/điều khoản cấp quyền thương mại rõ. Cần xác nhận với tác giả trước sử dụng thương mại. |
| [winter2897: Vietnamese Plate Dataset](https://github.com/winter2897/Real-time-Auto-License-Plate-Recognition-with-Jetson-Nano/blob/main/doc/dataset.md), commit `8741a28a1f4d4ebefa00b4908b374f2c849cb8e7` | Nhánh ảnh detection bbox biển VOC/Pascal và YOLO; nhánh OCR là bbox/class ký tự, cần kiểm tra thứ tự/tạo transcription chứ không giả định có text label. Có video đường phố minh họa, ghi nguồn một phần từ Mì AI. | Tên archive Drive `yolo_plate_dataset.zip`, `yolo_plate_ocr_dataset.zip` xác nhận bằng HTML metadata; dung lượng/số ảnh **chưa xác minh**, tài liệu không nêu. Không tải zip. | Chưa có thống kê xe tải/container; domain đường phố cần đối chiếu góc nhìn bàn cân. Không thấy giấy phép dataset/thương mại rõ; ghi nhận nguồn chưa đủ thay cho cấp quyền sử dụng. |

Không áp dụng số accuracy/FPS do tác giả công bố vào MacBook/camera công ty.
Trong bước này chỉ đọc tài liệu/metadata, chưa dùng dataset ngoài để training.

## 6. Kế hoạch dữ liệu và fine-tune detector trước

1. Người dùng gán bbox biển **đủ cả hai dòng**, readable/text/layout và xe trên
   40 ảnh. Gán riêng khóa cửa, thanh container, nhãn/chữ container, đèn, cạnh
   bàn cân xanh, vạch/sơn tương phản làm `hard_negative`; giữ ảnh không có xe/
   không có biển. Hard negative là vùng không phải biển, không phải class xe.
2. Đánh giá detector trên bbox thủ công: recall/precision ở IoU/ngưỡng cố định,
   phân loại miss/crop hẹp/khóa giả theo khoảng cách/độ lớn/hướng. Đánh giá OCR
   trên **crop thủ công** riêng với crop detector: đúng crop nhưng đọc sai mới
   là bằng chứng mạnh cho thay/fine-tune recognizer. Chưa có metric detector
   tự động cho bộ D05b vì bbox GT còn trống.
3. Thu thêm xe/lượt quay độc lập, ngày/đêm/mờ/che khuất, cân thật; quyền sử dụng
   rõ. Chọn detector trainable với giấy phép code/weights phù hợp, một class
   plate, có cả hai layout và hard negatives, đầu vào đủ giữ biển nhỏ. Khóa
   model/preprocess, pilot ngắn và evaluation trước khi xin tài nguyên training
   dài. Không quyết định fine-tune OCR chỉ từ một xe hay raw sai trên crop hẹp.
4. Chia theo **xe và capture group**, không random từng frame/crop. Video liên
   tục và cùng xe ở nhiều clip không được xuyên train/val/test; không dùng OCR
   hoặc track ID làm group. Audit giữ mỗi source clip nguyên một split ngay cả
   khi capture label bị đổi. Hai clip chưa đủ split đại diện độc lập.
5. Trước training chạy audit; exact PNG xuyên split bị chặn. Scene dHash chứa
   nền cố định nên chỉ là cờ nghi trùng; xem thủ công các cặp, cùng observation
   phải cùng split. Nếu thực sự khác thì ghi `duplicate_reviews` với
   `sample_ids:[id1,id2]`, `resolution:"reviewed_different_observations"`.
   Không lấy crop/augmentation của test vào train; chia trước augmentation.

```bash
edge-agent/.venv/bin/python scripts/offline-vision.py audit-labels \
  --dataset data/offline-vision/datasets/d05b-camera185 \
  --labels data/offline-vision/datasets/d05b-camera185/labels.manual.json \
  --output data/offline-vision/datasets/d05b-camera185/audit-manual-v1.json
```

Audit hiện tại: **0 exact PNG**, **140 cặp scene-dHash suspect**, chưa gán nhãn/
chia tập, `training_ready:false`. Không tự xóa ảnh. `training_ready` sau này
chỉ xác nhận các quy tắc audit, không chứng minh đủ số xe hoặc chất lượng nhãn.

Sau khi có nhãn/metric mới xem xét reviewer giao diện và RTSP ở task riêng.
Không nối ảnh/biển với signal hoặc tự tạo/sửa lượt cân/giao dịch D02.
