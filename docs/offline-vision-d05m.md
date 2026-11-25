# D05m — triển khai pilot Local + API theo lượt xe

Cập nhật 10/10/2026. D05m1 và D05m2 đã được triển khai, kiểm thử backend trên
PostgreSQL tạm, replay video thật qua backend và review bằng UI có đăng nhập.
Docker Compose local hiện đang chạy healthy; migration additive đã áp dụng tới
head trên volume hiện có, không reset dữ liệu. RTSP main stream camera .185 đã
được xác minh bằng một lần capture/giải mã live khoảng một phút; đây chưa phải
worker/preview tích hợp hoặc nghiệm thu pilot vận hành. API provider thật, lượt
xe thật và cân thật chưa nghiệm thu.

## Phạm vi đã chốt

- Local: FastAPI/PostgreSQL/web trên MacBook; worker là process riêng.
- PC cân: signal tiếp tục qua S01/S02; heartbeat là endpoint riêng.
- Camera .185 là nguồn chính; .172 đợi xác minh mapping. Live và replay được
  ghi rõ; replay chỉ có media time nếu không cung cấp clock anchor.
- AI API tối đa 3 attempts/visit, 300 attempts/ngày, 2 USD/ngày; evidence
  retention 30 ngày; bộ benchmark lưu riêng. Mọi kết quả cần nhân viên xác nhận.
- Không tạo/sửa giao dịch D02 tự động; không nối visit, signal, trip bằng OCR
  hoặc timestamp; loại định danh `tractor_plate`, `trailer_plate`,
  `painted_text`, `container_id`, `unknown` lưu riêng.

## Triển khai hiện có

### D05m1 — schema, persistence, mock

- Revision additive `e7a31c9d0f42_vehicle_visit_evidence_review`, sau revision
  S01; không sửa migration cũ. Thêm visit, evidence metadata, prediction,
  confirmation version, audit, AI job/attempt/daily budget và heartbeat.
- API `/api/vehicle-pilot`: tạo visit idempotent; lấy danh sách/detail có
  pagination; private evidence upload/content; append prediction; versioned
  confirmation; AI mock queue; heartbeat status. D01 session/CSRF/facility scope
  được kiểm tra ở backend.
- Binary file dùng root cấu hình `PILOT_EVIDENCE_ROOT`; UUID object key, MIME
  signature allowlist, max 10 MiB mặc định, quota 5 GiB/facility, hash, temp
  write + fsync + atomic rename, file/DB state `pending/stored/missing`. Không
  tự xóa file orphan. `reconcile_storage` phát hiện file/hash/state lệch và có
  thể sửa state từ file đã xác minh.
- Mock job chỉ claim/lease/persist trạng thái; không đọc ảnh, không gọi provider,
  không tạo prediction, không billable. Không bật worker nếu
  `PILOT_AI_MODE != mock`.
- `POST /api/scale-ingestion/heartbeat` dùng Bearer S01 agent; heartbeat không
  chèn signal. Contract/prompt Windows ở
  [`windows-scale-heartbeat-handoff.md`](windows-scale-heartbeat-handoff.md).
- Bổ sung D05m4a: heartbeat v1 mỗi 30 giây, UUID/sequence idempotent, chỉ giữ
  snapshot mới nhất/agent; trạng thái liên lạc dùng thời gian server, reader
  status riêng. API/UI theo scope D01; hợp đồng S02 batch không đổi. API, UI,
  migration và handoff Windows đã hoàn tất ở Mac; client Windows và live chưa
  triển khai.
- Retention mặc định 30 ngày được lưu theo từng evidence; worker riêng đánh dấu
  hết hạn, xóa binary và ghi `purged_at_utc`. Bản benchmark vẫn nằm ngoài
  evidence storage pilot.

### D05m2 — replay → API → review

- `python -m app.modules.vehicle_pilot.replay` gọi CLI D05a offline trong process
  riêng; mặc định sử dụng YOLOX-Nano D05f export
  `data/offline-vision/runs/d05f-vast-54567374/final/export/model.json`,
  threshold 0.25 đã đóng băng trong báo cáo, và FastPlate CCT-S v2 pinned
  `9ce7a5b`, whole/original. Bản kết quả giữ raw OCR và metadata model; không
  format-correct ký tự.
- Replay ingest bằng UUID5 từ nguồn/config/session; retry cùng bundle idempotent;
  ID/nội dung xung đột bị từ chối. Evidence của replay được copy vào storage
  private. Không gọi endpoint AI. Có thể dùng `--ingest-only` để gửi lại bundle.
- UI `/pilot` dùng session D01; có danh sách visit, evidence private, prediction
  local/API, nearby scale signal gắn nhãn “time proximity only”, heartbeat
  freshness và thao tác confirm/correct/unknown/split/missed. Version cũ nhận
  409; prediction không cập nhật confirmation. Poll list 5 giây chỉ khi tab hiện.
- Replay thật từ video camera-185, đoạn media 65–122s: 115 frame mẫu, 1 track,
  1 visit, 7 crop biển/7 lần OCR local. Không có nhãn đối chiếu nên prediction
  giữ unknown/cần xem lại; không tính accuracy. Trong DB/evidence root tạm, lần
  đầu lưu 1 visit + 7 evidence + 1 prediction; gửi lại bundle tạo 0 visit mới,
  báo 9 duplicate evidence/prediction/visit; D02 không có bản ghi được tạo.
- UI tạm đăng nhập D01 hiển thị visit và cả 7 ảnh private; trình duyệt tải đủ
  ảnh qua API content có quyền. Desktop 1440×960 và mobile 390×844 không tràn
  ngang sau khi sửa wrap cho hash dài trong metadata.
- 09/10 phát hiện web preview hiện lỗi kết nối do `.env` đặt
  `VITE_API_BASE_URL=http://localhost:8001`, trong khi API chỉ bind
  `192.168.1.13:8001`; URL còn thiếu prefix `/api`. Đây là cấu hình build-time,
  không phải cache là nguyên nhân gốc. Đã đổi thành `/api`, rebuild/recreate web;
  kiểm tra cùng origin `127.0.0.1:5174/` và `/api/health/live` trả 200,
  `/api/auth/me` trả 401 khi chưa đăng nhập. Web/API/DB đều healthy.

### D05m3 — provider API thật

- Chưa bật. [TrollLLM API docs](https://trollllm.xyz/docs/api-reference) công
  bố OpenAI-compatible `GET /v1/models` và
  `POST /v1/chat/completions`; model list có cờ `vision`, nhưng API reference
  không đưa ví dụ payload ảnh hoặc structured-output schema; pricing trên site
  được ghi là ước tính. [Privacy policy](https://trollllm.xyz/privacy) nói
  request được chuyển tiếp tới model providers với chính sách downstream riêng.
  Key được gửi trong chat trả `401` ở
  lần kiểm tra đầu. Thử lại `GET /v1/models` theo endpoint/API key format và
  User-Agent trong tài liệu vẫn trả `401 Unauthorized`; không gửi ảnh, không gọi
  model, không phát sinh usage/cost. Số dư credit trên dashboard không chứng
  minh key hợp lệ. Key đã dán vào chat cần được thu hồi/thay mới; không lưu key
  đó trong repo. API AI vẫn `disabled`.
- 09/10 người dùng yêu cầu lưu key vào `.env` local. Đã lưu đúng một mục
  `GEMINI_API_KEY` trong `.env` mode `0600`; file được Git ignore. Key không được
  đưa vào Compose, frontend, URL, argv hoặc log. `GET
  https://generativelanguage.googleapis.com/v1beta/models` dùng header
  `x-goog-api-key` trả HTTP 200 và liệt kê 50 model; có model Gemini hỗ trợ
  `generateContent`. Đây chỉ xác nhận key gọi được Models API; chưa xác minh
  quyền gửi ảnh, giá/model cụ thể, structured output hay downstream retention.
  Không gửi ảnh và không gọi `generateContent`. Theo [Gemini API
  reference](https://ai.google.dev/api), xác thực bằng header
  `x-goog-api-key`; [Models API](https://ai.google.dev/api/models) liệt kê model
  và supported actions. Key đã xuất hiện trong chat; nên thu hồi/thay sau khi
  hoàn tất kiểm tra.
- Chưa gọi model API thật cho tới khi chọn model cụ thể, xác minh ảnh/JSON
  output, giá thực tế và downstream retention; hiện chỉ xác nhận Models API.
  Dừng 401/403. Mock đã kiểm tra queue tối đa 20,
  giới hạn 3 job attempt/visit và 300 slot/ngày Asia/Ho_Chi_Minh. Tuy nhiên,
  trừ ngân sách 2 USD/ngày, dự trù chi phí trước request thật, usage reconciliation
  và trạng thái billing không chắc sau timeout CHƯA được nối với provider; không
  bật inference thật cho tới khi hoàn tất các cơ chế này.

### D05m4–m5 — live và cân thật

Cập nhật 10/10/2026: worker PyAV/TCP main .185 đã tích hợp health/preview và
bằng chứng chẩn đoán; xem [bàn giao camera live](camera-live-pilot.md).
Migration additive `e7a31c9d0f45` đã áp dụng; không reset volume hoặc sửa migration cũ.
Credential runtime ở Keychain; URI xác thực chỉ trong bộ nhớ, theo phê duyệt mới
của người dùng. Không cần proxy camera.

Heartbeat Windows tiếp tục cập nhật riêng. API AI thật vẫn disabled. ROI còn
provisional; visit/OCR/cân thật chỉ nghiệm thu khi có xe và người vận hành xác nhận.
Bằng chứng probe main stream 62,2s trước đó được giữ riêng ngoài repo; phiên
chạy liên tục mới được báo trong progress, không dùng probe thay nghiệm thu pilot.

## Lệnh local

Chạy sau khi Docker Desktop đang hoạt động và `.env` local đã được thiết lập:

```bash
./scripts/dev.sh up
./scripts/dev.sh status
cd backend
uv run python -m app.modules.vehicle_pilot.replay \
  --facility-code <FACILITY_CODE> \
  --video <VIDEO_PATH> \
  --camera-config <CAMERA_JSON> \
  --output <PRIVATE_RUN_DIR> \
  --start-seconds 0 --end-seconds 30
```

Mở `http://localhost:5174/pilot`, đăng nhập D01 và chọn cơ sở. Không public
evidence bằng static server.

```bash
cd backend
uv run python -m app.modules.vehicle_pilot.replay \
  --facility-code <FACILITY_CODE> --output <PRIVATE_RUN_DIR> --ingest-only
uv run python -m app.modules.vehicle_pilot.reconcile_storage
```

Tắt app bằng `./scripts/dev.sh down`; lệnh này giữ volume. Không dùng `down -v`.
Để tắt AI thật, giữ `PILOT_AI_MODE=disabled`.

## Kiểm thử / nghiệm thu còn lại

- Đã chạy trên hai PostgreSQL native database tạm đã drop sau khi kiểm tra:
  7 test D05m + 68 regression D01/D02/S01/S03 đều đạt. Một deprecation warning
  từ Starlette TestClient; không có test failure.
- Edge-agent: 162 passed, 3 deselected do môi trường không cài optional `torch`
  cho ba test training; các test còn lại đạt. `npm run build`, CLI `--help`,
  Python compile và `git diff --check` đạt. `docker compose ... config --quiet`
  đạt cú pháp.
- E2E replay thực và UI tạm đã kiểm tra idempotency, ảnh private, phạm vi D01
  trong test API, confirmation version conflict và D02 không bị ghi.
- Compose khởi động, migration và healthcheck API/web/DB đã đạt; chưa kiểm tra
  backup/restore, retention sweep trên volume chạy dài, thiếu file/quota, API
  restart khi job đang claim hoặc nhiều API process đồng thời. Đây vẫn là điều
  kiện trước khi dùng dữ liệu pilot thực tế.
- Backup/restore PostgreSQL + evidence sang môi trường tạm trước khi dùng dữ liệu
  pilot thực tế. Hiện chưa có backup/restore thực nghiệm.
- Camera live/reconnect/stream dropout/multi-vehicle/ROI, heartbeat trên client
  Windows, API thật, cost/latency, retention sweep và S03b chỉ nghiệm thu sau
  thiết bị/key được cấp và xác minh.

## Giới hạn vận hành

- Sau khi Docker được bật, Compose khởi động thành công: web `127.0.0.1:5174`,
  API `192.168.1.13:8001`, PostgreSQL `127.0.0.1:5433`. IP `.13` được đọc lại
  từ `en0` ngày 09/10; `.env` local đổi `API_BIND_IP` từ giá trị cũ `.17` sang
  `.13`. API live/ready và web trả 200; không mở router/firewall. PostgreSQL
  vẫn chỉ bind loopback. Các cổng pilot này đang được giữ chạy.
- E2E UI dùng API `127.0.0.1:8002`, Vite `127.0.0.1:5175` và database riêng
  tạm; các tiến trình/database test đã dừng/xóa sau khi kiểm tra.
- Không kết nối RTSP/CGI camera .185/.172 hoặc CANXE2015 trong lần kiểm tra này.
  Lỗi 401 cũ của camera cần quản lý xác nhận credential/quyền; không thử mật khẩu
  khác.
- Giá/model ID/vision payload của TrollLLM chưa đủ xác minh theo nguồn chính
  thức. Chính sách privacy nêu chuyển tiếp tới nhà cung cấp mô hình và điều khoản
  downstream riêng; ảnh pilot không được gửi trong lần này.
