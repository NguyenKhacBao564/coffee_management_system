# Hợp đồng heartbeat PC cân → API pilot

Phiên bản hợp đồng `1`. Đây là endpoint riêng, dùng xác thực agent S01 hiện có.
Heartbeat chỉ lưu snapshot sức khỏe agent/reader; nó không gửi trọng lượng,
không ghi `scale_signals`, lượt cân hoặc dữ liệu D02. Thay đổi này không sửa
hợp đồng batch S02 đang vận hành.

## Endpoint và chu kỳ

`POST <API_BASE_URL>/api/scale-ingestion/heartbeat`

### Endpoint VPN pilot — cập nhật 11/10/2026

API base qua Tailscale:
`http://nkb-mb-pm2p-1.tail54c504.ts.net:8001`.
Heartbeat dùng `/api/scale-ingestion/heartbeat`; batch S02 vẫn dùng
`/api/scale-ingestion/batches`. Giữ token, agent ID, sequence và outbox hiện có.
Dùng hostname này khi Mac đổi mạng; URL IP LAN cũ không tiếp tục được bảo đảm.
Tailscale Serve định tuyến theo hostname, nên URL chỉ dùng IP
`100.76.15.19:8001` có thể trả 404.

Docker API bind `API_BIND_IP=127.0.0.1`, port `8001`; Tailscale Serve trỏ
`http://127.0.0.1:8001`, không phụ thuộc IP Wi-Fi/hotspot. PostgreSQL vẫn chỉ
publish loopback `127.0.0.1:5433`. Máy Windows và Mac phải có Tailscale hoạt
động; policy phải cho gateway `100.117.137.90` đến Mac `100.76.15.19` TCP 8001.

Khởi tạo/khôi phục proxy tailnet trên Mac:
`tailscale serve --bg --http=8001 http://127.0.0.1:8001`.
Dừng riêng proxy: `tailscale serve --http=8001 off`.
Kiểm tra readiness ở `<API_BASE_URL>/api/health/ready`; HTTP 200 chỉ xác nhận
API sẵn sàng. Xác nhận Windows thực sự gửi được bằng sequence và
`received_at_utc` mới trong PostgreSQL.

- `Authorization: Bearer <agent-token>`; token được đọc từ secret file hoặc
  Windows Credential Manager, không ghi vào argv, URL, shell history hay log.
- `Content-Type: application/json`.
- Gửi mỗi **30 giây**, độc lập với ngưỡng cân `>= 1.000 kg` và việc có signal
  mới hay không. Heartbeat vẫn gửi khi reader trả `empty`.
- Request timeout hữu hạn; retry timeout/5xx bằng cùng body, `heartbeat_id` và
  `heartbeat_sequence`. Có thể backoff/jitter. Không xếp hàng heartbeat để gửi
  bù sau mất mạng; khi kết nối lại hãy tạo snapshot mới nhất với sequence mới.

## Payload v1

```json
{
  "schema_version": 1,
  "heartbeat_id": "0199a111-2222-7333-8444-555566667777",
  "heartbeat_sequence": 42,
  "agent_version": "1.0.0",
  "process_uptime_seconds": 720,
  "vendor_process_running": true,
  "reader_status": "empty",
  "last_successful_read_at_utc": "2026-10-09T08:30:00.123456Z",
  "pending_event_count": 0,
  "last_signal_ack_at_utc": "2026-10-09T08:29:30Z",
  "last_error_code": null
}
```

- `heartbeat_id`: UUID mới cho mỗi snapshot mới. Khi retry cùng snapshot, giữ
  nguyên UUID và toàn bộ body.
- `heartbeat_sequence`: số nguyên dương tăng bền vững theo từng snapshot mới,
  độc lập với sequence signal S02. Lưu local an toàn qua restart; không cấp lại
  cùng sequence cho ID khác.
- `agent_version`: nhãn phiên bản agent, nếu biết.
- `process_uptime_seconds`: uptime của tiến trình agent, không phải uptime PC.
- `vendor_process_running`: trạng thái tiến trình CANXE2015 nếu đo được.
- `reader_status`: `starting`, `ok`, `empty`, `error` hoặc `unavailable`, phản
  ánh lần kiểm tra reader hiện tại. `empty` không có nghĩa cân bằng 0.
- `last_successful_read_at_utc`: thời điểm lần đọc thành công gần nhất theo đồng
  hồ PC, có thể cũ. Không gửi lại trọng lượng cũ; server/UI không dùng timestamp
  này làm bằng chứng reader đang hoạt động.
- `pending_event_count`: số signal đang chờ ACK trong outbox; luôn là số không
  âm. Trường này không thay đổi checkpoint hoặc nội dung outbox.
- `last_signal_ack_at_utc`: thời điểm client ghi nhận ACK signal S02 gần nhất,
  nếu biết. Không tự suy ra từ server heartbeat.
- `last_error_code`: mã an toàn, chỉ dùng `A-Z`, `0-9`, `_`, tối đa 64 ký tự;
  không gửi exception text, path, username hay dữ liệu nguồn.
- Trường chưa đo được gửi `null`; không phỏng đoán. Timestamp phải là ISO-8601
  UTC (`Z` hoặc `+00:00`). Không gửi weight, vendor text hay raw file.

## Idempotency, thứ tự và ACK

- Server xác thực cùng agent đang active và facility đang active theo S01.
- PostgreSQL giữ **một snapshot hiện tại trên mỗi agent**; không lưu mọi lần
  heartbeat vô hạn và không tác động retention/evidence.
- Heartbeat sequence mới hơn thay snapshot trong transaction. Sequence cũ đến
  muộn được ACK `stale: true`, nhưng không được ghi hoặc làm mới thời điểm nhận.
- Gửi lại ID hiện tại với cùng sequence/nội dung nhận ACK duplicate mà không làm
  mới `received_at_utc`. Dùng lại ID với nội dung khác, hoặc sequence hiện tại
  với ID khác, nhận HTTP 409.
- Response `acknowledged: true` chỉ được phát sau transaction commit (hoặc sau
  khi xác định request là duplicate/stale). `persisted`/`applied` cho biết
  snapshot có được ghi/thay hay không. Chỉ `applied: true` làm mới snapshot.
- Không dùng heartbeat cũ trong hàng đợi để làm agent có vẻ đang online. Client
  cần giữ sequence tăng đơn điệu qua restart; khi reconnect chỉ gửi trạng thái
  mới nhất, không replay heartbeat cũ.

Ví dụ response cho snapshot mới/duplicate:

```json
{
  "schema_version": 1,
  "agent_id": "0199a000-1111-7222-8333-444455556666",
  "heartbeat_id": "0199a111-2222-7333-8444-555566667777",
  "heartbeat_sequence": 42,
  "acknowledged": true,
  "persisted": true,
  "applied": true,
  "duplicate": false,
  "stale": false,
  "received_at_utc": "2026-10-09T08:30:01.010000Z"
}
```

Với sequence cũ, response `acknowledged: true`, `persisted: false`,
`applied: false`, `stale: true`; `received_at_utc` chỉ thời điểm snapshot hiện
tại, không phải lúc nhận request cũ.

401/403 là lỗi cấu hình hoặc agent/facility bị vô hiệu hóa: dừng gửi và báo quản
lý, không thử token khác hoặc mật khẩu mặc định. 409 cần kiểm tra trạng thái
sequence/ID local. 422 là payload không hợp lệ. Timeout/5xx không xác định chắc
server đã nhận hay chưa; retry nguyên snapshot để nhận duplicate ACK nếu cần.

## Trạng thái UI

- Tính tuổi từ `received_at_utc` do server ghi, không dùng timestamp của lần đọc
  cân: `<=90s` đang liên lạc; `>90–180s` liên lạc chậm; `>180s` mất liên lạc.
- Chưa có heartbeat v1 được hiển thị riêng là chưa có tín hiệu. Snapshot của
  hợp đồng cũ được đánh dấu cũ, không gán thành trạng thái v1.
- `reader_status=empty/error/unavailable` được hiển thị riêng kể cả khi agent
  vẫn đang liên lạc. Không heartbeat mới không kết luận PC offline hoặc cân 0.
- Nếu API/web không truy cập được, UI báo không cập nhật được và giữ snapshot
  cũ có nhãn thời điểm; không chuyển trạng thái PC sang offline.
- Admin xem chi tiết kỹ thuật. Manager/Staff chỉ xem agent thuộc cơ sở đang hoạt
  động đã gán; bearer agent không thay thế session người dùng.
- Mọi timestamp UI hiển thị theo `Asia/Ho_Chi_Minh`; API lưu/trả UTC.

## Cấu hình mẫu

`docs/examples/windows-scale-heartbeat.config.example.json` là mẫu không chứa
địa chỉ server thật hoặc token. API base URL, secret store và đường dẫn state
được cung cấp tại thời điểm cài client. Mẫu này không thay đổi cấu hình signal
S02.

## Prompt bàn giao Windows

> Đọc client S01/S02 và hợp đồng heartbeat v1 trong repository Mac. Chỉ triển
> khai heartbeat riêng mỗi 30 giây; giữ nguyên route batch, threshold, event,
> outbox, ACK và checkpoint S02. Dùng Bearer token agent S01 từ Windows
> Credential Manager/secret file; không log token. Mỗi snapshot mới có UUID và
> sequence tăng bền vững; khi retry giữ nguyên body/ID/sequence. Không queue hoặc
> gửi bù heartbeat cũ sau reconnect; gửi snapshot mới nhất. Gửi `reader_status`
> hiện tại và các trường chưa biết là null; không gửi trọng lượng cũ. Thêm
> timeout/backoff hữu hạn, xử lý 401/403 dừng và báo, 409 yêu cầu kiểm tra
> sequence. Viết test xác nhận heartbeat không sửa outbox/checkpoint và không
> phát event. Trước khi chạy trên PC vận hành, bàn giao diff/test và yêu cầu
> người quản lý duyệt riêng bước cài đặt.


## Camera event-driven — bổ sung D05m4b (10/10/2026)

Không đổi payload/path/auth của S02 hoặc heartbeat. Agent phải giữ
`observed_at_utc` đúng thời điểm đọc nguồn (UTC), không thay bằng giờ retry/gửi;
đồng bộ đồng hồ PC. Server camera chỉ kích hoạt mẫu ≥1.000 kg có tuổi ≤10s
(dung sai future 2s), không dùng backlog dù received mới. Heartbeat không
thay signal và không tạo trigger. Mất signal/heartbeat không phải xe rời.

Hiện không có start/end observation-session; chuỗi signal mới liên tiếp coalesce
và rearm sau gap observed >120s. Đây là giới hạn chụp của worker, không phải
định nghĩa lượt cân. Nút thủ công vẫn hoạt động khi reader empty/error/offline.
Nếu muốn phân biệt hai xe sát nhau hoặc chụp lại xe đứng lâu, cần thống nhất
hợp đồng `capture_request_id`/`weigh_observation_session_id` và thao tác kết thúc
rõ ràng ở bước sau. Chưa yêu cầu Windows tự phát sinh những trường này hoặc
chuyển trọng lượng thành D02.
