# D05a — pipeline xe/biển số offline, bước đầu

## Phạm vi

D05a là mã mới dưới D05 đã lên kế hoạch. Hoàn tất pipeline/CLI và kiểm tra các
nhánh điều khiển bằng fixture, chạy thử video local thật. **Chưa nghiệm thu
khả năng đọc đúng biển số trên camera công ty.** D05 tổng thể còn chờ nhãn thủ
công, detector biển Việt Nam phù hợp và đánh giá thêm. Không triển khai D06
RTSP/trạng thái bàn cân, D07 ghép cân/xe hoặc thay S03/D02.

CLI không gọi database/API, không ghi offline result vào ứng dụng, không ghép
signal cân. Biển chưa đọc được: `proposed_plate: null`, `recognition: unknown`,
`status: needs_confirmation`; không tạo một xe có tên unknown.

## Kiểm kê dữ liệu và môi trường

- Video thực có trên máy:
  `Video_camera/camera_185_20261004_103800-104015.mp4`;
  SHA-256 `108f1af04ea7a6189323a9ffe4e7543b9388e1e5f3a719d3aca5f204c29dcc0d`.
  HEVC, 1920×1080, time_base 1/16000, duration 132.281 giây, 3.300 frame,
  khoảng 34.6 MB. Nominal 25 fps, average hơi khác; không tính thời gian bằng
  frame index/nominal fps. Video có xe tải tiến vào bàn cân, khác ảnh UI demo.
- Đã kiểm kê repository và vùng Documents/ChatGPT; ảnh có sẵn là screenshot
  giao diện D01/D02/S03, không phải tập nhãn camera. Không giả định file ảnh
  trong chat tồn tại local. Liệt kê Downloads bị quyền macOS từ chối trong
  lượt kiểm kê; không suy ra không có file ở đó.
- MacBook Pro Apple M2 Pro, 10 core, RAM 16 GB, macOS arm64. Có FFmpeg/ffprobe
  Homebrew 8.1.2, Python 3.12.7, công cụ PyTorch/OpenCV khác trong môi trường
  global; không dùng PyTorch hoặc GPU. Global metadata OpenCV khác bản import
  thực tế nên đã tạo **venv riêng** với OpenCV headless 4.12.0.88, NumPy 2.2.6,
  psutil 7.0.0 và pytest 8.3.2; backend Python/env giữ nguyên.
- Không có weights detector xe/biển số phù hợp đã cài. Sau kiểm tra nguồn và
  giấy phép, tải riêng 3 ONNX OpenCV Zoo tổng 73.8 MB, revision và SHA khóa.
  Không tải dataset, thuê GPU hoặc tạo tài nguyên cloud.
- Video, models, fixture, ảnh và report được Git ignore (`Video_camera/`,
  `data/`). Kết quả mới đặt trong thư mục riêng, ảnh/JSON 0600, thư mục run
  0700; CLI từ chối ghi đè thư mục kết quả có sẵn.

## Chuẩn bị và chạy

Chạy từ `/Users/nguyen_bao/Documents/ChatGPT/nhu-tung-demo`.
Venv/weights local hiện đã có. Khi tạo lại môi trường trên máy khác:

```bash
python3 -m venv edge-agent/.venv
edge-agent/.venv/bin/python -m pip install -r edge-agent/requirements-offline.txt
# Cần ffprobe trong PATH. Tải weights là bước rõ ràng, không tự tải lúc inference:
edge-agent/.venv/bin/python scripts/offline-vision.py fetch-models
```

Chạy video thật bằng CPU, output mới mỗi lượt:

```bash
edge-agent/.venv/bin/python scripts/offline-vision.py run \
  --video Video_camera/camera_185_20261004_103800-104015.mp4 \
  --config edge-agent/config/camera-185.offline.json \
  --output data/offline-vision/runs/camera-185-next
```

Có thể thêm `--start-seconds 60 --end-seconds 120` để chọn đoạn. Chỉ khi có
mốc bắt đầu được người dùng xác nhận, thêm ví dụ:
`--video-start-utc 2026-10-04T03:38:00Z`. Đây chỉ là cú pháp minh họa, **không
xác nhận mốc giờ thật của video**. CLI không suy ra UTC từ tên file hoặc đồng
hồ overlay; anchor ánh xạ media timestamp 0. Thời gian ghi report dựa trên
`CAP_PROP_POS_MSEC` của decoder FFMPEG. Lượt thật đối chiếu với ffprobe PTS có
sai lệch float tối đa 1.8e-15 giây; không có timestamp tăng đơn điệu sẽ báo lỗi,
không tự tạo clock bằng fps.

## Cấu trúc và interface

| Module | Trách nhiệm |
| --- | --- |
| video.py | Probe file local, decode, lấy mẫu theo media timestamp; không nhận URL/RTSP. |
| config.py, geometry.py | Config theo camera, ROI polygon chuẩn hóa 0–1, kiểm tra giới hạn. |
| detectors.py, types.py | Interface Detector.detect(image, media_seconds); adapter xe và biển số riêng. |
| tracking.py, sessions.py | Gán box theo IoU/khoảng cách, track trong run; phiên ROI có grace độc lập track. |
| selection.py | Chọn overview bằng độ sắc nét/kích thước crop xe; crop từ pixel thật. |
| ocr.py, consensus.py | Interface OCR.cost/read; raw text, chuẩn hóa trình bày, số lần nhất quán. |
| export.py | JSON/CSV, ảnh toàn cảnh/crop, HTML và template nhãn. |
| profiling.py, evaluate.py | Đo local process, đánh giá chỉ với nhãn thủ công hoàn chỉnh. |
| fixtures.py | Video/adapter scripted riêng, kết quả ghi fixture=true. |

Detector trả bbox pixel xyxy, label, score, model và corner nếu có. Biển số
được tìm trên crop xe sau khi xe vào ROI; crop/corner lưu kèm origin để kiểm tra
tọa độ. OCR có cost cho số lượt neural inference thực tế: hai dòng dùng 2 call.
Có thể thay adapter mà không sửa tracking, hợp đồng result hoặc tạo service.

## ROI, phiên và giới hạn tài nguyên

- `camera.example.json` chỉ là mẫu. `camera-185.offline.json` là polygon bàn
  cân phác từ video đã xem, **chờ người vận hành xác nhận**. V1 yêu cầu polygon
  lồi, không tự suy ra cabin trống hoặc toàn bộ xe nằm trên cân.
- Anchor vào ROI là bottom-center bbox xe. Hai lần quan sát trong ROI để mở
  phiên. Mặc định detect 2 Hz; decoder vẫn phải đọc frame nguồn, chỉ retrieve/
  detect/vision ở mẫu được chọn (video thật 265/3300). Không bật OCR ngoài ROI.
- Tracker ghép một-một theo IoU >=0.12 hoặc khoảng cách tâm <=0.10 đường chéo.
  Track giữ 3 giây, phiên chịu dropout 5 giây; track mới có thể nối lại phiên
  gần đó khi track cũ vắng. Xe khác đang được thấy cùng frame không cùng phiên.
  Ngoài ROI liên tiếp 3 giây đóng phiên; gap vượt grace đóng với lý do mất
  detection, **không phải bằng chứng xe đã rời bàn cân**. EOF cũng không chứng
  minh rời cân. Track/session chỉ có nghĩa trong camera/run.
- Mặc định tối đa 12 lượt plate detect/phiên, cách ít nhất 3 giây media; tối đa
  8 neural OCR call/phiên, 4 crop biển số lưu/phiên, 500 phiên/run. Overview,
  annotated và crop xe được thay bằng frame có chất lượng tốt hơn, không lưu
  mọi frame. Crop biển số giữ tối đa những lần đầu trong budget; có thể thiếu
  ảnh riêng của lần đọc sau, raw read vẫn có metadata và overview hữu ích.
- Dừng OCR khi có ít nhất 3 thời điểm quan sát cho cùng chuỗi và tỷ lệ >=0.8.
  Nhiều crop ở cùng frame không tạo nhiều phiếu; các ứng viên khác/đọc rỗng
  vẫn được xét để tránh ép đồng thuận. Không đủ hoặc mâu thuẫn => unknown.
  Mọi đề xuất vẫn cần xác nhận, không phải biển số đã chốt.
- Chuẩn hóa chỉ uppercase, bỏ khoảng trắng/dấu chấm/gạch; không đổi O↔0,
  I↔1, B↔8 hoặc thêm/xóa ký tự để khớp mẫu. Bộ lọc ứng viên alphanumeric dài
  5–12 không phải luật biển Việt Nam. Raw, raw_lines, strategy, normalized,
  score theo model và các ứng viên đều giữ riêng. Không cộng/so confidence xe,
  plate và OCR; chúng không cùng thang đo và chưa calibration.
- DNN OpenCV đặt 2 thread; số thread decoder là riêng, do backend OpenCV điều
  khiển. Đây không phải giới hạn 2 core cho toàn bộ CLI.

## Đầu ra và kiểm tra thủ công

Mở `data/offline-vision/runs/camera-185-d05a-final/review.html` bằng trình duyệt
local. Report không dùng CDN hoặc gửi ảnh đi. Mỗi phiên có camera/session/
track IDs, thời điểm media, end reason, đề xuất hoặc unknown, candidates/raw,
needs_confirmation và link overview/annotated/vehicle/plate crops khi có.
`result.json` còn có config snapshot, model revision/SHA/score semantics,
video fingerprint và thống kê. `sessions.csv` là bảng tóm tắt;
`sampled-detections.jsonl` giúp xem cả detection ngoài ROI.

Không có plate detection thì `plate_crops: []`, không dựng crop biển số giả.
Liên kết bằng chứng là đường dẫn tương đối trong run; không upload vào ứng dụng.
Dữ liệu raw và ảnh không được dùng để tự tạo xe/chuyến D02.

Đánh giá dùng một file nhãn **riêng**, sau khi người xem duyệt toàn bộ đoạn
video. Điền mẫu sau với run_id thật, interval media thật và matching một-một;
xe bị bỏ sót có predicted_session_id=null, biển không đọc được có plate=null.

```json
{
  "run_id": "COPY_FROM_RESULT",
  "label_origin": "manual_review",
  "complete_clip_review": true,
  "roi_ground_truth_sessions": [
    {
      "start_media_seconds": 69,
      "end_media_seconds": 132,
      "plate_visible": true,
      "plate": null,
      "predicted_session_id": "s00001"
    }
  ]
}
```

Trên đây là ví dụ định dạng, **không phải nhãn đã nghiệm thu**. Biển đọc rõ thì
người xem tự chép toàn bộ chuỗi; không chép đề xuất của model làm ground truth.

```bash
edge-agent/.venv/bin/python scripts/offline-vision.py evaluate \
  --result data/offline-vision/runs/camera-185-d05a-final/result.json \
  --labels data/offline-vision/manual-labels.json \
  --output data/offline-vision/evaluation-new.json
```

CLI từ chối nhãn chưa review/sai run ID hoặc matching trùng/không có
interval giao nhau. Báo riêng xe ROI matched/missed/unmatched, biển visible/
found, chuỗi đúng toàn bộ, unknown và mẫu số readable. Danh sách rỗng chỉ hợp lệ khi đã đánh dấu manual_review và duyệt đầy đủ
đoạn không có xe; các tỷ lệ không có mẫu số vẫn null. Không tính accuracy từ
confidence hoặc ACK; với fixture có cờ fixture để không nhầm kiểm tra control
flow với chất lượng model. Không phải benchmark AP/mAP detector toàn frame.

## Fixture và kiểm thử

```bash
edge-agent/.venv/bin/python -m pytest -q edge-agent/tests
edge-agent/.venv/bin/python scripts/offline-vision.py fixture \
  --case short-dropout --output data/offline-vision/fixtures/new-short-dropout
edge-agent/.venv/bin/python scripts/offline-vision.py run \
  --video data/offline-vision/fixtures/new-short-dropout/fixture.mp4 \
  --fixture-scenario data/offline-vision/fixtures/new-short-dropout/scenario.json \
  --config edge-agent/config/camera.example.json \
  --output data/offline-vision/runs/new-fixture-short-dropout
```

Các case: no-vehicle, outside-roi, enter-exit, short-dropout, no-plate,
conflicting-ocr. Adapter scripted chỉ kiểm tra cơ chế, không đại diện camera
công ty/khả năng model. Có test clock VFR đối chiếu ffprobe, track đổi giữa
phiên, hai xe, gap dài, normalization không sửa ký tự, budget OCR hai dòng,
RGB preprocessing đúng, CTC và OCR CPU smoke trên crop tự vẽ. Không seed DB.
Test model smoke chỉ chạy khi đã fetch weights local; test không tải mạng.

## Giới hạn và bước tiếp theo

- Model/giấy phép/revision: [THIRD-PARTY-NOTICES](../edge-agent/THIRD-PARTY-NOTICES.md).
  LPD YuNet huấn luyện biển Trung Quốc; CRNN là text OCR chung. Lượt video thật
  chưa tìm được plate trong budget, nên chưa có kết quả đọc đúng biển công ty.
  Biển nhìn thấy bằng mắt trong crop không được giả thành model detection.
- Tracking đơn giản có thể đứt/ghép sai khi nhiều xe sát nhau, khuất lâu hoặc
  bbox đổi mạnh; chỉ chống dropout ngắn theo cấu hình. Không có danh tính xe
  lâu dài, xe/người detector không chứng minh người đã xuống/cabin trống.
- Muốn nghiệm thu D05: xác nhận ROI, gán nhãn xe/plate/readable và một số crop
  biển Việt Nam 1–2 dòng/ngày/đêm; chọn hoặc fine-tune detector chuyên biệt có
  giấy phép code/weights rõ; đánh giá giữ raw/unknown và người xác nhận.
- Bước UI được giao sau: đọc/import artifact và màn hình reviewer cùng quyền
  cơ sở, giữ dự đoán và xác nhận tách biệt. Chưa nối vào S03/D02 hoặc auto-ghép
  signal. D06 RTSP sau: adapter nguồn stream, clock rõ, reconnect/backpressure,
  giới hạn buffer/CPU và thử mất stream; phiên cần kiểm tra liên tục khi nguồn
  đổi, không xem EOF/gap là xe rời cân. Chưa triển khai các bước này.
- CPU/time là một lượt local M2 Pro, gồm model init/media/evidence; không bao
  gồm imports, hash/report cuối hoặc process ffprobe con. RAM là OS high-watermark
  của process từ lúc khởi động (có imports) cộng sampling 100ms trong khoảng đo,
  không phải RAM Docker hay toàn máy.
  Compose vẫn đang chạy. Không dùng số này để dự báo cấu hình/cloud capacity.


## Kết quả chạy local đã lưu (06/10/2026)

| Chỉ tiêu riêng | Video camera-185, model thật | Fixture short-dropout, adapter scripted |
| --- | --- | --- |
| Frame detect / frame decode | 265 / 3.300 | 20 / 100 |
| Frame có box xe | 184 | 18 |
| Box xe cộng qua các frame | 195, không phải 195 xe | 18, không phải 18 xe |
| Track được tạo | 6, không phải 6 danh tính xe | 1 |
| Phiên xe trong ROI | 1 | 1 |
| Phiên tìm thấy plate bằng detector | 0 (12 lần thử) | 1 |
| Phiên có đề xuất OCR nhất quán | 0 | 1 (`51C12345`, ba thời điểm scripted) |
| Unknown | 1 | 0 |
| Biển đọc đúng toàn bộ / độ chính xác | Chưa đánh giá: chưa có nhãn thủ công | Không dùng scripted output làm độ chính xác model |

Kết quả thật: `data/offline-vision/runs/camera-185-d05a-final/`; phiên `s00001`,
media 69.000–117.520 giây, end_reason=detection_gap_expired; không chứng minh xe
rời cân. Overview tốt nhất ở 104.520 giây. Đã xem ảnh toàn cảnh/crop xe và thấy
biển trong ảnh; detector không tìm được trong budget thì giữ unknown, không tự
lấy chữ trên container hay số sơn trên xe thay thành biển. Không có crop plate
được model tìm thấy ở lượt này. Report không suy ra giờ thực từ overlay.

Đo một lượt cuối trên M2 Pro 10 core/RAM 16 GB: 33.216 giây gồm init và media/
ảnh bằng chứng (33.088 giây loop processing), CPU process 155.444 giây;
467.98% theo thang một core (khoảng 4.68 core), 46.80% trên tổng 10 core; peak
RSS 785.629.184 byte ≈749.23 MiB. Số này là local process trong khoảng đo, chưa
đo máy rảnh độc lập/độ trễ live/cloud. Không có số GPU.

Kết quả minh họa cơ chế đồng thuận: `data/offline-vision/runs/fixture-short-dropout/`.
Biểu diễn fixture=true và tên model scripted nằm trong JSON/HTML; không nhầm
những crop/giá trị giả này với kết quả camera-185 thật.
