# Khôi phục sender signal S02 trên PC cân — 12/10/2026

## Bằng chứng phía Mac

Agent đã xác định: `06c70368-50a1-470d-bf26-45391cd05069`, cân `WIN-TEST-01`.
Lúc 12:52:23 giờ Việt Nam, DB chỉ đọc cho thấy:

- Heartbeat sequence 4765, server nhận 12:52:17; vendor process vẫn chạy.
- Reader hiện `empty`; lần đọc thành công gần nhất 11:40:46 ngày 12/10.
- `last_error_code=SIGNAL_SENDER_PAUSED`, `pending_event_count=1309`.
- Client báo ACK signal gần nhất 04:13:36. Đây là lời báo của client, không
  chứng minh có event mới được insert; ACK có thể là duplicate.
- DB vẫn có 12.982 signal; mới nhất theo observed/received là sequence 12982,
  observed 00:16:53.312284, received 03:41:35.643751 ngày 12/10.

API và PostgreSQL healthy; readiness qua hostname VPN trả 200. API access log
vẫn nhận heartbeat 200 nhưng không có batch signal trong khoảng kiểm tra.
Như vậy đoạn Windows → server cho heartbeat đang hoạt động, trong khi client
báo riêng sender signal đã pause. Chưa xác định được nguyên nhân tạo pause
vì source/config tiến trình Windows đang chạy không nằm trong checkout Mac.

## Endpoint cần đối chiếu trên Windows

API base: `http://nkb-mb-pm2p-1.tail54c504.ts.net:8001`

- Readiness: `/api/health/ready`.
- Heartbeat: `POST /api/scale-ingestion/heartbeat`.
- Signal S02: `POST /api/scale-ingestion/batches`.

Cả sender signal và heartbeat cần dùng base thực tế này. Readiness không thay
cho kiểm tra ACK batch. Không dùng IP LAN cũ hoặc URL chỉ có IP Tailscale nếu
Tailscale Serve định tuyến theo hostname. Đọc token từ secret store đang dùng.

## Prompt để giao cho Codex trên PC Windows

> Điều tra và khôi phục sender S02 của agent
> `06c70368-50a1-470d-bf26-45391cd05069` đang chạy trên PC cân. Mac đã xác minh
> API qua `http://nkb-mb-pm2p-1.tail54c504.ts.net:8001` healthy và vẫn nhận
> heartbeat. Heartbeat lúc 12/10 12:52:17 giờ VN báo
> `SIGNAL_SENDER_PAUSED`, pending 1309, reader empty; lần đọc thành công gần
> nhất 11:40:46. DB Mac mới nhất vẫn sequence 12982, observed 00:16:53,
> received 03:41:35. Hãy đọc source/config của đúng process trước, tìm nơi tạo
> mã `SIGNAL_SENDER_PAUSED`, phân biệt pause thủ công/config, pause sau lỗi
> HTTP 401/403/409/422 hay lỗi transport. Đối chiếu endpoint riêng của sender
> với heartbeat; batch đúng là `/api/scale-ingestion/batches`. Không đoán tên
> cờ hoặc CLI resume khi source chưa có bằng chứng. Khôi phục sender theo
> cơ chế hiện có khi đã xác định nguyên nhân. Giữ token, agent ID, UUID,
> sequence, observed_at, nội dung event, checkpoint và outbox. Không xóa hoặc
> sửa event để né conflict; không phát mẫu cân giả. Backup outbox bằng cơ chế
> phù hợp SQLite trước thay đổi nếu cần. Mỗi event chỉ ACK local sau ACK server
> sau commit; retry giữ nguyên ID/body. Nếu 401/403 hoặc conflict còn lặp,
> dừng sender và báo nguyên nhân cụ thể, không đổi token hoặc reset state.
> Sau khôi phục, báo số batch gửi, HTTP code/ACK inserted/duplicate, pending
> trước/sau và observed time mới nhất; che token. Cho Mac đối chiếu DB độc lập.
> Giữ heartbeat riêng hoạt động, không sửa D02 hay nguồn CANXE2015.

## Điều kiện xác nhận đã khôi phục

Pending giảm có ACK hợp lệ; API ghi nhận batch; số signal hoặc duplicate ACK
khớp sự kiện gốc; DB có event observed mới hơn 00:16:53 nếu backlog thực sự
chứa mẫu mới. Gửi bù giữ giờ quan sát cũ. Chỉ mẫu đủ mới theo cấu hình hiện có
mới kích hoạt camera; không biến backlog thành trigger live.

Mac chưa thao tác/cài lại agent Windows trong lần sửa giao diện này.


Đối chiếu bổ sung lúc 13:11:50 VN: heartbeat sequence4804, server nhận13:11:47,
last_successful_read13:10:49, pending1483, vẫn SIGNAL_SENDER_PAUSED. DB count/
latestseq vẫn12982. Không coi sự kiện đang chờ gửi là đã có trong PostgreSQL.
