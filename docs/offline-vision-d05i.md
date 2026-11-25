# D05i — OCR trên crop camera: Phase 1–3

Cập nhật 07/10/2026. Thực hiện theo yêu cầu D05i mới, giữ ưu tiên toàn dự án
S03b → D06 → D07. Phase 1 đã bàn giao và nhận CSV người dùng; **Phase 2 đã
benchmark trên CPU, giữ kết quả khóa.** Phase 3 đã chạy theo chỉ đạo tiếp
ngày 07/10/2026; dừng bàn giao Phase 3 và chuẩn bị D05j. Phase 4 chưa làm.
Phần Phase 1 dưới đây giữ
số liệu tại thời điểm bàn giao; kết quả sau import ở phần Phase 2.

## Phạm vi và số liệu thực tế

| Nội dung | Số lượng |
| --- | ---: |
| Crop native sau gộp cùng frame/bbox/loại crop | 88 |
| Crop từ bbox thủ công đã xác nhận | 47 |
| Crop detector khớp bbox đã xác nhận | 41 |
| Frame có bbox biển đã xác nhận | 47 |
| Lượt quay/capture | 2 |
| Chuỗi biển khác nhau có transcript xác nhận trước đó | 2 |
| Bbox chưa có transcript đọc chắc | 32/47 |
| Nhãn khả năng đọc crop mới | 0/88 đã gán; 88 pending |

- Manual bbox từ `labels.confirmed.json` D05f, chỉ frame reviewed và
  `annotations_complete=true`; bbox xe không phải crop biển mục tiêu.
- Detector crop lấy từ proposals D05e đối chiếu IoU ≥ 0,5 một-một với bbox
  thủ công, và các matches trong hai báo cáo so sánh D05f đã lưu. Khớp bbox
  không xác nhận crop đủ chữ hoặc đọc được; đây là điều người dùng review.
- D05f dùng cả baseline D05d và model mới; reference giữ model, nguồn/hash,
  bbox float/IoU và score nếu nguồn có. Không tạo score cho match không lưu nó.
- Gộp cùng frame/annotation/loại crop/bbox native; giữ mọi reference. Những
  crop khác nhau của cùng frame vẫn tương quan, không tính là lượt xe độc lập.
- Không đưa 22 detector crop D05e chưa review hoặc frame `v002-f001259` chưa
  xác nhận đủ bbox vào bộ đã xác nhận. Danh sách loại trừ nằm trong summary.
- Hai chuỗi xác nhận là số chuỗi biết được, không phải tổng số xe/biển thật;
  không đoán danh tính cho bbox chưa có nội dung. Nhãn mới không kế thừa
  readability từ frame và không dùng OCR làm ground truth.

## Trang review và cách bàn giao nhãn

**Trang local:** [D05i crop readability](http://127.0.0.1:8767/review.html).
Server chỉ bind `127.0.0.1`; các trang 8765/8766 được giữ nguyên.

Tái sử dụng template/cấu trúc giao diện crop-review D05e với mode D05i:

1. Xem crop native và ảnh nearest-neighbor đúng **8×**, không làm mượt.
   Đánh giá chính thông tin trong crop; không suy chữ từ biển đã biết hoặc
   ảnh khác. Toàn cảnh có bbox chỉ để định vị, mặc định thu gọn.
2. Chọn `readable_full`, `readable_partial` hoặc `unreadable`; chưa xem thì
   giữ `pending`. Với crop đọc được, xác nhận bố cục và dòng đọc chắc.
   Biển hai dòng đọc toàn bộ chọn cả trên/dưới; một dòng chọn single.
3. Có thể nhập riêng toàn biển/dòng trên/dòng dưới nếu nhìn chắc. Không điền
   phần chưa chắc. Transcript từng dòng không có thì metric dòng đó phải
   báo thiếu ground truth, không tự tách chuỗi biển cũ để làm nhãn mới.
4. Layout/split y có gợi ý từ nhãn thủ công trước; split theo pixel crop gốc,
   cho phép sửa hoặc để trống. Thiếu split hợp lệ phải được báo khi phase
   sau so sánh tách dòng; không dùng nội dung mong đợi để đặt split.
5. Nhãn lưu localStorage theo fingerprint dataset, có xuất JSON/CSV và nạp
   JSON. Bản nháp chưa đủ chi tiết vẫn được giữ khi reload. JSON xuất chỉ
   nhận trạng thái hợp lệ; pending được giữ. Xuất file
   **`d05i-readability.manual.json`** và chuyển file/path cho Codex.

JSON có crop/frame/capture, timestamp media, source image/hash, bbox, crop
hash, `scene_hash` chuỗi uint64, references và thời gian người review chỉnh/
xuất. Import từ chối đổi inventory, nguồn, bbox, hash hoặc metadata; giữ
nhãn nguồn nguyên vẹn và ghi hash/path file người dùng trong provenance riêng.
Không có request gửi ảnh ra dịch vụ ngoài hoặc API ứng dụng.

Root kết quả: `data/offline-vision/runs/d05i-readability-20261007/`:
`crop-review.template.json`, `summary.json`, `verification.json`,
`review.html`, `crop-readability.js`, `crops/`, `zoom8/`, `contexts/`.
Ảnh và nhãn nằm dưới `data/` đã gitignore; không commit.

## Lệnh đã chạy

Từ repository `/Users/nguyen_bao/Documents/ChatGPT/nhu-tung-demo`:

```bash
edge-agent/.venv-training/bin/python scripts/d05i-crop-review.py prepare \
  --dataset data/offline-vision/runs/d05e-review-20261007/missed-frames \
  --labels data/offline-vision/training/d05f-review-20261007/labels.confirmed.json \
  --comparison data/offline-vision/runs/d05f-vast-54567374/manual_vehicle_crop/comparison.json \
  --comparison data/offline-vision/runs/d05f-vast-54567374/full_native_frame/comparison.json \
  --pending-inventory data/offline-vision/training/d05f-review-20261007/review-status.confirmed.json \
  --output data/offline-vision/runs/d05i-readability-20261007

edge-agent/.venv-training/bin/python -m http.server 8767 --bind 127.0.0.1 \
  --directory data/offline-vision/runs/d05i-readability-20261007

edge-agent/.venv-training/bin/python -m pytest edge-agent/tests -q
git status --short
git diff --check
```

CLI prepare từ chối ghi đè thư mục review đã có. Nếu server 8767 đang chạy,
không chạy thêm hoặc dừng dịch vụ khác để chiếm cổng.

**Lệnh import JSON dự kiến ở thời điểm Phase 1** (thực tế người dùng đã
bàn giao CSV; lệnh đã chạy nằm trong phần Phase 2):

```bash
edge-agent/.venv-training/bin/python scripts/d05i-crop-review.py import \
  --review-root data/offline-vision/runs/d05i-readability-20261007 \
  --labels /Users/nguyen_bao/Downloads/d05i-readability.manual.json \
  --output data/offline-vision/runs/d05i-readability-20261007/labels.readability.imported.json
```

Output import phải là file mới; không ghi đè JSON Downloads/template/nhãn cũ.

## Kiểm tra đã thực hiện

- Toàn bộ edge-agent: **99 passed, 0 failed**, 1 warning fixture ZIP trùng
  `same.txt` có chủ đích; thời gian 3,80 s. Bao gồm 10 case D05i mới:
  native/nearest8, gộp provenance, không kế thừa readability/transcript,
  loại frame thiếu xác nhận, immutable metadata, nhãn partial, import/hash/
  chống ghi đè và export/import JavaScript giữ nguyên uint64.
- Node chạy helper JavaScript thực tế: nhãn partial còn thiếu dòng có thể
  lưu nháp, chưa được export; bản hợp lệ roundtrip giữ nguồn/hash và chữ
  người nhập, từ chối hash bị đổi. Không biến fixture thành nhãn camera.
- Pixel crop native **88/88** khớp frame PNG nguồn; nearest-neighbor 8×
  **88/88** khớp lặp pixel chính xác; hash nguồn giữ nguyên. **268/268**
  asset HTTP trả 200, không có link lỗi. Chi tiết trong `verification.json`.
- Mở trang trên in-app browser: mode D05i, 88 pending, 12 mục/trang, 8 trang;
  ảnh zoom có kích thước native đúng 8 lần. Chưa thao tác gán nhãn thật.
- Git hiện toàn repository untracked; `git diff --check` không báo lỗi nhưng
  không có baseline tracked để chứng minh diff. Đã đọc lại các file sửa/tạo.

## Kế hoạch ghi tại Phase 1

- **Phase 2:** chỉ crop `readable_*`; baseline English PP-OCRv5 mobile,
  server rec nếu license/dung lượng phù hợp và một recognizer chuyên biển
  sau xác minh charset/bố cục/license/revision/hash. So sánh tách dòng/đọc
  nguyên và original/upscale2, giữ preprocessing bắt buộc mỗi model.
  Báo riêng đúng toàn biển/dòng trên/dòng dưới/CER, tử số/mẫu số, CPU/crop
  và RAM; không chọn biến thể bằng test. Dừng với bảng và đề xuất 1–2 model.
  VLM local chỉ khi được duyệt riêng; chưa tải/chạy hay gửi ảnh ra API ngoài.
- **Phase 3:** định dạng từ quy định chính thức có nguồn; raw tách khỏi
  ứng viên CTC beam/top-k đã ràng buộc. Vote ký tự có alignment cạnh
  consensus toàn chuỗi, giữ bất đồng/unknown và test. Dừng báo trước/sau
  theo crop/track; chưa áp dụng miền nghiệp vụ từ giả định định dạng.
- **Phase 4:** chỉ chuẩn bị generator/font có license, đo suy giảm từ crop
  thật, contact sheet và script CPU preflight 2 step/resume. Ảnh thật xác
  nhận chỉ dùng đánh giá; không thuê GPU/train dài trước người dùng duyệt.

15 transcript cũ chỉ hai biển lặp; kết quả sẽ là **chẩn đoán**, không gọi
accuracy xưởng. Crop người chưa xác nhận đọc được chưa chứng minh nguyên
nhân chỉ do recognizer; mẫu xa/unreadable phải tách khỏi metric OCR đọc rõ.
Không thay D02/S03, signal, database, token, volume hoặc Windows.

## Phase 2 — CSV đã import, benchmark CPU đã hoàn tất (07/10/2026)

**Dừng tại Phase 2 theo yêu cầu.** Trang ảnh/nhãn/raw prediction và đủ 12
biến thể: [D05i Phase 2 review](http://127.0.0.1:8768/d05i-phase2-20261007/review.html).
Chỉ bind loopback, giữ các server 8765/8766/8767 đang có.

### Nhãn và giới hạn ground truth

- Nhận `/Users/nguyen_bao/Downloads/d05i-readability.manual.csv`, SHA-256
  `ec049a263e8c48d91954f609f1c36426eb685edaed8c2436a353ccc8ad7b8ed4`.
  **88/88** ID/source/timestamp khớp template: 26 readable_full, 7
  readable_partial, 55 unreadable, 0 pending. Không chạy OCR trên 55 unreadable.
- 26 toàn biển là **49C02655 một dòng**, 13 frame × manual/detector, cùng một
  lượt quay. 7 partial là **dòng dưới 52755** của biển hai dòng, từ 2 frame
  (2 manual/5 detector). Không có transcript đọc chắc dòng trên; không có
  biển hai dòng readable_full. Hai capture và hai chuỗi biết được không phải
  26 xe độc lập. Không gọi kết quả này là accuracy xưởng.
- CSV không giữ fingerprint/hash ảnh/thời gian review như JSON. Import kiểm
  tra chính xác headers/inventory/ID/source/media time rồi gắn metadata bất
  biến từ template local; xác minh lại hash ảnh và nguồn. Không chứng minh
  được lịch sử thao tác review từ CSV này.
- 26 full chưa chọn checkbox dòng: suy ra `single` từ trạng thái full và
  layout người dùng. 6 partial thiếu checkbox: chỉ gắn `bottom` từ transcript
  bottom người dùng đã nhập; mục thứ 7 đã có checkbox. Ghi đủ **32** quy tắc
  chuyển đổi trong provenance. Không tự đoán ký tự hoặc transcript dòng trên.
- Một partial có cả full_text: giữ nguyên nhưng **không dùng** full_text đó
  để chấm toàn biển. CSV Downloads và template gốc không bị sửa.

### Thiết kế khóa trước inference

`plan.json` được ghi trước inference: ba model, split/whole × original/upscale2,
33 crop × 4 biến thể × 3 model = **396 case**, mỗi case chạy 3 lần và lấy
prediction lần đầu; 1.188 lần đo case. Tất cả prediction lặp giống nhau.
Hai warmup call/model; process riêng/model; CPUExecutionProvider, 2 intra-op
threads/1 inter-op thread. Giới hạn 600 s/worker và 660 s subprocess. Không
VLM, GPU hay API ngoài. Không loại case nào do thiếu split; không chọn variant
bằng kết quả camera. Chính sách chính đã cố định:
English split/original, server split/original, FastPlate whole/original.
`selected_variant=null`; chưa đổi recognizer của runtime.

- Original: native crop. Upscale2: cubic đúng 2×, không thêm border. Đây là
  phép thử mới, không phải `upscale2_pad` có border ở báo cáo D05f cũ.
- Paddle: BGR, chiều cao 48 px theo tỷ lệ, width tối thiểu 320/tối đa 3.200,
  pad phải zero sau normalize; CTC dictionary chính thức, không lọc ký tự.
- FastPlate CCT-S v2: RGB, linear stretch 128×64, NHWC uint8, normalize trong
  graph, không pad giữ tỷ lệ. 10 position heads (không CTC); không collapse
  ký tự lặp, chỉ bỏ padding `_` cuối chuỗi. Giữ cả raw slot/prediction.
  Config có region Vietnam nhưng không công bố bảo đảm đọc biển VN hai dòng.
- Tách dòng dùng separator pixel người dùng; nguyên biển hai dòng không có
  row boundary nên **không lấy suffix theo nhãn** để chấm dòng dưới.
- Exact/CER chỉ normalize trình bày: uppercase, bỏ whitespace/dấu chấm/gạch
  ngang, giữ raw. Không sửa nhầm ký tự. CER = số edit / số ký tự nhãn;
  báo riêng toàn biển và dòng dưới. Không gộp denominator khác nhau.

Nguồn/revision/license/hash trước inference nằm trong manifest từng model và
`edge-agent/THIRD-PARTY-NOTICES.md`: English v5 mobile 7,85 MB Apache-2.0,
server v5 84,50 MB Apache-2.0, FastPlate CCT-S v2 5,26 MB theo MIT của chính
project/model author. Hash weights/config được đối chiếu metadata release
chính thức; không suy giấy phép dataset từ giấy phép model. Các model file
nằm ngoài Git. Adapter tham khảo preprocessing chính thức có attribution.

### Bảng đầy đủ — tử số/mẫu số và tài nguyên

CPU và wall là median 3 lần/case rồi median 33 crop; gồm biến đổi ảnh,
preprocess model, inference, decode, không gồm đọc file/model load. Split
biển hai dòng bao gồm 2 calls/crop. Hai native threads làm CPU time có thể
lớn hơn wall time. RAM là **peak process riêng/model**, gồm Python/native
runtime/init/warmup; snapshot RSS trước/sau từng crop không phải peak crop.

| Model | Cách đọc | Ảnh | Toàn biển | Dòng trên | Dòng dưới | CER toàn biển | CER dưới | CPU / wall ms/crop | Peak RAM MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| english_mobile | split | original | 22/26 | N/A (0 chấm) | 7/7 | 4/208 (1.92%) | 0/35 (0.00%) | 29.09 / 14.62 | 107.22 |
| english_mobile | split | upscale2 | 22/26 | N/A (0 chấm) | 4/7 | 4/208 (1.92%) | 3/35 (8.57%) | 28.90 / 14.77 | 107.22 |
| english_mobile | whole | original | 22/26 | N/A (0 chấm) | N/A (0 chấm) | 4/208 (1.92%) | N/A | 28.70 / 14.15 | 107.22 |
| english_mobile | whole | upscale2 | 22/26 | N/A (0 chấm) | N/A (0 chấm) | 4/208 (1.92%) | N/A | 28.53 / 14.42 | 107.22 |
| fast_plate_cct_s_v2 | split | original | 26/26 | N/A (0 chấm) | 5/7 | 0/208 (0.00%) | 3/35 (8.57%) | 32.48 / 16.23 | 106.89 |
| fast_plate_cct_s_v2 | split | upscale2 | 26/26 | N/A (0 chấm) | 5/7 | 0/208 (0.00%) | 3/35 (8.57%) | 32.40 / 16.19 | 106.89 |
| fast_plate_cct_s_v2 | whole | original | 26/26 | N/A (0 chấm) | N/A (0 chấm) | 0/208 (0.00%) | N/A | 32.16 / 16.04 | 106.89 |
| fast_plate_cct_s_v2 | whole | upscale2 | 26/26 | N/A (0 chấm) | N/A (0 chấm) | 0/208 (0.00%) | N/A | 32.41 / 16.14 | 106.89 |
| paddle_server | split | original | 24/26 | N/A (0 chấm) | 7/7 | 2/208 (0.96%) | 0/35 (0.00%) | 148.34 / 73.75 | 430.95 |
| paddle_server | split | upscale2 | 23/26 | N/A (0 chấm) | 7/7 | 3/208 (1.44%) | 0/35 (0.00%) | 148.37 / 74.35 | 430.95 |
| paddle_server | whole | original | 24/26 | N/A (0 chấm) | N/A (0 chấm) | 2/208 (0.96%) | N/A | 147.07 / 73.68 | 430.95 |
| paddle_server | whole | upscale2 | 23/26 | N/A (0 chấm) | N/A (0 chấm) | 3/208 (1.44%) | N/A | 146.59 / 73.48 | 430.95 |

Toàn biển split và whole giống nhau vì 26 full đều một dòng. Dòng trên thiếu
nhãn **0/0, không phải 0%**; whole hai dòng có 7 nhãn bottom nhưng 0 có row
boundary để chấm, báo N/A (không phải 7 lỗi).

| Model, split/original | Full manual | Full detector | Bottom manual | Bottom detector |
| --- | --- | --- | --- | --- |
| English mobile | 11/13 | 11/13 | 2/2 | 5/5 |
| Paddle server | 12/13 | 12/13 | 2/2 | 5/5 |
| FastPlate CCT-S v2 | 13/13 | 13/13 | 2/2 | 3/5 |

### Diễn giải và đề xuất 1–2 recognizer

1. **FastPlate CCT-S v2** là ứng viên cho lần chẩn đoán tiếp trên nguyên biển:
   native full 26/26, CER 0/208, khoảng 32,16 ms CPU/16,04 ms wall và
   106,89 MiB peak process. Chưa đủ nhãn để kết luận toàn biển hai dòng;
   split bottom chỉ 5/7. Chưa thay model runtime hoặc chọn variant theo test.
2. **English PP-OCRv5 mobile** giữ làm đối chứng nhẹ cho đọc theo dòng:
   native bottom 7/7, khoảng 29,09 ms CPU/14,62 ms wall, 107,22 MiB RAM;
   full 22/26. Server native tăng full lên 24/26 nhưng bottom vẫn 7/7,
   khoảng 148,34 ms CPU/73,75 ms wall, 430,95 MiB RAM. Giữ server làm tham
   chiếu offline; bằng chứng hiện tại chưa đủ để ưu tiên nó trong runtime.

Upscale2 không giúp nhất quán: English full vẫn 22/26 nhưng bottom giảm
7/7→4/7; server full 24/26→23/26; FastPlate full giữ 26/26. Không lấy biến
thể thắng từng crop để gộp thành kết quả model. Raw English nhầm `4` đầu
thành `L`/`∠`; server có `4SC` thay `49C` và `L9C`. Các lỗi có cả manual lẫn
detector crop, chứng minh vẫn có thành phần lỗi recognizer; chưa đủ để quy
mọi lỗi cho bbox hoặc nguồn ảnh. 55 unreadable nằm ngoài metric này: kết
quả trên một biển rõ không chứng minh phần cứng/camera không còn giới hạn.

### Lệnh, artifacts và kiểm tra

```bash
# Trong /Users/nguyen_bao/Documents/ChatGPT/nhu-tung-demo
edge-agent/.venv-training/bin/python scripts/d05i-crop-review.py import \
  --review-root data/offline-vision/runs/d05i-readability-20261007 \
  --labels /Users/nguyen_bao/Downloads/d05i-readability.manual.csv \
  --output data/offline-vision/runs/d05i-readability-20261007/labels.readability.csv-imported.json

edge-agent/.venv-training/bin/python scripts/d05i-ocr-benchmark.py \
  --review-root data/offline-vision/runs/d05i-readability-20261007 \
  --labels data/offline-vision/runs/d05i-readability-20261007/labels.readability.csv-imported.json \
  --output data/offline-vision/runs/d05i-phase2-20261007

edge-agent/.venv-training/bin/python -m http.server 8768 --bind 127.0.0.1 \
  --directory data/offline-vision/runs
edge-agent/.venv-training/bin/python -m pytest edge-agent/tests -q
git diff --check
git status --short
```

Hai CLI từ chối ghi đè output hiện có; lần chạy lại phải dùng file/thư mục
mới. Model cache có manifest/hash kiểm tra khi nạp. Phiên bản thực tế trong
venv riêng: ONNX Runtime 1.23.2, NumPy 2.2.6, PyYAML 6.0.3, psutil 7.0.0,
OpenCV 4.12.0; macOS 15.7.5 arm64. Model process đo 6,40/32,22/7,06 s lần
lượt English/server/FastPlate, không gồm tải file hoặc benchmark model init.
Lần gọi đầu thiếu tên distribution `opencv-python` do đã cài bản headless;
sửa báo phiên bản bằng `cv2.__version__` trước khi tạo plan/inference.

Root `data/offline-vision/runs/d05i-phase2-20261007/` gồm plan.json,
summary.json, predictions.csv, review.html, verification.json và summary
riêng/model. Giữ raw, raw mỗi repetition, normalized, nhãn được chấm, shape
input model, confidence riêng từng model, timing và RSS; không so confidence
khác model như cùng thang đo.

- Toàn bộ edge-agent **107 passed, 0 failed**, 1 warning ZIP duplicate fixture
  có chủ đích, 3,93 s (lần chạy lại cuối). Thêm 8 case CSV/source/time/provenance, partial không
  dùng full GT, CER/missing GT, position decoder giữ chữ lặp, preprocessing
  RGB uint8, lấy lần đọc đầu thay vì chọn prediction khớp nhãn.
- 88/88 hash native crop, source video/nhãn upstream, CSV gốc và template
  giữ nguyên; template gốc vẫn 88 pending. Plan/code/model manifest/weights
  hashes khớp; CSV kết quả đủ 396 case duy nhất, mỗi case 3 lần, không case
  bị loại. HTTP review và 33 ảnh độc lập được kiểm tra; server loopback.
- Git repository toàn untracked, diff --check không báo lỗi nhưng không có
  baseline tracked để chứng minh diff. Không commit ảnh/model/nhãn.

**Dừng Phase 2.** Phase 3/4 chưa thực hiện; không training, thuê GPU, đổi
D02/S03, API nghiệp vụ, database, token, volume hoặc Windows.

## Bổ sung Phase 2 theo chỉ đạo — không đổi kết quả đã khóa

**“Quan sát chẩn đoán dựa trên transcript D05f”: FastPlate whole/original
xuất 29K52755 ở 5/7 crop partial**, đối chiếu annotation_id với transcript
đọc chắc trong `training/d05f-review-20261007/labels.confirmed.json` SHA-256
`80fac6a4ffc12984098ecc0f9d01edcc7710716aa642d5ba56d9cf4ff0bdd908`.
Hai prediction khác là `29H52755` và `29K527555`. Chỉ 2 thời điểm media
104/105 s; 2 manual và 5 detector crop không phải 7 quan sát độc lập.

Ghi riêng trong `d05i-phase3-20261007-v2/phase2-observation-d05f-transcript.json`.
Không nâng partial thành readable_full, không gộp vào bảng Phase 2/CER toàn
biển, không sửa bất cứ file nào trong root Phase 2 đã khóa. Transcript D05f
của frame không thay thế nhãn khả năng đọc từng crop trong Phase 1.

## Phase 3 — xếp hạng định dạng và vote ký tự (07/10/2026)

**Recognizer chính FastPlate whole/original; đối chứng English split/original**
theo lựa chọn người dùng, không chọn bằng test. Phần này là CLI chẩn đoán
local; pipeline vận hành D05a/config/runtime chưa được chuyển model.

### Nguồn định dạng và phạm vi

Cơ sở: Điều 37/Phụ lục 04 [Thông tư 79/2024/TT-BCA bản ký](https://hue.gov.vn/Portals/0/VBPL/Nam2024/T12/79-bca.signed.pdf)
và [Cổng Chính phủ tóm tắt seri](https://xaydungchinhsach.chinhphu.vn/mau-sac-seri-ky-hieu-bien-so-xe-cua-co-quan-to-chuc-ca-nhan-tu-01-01-2025-119241225071905346.htm).
Parser chẩn đoán nhận 2 chữ số địa phương, một chữ seri thuộc nhóm trong
quy định, 5 chữ số thứ tự; hỗ trợ seri riêng CD/RM/HC/KT, seri chữ+số 1–9
của nhóm mô tô nền xanh, và profile tương thích 4 số cũ. Không coi chữ+số
là seri thông thường của ô tô. Không sửa O/0, I/1, B/8; bỏ dấu trình bày.
Bản 4 số ghi rõ legacy; không nhận số thứ tự toàn zero.

Đã tra sửa đổi [51/2025](https://vbpl.vn/bocongan/Pages/vbpq-toanvan.aspx?ItemID=179019)
và [37/2026 bản ký, hiệu lực 08/06/2026](https://xdcs.cdnchinhphu.vn/446259493575335936/2026/4/29/37-bca-17774475322131775956925.pdf).
**Đây là tập con cú pháp, không phải xác minh đăng ký hợp pháp hoặc danh mục
địa phương đang cấp**. Không lọc mã tỉnh theo lịch xe/nhãn thật; 00 không
hợp lệ trong profile. Biển ngoài tập con (ngoại giao, tạm, quân đội, seri
mô tô hai chữ…) giữ raw và báo outside/unknown; không tự đổi thành biển
ô tô. Với D05j nhiều xe máy phải báo phần ngoài phạm vi, không gọi chúng
là biển sai pháp luật. Không suy màu biển/loại xe từ OCR.

### Giải mã và bằng chứng

Module mới `edge-agent/offline_vision/plate_domain.py`, tái dùng normalize,
CER và consensus toàn chuỗi hiện có:

- FastPlate là **position heads**, không CTC: beam 32 theo vị trí, giữ ký tự
  lặp và padding cuối; tổng log likelihood từ xác suất model. English dùng
  **CTC prefix beam** (blank/nonblank riêng), width 64, top-5 token/time
  step cộng blank; separator/dấu và repeat giữ đúng CTC semantics.
- English split hai dòng giữ separator người dùng, nối hai ma trận bằng một
  timestep blank bắt buộc; raw từng dòng vẫn giữ nguyên. Không dùng suffix
  biết từ nhãn để sửa/bổ sung dòng. Ma trận đầu ra 66 crop/model được lưu
  NPZ; từ điển/config pinned cho phép xem lại cách xếp hạng.
- Giữ raw/normalized và top-5 riêng, mỗi candidate mang nhãn **“đã ràng buộc
  định dạng”**. Proposal còn phải có log score loss ≤3 so với beam chưa
  ràng buộc/argmax và margin top-2 ≥ln(2), nếu không unknown. Các số này khóa
  trước inference, chưa hiệu chỉnh bằng validation; không gọi là confidence
  đã calibration và không so log score giữa model.
- Vote ký tự: Levenshtein alignment với medoid chỉ từ prediction; giữ
  insertion/deletion, histogram từng cột, bất đồng và vote chưa ràng buộc.
  Không truyền transcript ground truth vào decoder/alignment/vote.
- Track được namespaced source/session/track. Không gộp khác track; gom
  cùng timestamp media chỉ 1 quan sát, crop cùng frame bất đồng thì abstain.
  Empty/abstain vẫn tính denominator. Cần ≥3 frame riêng, mỗi ký tự ≥2
  frame và strict majority ≥2/3; tie/yếu/outside-format → unknown.
- Giữ consensus toàn chuỗi bên cạnh vote ký tự, cả raw và proposal-format;
  cả hai chỉ gợi ý cần người xác nhận, không gán vào D02/signal.

Plan/hash được lưu trước inference; giới hạn 600 s, CPUExecutionProvider,
không tải model mới hay gọi API ảnh. Lần đầu và v2 đều giữ raw Phase 2;
v2 bổ sung fail-closed cho track identity chưa biết, giữ bản đầu riêng.

### Kết quả theo crop

Chỉ **26 readable_full** một biển 49C02655 được chấm exact/CER chính thức:

| Model chính sách cố định | Raw trước | Proposal sau định dạng | Unknown sau | CER trước | CER sau, unknown tính chuỗi rỗng |
| --- | --- | --- | --- | --- | --- |
| FastPlate whole/original | 26/26 | 26/26 | 0/26 | 0/208 | 0/208 |
| English split/original | 22/26 | 24/26 | 2/26 | 4/208 | 16/208 |

English hai crop detector được xếp hạng lại đúng từ xác suất model; raw
vẫn `L9C…`/`∠9C…`. Hai crop manual còn unknown: một loss 3,236 vượt bound,
một top-2 margin 0,413 dưới ln(2). Không nới ngưỡng theo nhãn để biến thành
26/26. CER trên 24 proposal được phát ra là 0/192; **CER tính cả abstention
là 16/208**, nên không gọi mọi metric đều cải thiện. Candidate top-1 đúng
nhưng bị gate giữ unknown vẫn không tính là proposal đúng.

33 readable crop/model (26 full + 7 partial), tổng 66 row/66 NPZ, elapsed
6,05 s gồm init/inference/beam; median wall infer+beam FastPlate 23,16 ms,
English 125,81 ms/crop, một lần đo chẩn đoán, không so trực tiếp với median
3 lần/Phase 2 để tuyên bố speedup. Partial thiếu GT toàn biển vẫn loại khỏi
metric chính; quan sát D05f đã tách riêng bên trên.

### Kết quả theo track/nguồn crop

Hai session/track D05f đã có được gắn bằng khoảng media và mỗi session chỉ
một track; **chưa kiểm chứng liên kết bbox không gian**, không phải đánh giá
tracking mới. Manual/detector xử lý riêng, không cộng thành lượt độc lập.

| Nhóm thời gian/track | Frame readable riêng/nguồn | FastPlate consensus toàn chuỗi → vote ký tự | English consensus toàn chuỗi → vote ký tự |
| --- | ---: | --- | --- |
| v001/s00001/t00006, 104–105 s | 2 | unknown → unknown | unknown → unknown |
| v002/s00001/t00001, 146–198,52 s | 13 | 49C02655 → 49C02655 | 49C02655 → 49C02655 |

Bảng đúng cho cả manual/detector và cho raw/proposal-format (8 row chi tiết).
Không có gain theo track trên bộ này vì consensus toàn chuỗi đã đúng ở
nhóm đủ frame. Nhóm 29K ít bằng chứng, không hạ minimum từ 3 xuống 2 để chốt.
55 unreadable không chạy trong chẩn đoán, chưa đo coverage toàn lượt.

### Lệnh và kiểm tra

```bash
edge-agent/.venv-training/bin/python scripts/d05i-domain-diagnostic.py \
  --phase2 data/offline-vision/runs/d05i-phase2-20261007 \
  --d05f-labels data/offline-vision/training/d05f-review-20261007/labels.confirmed.json \
  --output data/offline-vision/runs/d05i-phase3-20261007-v2
edge-agent/.venv-training/bin/python -m pytest edge-agent/tests -q
git diff --check
git status --short
```

CLI không ghi đè output, lần chạy lại chọn tên mới. Bằng chứng/plan/hash/NPZ/
CSV/track histograms ở `data/offline-vision/runs/d05i-phase3-20261007-v2/`;
[trang trước/sau](http://127.0.0.1:8768/d05i-phase3-20261007-v2/review.html).
Verification: mọi file Phase 2 khớp hash ban đầu; raw 66/66 khớp lần chạy
Phase 2; model không đổi; source labels không sửa. Toàn edge-agent **132
passed, 0 failed**, 1 warning ZIP fixture có chủ đích, 3,52 s. Bao gồm parser
legacy/current/unsupported, slot repeats, CTC so với enumerate mọi path nhỏ,
alignment insert/delete, recovery chữ từ ba lỗi khác vị trí, ties/empty/
thiếu frame, timestamp trùng/track lẫn/unknown identity và D05j native/UI.

**Dừng Phase 3.** Theo chỉ đạo mới, tiếp chuẩn bị D05j (tài liệu riêng),
không làm Phase 4 synthetic hoặc fine-tune trước khi có đánh giá đa dạng.
Không đổi DB, D02/S03, token/volume/9 signal/Windows; không GPU/training.
