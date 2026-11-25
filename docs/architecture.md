# Kiến trúc nền tảng

## Thành phần

- **Web:** React 19.3.0, TypeScript 7.0.2, Vite 8.3.2, Tailwind CSS 4.3.3 và
  các primitive theo cấu trúc shadcn/ui. Web chỉ gọi HTTP API.
- **API:** FastAPI 0.118.2, SQLAlchemy 2.0.43, Alembic 1.16.5, psycopg
  3.2.10, Argon2-cffi 25.1.0; một modular monolith Python, cấu hình qua biến
  môi trường.
- **Database:** PostgreSQL 17.5; Docker Compose dùng volume named để giữ dữ liệu.
- **Edge agent:** tiến trình riêng dự kiến cho camera/OCR/đầu cân, chưa tạo ở
  D00.

Dependency frontend khóa bằng `package-lock.json`; dependency Python khóa bằng
`backend/uv.lock`. Compose image chọn Python 3.13.5, Node 20.19.4 và PostgreSQL
17.5. Nền tảng local là macOS arm64; chọn image chính thức đa kiến trúc và
không yêu cầu CUDA.

## Luồng đăng nhập D01

```text
Trình duyệt ── same-origin /api ──> Vite proxy ──> FastAPI ──> PostgreSQL
      │                                  │               ├─ users/facilities
      ├─ HttpOnly session cookie ────────┘               ├─ auth_sessions (hash)
      └─ CSRF token trong memory ── X-CSRF-Token ────────└─ account_audit_logs
```

Cookie chứa token ngẫu nhiên 256-bit; database chỉ lưu SHA-256 của token. API
đọc user, role và cơ sở được phép từ database ở mỗi request. CSRF synchronizer
token được ràng buộc bằng HMAC với hash session, ổn định giữa các tab của cùng
session, trả qua JSON và chỉ lưu hash; frontend chỉ giữ token trong state bộ
nhớ, không dùng localStorage/sessionStorage. Các request thay đổi dữ liệu phải
có token ở header. `SameSite=Lax`, `HttpOnly`, TTL cấu hình; cookie có `Secure`
khi `APP_ENV` khác local/development/test.

Mật khẩu dùng Argon2id với `time_cost=3`, `memory_cost=65536 KiB`, `parallelism=4`,
hash 32 byte. Đăng nhập sai được giới hạn trong PostgreSQL để áp dụng đồng nhất
giữa các tiến trình API. Sự kiện thay đổi tài khoản/role/cơ sở, kích hoạt, vô
hiệu hóa và đặt lại/đổi mật khẩu được audit mà không lưu secret.

Các route D01: `GET /api/auth/csrf`, `POST /api/auth/login`, `GET /api/auth/me`,
`POST /api/auth/logout`, `POST /api/auth/change-password`,
`POST /api/auth/active-facility`, `GET /api/facilities`, `/api/admin/accounts`,
`/api/admin/audit` và `/api/admin/system/status`. Admin bootstrap dùng lệnh
interactive `python -m app.modules.accounts.bootstrap_admin` sau migration.

## Luồng nền tảng D00

```text
Trình duyệt ──HTTP──> React/Vite ──HTTP──> FastAPI ──SQL──> PostgreSQL
                                      ├── /api/health/live
                                      └── /api/health/ready ── SELECT 1
```

`live` chỉ phản ánh tiến trình API. `ready` thử truy vấn database và trả HTTP
503 nếu không kết nối được; payload không tiết lộ chi tiết database. D01 tạo
migration riêng cho tài khoản/facility/session/audit, không sửa baseline D00.
API log ra stdout/stderr theo mức cấu hình, không ghi URL kết nối, mật khẩu,
cookie hoặc request body.

## Local và đường mở rộng cloud

Compose local chạy web, API và PostgreSQL. `scripts/dev.sh up` đợi database,
áp dụng migration rồi khởi động API/web. `down` giữ volume. Host port mặc định
5174/8001/5433 để tránh PostgreSQL local thường dùng cổng 5432.

Dockerfile chạy Linux với Python 3.13.5 và Node 20.19.4; cấu hình qua environment để
có thể chuyển sang Linux cloud. Cloud Run/Cloud SQL, lưu ảnh object storage,
secret manager, backup cloud và mọi tài nguyên tính phí chưa được tạo/bật.

## Ranh giới miền dự kiến

`modules/accounts`, `facilities`, `trips`, `weighings`, `goods`, `evidence`,
`quality`, `devices`, `audit`, `reports` dành cho task tương ứng. D01 hiện sở
hữu schema account/session/audit và quyền đọc/chọn cơ sở; các module nghiệp vụ
khác chưa áp đặt schema hoặc quan hệ.

## D02 — vận hành thủ công

- `trips.models` sở hữu `vehicles`, `schedules`, `schedule_lines`, `trips` và
  `business_audit_logs`; `weighings.models` sở hữu `weigh_events` và
  `weigh_results`; `goods.models` sở hữu `goods_items` và
  `goods_transactions`. Alembic import metadata từ các module này.
- Mọi API D02 dùng cookie session, role và cơ sở lấy lại từ database theo D01;
  ghi dữ liệu cần CSRF. Staff/manager chỉ thao tác ở cơ sở đang được gán;
  admin được đọc nhưng bị từ chối mọi thao tác nghiệp vụ.
- Mỗi lần xe lên cân là `weigh_event`; từng số cân bất biến là
  `weigh_result`. Thay số cân tạo bản ghi mới liên kết qua
  `replaces_result_id` và lý do. Cân lại là lượt cân liên kết qua
  `reweigh_of_event_id`. Chỉ kết quả được chọn rõ ràng được dùng cho giao dịch.
- Nguồn cân trong D02 được lưu `manual`. Hai xác nhận vị trí xe và người đã
  xuống là lời xác nhận người thao tác. Kết quả chưa đủ xác nhận không được
  chọn. Không có luồng camera/OCR/đọc liên tục trong D02.
- Giao dịch lưu `NUMERIC(14,3)`. Backend tính lại cân nhập `trước - sau`, cân
  xuất `sau - trước`; yêu cầu dương, cùng trip/facility, đúng thứ tự và kết quả
  đã chọn. Giao dịch được tạo ở trạng thái `draft`; submit/confirm khóa bản ghi
  chuyến trong transaction và kiểm tra lại khoảng cân. Các khoảng kề nhau dùng
  chung một mốc được phép; khoảng chồng lấn pending/confirmed bị từ chối.
- `Idempotency-Key` giúp retry tạo giao dịch không nhân đôi. Version được dùng
  để từ chối sửa nháp bằng dữ liệu cũ. Xác nhận lặp một giao dịch đã xác nhận
  trả lại cùng bản ghi. Mọi chuyển trạng thái nghiệp vụ được ghi audit.
- Tổng quan lọc facility và ngày địa phương `Asia/Ho_Chi_Minh`; chỉ cộng giao
  dịch confirmed và dùng nhãn “lượng đã nhập/đã xuất”. Không có suy diễn tồn
  kho.

Các lựa chọn về trạng thái, xác nhận thủ công, giới hạn một giao dịch trên một
khoảng chênh lệch và chính sách hủy/thay thế là ma trận quyền/workflow của demo
D02; cần công ty xác nhận trước khi coi là quy trình vận hành cuối cùng.

## S01 — scale signal ingestion

`modules/scale_ingestion` sở hữu `scale_agents` và `scale_signals`. Agent giữ
facility/scale code ở server; endpoint chỉ xác thực Bearer token (SHA-256 hash
trong DB), kiểm tra agent và facility đang hoạt động mỗi request, không dùng
session cookie hay CSRF. Agent CLI là lệnh quản trị local, token file mặc định
được Git ignore và đặt permission hạn chế.

Batch dùng insert PostgreSQL với unique constraints agent/event và agent/sequence.
Conflict được đọc lại trong transaction để phân biệt duplicate giống nội dung
và xung đột; conflict làm rollback toàn bộ phần mới của batch. Response ACK chỉ
được dựng sau commit. Signal dùng bảng riêng, `NUMERIC(14,3)`, không cập nhật
weigh event hoặc hàng hóa D02. `observed_at_utc` là lúc PC quan sát UI, không có
thiết bị timestamp/stability proof; không thể kết luận UI còn cập nhật từ một
giá trị lặp lại.


## S03 — Theo dõi tín hiệu đã lưu

- Router `modules/scale_ingestion/monitoring.py` chỉ có GET dưới
  `/api/scale-monitoring`; xác thực bằng session D01. Bearer của agent chỉ dành
  cho ingestion S01, không cấp quyền đọc trang/API người dùng.
- Mỗi request đọc lại quyền từ database. Admin xem mọi cơ sở đang hoạt động
  theo D01; manager/staff xem các cơ sở đang hoạt động được gán. Truy cập trực
  tiếp ID ngoài phạm vi trả 404. Agent đã vô hiệu hóa vẫn có thể xem lịch sử ở
  cơ sở được phép; trạng thái này không được diễn giải là PC online/offline.
- Catalog agent phân trang kèm mẫu gần nhất bằng truy vấn con theo index hiện
  có `(agent_id, observed_at_utc)`. Lịch sử và latest sắp xếp
  `observed_at_utc DESC, id DESC`; mẫu nhận bù cũ không thay latest bởi thời
  gian nhận. Lọc UTC và phân trang giới hạn 100 bản ghi/request; không thêm
  index hoặc migration cho phạm vi này.
- `provenance.py` nhận diện đúng cặp agent/event thuộc manifest 9 event S03a
  đã đối chiếu PostgreSQL. Boolean `is_acceptance_test` là chú thích trả về,
  không phải field mới trong DB; source và toàn bộ bản ghi gốc giữ nguyên.
  Event tương lai của cùng agent không tự nhận nhãn nguồn giả. Chưa có cơ chế
  kết luận nguồn thực tế cho event ngoài manifest.
- React `/scales` dùng HTTP cùng origin với session, tải catalog rồi lịch sử
  tuần tự và đợi khoảng 5 giây sau lượt tải. Abort/timeout 8 giây, hủy timer
  khi rời trang; tab ẩn dừng tải và tiếp tục khi hiển thị lại. Lỗi kết nối giữ
  snapshot cùng bộ lọc và ghi rõ chưa cập nhật; lỗi quyền xóa snapshot.
- Thời gian API UTC/microsecond; UI hiển thị Asia/Ho_Chi_Minh, nhập khoảng lọc
  theo giờ Việt Nam rồi đổi UTC. Card latest độc lập khoảng lọc lịch sử.
  Đồ thị chỉ có các điểm rời của trang lịch sử hiện tại, không nối/nội suy.
  Bảng và đồ thị cuộn ngang riêng trên mobile.
- Không tạo/sửa cân thủ công, giao dịch hoặc quan hệ chuyến xe D02; không có
  WebSocket, Redis, microservice hoặc hạ tầng cloud trong S03.

Image web local mang cấu hình runtime `vite.preview.config.js` riêng để proxy
`/api` cùng origin tới `VITE_API_PROXY_TARGET` (Compose: `http://api:8000`).
Cấu hình này không phụ thuộc plugin React/Tailwind chỉ có ở stage build;
`npm run preview` dùng nó rõ ràng. Host port web/API/DB giữ nguyên.


## D05a — pipeline xe/biển số offline

`edge-agent/offline_vision` là package CLI local, không phải microservice và
không được đưa vào process/image API/web. Dependency Python/OpenCV CPU có
venv và requirements riêng. Entry point `scripts/offline-vision.py` chỉ gọi
package này; không import ORM/backend hoặc gửi HTTP request lúc inference.

```text
File video + camera JSON
  → decode media PTS + lấy mẫu 2 Hz
  → detect xe COCO (car/bus/truck) → track ID cục bộ
  → anchor vào polygon bàn cân → phiên ROI / grace dropout
  → chọn overview/crop xe → detector biển số riêng
  → OCR có budget / giữ raw → chuẩn hóa trình bày / các ứng viên
  → đề xuất cần xác nhận hoặc unknown → JSON / CSV / ảnh / HTML local
```

Detector/OCR có Protocol nhỏ; tách video, config/geometry, tracking, sessions,
selection, detectors, OCR, consensus và export. OpenCV Zoo YOLOX-s / LPD YuNet /
CRNN có nguồn, license code/weights, revision và checksum được khóa riêng
trong `edge-agent/THIRD-PARTY-NOTICES.md`; fetch-models là bước tải rõ ràng.
Vehicle detector không được coi có class biển số. Plate model huấn luyện biển
Trung Quốc/OCR text chung nên khả năng biển Việt Nam chưa được nghiệm thu.

ROI camera-185 phác từ video, chưa phải cấu hình đã xác nhận. Phiên dùng
bottom-center box, cần hai observation, chịu dropout ngắn và có thể nối track
mới; không có danh tính xe lâu dài. Gap/EOF không chứng minh rời bàn cân. Sau
consensus nhiều thời điểm, đề xuất vẫn needs_confirmation. Không đổi ký tự để
ép mẫu; không gộp confidence giữa model. Media clock không thành UTC nếu thiếu
anchor rõ ràng; giữ time trong video và source fingerprint để kiểm tra.

File input/evidence/models ở vùng Git ignore, không có migration hoặc DB write.
UI reviewer và adapter RTSP chỉ là đề xuất sau; chưa ghép signal/chuyến xe,
chưa tạo/sửa D02, không đổi S03 hoặc xác nhận cabin trống. Chi tiết CLI, đánh
giá có nhãn và kết quả local trong `docs/offline-vision-d05a.md`.

## D05b — dữ liệu thủ công và chẩn đoán OCR

`dataset.py` đọc video hai lượt: chọn theo khoảng thời gian, khác biệt dHash và
độ nét, rồi lưu PNG từ pixel decode gốc. Manifest khóa SHA video/ảnh, media PTS,
bbox/crop xe gợi ý và nguồn model; annotation của người dùng nằm riêng, không
lấy OCR làm ground truth. `labeling.html` hoạt động local, vẽ bbox ở tọa độ ảnh
gốc, gán layout/đường tách dòng, readability và group xe/lượt quay.

`benchmark.py` kiểm tra nhãn/provenance trước khi crop. CRNN baseline và
recognizer Paddle ONNX CPU dùng cùng crop, layout thủ công và ba biến thể cố
định; raw prediction và score model riêng. Không có nhãn readable thì không
có độ chính xác; không chọn biến thể tốt nhất từng ảnh để báo accuracy.
`duplicate_audit` giữ toàn bộ một xe/lượt quay trong một split và chặn ảnh
trùng/suspect chưa kiểm tra xuyên split. Đây là audit dữ liệu, không xác nhận
đủ dữ liệu huấn luyện hoặc đại diện camera công ty.

`sampling.py` giữ pool PNG tạm có giới hạn cho ba khoảng tuổi phiên theo media
time. OCR chỉ chạy sau khi đọc xong clip, phân lượt sớm/giữa/muộn, ưu tiên crop
có chất lượng và giảm lặp gần nhau. Pool được dọn sau export. Đây là chính sách
offline, chưa áp dụng vào RTSP. Geometry/sharpness/dHash chỉ là heuristic, không
chứng minh bbox là biển hoặc chữ đúng. D05b không import backend/ORM, ghi DB,
ghép signal, đổi D02/S03 hoặc tạo service; hướng dẫn trong
`docs/offline-vision-d05b.md`.

## D05c — chuẩn bị detector fine-tune offline

`scripts/plate-training.py` dùng package `offline_vision/fine_tune` và môi
trường `.venv-training` riêng; không import backend/ORM hoặc kết nối DB.
Raw archive/ảnh được giữ, audit manifest tách khỏi review thủ công và output
COCO chuẩn hóa class `license_plate`. Nhãn rỗng không tự là negative; camera
chưa được reviewed hoặc biển chưa định vị bị loại khỏi train. Hard negative
khóa/thanh là vùng kiểm tra, không phải một class mới hoặc toàn frame âm.

Split chặn cùng xe/capture/source, exact duplicate và cross-split similarity
chưa được rà soát; original external test không chuyển vào train/val. Chọn
checkpoint/ngưỡng bằng val, test theo plan được khóa riêng. Chỉ hai video
camera không đủ đánh giá accuracy tổng quát.

YOLOX-Nano source/COCO weights pinned, code Apache2; một head plate trainable.
Finite sampler, seed/config/data hash và bounded cumulative steps/epoch cho
resume. Preflight synthetic chỉ2 optimizersteps mỗi thử nghiệm, có batch
visualization/checkpoint roundtrip/ONNX CPU parity. ONNX adapter implement
Detector protocol; CLI D05a cho thay plate detector qua manifest optional,
không cho model synthetic làm model camera. LPD YuNet/OCR mặc định giữ nguyên.
Details và trạng thái thiếu ZIP/manual labels: `docs/plate-detector-d05c.md`.
## D05f — adaptation detector offline

Tái dùng trainer YOLOX và benchmark D05b/D05d, không thêm dịch vụ hoặc đường
ghi database. Nhãn xác nhận đầy đủ/presence tách biệt proposal; `scene_hash`
uint64 đi qua JSON trình duyệt bằng chuỗi thập phân. Group camera được giữ
nguyên qua split. Manifest/hash bất biến kiểm tra ở loader, resume và export.

`fine_tune/adaptation.py` tạo epoch hữu hạn: public một lần, camera cap20%,
chọn một biến thể ảnh gốc/crop xe mỗi parent frame; augmentation nhẹ không
lật ngang. D05d best khởi tạo model một class strict; optimizer/scheduler mới.
Public validation chọn checkpoint, camera test chỉ kiểm tra có giới hạn.

ONNX D05f giữ BatchNorm, tắt ORT optimization theo metadata để giảm sai khác
FP32. Detector interface và input BGR/top-left letterbox giữ nguyên. Parity
tensor thô và detection sau threshold/NMS có phạm vi bằng chứng riêng, xem
`plate-detector-d05f.md`; không gán quality_accepted từ số proposal/OCR.

## S03c — biểu diễn signal và giới hạn KPI

ScaleSignal vẫn là raw event bất biến; `observed_at_utc` dùng làm trục thời gian
quan sát, `received_at_utc` chỉ cho biết server nhận. API `/signals/chart` giảm
mẫu trong PostgreSQL theo bucket, giới hạn số điểm trước khi trả UI; chart và
bảng phân trang là hai truy vấn độc lập. Summary đếm mẫu theo ngày/tháng local
Asia/Ho_Chi_Minh, không cộng trọng lượng.

Hiện không có entity lượt cân quan sát. `WeighEvent`/`WeighResult` D02 là luồng
nghiệp vụ manual và không được tái dùng làm quan sát signal. Vì vậy API để KPI
observation/confirmed/review là null; dashboard không thay bằng số sample hoặc
camera_visit. Mô hình tương lai: observation chứa nhiều raw IDs và nhiều stable
segments; từng segment giữ window, count, min/max/representative và algorithm
version để replay từ raw. Xác nhận vẫn riêng, không sinh giao dịch.

## D05m — pilot vehicle visit local

- `modules/vehicle_pilot` sở hữu `camera_visits`, `camera_evidence`,
  `vehicle_predictions`, `camera_visit_confirmations`, audit và AI job/attempt/
  daily budget. `camera_visit` là phiên quan sát camera, không phải chuyến hoặc
  lượt cân D02. `scale_signal` chỉ được trả là tín hiệu gần thời gian (nếu visit
  có đồng hồ thực); không tạo quan hệ nghiệp vụ.
- Evidence binary ở persistent storage qua `EvidenceStorage`, không nằm trong
  PostgreSQL hoặc static/public path. Mỗi object dùng UUID, content signature,
  size/hash, temporary write + atomic replace và manifest DB `pending/stored/
  missing`. Đối soát hiện báo trạng thái; không tự xóa file mồ côi.
- Route `/api/vehicle-pilot` dùng session D01 và CSRF khi ghi. Phạm vi cơ sở
  được tính lại từ DB; endpoint nội dung ảnh cũng yêu cầu quyền. Scale Bearer
  token chỉ gọi ingestion/heartbeat, không được dùng ở route người dùng.
- Prediction là append-only; confirmation có version và audit để phát hiện
  cập nhật cạnh tranh. API trả muộn không có endpoint ghi đè confirmation. Không
  có route nào sửa trip/weigh/goods D02.
- `modules.vehicle_pilot.replay` chạy CLI rời, gọi pipeline D05a offline bằng
  subprocess và ingest bundle vào DB ứng dụng theo ID ổn định. Mặc định chọn
  detector ONNX D05f threshold 0.25, model FastPlate pinned whole/original.
  Replay không suy ra giờ thực nếu thiếu `video_start_utc`.
- `modules.vehicle_pilot.worker` hiện chỉ là mock queue worker có claim/lease;
  `mock_completed` ghi rõ không inference, không billable, không tạo prediction.
  Provider thật bị khóa cho tới khi model vision, payload ảnh/schema, giá,
  chính sách downstream và credential được xác minh.
- `scale_agent_heartbeats` là snapshot tối đa một dòng/agent, ghi heartbeat v1
  độc lập với `scale_signals`; UUID + sequence idempotent, sequence cũ không
  ghi đè snapshot mới. Client gửi 30 giây/lần, độc lập threshold. UI đo liên lạc
  bằng `received_at_utc` server: <=90s đang liên lạc, >90–180s chậm, >180s mất;
  reader empty/error được tách riêng. Không có heartbeat/signal không chứng minh
  PC offline hoặc cân bằng 0; nếu API không truy cập được UI đánh dấu snapshot
  không cập nhật thay vì đổi trạng thái PC. Admin thấy telemetry kỹ thuật;
  manager/staff bị giới hạn theo cơ sở D01. Chi tiết payload/ACK Windows trong
  `windows-scale-heartbeat-handoff.md`. Hợp đồng S02 batch không đổi.
- Compose giữ web 5174/API 8001/PostgreSQL host 5433. PostgreSQL bind loopback;
  evidence dùng named volume. API, web và worker không đọc RTSP trong request.

## D05m4 — camera live local

Tiến trình `app.modules.vehicle_pilot.live_worker` chạy trên Mac độc lập API/web,
dùng chung `offline_vision.pipeline.process_frame`, D05f và FastPlate pretrained.
Capture PyAV/Keychain → latest-frame queue 2 → inference/ROI/tracking → state +
outbox SQLite → persistence module vehicle_pilot/PostgreSQL. API có nhiều worker
không tạo camera loop. Preview và diagnostic dùng quyền D01/cơ sở, không static public.

`camera_runtime` giữ một health snapshot/camera; `camera_diagnostics` giữ metadata
snapshot/clip kiểm tra 24h. Binary ở bind mount cấu hình riêng dưới existing
EvidenceStorage; vehicle evidence dùng bảng/storage/retention 30d hiện có.
Ảnh native trước resize, preview giảm kích thước riêng. Không nối D02 tự động;
AI thật disabled, snapshot không tạo AI job. Chi tiết ở `camera-live-pilot.md`.


## D05m4b — camera theo sự kiện (mặc định pilot)

Worker và model dùng chung D05m4. `EventGate` lưu deadline/counters và cursor
signal trong SQLite state; idle tắt LiveSource/đóng RTSP, không decode/inference.
`scale_agent_id` được cấu hình theo agent/cơ sở đã bàn giao. Chỉ observed UTC
đủ mới (10s) và ≥1.000 kg kích hoạt; heartbeat không là trigger/điều kiện xe rời.
Chuỗi signal coalesce, cửa sổ 20s/4 ảnh, model calls hữu hạn; rearm-gap 120s
chỉ là heuristic chụp, không phải liên kết xe hay chốt cân.

CameraDiagnostic hiện có giữ process/photo/preview commands hữu hạn; camera row
lock + request UUID bảo vệ duplicate/conflict và preview lease ≤120s. Photo
chuyển capturing→saving trước ghi file; outbox/recovery hoàn tất stored sau
metadata commit. File visit có bản riêng không bị diagnostic retention 24h xóa
trước ACK. Preview-only không inference; evidence native không dùng preview
640×360. Health giữ worker reporting riêng với idle_unchecked/starting/source
lỗi/processing. D02 và schema S01/S02 giữ nguyên. Chi tiết/rủi ro trong
`camera-event-driven-pilot.md`.
