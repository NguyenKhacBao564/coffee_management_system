# S03c / D06a — Tín hiệu cân và khảo sát detect người

Ngày thực hiện: 12/10/2026. Phạm vi chỉ theo dõi/đối chiếu; không chốt lượt
cân, không tạo giao dịch nhập/xuất, không thay raw signal/sequence/outbox/D02,
không đổi agent Windows, không train hoặc thuê GPU.

## S03c — thời gian signal

`scale_signals` giữ `observed_at_utc` do PC gửi (đã parse/chuẩn hóa UTC),
`received_at_utc` do API gán lúc nhận và `vendor_text`. Schema không có một
trường thứ ba lưu nguyên văn timestamp từ đồng hồ thiết bị trước chuyển đổi;
do đó có thể đối chiếu observed với received nhưng không chứng minh độc lập
đồng hồ/chuỗi timestamp gốc của CANXE2015. Không sửa dữ liệu lịch sử.

Đối chiếu PostgreSQL read-only, event sequence `12876`:

| Mốc | UTC lưu ở DB | Asia/Ho_Chi_Minh | Ý nghĩa |
| --- | --- | --- | --- |
| PC quan sát | 11/10 17:16:00.314137 | 12/10 00:16:00.314137 | `observed_at_utc` |
| Server nhận | 11/10 20:41:35.358634 | 12/10 03:41:35.358634 | `received_at_utc` |

Chênh lệch là **12.335 giây (3 giờ 25 phút 35 giây)**. Nhiều sequence liền
kề cùng có received time gần như đồng thời trong khi observed time tăng đều;
đây là bằng chứng của batch gửi bù/backlog, không phải phép cộng/trừ múi giờ.
Múi giờ Việt Nam là UTC+7 cho cả hai trường, nên ví dụ hiển thị đúng ngày
12/10. Tại lúc đối chiếu gần nhất, snapshot agent `06c70368-50a1-470d-bf26-45391cd05069`
ở sequence heartbeat 4344 báo `reader_status=empty`, `pending_event_count=801`,
`last_error_code=SIGNAL_SENDER_PAUSED`; heartbeat được nhận 09:18:39 ngày 12/10.
Điều này cho biết sender signal đang giữ backlog trong khi heartbeat vẫn chạy;
không được kết luận các batch pending đã tới API. Không sửa hay xóa backlog.

UI và truy vấn thống kê dùng `observed_at_utc`; ranh giới ngày/tháng được tính
theo `Asia/Ho_Chi_Minh`. `received_at_utc` chỉ dùng để trình bày/đếm độ trễ.

## S03c — API và giao diện

- API session-authenticated và lọc phạm vi facility có thêm endpoint chỉ đọc
  `/api/scale-monitoring/signals/chart` và `/api/scale-monitoring/summary`;
  không có migration. Chuỗi chart tối đa 1.200 điểm mặc định, giới hạn API
  2.000, chia bucket theo thời gian và giữ first/last/min/max. CTE thực hiện
  giảm mẫu ở PostgreSQL; không gửi toàn bộ signal cho trình duyệt.
- Endpoint chart độc lập endpoint/phân trang bảng (`30` dòng/trang). Chart xếp
  theo observed time, dùng đoạn thẳng, không smoothing; ngắt đoạn khi cách
  nhau trên 60 giây. Tooltip có trọng lượng, observed/received theo giờ VN và
  sequence. Mốc 60 giây là quy ước hiển thị ban đầu, không phải quy tắc nhận
  diện phiên hay ngưỡng ổn định của cân.
- Bộ lọc nhanh 1 giờ/24 giờ/7 ngày/tháng này/mọi thời gian, khoảng tùy chọn,
  kéo ngang để zoom. Mặc định 24 giờ. Mẫu hiển thị tự đổi kg/t; metadata event,
  sequence và source nằm trong hàng mở rộng.
- Tóm tắt đếm mẫu observed theo ngày/tháng VN, và số mẫu nhận trễ trên 60 giây
  trong khoảng lọc. Không SUM weight. Daily breakdown tối đa 366 ngày, API trả
  cờ khi bị rút gọn.
- D02 hiện có `weigh_events`/`weigh_results` là lượt cân/kết quả nghiệp vụ
  manual; không có entity “lượt cân quan sát” tách raw signal. Vì vậy KPI
  observed/confirmed/review trả `null` trong API và UI ghi “chưa đủ dữ liệu”/
  “chưa có workflow”; không dùng số signal hoặc camera_visit thay thế. Không
  hiển thị tổng khối lượng nhập/xuất.

### Thiết kế lớp lượt cân quan sát (chưa triển khai)

Tách entity này khỏi `scale_signals` và D02. Mỗi observation có thể tham chiếu
nhiều raw signal và có nhiều `stable_segment` (đoạn ổn định), mỗi đoạn lưu
thời điểm đầu/cuối, số mẫu, min/max và giá trị đại diện; giữ liên kết về raw ID.
Lưu trạng thái `observed`, `needs_review`, `confirmed` và audit xác nhận. Ghi
`algorithm_version` cùng cấu hình để tính lại mọi segment từ raw signal; không
ghi đè raw hoặc D02. Không có signal/heartbeat không được dùng để kết luận xe
đã rời. Chưa chạy thuật toán hoặc tạo entity.

Ngưỡng cần chốt sau khi quan sát luồng thật: tuổi tối đa của mẫu để vào phiên,
thời gian duy trì ổn định, biên độ kg hoặc %, số mẫu tối thiểu, khoảng mất mẫu
được phép nối, và điều kiện tách hai plateau thành hai segment. Các ngưỡng này
không thể suy ra an toàn từ signal hiện có; phải có phiên được người vận hành
đối chiếu.

## D06a — COCO person feasibility

Đã kiểm tra file local `data/offline-vision/models/object_detection_yolox_2022nov.onnx`:
SHA-256 `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`,
OpenCV Zoo YOLOX-s COCO 80 lớp, revision đã pin trong `detectors.py`, Apache-2.0.
Class COCO `person` là index 0. Adapter đang dùng trong pipeline lọc riêng
car/bus/truck (2/5/7); phép thử dưới đây dùng model COCO gốc, không dùng model
plate D05f.

Phép thử CPU offline, lấy 1 frame mỗi 2 giây, decode YOLOX, lọc class 0 ở
score 0,25 rồi NMS IoU 0,45:

| Video | Mẫu frame | Frame có bbox person | Bbox giữ sau NMS | Score lớn nhất |
| --- | ---: | ---: | ---: | ---: |
| `camera_185_20261004_073000-073500.mp4` | 151 | 81 | 113 | 0,9156 |
| `camera_185_20261004_103800-104015.mp4` | 66 | 35 | 61 | 0,8830 |

Inference mất khoảng 38 giây cho 218 frame trên Mac. Score chưa hiệu chuẩn và
đây không phải precision/recall; mẫu cách 2 giây có thể bỏ lỡ người xuất hiện
ngắn. Ảnh candidate được lưu tại
`output/d06-person-review/camera185-person-candidate.jpg`, từ video đầu ở
media time 158s (OSD 07:32:37), bbox `[1231,480,87,185]` trên ảnh 1920×1080.
Quan sát ảnh cho thấy một người đi cạnh xe được đóng khung hợp lý. Đây chỉ là
bằng chứng đề xuất; không kết luận cabin trống, tài xế đã xuống, xe cân được,
hoặc đúng/sai nghiệp vụ.

Không tìm thấy video/capture camera `.172` trong `Video_camera` hoặc evidence
camera; chưa thử kết nối camera. Cần cung cấp một đoạn video gốc ngắn từ .172,
độ phân giải native, thấy bàn cân + cabin + vùng người có thể bước xuống,
kèm kênh và timestamp/OSD; không cần gửi credential.

### Phác thảo vận hành ROI/người

- Mỗi camera giữ profile và tọa độ riêng: `weighbridge` polygon, `cab/vehicle`
  area và vùng xuống xe hai bên (các vùng cần xác nhận trên overlay gốc). ROI
  bàn cân .185 hiện là polygon provisional trong
  `edge-agent/config/camera-185.live.json`; không tái dùng polygon này làm ROI
  cabin/người. Camera .172 cần profile mới sau khi nhận video.
- Tracking chỉ theo từng camera. Không ghép ID xuyên camera. Kích hoạt person
  inference chỉ trong active observation có timeout/budget, không chạy vòng
  liên tục lúc idle. Nếu không detect người thì kết quả `unknown/no evidence`,
  không phải “cabin trống” hoặc cho phép chốt cân.

## Kiểm tra

- `npm run build` trong `frontend`: thành công.
- `python3 scripts/test-d02.py`: **72 passed, 1 warning** trên PostgreSQL tạm;
  có test chart tách phân trang, giảm mẫu giữ cực trị, scope theo cơ sở, thống
  kê qua ranh giới ngày VN, batch backfill và vùng không có tín hiệu không bị
  diễn giải thành lượt cân/trọng lượng 0. DB tạm đã xóa; app DB/volume giữ nguyên.
- Không tạo migration, không thay đổi raw signal/D02, không gọi API AI, không
  train hoặc thuê GPU.


## S03d — sửa biểu đồ và điều tra sender, 12/10 khoảng 13 giờ

Lỗi trước sửa: SVG vẽ chấm lớn trên mọi điểm khiến chấm che đường; gap được
suy ra từ khoảng cách **điểm đã giảm mẫu**, nên một chuỗi raw liên tục vẫn có
thể bị ngắt. Bộ lọc nhanh còn giữ mốc kết thúc lúc mở/chọn trang.

Đã sửa:

- LAG theo observed time của raw từng agent, rồi đánh số đoạn khi gap >60s.
  Giữ series key đó qua giảm mẫu; không dùng khoảng cách giữa điểm giảm mẫu
  để suy ra nguồn mất dữ liệu. Không nối hai agent hoặc qua gap thật.
- Time bucket giữ đầu/cuối/min/max, tối đa 1.200 mặc định/2.000 điểm. Điểm
  vẫn có timestamp/weight raw; không làm mượt, không thêm cân 0.
- Bỏ chấm trên toàn chuỗi; chấm hiện cho đoạn đơn lẻ hoặc điểm đang xem.
  Trục dùng một đơn vị, tick dễ đọc; tooltip/tap, kéo zoom có vùng chọn.
- Nút **Xem rõ đoạn tín hiệu cuối** mở khoảng ngắn và tải lại dữ liệu đúng
  khoảng đó. Ở khoảng 24h, đợt cân vài phút vẫn rất hẹp theo trục thời gian
  thật; không kéo giãn từng lượt rồi gọi đó là trục thời gian liên tục.
- Preset 1h/24h/7d/tháng tự tính tới hiện tại khi polling. Custom/zoom giữ
  khoảng lịch sử cố định, có thông báo rõ. Bảng/chart vẫn phân trang độc lập.
- Reuse heartbeat route; staff/manager thấy trạng thái delivery an toàn
  paused/pending/no_pending/unknown và số pending, quyền cơ sở không đổi.
  UUID/version/mã lỗi/uptime kỹ thuật vẫn admin-only. Lỗi refresh có nhãn
  snapshot cũ, không biến thành PC offline.

### Hai snapshot chỉ đọc

| Giờ VN | Heartbeat sequence | Server nhận heartbeat | Pending | Mã lỗi | Số signal / latest seq |
|---|---:|---|---:|---|---|
| 12:52:23 | 4765 | 12:52:17 | 1309 | SIGNAL_SENDER_PAUSED | 12982 / 12982 |
| 13:11:50 | 4804 | 13:11:47 | 1483 | SIGNAL_SENDER_PAUSED | 12982 / 12982 |

Reader ở cả hai lần là empty; vendor process ở lần đầu đang chạy. Lần đọc
thành công gần nhất đã thay từ 11:40:46 thành 13:10:49. Đây là trạng thái
client báo; chưa thấy weight cụ thể trong outbox Windows. Signal mới nhất DB
vẫn observed **00:16:53**, received **03:41:35** ngày 12/10. Heartbeat đang đi
được; client báo sender riêng bị pause và backlog tăng, chứ không phải web
cache giấu signal mới đã commit.

Readiness local/tailnet 200; Tailscale gateway direct. API access log khoảng
trước/sau sửa vẫn heartbeat 200; không thấy batch gửi trong khoảng kiểm tra.
Mac chưa biết nguyên nhân cờ pause phát sinh từ config/thao tác/lỗi nào vì
source/config Windows đang chạy không có tại đây. Hướng xử lý trên đúng PC
nằm trong `windows-scale-sender-recovery-20261012.md`; chưa tuyên bố khôi phục
được signal mới. Không đổi token, sequence, outbox hoặc dữ liệu lịch sử.

### Kiểm tra sau sửa

- `npm run build --prefix frontend`: đạt.
- `python3 scripts/test-d02.py`: 74 passed; gồm regression chuỗi raw liên tục
  nhưng điểm giảm mẫu cách xa, gap thật qua sampling, agent khác series,
  quyền cơ sở, duplicate/backfill. DB kiểm thử tạm riêng đã xóa.
- `python3 scripts/test-d05m.py`: 18 passed; thêm status sender paused cho
  manager/staff đúng scope; heartbeat không tạo signal. DB tạm riêng đã xóa.
- Mỗi runner có một warning deprecation Starlette/anyio đang có.
- API/web rebuild, readiness local/tailnet và web 200. Không migration.
- Chrome session Manager: 1h trống → 24h có dữ liệu → đoạn cuối **149/149**
  mẫu, **00:15:09–00:17:23**. Tap ra 3,21t, observed 00:16:30, received
  03:41:35, sequence12937. Kéo zoom 00:15:41–00:16:27 tải **92/92** mẫu.
  Giao diện hiển thị PC liên lạc/reader empty/sender pause/pending1483.
- Ảnh: `output/scale-monitoring-20261012/chart-fixed.png`.
- Git checkout toàn repo untracked; diff trước/sau được đọc từ bản chụp tạm,
  `git diff --check` sạch. Không stage/commit; DB/volume ứng dụng giữ nguyên.


## 13/10/2026 — S03e: tổng quan theo điểm đại diện và zoom

### Định nghĩa biểu đồ

- `GET /api/scale-monitoring/signals/chart` có `view=raw|overview|auto`.
  Default API vẫn raw để tương thích client cũ; web gửi auto. Auto dùng overview
  khi khoảng lọc dài hơn 3 giờ; khoảng ngắn dùng raw. Chọn chế độ bằng tay được.
- Một đoạn hiển thị là chuỗi raw cùng agent không có gap observed >60s.
  Đây là nhóm để vẽ, **không phải entity lượt cân quan sát/đã chốt**, không
  kết luận xe rời khi gap. Nhóm được tính lại trong khoảng lọc hiện tại.
- Overview lấy **một event thật** có weight xuất hiện nhiều nhất trong đoạn;
  nếu đồng hạng, chọn event gần giữa thời gian đoạn, rồi tie-break bằng ID.
  `representative_method=most_frequent_weight_actual_sample_v1`. Giữ nguyên
  event ID, sequence, observed/received và weight. Trả start/end/count của đoạn
  để truy về raw. Không coi đây là kiểm tra ổn định thời gian/biên độ.
- Mỗi điểm cách đều theo **thứ tự đoạn**; tick/tooltip ghi giờ thật. Khoảng
  cách ngang không thể hiện thời lượng. Đường nối nét đứt so sánh các điểm,
  không nội suy trọng lượng lúc không có mẫu. Raw view giữ trục thời gian thật
  và ngắt đường theo raw gap. Như vậy các đợt vài phút trong nhiều ngày không
  bị ép thành cột dọc, đồng thời giữ được diễn biến gốc khi mở một điểm.
- One point/segment trong giới hạn 1.200 mặc định, tối đa 2.000; nếu số đoạn
  vượt giới hạn, giảm mẫu đại diện theo time bucket first/last/min/max và báo
  rõ số đoạn ban đầu/số điểm còn lại. Không tải toàn bộ raw vào trình duyệt.
- Bảng phân trang, summary theo ngày VN và KPI chưa đủ dữ liệu vẫn riêng.
  Không SUM weight hoặc lấy số điểm đại diện làm số lần cân đã xác nhận.

### Cách zoom

1. Nhấp đúp một điểm overview: mở raw trong start/end đoạn +30s hai phía.
2. Kéo ngang chọn vùng: overview ánh xạ sang bounds các đoạn; raw chọn khoảng
   theo thời gian. API lấy lại dữ liệu cho khoảng đó.
3. Nút Phóng to/Thu nhỏ: giảm/tăng gấp đôi khoảng thời gian quanh tâm.
4. Quay lại khoảng trước/Đặt lại zoom: history tối đa20 trạng thái gồm range,
   preset và view. Preset mới hoặc Apply custom là một khoảng gốc mới.

Các nút nằm ngoài component chuỗi dữ liệu để vẫn quay lại/thu nhỏ được khi
zoom vào khoảng trống. Zoom đổi điều kiện đọc API; không ghi dữ liệu.

### Kiểm tra thực tế

- `npm run build --prefix frontend`: đạt.
- `python3 scripts/test-d02.py`: **77 passed, 1 warning** Starlette/anyio;
  PostgreSQL tạm đã drop, DB ứng dụng giữ nguyên. Ba regression mới kiểm tra
  mẫu đại diện có thật/modal/tie/metadata và không tạo WeighEvent, bounded giữ
  cực trị đại diện, auto theo span và empty không tạo zero. Scope/backfill cũ
  vẫn đạt. Không thay heartbeat/router ingestion nên không chạy lại pilot suite.
- API/web rebuild và healthy. Không migration; giữ nguyên raw, token/outbox,
  Windows agent, D02. Git diff check sạch, toàn checkout untracked, không
  stage/commit; diff nguồn kiểm tra đối chiếu bản chụp trước sửa.
- Chrome session Manager: 7 ngày auto trả **63 điểm / 12.982 raw**, point nối
  theo thứ tự. Nhấp đúp điểm mở **199/199** mẫu trong
  11/10 **10:23:11–10:25:50**. Phóng to trả160 mẫu trong10:23:50–10:25:10;
  thu nhỏ199 mẫu; Quay lại khôi phục160; Đặt lại quay về63 điểm/7 ngày.
- Kéo overview chọn vùng trả17 điểm/3.239raw trong
  10/10 23:42:59–11/10 11:48:18. Đặt lại khôi phục63 điểm.
- Ảnh giao diện: `output/scale-monitoring-20261013/overview.png`.
- Chỉ quan sát trạng thái hiện có: sender Windows vẫn paused, UI pending8755
  lúc khoảng06:42 ngày13/10; latest observed00:16:53 ngày12/10. Task biểu đồ
  không khôi phục sender và không tuyên bố có cân mới.
