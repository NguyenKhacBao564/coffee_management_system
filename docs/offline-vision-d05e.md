# D05e — review crop và benchmark OCR sau fine-tune

Cập nhật 07/10/2026. Review assets đã tạo từ hai lượt D05d. Đã nhận nhãn
full-frame và chạy benchmark detector/OCR trên CPU; review 22 crop detector
riêng vẫn đang chờ JSON. Không dùng raw OCR làm nhãn.

**Cập nhật sau xác nhận của người dùng trong D05f:** các frame đã xem có đủ
bbox, biển v002 là `49C02655`; 7 transcript `29C02655` được sửa trong bản xử lý
riêng. Hiện có hai chuỗi biển đọc chắc, không phải ba. Sửa thêm tách dòng crop
detector theo `split_y` tuyệt đối. Các số OCR bên dưới là kết quả lịch sử trước
sửa nhãn/code; kết quả hiện tại và giới hạn được ghi trong
[D05f](plate-detector-d05f.md). File nguồn và báo cáo cũ giữ nguyên.

## Trang review local

Server local chỉ bind `127.0.0.1:8765` trong phiên Codex hiện tại:

- Crop detector: [mở review 22 crop](http://127.0.0.1:8765/crop-review/review.html)
- Frame tìm detector miss — công cụ gán nhãn D05b: [mở 61 frame](http://127.0.0.1:8765/missed-frames/label.html)

Trang crop cho từng detection có toàn cảnh với bbox, crop PNG ở đúng pixel gốc,
bản phóng 4×, timestamp media, score, track và video nguồn. Trang không hiển thị
OCR. Có lựa chọn `đúng biển`, `sai vùng`, `cắt thiếu`, `pending`; biển thật có
nhãn bố cục, readable/uncertain/unreadable, text nhập thủ công và ghi chú. JSON
được lưu tạm trong localStorage và tải xuống; CSV cũng tải được. Hãy giữ pending
khi không thể xác nhận qua ảnh.

D05d chỉ lưu tối đa 4 crop evidence/phiên, nên hai thư mục output ban đầu có 8
crop JPEG. Script D05e đã dựng lại toàn bộ 22 prediction từ `plate_observations`
và chính video gốc đã hash: 6 crop ở video `103800–104015`, 16 crop ở video
`073000–073500`. Crop tái tạo là PNG lossless từ frame decoder và bbox D05d,
khớp kích thước đã ghi trong result; source vẫn là video HEVC gốc. 22 crop này
chỉ là những box được pipeline gọi/trả trong phiên ROI và ngân sách lấy mẫu,
không phải toàn bộ frame hoặc toàn bộ biển có thể có trong video.

## Nhãn full-frame để tìm miss

`missed-frames/label.html` là bản làm việc riêng dùng UI/gán nhãn D05b. Giữ
nguyên bộ D05b ban đầu. Bản mới có 61 frame: 40 frame gốc và 21 frame đúng
timestamp của các lần D05d gọi plate detector. Re-run trên vehicle suggestions
của 40 frame gốc tạo 18 proposal trên 13 frame; 27 frame gốc không có proposal;
33/40 frame có vehicle suggestion. 21 frame D05d có vehicle track; 22 proposal
pipeline nằm trên 18 frame, còn 3 lần gọi trả 0 box có frame để rà miss. Gộp hai
nguồn có 40 proposal trên 31/61 frame; 30 frame không có proposal. Proposal là
dự đoán, không phải nhãn. Bảy frame gốc không có vehicle suggestion cũng cần
xem vì detector xe có thể đã bỏ qua xe.

Vẽ bbox của mọi biển thật nhìn thấy trong ảnh gốc, kể cả vùng không có bbox cam.
Đánh dấu `Đã xem frame` sau khi kiểm tra. Chỉ frame đã review mới được tính vào
miss/match; frame trống chưa xem không được coi là âm. Nhãn biển/readability,
layout, split line hai dòng và text phải do người xem xác nhận. Không đưa model
proposal vào annotation.

1. Mở trang crop, chọn trạng thái từng item. Nội dung biển chỉ nhập khi đọc từ
   crop/video bằng mắt và đủ chắc.
2. Mở frame labeler; rà cả 61 frame, gồm ba timestamp D05d không có box, vẽ bbox
   đầy đủ và đánh dấu đã xem. Đây là bằng chứng tìm miss và cho phép benchmark
   crop manual/detector trên đúng frame model đã xử lý.
3. Tải JSON từ cả hai trang về thư mục
   `data/offline-vision/runs/d05e-review-20261007/`; giữ template nguyên vẹn.
   Tên tải mặc định là `d05e-crop-labels.manual.json` và `labels.manual.json`.

## Nhãn full-frame và benchmark

Nhận file `labels.manual (1).json` ngày 07/10/2026, cùng `dataset_id` với
manifest. Bản xuất có 60/61 frame đã review, gồm 106 bbox thủ công: 58 xe và
48 biển. Một frame `v002-f001259` tại media 51s còn chưa review; frame này có
bbox nhưng bị loại khỏi benchmark. Trong 60 frame được tính có 47 bbox biển,
15 nhãn đọc chắc kèm nội dung, 5 chưa chắc, 23 không đọc được và 5 đang pending.
15 nhãn đọc chắc chỉ có ba chuỗi biển khác nhau, lặp qua các frame gần nhau.

JSON trình duyệt đã làm tròn `scene_hash` 64-bit ở cả 61 frame. Bản gốc trong
Downloads được giữ nguyên; bản import local phục hồi riêng trường này từ
`manifest.template.json`, sau khi xác nhận các trường provenance khác khớp.
Trang gán nhãn frame chỉ giữ thay đổi trong phiên trang cho tới khi tải JSON;
không tự lưu nhãn vào file hoặc localStorage.
Bốn bbox biển không đọc được được chọn bố cục hai dòng nhưng thiếu `split_y`;
giữ nguyên bbox/readability và loại riêng khỏi OCR vì không thể tự đoán đường
tách. Chi tiết và SHA-256 nguồn ở `missed-frames/labels.manual.import-notes.json`.

Ghép một-một tại IoU≥0,5 trên 60 frame đã review: **24/47 biển được detector
match (recall chẩn đoán 51,1%)**, 23 bbox biển không match; 16/40 proposal không
match. Có 13 frame đã review không có bbox biển, trong đó 5 proposal không
match. Trên riêng 21 frame D05d thật sự gọi detector: 17/21 bbox match (81,0%),
4 miss và 5/22 proposal không match. Kết quả giữa hai video khác nhau: v001
match 5/9, v002 match 12/12. Ở IoU≥0,75 toàn bộ 60 frame chỉ có 14/47 match;
bbox còn cần căn chỉnh tốt hơn.

OCR chạy trên 37 crop manual và 23 crop detector; exact whole-plate sau chuẩn
hóa trình bày được tính trên nhãn đọc chắc có nội dung (15 crop manual, 14 crop
detector đã match):

| Recognizer | Biến thể | Crop manual | Crop detector |
| --- | --- | ---: | ---: |
| CRNN baseline | Gốc | 0/15 | 0/14 |
| CRNN baseline | Cubic 2× + padding | 0/15 | 0/14 |
| CRNN baseline | CLAHE xám | 0/15 | 0/14 |
| PP-OCRv6 tiny | Gốc | 4/15 | 5/14 |
| PP-OCRv6 tiny | Cubic 2× + padding | 4/15 | 6/14 |
| PP-OCRv6 tiny | CLAHE xám | 4/15 | 3/14 |

Benchmark giữ raw output; không sửa ký tự. Paddle đọc đúng hoàn toàn tốt nhất
6/14 trên crop detector upscale, còn CRNN không khớp toàn biển trong mẫu này.
Đây là chẩn đoán nhỏ, không phải accuracy production: các frame tương quan
theo video/xe và chỉ có ba chuỗi nhãn khác nhau. Mẫu đọc chắc từ v001 chủ yếu
khó hơn và còn miss detector; không đủ dữ liệu độc lập để so sánh tổng quát
chất lượng crop.

Sau khi lưu `labels.manual.json`, chạy:

```bash
edge-agent/.venv/bin/python scripts/offline-vision.py benchmark-ocr \
  --dataset data/offline-vision/runs/d05e-review-20261007/missed-frames \
  --labels data/offline-vision/runs/d05e-review-20261007/missed-frames/labels.manual.import.json \
  --output data/offline-vision/runs/d05e-review-20261007/ocr-benchmark-v2 \
  --model-dir data/offline-vision/models \
  --recognizer-dir data/offline-vision/benchmark-models/paddle-tiny \
  --detector-match-iou 0.5
```

Benchmark chỉ chạy OCR trên frame đã review, bbox manual có layout một/hai dòng
được chọn thực tế. Ghép detector với manual bbox một-một theo IoU≥0,5 trong cùng
frame. Với từng nhãn, chạy cả crop manual và crop detector nếu detector match;
nhãn manual không match được báo là miss, không giả vờ có detector crop tương
ứng. Proposal không match được giữ riêng để người xem rà; chỉ có thể gọi FP sau
khi frame được rà đầy đủ.

Chạy CRNN_EN và PP-OCRv6 tiny qua ba biến thể cố định: gốc, cubic2× + padding,
gray CLAHE. Biến thể áp dụng trước preprocessor riêng của model. CRNN đổi xám,
chuẩn hóa và ép từng dòng về100×32, không giữ tỷ lệ; Paddle giữ BGR/tỷ lệ, resize
cao48, rộng tối thiểu320/tối đa3200, chuẩn hóa rồi pad phải. Tách dòng chỉ theo
nhãn manual. Raw text giữ nguyên; không sửa O/0 hay ký tự để khớp. Exact whole
plate chỉ tính trên nhãn `readable` có text thủ công; confidence của hai model
không so chéo.

Output gồm `summary.json`, `predictions.csv`, các crop OCR PNG và
`detection-matches.csv`; báo riêng recall/miss và OCR trên matched crops. Crop
manual có thể đọc tốt nhưng crop model xấu hướng tới bbox/crop; crop manual rõ
mà cả recognizer đều sai là tín hiệu xem lại OCR. Nếu source gốc khó đọc, cần
xem chất lượng video/góc camera. Hai clip và các frame cùng xe không độc lập,
nên mọi metric chỉ là chẩn đoán trên hai video này.

## Còn chờ

Chưa nhận `d05e-crop-labels.manual.json` từ trang review crop; vì vậy chưa có
số đúng biển/sai vùng/cắt thiếu trên đủ 22 crop. Nhãn frame full-frame cho phép
đánh giá detector và OCR trên crop manual/detector đã match, nhưng chưa thay thế
review trực tiếp toàn bộ crop detector. Chưa có ảnh từ lượt quay hoặc xe độc lập
để nghiệm thu độ ổn định xưởng.

## Tệp tạo trong D05e

- Script: `scripts/d05e-prepare-review.py`.
- UI crop: `edge-agent/offline_vision/d05e_crop_review.html`.
- D05b labeler được mở rộng để vẽ orange model proposals:
  `edge-agent/offline_vision/labeling.html`.
- Benchmark paired manual/detector crop:
  `edge-agent/offline_vision/benchmark.py`, gọi qua `scripts/offline-vision.py`.
- Output local, gitignored: `data/offline-vision/runs/d05e-review-20261007/`.

Không chạy training/GPU, không thay database, D02 hoặc S03.
