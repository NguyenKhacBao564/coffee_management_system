# D05m4 — Camera .185 chạy liên tục trên MacBook

> Cập nhật 10/10/2026: mặc định hiện tại là `event_driven`, preview tắt và RTSP
> đóng khi idle. Số đo/chạy liên tục bên dưới là bằng chứng D05m4 trước đây.
> Chế độ `continuous` vẫn là lựa chọn cấu hình. Xem [D05m4b](camera-event-driven-pilot.md)
> cho nút kích hoạt, cấu hình và số đo mới.

## Phạm vi

Camera trực tiếp `192.168.1.185`, RTSP/TCP main, channel 1 / subtype 0,
HEVC 1920×1080 / 25 fps. Đây là **live**, không phải playback NVR. Camera
`.172`, mapping NVR và firmware chưa được nghiệm thu trong bước này.
Worker là tiến trình Mac riêng; API/web không chứa vòng đọc RTSP hoặc inference.

Nhịp cấu hình 3 Hz; thời gian xử lý thực tế được báo riêng. Chỉ chạy OCR khi
xe vào ROI. Không có xe hoặc OCR là bình thường. D05f và FastPlate pretrained
được kiểm tra hash trước khi chạy; không thay model runtime hay huấn luyện thêm.

## Chạy/dừng

Từ thư mục repository:

```bash
python3 scripts/camera-worker.py start
python3 scripts/camera-worker.py status
python3 scripts/camera-worker.py stop
python3 scripts/camera-worker.py restart
```

`start` không tạo worker thứ hai khi lock đang được giữ. `stop` gửi SIGTERM,
đợi decoder đóng và trạng thái/outbox được lưu; nếu chưa dừng an toàn, `restart`
sẽ từ chối tạo thêm worker. Worker chạy riêng khỏi terminal; không tự khởi động
sau reboot Mac. Sau reboot cần chạy `start`.

Chạy có giới hạn để chẩn đoán (dừng worker hiện tại trước):

```bash
PYTHONPATH=backend edge-agent/.venv/bin/python -m app.modules.vehicle_pilot.live_worker \
  --config edge-agent/config/camera-185.worker.json --duration-seconds 60
```

Cấu hình runtime: `edge-agent/config/camera-185.worker.json`; ROI/ngân sách
pipeline: `edge-agent/config/camera-185.live.json`. Đường storage/state là
đường tương đối repository, không phụ thuộc tên tài khoản hay đường Mac cố định.
DB local được đọc từ `.env` qua cơ chế CLI S01 hiện có; không đưa URL có password
vào argv. API LAN vẫn lấy `API_BIND_IP`/`API_PORT` từ `.env`.

Cài dependency vào venv edge hiện có khi dựng lại môi trường:

```bash
edge-agent/.venv/bin/python -m pip install -r edge-agent/requirements-live.txt
```

## Secret

Người dùng cho phép URI có userinfo **chỉ trong bộ nhớ** ở task này. Runtime đọc
username/password từ macOS Keychain, account `pilot`, service
`nhu-tung-camera-185-runtime-username` và `nhu-tung-camera-185-runtime-password`.
Helper native `data/pilot/bin/camera-keychain` đọc qua pipe riêng, không đưa
credential vào argv, environment, config công khai, frontend hay log.

Helper được biên dịch từ `scripts/camera-keychain.swift`; Keychain ràng buộc quyền
đọc với chương trình đã tạo mục secret. Không biên dịch đè helper đang dùng tùy
ý; nếu cần đổi binary và Keychain yêu cầu quyền, người vận hành xác nhận trong
hộp thoại macOS. Bản file credential cũ ngoài repo vẫn giữ 0600; worker không đọc
file này. Không chép secret vào JSON config/README.

PyAV tạo URI xác thực sau khi đọc secret và percent-encode; libav logging ở
`AV_LOG_QUIET`, exception chỉ chuyển thành mã lỗi cố định. Xác thực bị từ chối
thì dừng nguồn sau một lần; không đoán mật khẩu. Không thêm proxy/dịch vụ camera.

## Persistence và giới hạn

- Tái sử dụng `pipeline.process_frame`, Tracker, SessionManager, CandidatePool,
  detector D05f và FastPlate. Offline và live dùng chung đường xử lý frame.
- Queue decoder tối đa 2 AVFrame; khi đầy bỏ frame chờ cũ để nhận frame mới.
  Không đệm video liên tục. RTSP mở/đọc timeout 5 giây; reconnect backoff 1–30s.
- Gián đoạn stream không dùng làm bằng chứng xe rời ROI. Khi khôi phục, đóng băng
  thời gian vắng detection qua khoảng gián đoạn; visit còn dang dở được giữ UUID
  và ghi interrupted. Tracking không phải danh tính xe lâu dài; vẫn cần review.
- State phiên và outbox SQLite bền vững ở `data/pilot/camera-185/`. Mở/kết thúc
  phiên ghi state cùng transaction outbox. Sender ACK nội bộ sau commit PostgreSQL.
  Cùng ID/nội dung không thêm bản ghi; payload đổi trả mã conflict và giữ outbox.
- Worker là thành phần backend local đáng tin cậy, như replay worker D05m2:
  gọi persistence cùng module vào **DB của API**, không cần browser session và
  không gửi agent token cân. Mất DB giữ outbox; API restart không dừng capture.
- File evidence giữ native trước resize. Ảnh entry là bản riêng bất biến;
  ảnh tốt nhất/crop tiếp theo giữ ID/hash riêng. API dùng D01/CSRF cho review;
  prediction local không tự xác nhận loại định danh, không sửa D02.
  Metadata cuối giữ plate_observations (gốc crop xe, bbox biển trong crop,
  timestamp) và snapshot config; ID interrupted cho restart/shutdown tách
  riêng để gửi lại không bị xung đột nội dung.
- Quota spool 2 GiB: dừng xử lý rõ ràng khi vượt, giữ dữ liệu pending để xử lý.
  Evidence dùng quota cơ sở hiện có 5 GiB và retention 30 ngày. File được ghi
  trước DB commit; gửi lại sửa handoff chưa hoàn tất. Reconcile storage hiện có
  phát hiện file/DB thiếu; không tự xóa evidence xe để vượt quota.
- `compose.local.yml` bổ sung bind mount `data/pilot/evidence/live` dưới
  `/data/evidence/live` cho API/retention; named volume evidence và PostgreSQL
  giữ nguyên. Lỗi gửi outbox không chặn health nguồn/decode/inference.

## Health và web

URL: **http://127.0.0.1:5174/pilot**. Đăng nhập D01 bằng tài khoản được cấp.

`GET /api/vehicle-pilot/cameras` trả latest snapshot mỗi camera, có quyền cơ sở.
Worker gửi mỗi 30s: received / decoded / processed timestamp riêng, FPS, queue,
độ trễ, reconnect, error code, evidence và AI job state. Worker reporting quá
75s coi là gián đoạn health; frame/decode/process quá 45s là gián đoạn stage
(đủ dư cho chu kỳ health 30s). Ảnh giống nhau không được dùng để kết luận stale.

Timestamp frame là **giờ Mac nhận UTC**, không giả vờ đã đồng bộ đồng hồ camera;
UI hiển thị Asia/Ho_Chi_Minh. Receive FPS là số video packet mỗi giây tường,
nominal FPS lấy stream. Latency là decode → xử lý xong, không phải độ trễ từ
sensor đến màn hình. Counter là từ lần khởi động worker hiện tại.

Preview JPEG 640×360 khoảng 1 Hz, chỉ qua endpoint D01 có phân quyền, `no-store`.
Ẩn tab/rời trang hủy polling; request kế tiếp chỉ chạy sau khi request trước xong.
Mất API giữ dữ liệu cũ và ghi chưa cập nhật, không kết luận camera/PC cân offline.
Heartbeat cân và reader hiển thị riêng trên cùng trang; signal chỉ gần thời gian
visit, chưa ghép/chốt trọng lượng.

## Bằng chứng kiểm tra

- Snapshot native + ROI tối đa 1 mỗi 600s; cadence được lưu qua restart.
- Diagnostic ở `live/diagnostics/camera-185`, riêng evidence xe; giữ 24h,
  quota 128 MiB. Cleanup khi worker chạy; khi worker dừng, API vẫn từ chối file
  đã hết hạn; xóa vật lý tiếp tục khi worker chạy lại.
- Nút **Thu clip kiểm tra 15 giây** tạo request có CSRF/quyền cơ sở. Một clip
  đang chờ/đang thu, cách nhau tối thiểu 60s; request quá 60s ghi interrupted.
  Chỉ thu khi còn frame. Clip lỗi/shutdown không báo success.
- Clip diagnostic encode H.264 960×540, mục tiêu 3 fps từ frame được lấy mẫu;
  thời lượng media có thể khác thời gian tường. Đây không phải remux main stream.
  Không ghi video liên tục. Snapshot/clip không tạo visit/OCR/AI job.
- API AI thật vẫn disabled: chưa có model/giá/schema/policy được chốt cho
  inference. Queue mock/giới hạn đã có giữ nguyên; không phát sinh phí trong
  nghiệm thu nguồn. Nhập biển thủ công vẫn hoạt động.

## Kiểm chứng và giới hạn

Kết quả phiên giám sát và số liệu cuối ở `data/pilot/camera-185/supervision-report.json`
và `docs/progress.md`; kiểm tra sau triển khai cuối ở
`data/pilot/camera-185/handoff-final.json`. Test backend dùng PostgreSQL tạm, không seed DB ứng dụng;
35 test liên quan edge/pipeline và 12 backend pass. Build frontend đạt.

Không có xe thật trong phiên thì chỉ nghiệm thu nhận/giải mã/xử lý liên tục,
preview, health, restart và clip. Visit xe thật, chất lượng OCR, thao tác review
trên xe thật, API AI thật và S03b vẫn chưa nghiệm thu. ROI đang provisional,
người vận hành phải xác nhận bằng overlay trước khi dùng mở/đóng lượt thực tế.
