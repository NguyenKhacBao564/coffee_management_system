# S01 — Scale ingestion API v1

## Phạm vi và giới hạn ý nghĩa

S01 nhận các giá trị được quan sát từ giao diện CANXE2015. Server chỉ lưu một
signal riêng; endpoint không tạo/sửa `weigh_events`, kết quả cân D02 hay giao
dịch hàng. API không nhận facility/cân từ payload và không nhận `stable`,
timestamp của thiết bị hoặc biển số.

Số đọc được từ UI không chứng minh đầu cân đang ổn định hay UI vẫn đang cập nhật.
Do client không có timestamp từ thiết bị, `observed_at_utc` là giờ PC ghi nhận;
`received_at_utc` do server thêm. Không suy ra freshness/ổn định hoặc ghép xe từ
giá trị tín hiệu này.

## Endpoint và xác thực

`POST /api/scale-ingestion/batches` chỉ nhận `Authorization: Bearer <token>`.
Token phải thuộc agent còn hoạt động và cơ sở gắn với agent còn hoạt động. Cookie
session người dùng không được đọc thay thế Bearer token; CSRF của trình duyệt
không áp dụng. Không gửi token qua query string hoặc command line. Token ngẫu
nhiên 256-bit; database chỉ lưu SHA-256. Token được kiểm tra lại mỗi request.

Batch có 1–50 event, body tối đa mặc định 65.536 byte (`SCALE_INGESTION_MAX_BODY_BYTES`,
cấu hình 1 KiB–1 MiB). Mỗi `vendor_text` tối đa 500 ký tự; trọng lượng là chuỗi
thập phân không dấu phân cách, hữu hạn, tối đa 3 chữ số lẻ, từ 1000 đến
`99999999999.999` kg. Timestamp phải là ISO-8601 có múi giờ UTC `Z` hoặc
`+00:00`. Timestamp tương lai vượt `SCALE_INGESTION_MAX_FUTURE_SECONDS` (mặc
định 300 giây, cấu hình tối đa một giờ) bị từ chối; timestamp quá khứ dùng để
gửi bù giữ thời điểm quan sát UTC sau chuẩn hóa microsecond bên dưới. Sequence
phải dương, nhưng server không bắt sequence đến theo thứ tự thời gian/nhận.

### Chuẩn hóa timestamp

- `observed_at_utc` được chuẩn hóa về UTC với **độ chính xác microsecond**
  (6 chữ số sau dấu chấm của giây). API vẫn nhận timestamp 7 chữ số do client
  .NET/S02 gửi, với UTC `Z` hoặc `+00:00` như hợp đồng hiện có.
- Mọi chữ số sau vị trí thứ 6 được **bỏ đi, không làm tròn**. `.1234561` và
  `.1234569` cùng chuẩn hóa thành `.123456`; `.9999999` thành `.999999` trong
  cùng giây, không chuyển sang giây tiếp theo. Phần dư nhỏ hơn 1 microsecond
  nằm ngoài độ chính xác của hợp đồng; đây là chuẩn hóa độ phân giải.
- Parser hiện dùng `datetime.fromisoformat`, sau đó chuẩn hóa timezone UTC.
  Timestamp đã chuẩn hóa được dùng cho kiểm tra tương lai, lưu PostgreSQL
  (`timestamptz`, độ chính xác 6) và so sánh nội dung khi gửi lại. Giới hạn thời
  gian tương lai vẫn giữ nguyên; không thay thời gian quan sát bằng thời gian nhận.
- So sánh timestamp khi gửi lại là **bằng chính xác sau chuẩn hóa**, không dùng
  khoảng dung sai. Biểu diễn 6 chữ số tương đương nhận duplicate ACK; timestamp
  khác 1 microsecond vẫn là khác nội dung và trả 409 cho cùng event ID/sequence.

Payload mẫu (UUID và số liệu giả):

```json
{
  "schema_version": 1,
  "agent_id": "0199a111-2222-7333-8444-555566667777",
  "events": [
    {
      "event_id": "0199a222-3333-7444-8555-666677778888",
      "sequence": 41,
      "observed_at_utc": "2026-10-05T03:15:00.500Z",
      "weight_kg": "3270",
      "vendor_text": "S01 test data · 3270 kg",
      "source": "canxe2015_ui"
    }
  ]
}
```

Response HTTP 200 sau khi PostgreSQL commit:

```json
{
  "schema_version": 1,
  "agent_id": "0199a111-2222-7333-8444-555566667777",
  "persisted": true,
  "acknowledged_event_ids": ["0199a222-3333-7444-8555-666677778888"],
  "inserted_count": 1,
  "duplicate_count": 0,
  "server_received_at_utc": "2026-10-05T03:15:01.100000Z"
}
```

Batch atomar: mọi event mới được lưu cùng transaction, hoặc phần mới của batch
bị rollback. Event đã commit trong request trước vẫn còn nếu một retry sau đó
xung đột. HTTP 200 và `persisted: true` chỉ được trả sau commit.

## Chống trùng và checkpoint phía client

- `Unique(agent_id,event_id)` và `Unique(agent_id,sequence)` được enforce ở
  PostgreSQL. Insert conflict được đối chiếu lại trong transaction, nên hai
  request đồng thời không tạo bản ghi trùng.
- Cùng `event_id`, `sequence` và nội dung nghiệp vụ là duplicate hợp lệ; server
  ACK lại. Trọng lượng được so sánh theo Decimal nên `3270` bằng `3270.000`.
  `observed_at_utc` được so sánh chính xác theo chuẩn UTC/microsecond bên trên;
  `received_at_utc` không tham gia so sánh.
- Cùng event ID hoặc sequence nhưng khác nội dung trả 409 và rollback phần mới
  của batch. Event ID/sequence lặp ngay trong cùng payload trả 422.
- Client chỉ xóa event khỏi outbox/tiến checkpoint khi nhận HTTP 200, JSON hợp
  lệ, `schema_version == 1`, `persisted == true`, `agent_id` đúng và tập ID được
  ACK khớp đầy đủ ID đang chờ. Timeout/mất response thì giữ nguyên `event_id`,
  sequence và payload, gửi lại; duplicate ACK xác nhận dữ liệu đã bền vững.
  Checkpoint/outbox cần được client ghi bền vững trước network I/O.

Mã lỗi:

| HTTP | Ý nghĩa |
| --- | --- |
| 401 | Thiếu/sai Bearer token. |
| 403 | Agent/cơ sở không hoạt động hoặc `agent_id` không khớp token. |
| 409 | Event ID/sequence đã được dùng với nội dung khác. |
| 413 | Request vượt giới hạn byte cấu hình. |
| 422 | Hợp đồng/số liệu/timestamp không hợp lệ. Response chỉ nêu vị trí/lỗi, không echo token hoặc body. |
| 503 | PostgreSQL tạm không khả dụng; response không có `persisted: true`. |

## Tạo, vô hiệu hóa và đổi token agent

Chạy CLI trên Mac từ repository sau khi Compose DB đã chạy. CLI tự chuyển host
Compose `db` sang port PostgreSQL được publish trên localhost. Dùng facility code
đang hoạt động; mỗi scale code chỉ dùng một lần trong một cơ sở:

```bash
cd backend
python -m app.modules.scale_ingestion.cli create \
  --facility-code DEMO --scale-code SCALE-01 --display-name "Cân kho chính"
python -m app.modules.scale_ingestion.cli disable AGENT_UUID
python -m app.modules.scale_ingestion.cli rotate-token AGENT_UUID
cd ..
```

CLI không ghi đè agent hiện có. File token nằm trong
`data/scale-agent-tokens/AGENT_UUID.token`; thư mục/file đặt quyền 0700/0600 và
đã được Git ignore. CLI chỉ in agent ID và đường dẫn, không in token. Rotation
thay hash trong DB; token cũ mất hiệu lực. Không đưa file này vào backup chia sẻ,
Git hoặc log.

## Thử API local bằng simulator

Chỉ chạy trên agent/cơ sở test và dữ liệu giả. Không dùng database ứng dụng có dữ
liệu vận hành nếu chưa được yêu cầu. Tạo agent trên database/stack nghiệm thu
riêng; sau đó set ID và đường dẫn token qua environment (không đưa token vào
argv):

```bash
export SCALE_AGENT_ID='AGENT_UUID'
export SCALE_AGENT_TOKEN_FILE="$PWD/data/scale-agent-tokens/$SCALE_AGENT_ID.token"
export SCALE_API_URL='http://localhost:8001'
python3 scripts/simulate-scale-agent.py --mode valid
python3 scripts/simulate-scale-agent.py --mode drop-ack
python3 scripts/simulate-scale-agent.py --mode resend
```

Simulator tạo số liệu ghi rõ `S01 simulator test reading`, lưu batch pending
trước khi gửi và giữ state/checkpoint tại `data/scale-simulator-state.json`
(0600, Git ignored). `drop-ack` đọc response HTTP nhưng cố ý không chấp nhận ACK,
giữ outbox; `resend` gửi lại cùng batch rồi chỉ cập nhật checkpoint nếu ACK hợp
lệ. Đây là hành vi của client test harness, không có chế độ phá response trong
API production. Một state file gắn với đúng một agent.

## Lưu trữ

`scale_agents` lưu định danh agent, facility/cân gắn cố định, trạng thái, hash
token và thời điểm tạo. `scale_signals` là bảng riêng, bất biến qua API, dùng
`NUMERIC(14,3)` và có index `(agent_id, observed_at_utc)`. API S01 không có route
sửa/xóa hay truy vấn dữ liệu, không dùng cookie/CSRF và không tác động D02.

## Tiêu chí đối chiếu PostgreSQL cho S03a nguồn giả

- Dùng database của API đã nhận request và transaction chỉ đọc. Manifest phải
  có tập ID phân biệt; mỗi ID tồn tại đúng một bản ghi, đúng agent. Kiểm tra
  sequence, Decimal trọng lượng, source và thời gian quan sát khi có trong manifest;
  phân biệt dữ liệu ngoài đợt thử nếu có, kiểm tra sequence trùng và ranh giới D02.
- Chuẩn hóa timestamp manifest về UTC/microsecond bằng cách bỏ phần dư trước
  khi so sánh chính xác với PostgreSQL. Khác biệt ở chữ số thập phân thứ 7 nằm
  ngoài độ phân giải hợp đồng, không tính là sai lệch dữ liệu ở độ chính xác
  đã thống nhất. Không sửa bản ghi hoặc dùng dung sai để làm khớp đối chiếu.
- PostgreSQL xác nhận số hàng đã lưu, tính duy nhất của event ID/sequence và
  thời gian quan sát đã chuẩn hóa trong snapshot. Kiểm thử trên DB tạm xác nhận
  hành vi duplicate ACK, conflict, atomic và ACK sau commit của triển khai.
- Kết quả replay/mất ACK/lỗi mạng/restart, checkpoint/backlog và số mẫu dưới
  ngưỡng là bằng chứng phía client nếu chỉ có bàn giao client. Snapshot cuối
  không tự chứng minh từng lần retry, toàn bộ trạng thái trung gian hoặc mẫu bị
  loại không có ID/giá trị để đối chiếu. Source `canxe2015_ui` không chứng minh
  nguồn giả đã đọc CANXE2015; S03b đọc nguồn thực tế/đo tài nguyên nghiệm thu riêng.


## S03 — API người dùng để theo dõi (chỉ đọc)

Hợp đồng POST/ACK S01 giữ nguyên. Các GET sau nằm dưới prefix riêng
`/api/scale-monitoring`, yêu cầu cookie session D01 hợp lệ. Bearer agent không
thay thế session (401). Admin có phạm vi mọi cơ sở đang hoạt động theo D01;
manager/staff chỉ có cơ sở đang hoạt động được gán, kiểm tra lại mỗi request.
ID cơ sở/agent ngoài quyền hoặc không tồn tại trả 404, kể cả khoảng lọc rỗng.

| GET | Query và kết quả |
| --- | --- |
| `/api/scale-monitoring/agents` | `facility_id` tùy chọn, `page`, `page_size` mặc định 50. Trả `items`, `total`, `page`, `page_size`; mỗi agent có ID, tên, scale code, trạng thái hoạt động, ID/code/tên cơ sở và `latest` hoặc null. |
| `/api/scale-monitoring/agents/{agent_id}/latest` | `facility_id` tùy chọn để thu hẹp quyền. Trả `agent_id`, `latest` hoặc null. |
| `/api/scale-monitoring/signals` | Lọc `facility_id`, `agent_id`, `observed_from`, `observed_to`; `page_size` mặc định 30. Trả `items`, `total`, `page`, `page_size`. |

- Không chỉ định cơ sở nghĩa là toàn bộ phạm vi được phép. Lịch sử lọc theo
  thời gian quan sát UTC, hai đầu bao gồm; datetime có `Z` hoặc `+00:00`.
  Khoảng đảo ngược/không UTC trả 422. `page` 1–10000, `page_size` 1–100.
- Catalog có thứ tự `facility.code`, `scale_code`, `agent_id`. Latest và lịch
  sử dùng `observed_at_utc DESC, id DESC` để phân biệt các timestamp bằng nhau.
  Phân trang offset ổn định với tập dữ liệu không đổi; event mới có thể dịch
  trang giữa hai lần tải, đây không phải snapshot lịch sử xuyên request.
- Mỗi signal trả `event_id`, `agent_id`, `sequence` (chuỗi số nguyên chính xác),
  `weight_kg` (chuỗi Decimal 3 chữ số lẻ), `source`, `observed_at_utc`,
  `received_at_utc` có thật từ schema và chú thích `is_acceptance_test`.
  Hai timestamp UTC với độ chính xác microsecond theo hợp đồng trên; không
  tự thêm thời gian thiết bị, heartbeat hoặc trạng thái ổn định.
- Không trả token/hash token, vendor text hoặc dữ liệu nội bộ xác thực. Không
  có route tạo/sửa/xóa trong prefix theo dõi. Agent bị vô hiệu hóa vẫn xem
  lịch sử được khi cơ sở nằm trong quyền người dùng.
- `is_acceptance_test` chỉ đúng cho **9 cặp agent/event đã nghiệm thu S03a**
  trong `provenance.py`, trích manifest SHA-256
  `2f8ab406786ee482afb409ad4014f077dd8126a50ad3b43cb1e606e57a7b3416`.
  Đây là chú thích từ bằng chứng, không sửa `source=canxe2015_ui`/bản ghi gốc
  và không đánh dấu toàn bộ event tương lai của agent là nguồn giả. Event
  khác không có nhãn kiểm thử không đồng nghĩa đã chứng minh nguồn cân thật.
- UI dùng “Chưa có mẫu”/“Có mẫu ghi nhận”; không có mẫu mới không chứng minh
  PC offline hoặc cân về 0. Agent chỉ tạo mẫu khi đọc thành công ≥1.000 kg;
  mẫu không phải số cân ổn định hoặc đã chốt. Card latest dựa vào quan sát
  mọi thời gian; đồ thị điểm rời và bảng thuộc trang/bộ lọc lịch sử đang chọn.

## Heartbeat agent riêng (hợp đồng v1)

`POST /api/scale-ingestion/heartbeat` dùng lại Bearer agent S01 và cơ sở cố
định của agent. Chu kỳ client là 30 giây, độc lập với threshold cân và signal
batch. Heartbeat chỉ lưu snapshot trạng thái agent/reader; không tạo
`scale_signals`, lượt cân, trip hay giao dịch D02. Request có
`schema_version=1`, UUID `heartbeat_id`, sequence riêng tăng đơn điệu và các
trường sức khỏe reader/agent. Xem payload, retry và config Windows tại
[`windows-scale-heartbeat-handoff.md`](windows-scale-heartbeat-handoff.md).

- Bảng snapshot `scale_agent_heartbeats` giữ tối đa một dòng trên mỗi agent.
  Migration v1 là additive; snapshot legacy được giữ nhưng không coi là
  heartbeat v1. Không tạo lịch sử heartbeat vô hạn.
- Server serialize theo row agent. Sequence mới hơn mới được áp dụng; request
  sequence cũ được ACK stale và không ghi đè hoặc làm mới thời điểm nhận. Retry
  ID/sequence/nội dung hiện tại trả duplicate ACK mà không làm mới
  `received_at_utc`. Dùng lại UUID/sequence cho heartbeat khác trả 409.
- `received_at_utc` do server ghi và là mốc duy nhất cho trạng thái liên lạc.
  `last_successful_read_at_utc` có thể cũ và không phải bằng chứng reader còn
  hoạt động. Trường chưa đo được là `null`; mã lỗi chỉ là safe code.
- API web dùng session D01 và phạm vi cơ sở đang hoạt động. Admin thấy chi tiết
  kỹ thuật; Manager/Staff chỉ thấy trạng thái liên lạc và reader trong cơ sở
  được gán. Bearer agent không thay thế quyền người dùng.
- UI: `<=90s` đang liên lạc; `>90–180s` liên lạc chậm; `>180s` mất liên lạc;
  chưa từng nhận v1 là chưa có tín hiệu. Reader empty/error/unavailable vẫn
  phân biệt độc lập. Khi API/web không truy cập được, UI báo snapshot chưa cập
  nhật và không suy ra PC offline/cân 0. Timestamp UI theo giờ Việt Nam.
- Hợp đồng S02 batch, threshold, outbox/checkpoint và signal ACK không đổi.
  Client Windows chưa được sửa/cài hoặc nghiệm thu bằng task này.
