# D05k — Đa dạng OCR và fine-tune FastPlate có giới hạn

Ngày 08/10/2026, Asia/Ho_Chi_Minh. Trạng thái: đã hoàn tất dữ liệu, CUDA preflight, train có giới hạn, export,
tải về và đánh giá. Model mới **chưa cải thiện trên test đã khóa**; giữ pretrained
trong runtime. Hoàn tất thử nghiệm D05k, chưa đạt tiêu chí thay model.

## Quyết định và ranh giới

- Gold chỉ validation/test. Câu “gold không thuộc test” trong bước4 không áp
  vào train vì quyết định đã chốt gold chỉ val/test có ưu tiên; gold train=0.
- Camera185 luôn test chính cho OCR, kể cả crop có source_split=train trong
  task detector cũ. Không dùng nhãn camera để fit recognizer lần này.
- Chỉ source hints +hai raw recognizer đồng thuận là silver; không gọi silver
  là người xác nhận. Những nhãn review mới dành đợt đánh giá sau, không thay test.
- Chỉ đạo mới của người dùng 08/10 cho phép xử lý dữ liệu và đưa lên GPU đã
  cấp khi cần; thay yêu cầu chờ duyệt contact sheet/Mac trước. Contact sheet
  vẫn bàn giao. Không thuê mới, không destroy/stop instance bằng tool.
- D02/S03, token, volume, database, Windows và detector D05f giữ nguyên.

Root local: `data/offline-vision/runs/d05k-20261008/`.
Trang tổng hợp: http://127.0.0.1:8768/d05k-20261008/index.html
Server loopback8768 hiện có được tái dùng, không mở cổng mới.

## 1. Khóa gold và baseline trước silver/generator

`evaluation/evaluation.lock.json`, SHA256
`54e361cbd7b8df760a7ab861923413d0abb3a43d4853cb0710b1f7870ffe83a6`.
137 crop: camera88 +gold công khai49; tất cả nativePNG, lưu hash/source/bbox,
layout/readability/nhãn và provenance. Xác minh mọi47bbox thủ công camera
D05f đã có trong D05i. Readability theo từng crop D05i có ưu tiên; không nâng
partial thành GT toàn biển từ transcript cấp track D05f. Ba frame D05j mới
chưa xác nhận được giữ ngoài tập. Không có export mới trong Downloads tại lúc kiểm kê.

Gold công khai chia trước inference theo chuỗi biển, union exact crop pixel và
crop dHash≤4, seed185, khoảng60%test/40%val theo source/layout. Cùng nhóm không
sang split khác. Public vehicle/capture ID chưa biết: không tuyên bố chống
leakage hoàn toàn. CarTGMT và motorcycle giữ mẫu số riêng.

FastPlate CCT-S v2: whole/original, RGB linear stretch128×64, không padding
ngoài graph, normalization trong graph, argmax10position heads, strip pad `_`;
không CTC, không ràng buộc format để đổi prediction, không chọn biến thể bằng test.

| Split/nguồn | Đúng toàn biển | CER lỗi/ký tự | Chuỗi GT khác nhau |
|---|---:|---:|---:|
| Test camera readable_full |26/26|0/208|1|
| Test camera partial |Không có GT toàn biển,7crop|Không xác định|0 fullGT|
| Test camera unreadable |Không có GT toàn biển,55crop|Không xác định|0|
| Test CarTGMT |17/17|0/134|17|
| Test GreenParking motorcycle |9/12|3/104|12|
| Val CarTGMT |11/12|1/96|12|
| Val motorcycle |7/8|1/69|8|

Giữ raw/known_lines cho partial. Whole recognizer không trả ranh giới dòng,
không cắt prediction theo GT để tạo metric dòng. Quan sát D05i5/7 khớp
transcript D05f là chẩn đoán riêng, không cộng vào exact/CER này.
Kết quả D05i Phase2/3, D05j cũ khóa nguyên vẹn. CSV export ban đầu lỗi do
public rows có thêm original_sha256; đã sửa union columns và xuất lại từ
baseline.json có sẵn, không thay nhãn/rows hoặc rerun chọn biến thể.
Hash các đầu ra baseline ở `evaluation/baseline.hashes.json`.

## 2. Silver và hàng đợi review

Tái dùng419CarTGMT ảnh native đã dedupe và proposals detector D05f SHA
`5233aa1b66331feeac6fb1f04e8cf7b5c5104ef1f04578798f3fd0386388794c`.
Policy ghi trước inference: đúng1proposal, score≥.75. Hai proposals hoặc
score thấp →review. Gate detector này chưa phải xác suất bbox đúng được hiệu chỉnh.
FastPlate whole/original; English original và row projection image-only nếu
thấy2hàng. Row split là hypothesis, không GT, không chọn theo source/OCR đúng.
Chỉ normalize chữ hoa/khoảng trắng/chấm/gạch nối; không O↔0/I↔1.
Cả hai raw normalize phải khớp mọi gợi ý nguồn và parser VN subset D05i.
Ngoài subset chuyển review, không tuyên bố biển bất hợp pháp.

- **150 silver**,110chuỗi khác nhau, `label_origin=silver`, train riêng.
- **252 review**:244bất đồng OCR,6proposal nhiều/thiếu,2score thấp.
- **17 loại**:15liên quan gold/crop gần trùng,2silver gần trùng với nhau.
- Loại cả val lẫn test theo hash file/native crop pixels +crop dHash≤4 và
  chuỗi đã biết. Giữ cả29K52755 partial như holdout identity từ D05f.
  dHash là heuristic triage, không chứng minh mọi capture/xe công khai độc lập.
- `silver/plan.json`, `silver.labels.json`, `audit.json`; incoming/gold gốc giữ.
- `silver/review/label.html`: tái dùngD05b/D05j, sắp bất đồng giảm dần,
  lọc riêng OCR/bbox/format,20ảnh/trang, autosave/JSON. Source/raw là gợi ý;
  không tự vẽ bbox thành gold, không train ảnh không có transcript hợp lệ.

## 3. Synthetic

Canonical **synthetic-v2/**:1024chuỗi ngẫu nhiên khác nhau,342white/341yellow/
341blue,512một dòng/512hai dòng. Held-out strings không được render vào train.
Renderer approximate520×110 hoặc330×165 tỷ lệ, glyph boxes theo nét font thật,
normalization transcript không thêm/sửa ký tự. Render lớn→geometry/jitter có
margin→downscale glyph9–11px→blur/weather/codec native→official resize128×64.
Che chỉ margin, <1/3 **và không giao bất kỳ glyph bbox nào**; vi phạm reject,
không dùng ?/pad làm ký tự bị che. Không flip ngang; màu chỉ nhẹ.

Tái dùng `camera_augmentation.py`/config D05j, seed theo epoch/sample/draw.
HEVC thật bằng FFmpeg/libx265 một frame; không gọi JPEG là HEVC. Night/rain/
geometry là stress preset chưa hiệu chỉnh bằng camera đa điều kiện. D05j
calibration được giữ từ trước, không chỉnh theo kết quả test D05k.
48preview/contact sheet cạnh camera test ở `synthetic-v2/review.html`.
Synthetic bản đầu giữ để truy vết, không dùng train: bảnv2 chuyển blur/codec
sang raster native sau downscale thay vì render lớn.

Font [Roboto Condensed](https://github.com/google/fonts/tree/69d0549e8fc7ad72e1531734c81237be401ec4fd/ofl/robotocondensed),
SIL OFL1.1, license/hash giữ trong manifest. Đây là font gần đúng, không khẳng
định font dập biển chính thức. Không tạo biển đại diện đăng ký có thật.
Car/truck5digits, tập provincecode quen thuộc, blue chỉ11seri; white/yellow20seri.
Cơ sở mẫu: [TT79/2024](https://vanban.chinhphu.vn/?pageid=27160&docid=211945)
Điều37/Phụ lục04 và [giải thích Bộ Công an](https://bocongan.gov.vn/bai-viet/nhan-dien-mau-sac-seri-ky-hieu-bien-so-xe-cua-co-quan-to-chuc-ca-nhan-tu-01012025-d1-t1617).
Đã rà sửa đổi [TT51/2025](https://vanban.chinhphu.vn/?pageid=27160&docid=214486)
và [TT37/2026](https://vanban.chinhphu.vn/?pageid=27160&docid=217949): phần sửa
TT79 ở TT37 liên quan thủ tục đăng ký, không đổi quy tắc seri/màu thông thường
được dùng cho generator này. Không bao phủ mọi loại xe/biển ngoại giao/quân đội/
motorcycle hoặc seri đặc biệt; parser là subset hỗ trợ, không validator đăng ký.

## 4. Gói, môi trường và train thực tế

Gói **đã train**: `data/offline-vision/training-packages/d05k-first-ocr-v3.zip`.
SHA-256 `a40e11bcd7a981fd70b0024e5e5f7456c94150a3df64decfb3fd2921727fab9e`;
đã đối chiếu remote trước giải nén. Run `/workspace/d05k-run-20261008/package-v3`.
Bản v1/v2 và ZIP gốc giữ để truy vết.

Gói **tái lập có sửa export/launch**: `data/offline-vision/training-packages/d05k-first-ocr-v4.zip`.
SHA-256 `4f417855e8e29feca294a1f5b2ff240d6c4c44165e27f74662266854f914fddc`.
Remote giải nén mới, xác minh 1.407 file; dataset, config, pretrained và evaluation
khớp v3 từng hash. v4 sửa đường export và bổ sung runner/dependencies, không đổi
phương pháp train hoặc train lại để chọn kết quả. Lệnh inspect và export trong
README được kiểm tra trên v4 với checkpoint v3. Không đóng gói .env, token,
database, full repository hoặc video; chỉ crop, model, code offline và thông tin
cần thiết. Quyền dữ liệu công khai chưa có giấy phép phân phối lại toàn bộ;
gói dành cho chạy riêng theo ủy quyền của người dùng.

### Model và cấu hình

FastPlate MIT pinned `9ce7a5b64a939aa421c243b331d42e6bc25ffd44`, tái dùng
build_model/cce_loss/target_transform chính thức.
[CLI train](https://ankandrew.github.io/fast-plate-ocr/latest/training/cli/train/)
và [weights release](https://github.com/ankandrew/fast-plate-ocr/releases/tag/arg-plates).

- Trainable Keras: `dc6db494714d88e1fb0a21b4e4e96089842dd5440418262abfc382454453c2c8`.
- Model config: `244c3c712205750e9747bca4707cd553a84005f41959745bff676b0fca8faba3`.
- Pretrained ONNX: `384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b`.
- Vocab 37: 0–9, A–Z, `_`; 10 position heads. Load strict, skip_mismatch=false:
  nạp 192 tensors/1.061.339 phần tử; không bỏ weight do mismatch. Sau nạp full
  model, loại 22 tensors của region branch khỏi graph OCR; giữ 977.382 parameters.
  Không đổi plate head/vocab. Optimizer mới cho fine-tune.
- Keras 3.13.2, PyTorch 2.14.0+cu126, CUDA 12.6, RTX 3090 Ti 24.564 MiB,
  driver 550.163.01. Venv riêng `/workspace/d05k-venv`; không đổi driver/services.
- Trước optimizer update: Keras/pretrained ONNX trên 20 val khớp 20/20 raw,
  max probability error 5,22e-7, tolerance cố định 5e-4.
- Mỗi epoch: 150 silver (mỗi crop một lần) + 150 synthetic lấy không hoàn lại
  từ pool 1.024. Batch 16, 19 batch/epoch, batch cuối 12; drop_last=false.
  Tỷ lệ 1:1 có cấu hình. Lặp qua epoch có chủ đích; không nhân bản file/sampler vô hạn.
- Augmentation online có seed theo sample/epoch/draw, trước preprocessing
  chính thức. Loader upstream augment sau resize nên dùng adapter native hiện có.
- Seed 185, LR 1e-5, AdamW, cosine floor 0,3, weight decay 1e-4, clipnorm 1.
  Giới hạn 8 epoch / 240 step / 1.200 giây tổng qua resume; outer timeout 1.260 giây.
  Không tự restart. `.keras` lưu optimizer và scheduler iterations; state lưu vị trí.
- Chọn **checkpoint fine-tune** bằng source-macro exact trên gold validation,
  tie bằng CER, tie tiếp giữ epoch sớm nhất. Initial pretrained là comparator riêng.
  Không dùng test/camera để chọn checkpoint, threshold hoặc preprocessing.

### Preflight và vòng train

CUDA preflight hai batch thật đạt: loss 0,14476454 / 0,14528291, hữu hạn;
compute batch 0,464 / 0,246 giây (không gồm loader). Lưu/load checkpoint đạt,
optimizer iterations=2, mọi optimizer array giữ nguyên, prediction resume
khớp atol=1e-6. Validation 18/20. Peak VRAM 4.497.621.504 bytes (~4,19 GiB).
Ảnh batch/metadata ở `gpu/preflight/`; weights preflight không dùng cho train.

Train trong tmux `d05k-ocr-fixed`, kết thúc tự nhiên sau **8 epoch, 152 step,
79,268 giây**, optimizer iterations=152; 19 batch mỗi epoch đúng như manifest.
Epoch đầu 10,29 giây, các epoch sau khoảng 9,5–9,7 giây. Không dừng vì metric
chưa tăng. Cả 8 lần validation đều 18/20, macro exact 0,8958333, CER 2/165;
`best.keras` là epoch 1 theo tie policy; `last.keras` là epoch 8.

Lỗi vận hành đã sửa: FFmpeg probe stdin kết hợp process group của GNU timeout
trong tmux gây SIGTTIN, dừng preflight trước optimizer update. Abort lần preflight
bị dừng, lưu log, runner thêm `exec </dev/null`, rồi preflight mới đạt. Không đổi
augmentation để né lỗi. Lỗi selector ban đầu đã sửa nhận head 10×37.

### ONNX và tải về

PyTorch 2.14/Keras exporter gặp hai lỗi: ONNXScript 0.5.6 thiếu torch_2_11;
0.7.2 qua bước import nhưng Dynamo lỗi data-dependent guard. Legacy exporter
cũng lỗi convolution kernel shape. Giữ nguyên checkpoint, dùng backend
TensorFlow CPU 2.20.0 + tf2onnx 1.17.0 qua
[Keras ONNX export](https://keras.io/api/models/model_saving_apis/export/).
Đây là chuyển định dạng, không fitting hoặc chọn lại checkpoint.

Lưu prediction gốc Torch/Keras trước chuyển backend; so cả TensorFlow/Keras và
ONNX với prediction đó trên **137/137** native crop đã khóa. Raw khớp hoàn toàn,
max absolute error **3,06964e-6**; atol=1e-4, rtol=1e-3 cố định. Input float32
NHWC `[1,64,128,3]`, RGB 0–255, normalization trong graph, opset 17.
Export replay từ README v4 cũng đạt 137/137, cùng sai lệch 3,06964e-6.
Hash ONNX replay khác do graph được tạo lại; không tuyên bố export byte-identical.
Bản đánh giá và bàn giao dùng hash ONNX v3 ở dưới; không thay bằng replay.

Tên file `detector-ocr.onnx` do adapter đặt; đây là **recognizer OCR**, không phải
detector biển số. Detector D05f giữ nguyên.

- Checkpoint best SHA-256: `2dab4384b33d181791b0371ec78d708fa09aac0c95c22512193a38ab5ee6e912`.
- ONNX SHA-256: `cf675fce2a74fd8302e68bbbe59070eed529cec4a67aba195d7d572401a4e664`.
- ZIP kết quả: `gpu/d05k-results.zip`, SHA-256
  `da1c98fd147b0a417260ca925a53d6db2d0bec89b3b2b79c718fc456087d5618`.
- Tải về Mac và đối chiếu **48/48** file với manifest remote, hash ZIP khớp.
  Có best/last/initial, config, state, log, preflight, parity, dependencies,
  license, hash; không cần giữ GPU để bảo toàn kết quả này.
- `gpu/export.exit` của exporter cũ vẫn giữ trạng thái lỗi; **export-tf.exit=0**
  và parity là bằng chứng export cuối thành công. Không sửa log lịch sử.

## 5. Kết quả trên test khóa và quyết định runtime

Cùng FastPlate whole/original, không thử thêm biến thể sau khi xem test.

| Test | Pretrained exact | Fine-tuned exact | CER trước → sau | Chuỗi GT khác nhau |
|---|---:|---:|---:|---:|
| Camera185 readable_full |26/26|26/26|0/208 → 0/208|1|
| CarTGMT |17/17|17/17|0/134 → 0/134|17|
| GreenParking motorcycle |9/12|9/12|3/104 → 3/104|12|

- Camera đủ đọc: toàn bộ một dòng, 13 frame với manual/detector crop thành
  26 crop tương quan. Camera hai dòng gồm 35 crop nhưng không có GT toàn biển
  đủ đọc, **không có mẫu số exact toàn biển cho nhóm này**.
- CarTGMT một dòng 11/11, hai dòng 6/6, cả hai model; motorcycle hai dòng 9/12.
- Camera readable_partial 7: GT chỉ dòng dưới `52755`, không chấm exact/CER
  toàn biển. Raw trước/sau đều giữ nguyên; 5/7 raw khớp transcript cấp track
  `29K52755` đã xác nhận D05f. Đây là **quan sát chẩn đoán theo transcript D05f**,
  không gộp bảng gold toàn biển; không suy ra ký tự bị che đã được nhìn thấy.
- Camera unreadable 55 không chấm exact/CER. Sáu raw prediction thay đổi trong
  nhóm này; không có bằng chứng chúng tốt hơn. Giữ là gợi ý/unknown cần xác nhận.
- Màu biển và mức che vẫn pending trong gold: không tự suy nhãn hoặc báo
  accuracy biển vàng/xanh/container bị che. Metrics JSON có strata pending rõ ràng.
- Validation cũng giữ Car 11/12, motorcycle 7/8. Không đánh giá last để chọn theo test.

**Không đề xuất thay runtime**: secondary không kém nhưng camera không cải thiện.
Baseline đã chạm trần 26/26 trên chỉ một biển rõ; silver chọn bằng đồng thuận
cũng thiên về mẫu dễ. Thử nghiệm này không chứng minh synthetic vô ích hoặc
model lớn/nhỏ là nguyên nhân. Cần gold test mới đa biển/lượt xe/ánh sáng, nhất
là hai dòng đọc đủ và màu/che xác nhận, trước một đợt so sánh khác. Không kéo dài
training/chỉnh LR theo test hiện tại.

Ảnh/GT/raw trước-sau: `comparison/review.html`; số liệu và strata:
`comparison/comparison.json`, CSV và hash. Bảng này không phải accuracy toàn
camera/xưởng; public vehicle/capture IDs và overlap với pretrained train chưa biết.

## 6. Lệnh và kiểm chứng

```bash
# Repo Mac: đánh giá checkpoint đã chọn, output mới, không overwrite test/nhãn.
edge-agent/.venv-training/bin/python scripts/d05k-evaluate.py --evaluation data/offline-vision/runs/d05k-20261008/evaluation --results data/offline-vision/runs/d05k-20261008/gpu/results --output data/offline-vision/runs/d05k-20261008/comparison-new
# README gói v4; từ thư mục giải nén, dependencies/backend được cài riêng.
exec </dev/null
export KERAS_BACKEND=torch
python -m offline_vision.ocr_finetune inspect --root . --output inspect
python -m offline_vision.ocr_finetune preflight --root . --output preflight
python -m offline_vision.ocr_finetune train --root . --output results
python -m offline_vision.ocr_finetune train --root . --output results --resume
python -m offline_vision.ocr_finetune export --root . --output results --resume
# Runner có timeout/tmux: bash run-bounded.sh "$PWD"
# Export chạy Torch reference rồi TensorFlow CPU riêng, không cần GPU mới.
```

Không chạy lại lock vào đường dẫn cũ; CLI từ chối overwrite. Nếu thêm gold mới,
đó là đợt đánh giá mới, không sửa bộ đã khóa để tăng điểm. Review 252 mục
bất đồng và contact sheet synthetic có sẵn; không yêu cầu gán tay toàn bộ CarTGMT.

Full edge-agent **164 passed, 0 failed, 3,82 giây**, một warning ZIP duplicate fixture có
chủ đích. Tests thêm: silver/raw agreement, proposal gate, gold/dHash/string
leakage, split union/seed, finite epoch/cấm gold train, row hypothesis, safe cover,
jitter, native downscale/seed. Browser đã kiểm tra filter 8 bbox / 244 OCR, phân trang và tải đủ 137/137
ảnh review trước/sau; không gán nhãn thay người dùng. Gold/Phase2 cũ được xác minh hash.
Git diff --check sạch; repository vẫn toàn untracked như trước, chưa có tracked
baseline để báo diff đầy đủ. Data/models ngoài Git. Không thao tác database.

GPU hiện không còn job train; sau khi kết quả đã tải và hash xác nhận, người dùng
**có thể Stop instance** để dừng chi phí compute. Agent không Stop/Destroy instance.
