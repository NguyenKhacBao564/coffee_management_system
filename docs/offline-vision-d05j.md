# D05j — Dataset đa dạng để đánh giá FastPlate trước fine-tune

07/10/2026, theo chỉ đạo sau D05i Phase 3. **Đã audit local/chọn ảnh và mở
review; chưa có nhãn xác nhận, chưa hoàn tất đánh giá FastPlate đa dạng.**
Không làm Phase 4 synthetic/train/GPU; không đổi database hoặc D02/S03.

## Dữ liệu đã có và nguồn

Người dùng xác nhận tải từ [THỊ GIÁC MÁY TÍNH — Tổng hợp data](https://thigiacmaytinh.com/tai-nguyen-xu-ly-anh/tong-hop-data-xu-ly-anh/)
và cho phép dùng local. Nguồn công bố đây là mẫu thử chương trình, gồm ảnh
ô tô biển dài/vuông/vàng và xe máy GreenParking. Giữ attribution tác giả
THỊ GIÁC MÁY TÍNH/GreenParking; không coi mô tả sample cộng đồng là giấy phép
MIT/CC cho dataset. Dùng để review/đánh giá local theo chỉ đạo người dùng;
chưa phân phối lại, train hoặc khẳng định quyền thương mại rộng hơn.

- [CarTGMT Google Drive được nguồn dẫn](https://drive.google.com/file/d/1U5ebTzW2c_sVVTCSX1QH-ZJFpLijMdUv/view)
- [GreenParking trong repo của nguồn](https://github.com/thigiacmaytinh/DataThiGiacMayTinh/blob/main/GreenParking.zip)

Không tải lại ZIP/bộ lớn. Audit bản người dùng đã giải nén ở incoming:

| Nguồn | Ảnh đọc được/tổng ảnh | Lỗi decode | Chọn review |
| --- | ---: | ---: | ---: |
| CarTGMT | 944/944 | 0 | 32 |
| GreenParking | 1.748/1.748 | 0 | 32 |
| Tổng ảnh toàn cảnh | 2.692/2.692 | 0 | 64 |
| greenparking2char | 61.775 file, chưa audit pixel | — | 0 |
| greenparkingchar | 71.275 file, chưa audit pixel | — | 0 |

Hai thư mục ký tự rời không thể chấm toàn biển, chưa dùng. File names,
`CarTGMT/_report.csv`, `GreenParking/location.txt` được hash và giữ riêng
làm reference của nguồn, **không nhập như nhãn đã xác nhận**. Không có OCR
đề xuất trong biểu mẫu gán GT. Không tự đoán tọa độ location hay sửa chuỗi
trong tên file. Dữ liệu camera D05f vẫn giữ nguyên ở nguồn cũ, không trộn
với dataset mới để tăng denominator.

## Audit và chọn ảnh

`audit.json` ghi mọi original path/hash/size/dHash chuỗi uint64, độ sáng và
Laplacian toàn ảnh; đây chỉ là feature chọn ảnh, không đại diện chất lượng
crop biển. Có **82 cặp** trùng hash file hoặc pixel, **1.266 cặp** khác hash
nhưng dHash toàn frame ≤4. Không phát hiện cặp cross-source theo phép kiểm
này. Không gọi các cặp đó là số ảnh phải xóa; không xóa/filter hàng loạt.

Nhóm connected components các cặp nghi trùng; chọn một component/nguồn,
32/source theo strata độ sáng rồi novelty dHash, tie theo sharpness/hash.
64 ảnh thuộc64 component khác nhau, chưa chứng minh64 xe khác nhau. Mọi
ảnh đã chọn xuất PNG từ native decoded pixel, không resize/crop cho model.
Contact sheets thu nhỏ chỉ để xem; ảnh gốc và bbox vẽ vẫn native. 2.692
hash nguồn/64 pixel matches đã kiểm tra. Ảnh tĩnh giữ media_seconds và
frame_index **null**, không suy giờ thật từ filename hoặc timestamp overlay.

## Trang review và việc người dùng cần hoàn tất

[Trang D05j 64 ảnh](http://127.0.0.1:8768/d05j-diverse-review-20261007-v2/label.html)
đã mở trong app và giữ để người dùng gán. Tái dùng labeler D05b; adapter
D05j đổi tiêu đề/caption/dropdown cho ảnh tĩnh, không làm lại pipeline.
Tất cả 64 frame chưa review, split `unassigned`, bbox/GT trống.

1. Vẽ đủ mọi bbox biển trên ảnh gốc; chọn trạng thái readable/uncertain/
   unreadable, nhập transcript chỉ khi chắc. Biển hai dòng đặt separator
   giữa hai dòng; không chép prediction hoặc suy chuỗi từ tên file.
2. Chọn frame có/không biển và “đã rà đầy đủ”. Có biển chưa gán đủ không
   làm negative. Với crop sai vùng/khóa container, xác nhận không chứa
   biển thật trước khi làm hard negative.
3. Nhập mã cùng xe/biển và capture/pass nếu biết; không biết để chưa rõ,
   không tạo nhóm độc lập giả. Giữ split chưa chia, chưa dùng test chọn
   model/ngưỡng/policy. Thông tin nhóm từ nguồn cần được xác minh.
4. Trong Ghi chú hoặc `conditions.manual.csv` theo sample_id, ghi
   `plate_color` (white/yellow/blue/other/uncertain), bố cục, xe car/truck/
   tractor/trailer/motorcycle, occlusion none/partial/heavy, lighting,
   blur/angle, vehicle_group_id/capture_group_id/pass_id. Không có thông
   tin thì unknown, không mặc định ngày hoặc biển trắng.
5. Bấm **Tải nhãn JSON**, lưu tên `d05j-labels.manual.json` và bàn giao
   đường dẫn; nếu điền bảng điều kiện, chuyển kèm `conditions.manual.csv`.
   Trang giữ nhãn trong bộ nhớ khi đang mở, **cần xuất JSON trước khi đóng/
   reload**. Nạp JSON đã lưu để tiếp tục; scene_hash string được kiểm tra.

Hiện chưa có số biển duy nhất hoặc phân bố vàng/che/xe tải được xác nhận.
Nguồn sample không chứng minh coverage container camera xưởng. Cần bổ sung
clip/ảnh được phép từ nhiều lượt/xe camera185, biển vàng, rơmoóc/container
che một phần, ngày/đêm, xa/gần/góc/blur; giữ các failure không có frame đọc
được trong thống kê coverage. Mục tiêu50–100 lượt trong D05g là kế hoạch
thu thập, không tiêu chí pass đã chốt. Không tự quét camera/RTSP hoặc lấy
nguồn Internet mới để điền lỗ hổng.

## Plan đánh giá trước fine-tune

`evaluation-plan.json` khóa policies/metrics trước nhãn/benchmark:

- FastPlate CCT-S v2 **whole/original** chính; English v5 mobile
  **split/original** đối chứng. Dùng đúng preprocess Phase2, CPU và
  source/hash hiện có. Không chọn biến thể tốt nhất theo test.
- Báo riêng raw/normalized, candidates định dạng/gated unknown. Exact
  toàn biển, CER (unknown tính rỗng và CER trên accepted tách riêng),
  coverage, CPU/wall/RAM; dòng trên/dưới chỉ nếu có transcript người gán.
  Không lấy đuôi whole prediction theo GT để chấm dòng.
- Dedupe sau crop/bbox; nhóm cùng xe/capture và component nghi trùng phải
  cùng split. Chọn validation trước test theo nhóm đã xác nhận. Chưa đủ
  nhóm thì chỉ mô tả, không khẳng định independence/leakage hoàn toàn.
- Báo theo xe/biển/capture và màu/bố cục/loại xe/che khuất. Xe máy có seri
  ngoài parser tập con D05i báo outside-scope, không gọi biển đó không hợp
  lệ. Ô tô/xe tải/container không gộp denominator với xe máy.
- Snapshot public có thể trùng pretraining FastPlate; chưa có manifest
  pretraining để loại trừ. Camera mới giữ độc lập là bằng chứng cần thêm.
- Track/vote chỉ chấm khi có chuỗi media/pass/track thật hoặc nhóm người
  dùng xác nhận; ảnh tĩnh rời không tạo track giả bằng tên file.

Chưa có nhãn nên chưa báo FastPlate exact/accuracy trên D05j. Sau import
sẽ tái dùng validator/crop/benchmark modules D05b/D05i; không viết pipeline
video mới. Chỉ cân nhắc fine-tune sau khi bộ này và camera mới cho thấy lỗi
recognizer còn đáng kể trên crop rõ; nguồn ảnh/crop sai cần xử lý riêng.

[FastPlate official README pinned](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/README.md)
có workflow train/fine-tune Keras3 và export; MIT đã ghi trong notices.
Lần train sau phải xác minh checkpoint trainable/config/vocabulary/hash;
ONNX inference hiện tại không được mặc định là checkpoint optimizer/train.
Chưa cài dependencies training, tải checkpoint trainable hoặc chạy training.

## Lệnh, artifacts và kiểm tra

```bash
# Trong /Users/nguyen_bao/Documents/ChatGPT/nhu-tung-demo
edge-agent/.venv-training/bin/python scripts/d05j-prepare-review.py \
  --incoming data/offline-vision/incoming \
  --output data/offline-vision/runs/d05j-diverse-review-20261007-v2 \
  --per-source 32
edge-agent/.venv-training/bin/python -m pytest edge-agent/tests -q
```

CLI refuse overwrite; lần sau dùng thư mục mới. Root đã bàn giao gồm
`manifest.template.json`, `labels.template.csv`, `conditions.manual.csv`,
`audit.json`, `evaluation-plan.json`, `verification.json`, `label.html`,
`contact-1..4.jpg` và64 PNG trong frames/. Mọi dữ liệu nằm dưới data đã
Gitignore, không đóng vào repository/app/DB.

Full edge-agent132 passed/0 failed/1 warning ZIP fixture chủ đích,3,52s;
bao gồm kiểm tra pixel/hash, không suyGT từ filename/report, uint64 string,
cap bounded, output không ghi đè và JS khởi tạo labeler với null timestamp.
Browser xác nhận 1/64, 0 reviewed, caption ảnh tĩnh và64 options; HTTP64
ảnh trả200. Giữ server loopback8768 và cổng khác; không cloud/GPU/database.

## 07/10/2026 — Điều chỉnh review trước khi gán nhãn + Phase D

Bản bàn giao hiện tại: `data/offline-vision/runs/d05j-expanded-20261007/`.
Trang vào: <http://127.0.0.1:8768/d05j-expanded-20261007/index.html>.
Tái sử dụng D05b native-image editor, D05f `YoloXPlateDetector`, bộ đọc video,
FastPlate/Paddle preprocessing đã có; chưa train hoặc nối database.

### Nhãn CSV nhận được

- Bản gốc `/Users/nguyen_bao/Downloads/labels.manual.csv` giữ nguyên,
  SHA-256 `ca894e48d3353f95e70189d287bf0719cbb18bded9dd6122ee58a9b4bd89003e`.
  Lưu bản sao `imported/labels.original.csv`, JSON riêng
  `imported/labels.imported.json`, và `import-report.json`.
- 64 frame, 53 đã xem, 49 bbox có transcript/readability xác nhận:
  29 CarTGMT và 20 GreenParking. Hai mục `d05j-0021`, `d05j-0055` có
  readability readable nhưng frame chưa xác nhận: chỉ bản eligibility đặt
  pending, giữ nguyên transcript và CSV gốc. Tổng 6 bbox pending; 9 frame
  chưa có bbox. Không suy diễn các frame đó là mẫu âm.
- CSV cũ không xuất completeness, màu hoặc mức che. Những trường này vẫn
  unknown/pending; không suy từ ghi chú/OCR/filename. `scene_hash` luôn là
  chuỗi; kiểm tra JSON export/import với giá trị `18446744073709551615`.

### Review chính: CarTGMT

- `_report.csv` SHA-256
  `eace9a625414aeab68b3f2d866c12bb3f1316f02ecaf45db753e5fda485a44e7`.
  476 dòng có chuỗi /476 filename; **18 ảnh thiếu**, 458 đọc được,
  **39 bản trùng pixel** gộp nhưng giữ tham chiếu → **419 ảnh review**.
  Danh sách ảnh thiếu/trùng: `cartgmt/audit.json`; giữ toàn bộ incoming gốc.
  Không có cặp dHash≤4 giữa 419 ảnh sau gộp; đây chỉ là phép triage full-frame,
  không chứng minh không có ảnh gần trùng/xe lặp sau crop.
- `cartgmt/label.html`: nguồn hiển thị riêng **“gợi ý của nguồn — KHÔNG phải
  nhãn xác nhận”**. Bbox D05f là proposal (threshold .25, NMS .45), giữ model
  hash/provenance. Không có annotation manual được sinh từ OCR/detector.
- 14 frame CSV cũ trùng SHA ảnh gốc được chuyển nhãn; 12 có transcript đọc
  được, 13 đã xem. Toàn bộ 32 CarTGMT cũ vẫn xem ở
  `cartgmt-imported/label.html`, kể cả ảnh không có gợi ý nguồn. Hai trang
  có ảnh trùng: không cộng mẫu số giữa chúng.
- 20 ảnh/trang, ←/→ đổi ảnh; B nhận một bbox, xóa/vẽ lại để chỉnh;
  1 Đúng/xác nhận bản sửa; 2 Sửa; 3 Không đọc được; 4 Không có biển;
  S xuất JSON. Cần bố cục thực tế và đường tách thủ công cho biển hai dòng.
  Các gợi ý trùng nhưng bất đồng chuỗi phải nhập đọc thủ công trước xác nhận.
- Crop proposal có kích thước native, preview 2× chỉ để xem. Màu/mức che/loại
  xe lưu theo **từng annotation**. `visible_text` dùng `?` cho phần bị che;
  Không đọc được không xóa visible_text, và không có GT toàn biển.
  Không có biển là quyết định explicit; không suy từ thiếu bbox.
- localStorage autosave theo dataset UUID + vị trí; không có ảnh/base64 trong
  nhãn. Xuất `labels.d05j.cartgmt.json` để đưa vào CLI. JSON import kiểm tra
  inventory/hashes/bbox; CSV legacy không giữ visible_text/condition tags.
  Frame/crop chưa xác nhận vẫn pending. Trang cũ và CSV gốc không ghi đè.

### GreenParking và camera185

- `motorcycle/label.html`: giữ 32 ảnh GreenParking, trong đó 20 transcript
  đọc được. Nhóm **motorcycle**, ưu tiên sau, mẫu số riêng. Không gộp
  CarTGMT/camera; chưa đưa ảnh ký tự rời vào benchmark/train.
- `camera185-v3/label.html`: native 1920×1080, media PTS/frame index decoder,
  nguồn/hash video giữ. Tái dùng sampled vehicle tracks D05f, ≤16 timestamp
  theo quantile/track và bổ sung các timestamp bbox hai dòng đã gán trước;
  thử plate detector trên crop xe **tự động** ở độ phân giải gốc. Ưu tiên
  reference bbox biển hai dòng đã xác nhận nếu có; chọn crop rõ nhất theo
  Laplacian×sqrt(area), không dùng OCR làm tiêu chí/GT.
- 9 track có quan sát truck; tổng 101 frame candidate (track có thể lặp ở
  cùng timestamp). Chọn 3 frame: v001/t00001 24s, v001/t00006 105s,
  v002/t00001 109,52s. Hai frame có bbox tham chiếu manual; bbox ở frame
  trích mới vẫn cần chỉnh/xác nhận (seek theo PTS có thể khác frame cũ).
  Frame thứ ba chỉ là proposal theo tỷ lệ hình dạng, **chưa chứng minh có
  biển hai dòng thật**; có thể sai vùng/khác bố cục. Detection score không
  có cho bbox manual reference, trả null; không bịa score.
- `visible_text`, màu, mức che và mọi annotation mới vẫn pending. Không tự
  điền transcript cũ vào frame mới; không coi 3 track là 3 xe khác nhau.
  Hai video hiện tại chưa bổ sung được nhiều biển/điều kiện độc lập.

### Benchmark trên nhãn hiện có (CPU, policy đã chốt trước inference)

Root kết quả: `benchmark-final-v2/`: plan/hash, summary, predictions CSV,
49 crop native và HTML ảnh/GT/raw. Policy **FastPlate whole/original** và
**English mobile split/original**; không search biến thể/chọn bằng test.
FastPlate: BGR→RGB, stretch linear 128×64 NHWC uint8, normalize trong graph.
English: BGR, giữ aspect height48, width≥320/max3200, [-1,1], right zero pad;
biển hai dòng tách đúng split_y thủ công rồi nối raw, không sửa ký tự.
Chuẩn hóa chỉ chữ hoa, bỏ khoảng trắng/dấu chấm/gạch nối trình bày.

| Nhóm | Số biển xác nhận duy nhất | FastPlate đúng toàn biển | English đúng toàn biển |
|---|---:|---:|---:|
| CarTGMT một dòng | 19 | 18/19 | 11/19 |
| CarTGMT hai dòng | 10 | 10/10 | 8/10 |
| CarTGMT riêng, tất cả | 29 | 28/29 | 19/29 |
| GreenParking motorcycle hai dòng (riêng) | 20 | 16/20 | 13/20 |

- CER CarTGMT: FastPlate **1/230**, English **25/230** ký tự;
  motorcycle riêng **4/173**, **7/173**. Không cộng hai mẫu số nguồn.
- CarTGMT CPU inference wall/crop khoảng 16,3ms FastPlate /19,7ms English;
  đo cụ thể trong summary (hai dòng English hai lần inference). CPU process
  time cũng ghi riêng (tính các thread); RSS peak **của cả process hai model**
  **121,8MiB**, không gọi là RAM riêng từng model. Không suy ra server/GPU.
- Màu/mức che của 49 crop đều pending: có strata `pending`, chưa có số liệu
  xác nhận riêng biển vàng hoặc che khuất. 29/20 là số chuỗi normalized GT
  khác nhau, không chứng minh 49 xe/capture độc lập. Bbox là manual; chưa
  đo chất lượng crop detector/recall hoặc accuracy tại xưởng.
- CLI sẵn sàng cho nhãn JSON mới, xuất raw/visible_text cho crop partial hay
  unknown có bố cục/split xác nhận. Không tính `?`/unknown là GT toàn biển;
  chúng ngoài mẫu số exact/CER full, không khôi phục ký tự bằng OCR/format.
  Không tự chọn variant hoặc threshold theo kết quả này.

### Phase D — augmentation online chuẩn bị, chưa train

- Module `edge-agent/offline_vision/camera_augmentation.py`; output
  `augmentation-v3/`: adapter config, camera stats, manifest/hash, 140 preview
  (28 real reference +112 biến thể), 7 contact sheets và HTML.
- 47 bbox camera đã xem dùng đo luma/contrast/độ nét/kích thước. Plate-height
  p10/median/p90: **10,6/18/26,4px**. Glyph-height proxy trên 15 crop có
  readability/layout/line separator xác nhận: **9/10/11px**. Đây là connected
  component proxy, không phải character bbox GT. Không coi chiều cao biển
  18px là chiều cao từng ký tự, và không dùng upscale làm độ phân giải native.
- Brightness shift ±0,1093 từ luma quantile; contrast khoảng 0,801–1,25;
  downscale về glyph-height proxy 9–11px, chỉ giảm nếu ảnh nguồn lớn hơn.
  Gamma, glare/shadow/night+noise; rain/fog/dust; motion/defocus; JPEG/HEVC;
  geometry/perspective nhỏ + jitter bbox; che 0–50% chiều cao dòng trên;
  saturation ±2%, không hue shift/horizontal flip.
- **Giới hạn hiệu chỉnh:** chưa có night/rain/fog/pose/codec reference đủ
  đa dạng. Các biên độ ấy là stress preset có giới hạn được ghi rõ trong
  config, chưa gọi là phân phối suy giảm camera đã đo. Cần duyệt contact
  sheet và bổ sung camera thật trước fitting. Không báo augmentation cải
  thiện OCR khi chưa train/đánh giá độc lập.
- Seed khóa theo seed/epoch/sample_id/draw. Val/test trả pixel và transcript
  nguyên vẹn; không materialize augmentation thành dataset, không nhân bản
  GT và không tự chia tập. Preview dùng ảnh camera hiện có chỉ để minh họa.
  Test camera độc lập tương lai không dùng chỉnh biên độ/threshold.
- Bbox jitter clip ảnh và đánh dấu `may_cut_glyph`; nếu crop vào bên trong
  GT bbox, không eligible cho native FastPlate training khi chưa có character
  boxes. Che dòng trên có row transcript explicit thì thay dòng trên bằng
  `?`, giữ dòng dưới; không có row mapping thì mask toàn chuỗi bảo thủ.
  Không đoán vị trí từng ký tự bị che theo spacing đều. Không có transcript
  hoặc có `?` không eligible cho native trainer hiện tại.
- HEVC thật đã chạy bằng FFmpeg/libx265 một frame CRF28, pad cạnh đến size
  codec rồi trả kích thước native; không gọi JPEG là HEVC. Chỉ là codec stress
  một frame, chưa tái tạo temporal compression của camera.

### FastPlate training config và giới hạn tích hợp

Đã đọc code chính thức pinned `9ce7a5b64a939aa421c243b331d42e6bc25ffd44`
(version1.1.0; MIT): [CLI train](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/fast_plate_ocr/cli/train.py),
[loader](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/fast_plate_ocr/train/data/dataset.py).
Code/hashes nguồn lưu ở `augmentation-v3/upstream/`, attribution/license đã có
trong notices. Albumentations2.0.8 MIT trong venv augmentation riêng;
versions cần thiết khóa trong `dependencies.txt` (OpenCV4.12.0.88).

- CLI có `--augmentation-path` → `A.load(..., data_format='yaml')`.
  Đã xuất **`fastplate.albumentations.yaml`**, A.save/load và actual-image
  transform parity với explicit `set_random_seed` đạt.
- YAML native chỉ gồm brightness/contrast, gamma, motion/defocus, JPEG.
  Loader native resize trước augmentation, tạo y trước `transform(image)`;
  không có label-aware hook/`?` trong alphabet model hiện tại. Adapter native
  crop/downscale/HEVC/jitter/occlusion không giả vờ đã nối vào trainer.
  Cần adapter dataset/masked-loss được kiểm chứng riêng trước train masked GT;
  không đổi `?` thành pad `_` hay ký tự OCR mong đợi.
- YAML không serialize RNG Compose seed; CLI chỉ đặt seed Keras/Python/NumPy.
  Khi tích hợp thực sự phải đặt Albumentations seed/sample/epoch rõ ràng.
  `camera_augmentation.augment` hiện đã deterministic. Chưa dùng YAML để train.

### Lệnh và kiểm chứng

```bash
# Tạo bản review mới, output phải chưa tồn tại; không ghi đè dữ liệu đã gán.
edge-agent/.venv-training/bin/python scripts/d05j-expand-review.py \
  --csv /Users/nguyen_bao/Downloads/labels.manual.csv \
  --output data/offline-vision/runs/d05j-expanded-NEXT

# Sau khi người dùng xuất JSON từ review chính, dùng đúng dataset UUID/root.
edge-agent/.venv-training/bin/python scripts/d05j-benchmark.py \
  --review-root data/offline-vision/runs/d05j-expanded-20261007/cartgmt \
  --labels /Users/nguyen_bao/Downloads/labels.d05j.cartgmt.json \
  --output data/offline-vision/runs/d05j-benchmark-NEXT

# Lần thực tế đã chạy dùng CSV-imported inventory64, không phải template419.
edge-agent/.venv-training/bin/python scripts/d05j-benchmark.py \
  --review-root data/offline-vision/runs/d05j-diverse-review-20261007-v2 \
  --labels data/offline-vision/runs/d05j-expanded-20261007/imported/labels.imported.json \
  --output data/offline-vision/runs/d05j-expanded-20261007/benchmark-final-v2

edge-agent/.venv-augmentation/bin/python scripts/d05j-prepare-augmentation.py \
  --output data/offline-vision/runs/d05j-augmentation-NEXT

edge-agent/.venv-training/bin/python -m pytest edge-agent/tests -q
```

- Full edge-agent: **149 passed,0 failed**, 1 warning duplicate ZIP fixture
  có chủ đích, 3,65s. 17 test mới gồm bbox/seed/label masking/val-test/empty GT,
  source suggestion không thành GT; Node chạy JS editor thật kiểm tra pending,
  xác nhận, autosave restore, JSON export/import uint64 và reject tamper.
- Browser thực kiểm tra main419/21trang, paging21/419, autosave; fixture riêng
  kiểm tra bbox/correct cần layout/split. Việc đợi download event trong IAB
  timeout, vì vậy export/import được kiểm chứng bằng unit JS, không tuyên bố
  đã kiểm tra native-download end-to-end. Fixture không vào benchmark/data GT.
- Hash/inventory/source/baseline/models/Phase2 bất biến kiểm tra ở
  `verification.json`. Git toàn untracked như trước; `git diff --check` sạch,
  không có tracked baseline để báo diff. Không commit dữ liệu/ảnh/models.
- Chờ review/condition tags/camera đa dạng; chưa huấn luyện, thuê GPU, thay
  database, D02/S03, token, volume hoặc các event nghiệm thu.
