# Tiến độ D00–D02 và S00–S04

## D00 — nền tảng dự án

Trạng thái: **hoàn thành**.

### Đã làm

- Tạo repository độc lập `nhu-tung-demo`, không chỉnh sửa repository cà phê.
- Dựng khung FastAPI, SQLAlchemy engine, Alembic baseline rỗng và hai health
  endpoint.
- Dựng giao diện tổng quan tiếng Việt, điều hướng placeholder được đánh dấu
  “Sắp có”, trạng thái API/DB gọi trực tiếp, không sinh số liệu nghiệp vụ giả.
- Tạo Docker Compose web/API/PostgreSQL với volume named, healthcheck và script
  up/status/logs/migrate/down; lệnh down không xóa volume.
- Ghi nhận quy tắc nghiệp vụ và câu hỏi mở trong tài liệu.
- Khóa dependency bằng `frontend/package-lock.json` và `backend/uv.lock`; thêm
  favicon, responsive menu và healthcheck cho cả ba dịch vụ Compose.

### Kiểm tra môi trường ban đầu

- Máy: macOS 15.7.5, Apple Silicon arm64; Node.js 20.19.4, npm 10.8.2, Python
  3.14.6, Git 2.48.1. `uv 0.8.17` tạo môi trường Python 3.13.5 để khóa/cài
  dependency; PostgreSQL local là 17.5.
- Lúc kiểm tra ban đầu Docker CLI chưa kết nối được daemon/socket. Daemon sau đó
  hoạt động; đã chạy nghiệm thu Compose đầy đủ.
- PostgreSQL local đang chạy ở `127.0.0.1:5432`; không dừng hoặc chiếm dịch vụ
  này. Cổng Compose host được đặt riêng là 5433, API 8001, web 5174.

### Kết quả nghiệm thu

- **Đã chạy — thành công:** `npm ci` và `npm run build`; TypeScript và Vite
  build đạt. npm audit báo 0 vulnerability.
- **Đã chạy — thành công:** `uv lock`, `uv sync --frozen`; FastAPI 0.118.2,
  SQLAlchemy 2.0.43, psycopg 3.2.10. Migration mới tạo
  `0001_d00_platform_baseline`; Alembic báo revision `head`.
- **Đã chạy — thành công:** `/api/health/live` và `/api/health/ready` trả 200
  khi database kết nối. Chặn kết nối tới database kiểm tra riêng làm readiness
  trả 503, live vẫn trả 200; mở lại kết nối làm readiness trở về 200.
- **Đã chạy — thành công:** trước khi Compose khả dụng, tạo marker trong
  database native riêng và xác nhận marker còn sau khi restart tiến trình API;
  sau đó đã xóa database native này.
- **Đã chạy — thành công:** `docker compose ... config --quiet` và
  `docker compose ... build` cho web/API; build đa kiến trúc ARM64 hoàn tất.
  `npm ci` trong image báo 0 vulnerability.
- **Đã chạy — thành công:** `./scripts/dev.sh up` chạy migration mới trên
  PostgreSQL container; cả ba service `db`, `api`, `web` báo healthy. Các
  endpoint live/ready và web trả HTTP 200.
- **Đã chạy — thành công:** dừng riêng database container làm `live` vẫn 200,
  `ready` trả 503; khởi động lại DB làm `ready` trở về 200.
- **Đã chạy — thành công:** tạo marker tạm trong volume PostgreSQL; chạy
  `./scripts/dev.sh down` rồi `up` lại vẫn đọc được marker. Đã xóa bảng marker;
  giữ volume sạch và stack Compose đang chạy.
- **Đã chạy — thành công:** trình duyệt desktop 1440×960 và mobile 390×844;
  không tràn ngang. Menu mobile mở được. Qua web container, giao diện đổi sang
  “Mất kết nối API” khi dừng API và trở về sẵn sàng khi API chạy lại. Sau khi
  thêm favicon, console không còn lỗi tải tài nguyên.
- **Đã chạy — thành công:** production preview trả 200 cho HTML, bundle JS, CSS
  và favicon.
- Database marker kiểm tra trên PostgreSQL native đã được xóa riêng sau khi
  xác minh. PostgreSQL máy chủ native vẫn hoạt động và không bị dừng.
- Ảnh giao diện đã lưu tại `output/playwright/desktop-dashboard.png` và
  `output/playwright/mobile-dashboard.png`.

### Trạng thái bàn giao

- Docker Compose stack đang chạy ở web `http://localhost:5174`, API
  `http://localhost:8001`, PostgreSQL host port `5433`.
- `.env` có mật khẩu ngẫu nhiên chỉ dùng local và được `.gitignore` bỏ qua.
- D01 được triển khai bên dưới; chưa bật tài nguyên cloud hoặc truy cập thiết
  bị camera/cân.

## D01 — đăng nhập, tài khoản, phân quyền và phạm vi cơ sở

Trạng thái: **hoàn thành**.

### Đã làm

- Thêm migration Alembic `0002_d01_accounts_sessions`; giữ nguyên baseline
  `0001_d00_platform_baseline`. Migration tạo users, facilities, liên kết
  user–facility, auth sessions, login attempts và account audit.
- Thêm đăng nhập/đăng xuất/thông tin bản thân, đổi mật khẩu, đổi cơ sở đang
  chọn; cookie session opaque 256-bit, HttpOnly, SameSite=Lax, TTL mặc định
  8 giờ cấu hình được, Secure với môi trường ngoài local/development/test.
  Database chỉ lưu SHA-256 session-token hash. Session được đọc từ DB mỗi lần
  gọi API và còn hiệu lực sau restart API.
- Thêm Argon2id qua `argon2-cffi==25.1.0`; thư viện và tham số được ghi tại
  `docs/architecture.md`. Bổ sung `pytest`/`httpx` trong dev dependency group,
  khóa trong `backend/uv.lock` để kiểm thử API.
- Mọi POST/PATCH cần CSRF synchronizer token được HMAC-bind với session ở
  `X-CSRF-Token`; token ổn định trong session, chỉ trả trong JSON và frontend
  giữ trong memory. Không dùng localStorage hoặc
  sessionStorage cho thông tin xác thực. Lỗi validation không echo raw body.
- Giới hạn đăng nhập mặc định 5 lần/15 phút theo username chuẩn hóa; lỗi đăng
  nhập dùng thông báo chung. Log và audit không chứa mật khẩu, password hash,
  cookie/session token hoặc request body.
- Thêm bootstrap Admin tương tác: prompt username/tên hiển thị, nhập và xác nhận
  mật khẩu ẩn; không có mật khẩu mặc định, không nhận mật khẩu qua argv, chạy
  lại không ghi đè hoặc tạo thêm Admin. Có thể tạo cơ sở `DEMO` idempotent.
- Admin tạo/sửa tài khoản, role, phạm vi cơ sở, bật/tắt tài khoản, đặt lại mật
  khẩu; danh sách có tìm kiếm, lọc và pagination phía backend; trang có ngày tạo,
  lần đăng nhập gần nhất và tab audit. Không có API xóa account.
- API kiểm tra role/scope từ DB ở từng request. Manager/staff cần tối thiểu một
  cơ sở hoạt động và chỉ thấy cơ sở đang hoạt động được gán. Chặn xem cơ sở khác
  và chặn Admin cuối cùng đang hoạt động bị vô hiệu hóa/hạ quyền trong
  transaction. Tắt tài khoản hoặc đổi/đặt lại mật khẩu thu hồi session.
- Proxy Vite đưa `/api` cùng origin tới API; UI đăng nhập, kiểm tra phiên sau khi
  tải lại, đổi mật khẩu/đăng xuất, chọn cơ sở, điều hướng Admin và quản lý tài
  khoản. 401 tách biệt lỗi mạng/503; Manager/staff không thấy menu Admin hoặc
  thông tin kỹ thuật. Các nghiệp vụ chưa triển khai vẫn ghi “Sắp có”.

### Ma trận quyền D01

| Vai trò | Tài khoản/audit | Trạng thái API/DB chi tiết | Cơ sở được liệt kê/chọn |
| --- | --- | --- | --- |
| Admin | Quản lý và xem audit | Có | Mọi cơ sở đang hoạt động |
| Manager | Không | Không | Cơ sở đang hoạt động được gán |
| Staff | Không | Không | Cơ sở đang hoạt động được gán |

D01 chưa cấp quyền sửa dữ liệu nghiệp vụ cho Admin; Manager/Staff chưa có API
nghiệp vụ trong các task sau.

### Kết quả kiểm tra

- **Đã chạy — thành công:** `npm run build` (TypeScript và Vite production
  build).
- **Đã chạy — thành công:** `./scripts/test-d01.py`; 11 kiểm thử API đạt trên
  PostgreSQL database tạm riêng. Bao gồm CSRF, generic login/rate limit, cookie
  flags, role/scope hai cơ sở, thay đổi quyền có hiệu lực ngay, deactivate/reactivate,
  reset/change password, Admin cuối cùng, audit/không echo secret, bootstrap và
  session sống qua restart tiến trình API. Database kiểm thử được xóa sau lượt
  chạy; volume ứng dụng không bị tác động.
- **Đã chạy — thành công:** `uv lock --check` và `python -m compileall` cho
  `app`, `migrations`, `tests`.
- **Đã chạy — thành công:** `./scripts/dev.sh up`; migration D01 áp dụng lên
  database Compose hiện có, không reset dữ liệu. `db`, `api`, `web` healthy; host
  port vẫn 5433/8001/5174; PostgreSQL native 5432 không bị tác động.
- **Đã chạy — thành công:** kiểm tra browser trên API/database kiểm thử riêng.
  Đăng nhập, tải lại vẫn giữ phiên; Admin tạo staff/gán cơ sở, vô hiệu hóa rồi
  kích hoạt; staff không thấy menu Admin và đường dẫn `/admin/accounts` quay về
  tổng quan. Đăng xuất đưa về trang đăng nhập. Desktop 1440×960 và mobile
  390×844; `scrollWidth` bằng viewport ở cả trang staff và trang tài khoản.
- **Ảnh đã lưu:** `output/playwright/d01-login.png`,
  `output/playwright/d01-accounts-desktop.png`,
  `output/playwright/d01-staff-desktop.png`,
  `output/playwright/d01-staff-mobile.png`.
- **Cảnh báo duy nhất:** Starlette TestClient phát deprecation warning cho alias
  `anyio.abc.BlockingPortal`; không làm fail kiểm thử.

### Trạng thái bàn giao D01

- Mở web local tại `http://localhost:5174`; API docs tại
  `http://localhost:8001/docs`.
- Database ứng dụng chỉ nhận migration; không có tài khoản kiểm thử hoặc Admin
  được tạo tự động. Sau khi khởi động stack, tạo Admin bằng lệnh ở README rồi
  đăng nhập. Dữ liệu test đã ở DB riêng và được xóa.
- D01 hoàn tất trước D02; chưa tạo tài nguyên cloud.

## D02 — lịch hàng, chuyến xe, cân thủ công và giao dịch nhập/xuất

Trạng thái: **hoàn thành**.

### Đã triển khai

- Revision mới `a4e0b078241b` nối tiếp `0002_d01_accounts_sessions`; tạo
  danh mục xe, lịch/dòng hàng dự kiến, chuyến, lượt cân/kết quả cân, loại hàng,
  giao dịch và audit nghiệp vụ. Không sửa migration D00/D01; không seed dữ liệu.
- Thêm API D02 theo phiên cookie và CSRF D01. Scope/role được lấy từ DB tại
  từng request; staff/manager chỉ thao tác ở cơ sở được gán; admin chỉ đọc.
  Tất cả ID và liên kết trong body được kiểm tra facility phía backend.
- Thêm UI Chuyến xe (lọc ngày/biển số/trạng thái, phân trang), Lịch hàng
  (tạo/sửa/hủy manager), Cần xác nhận, chi tiết chuyến/timeline, ghi cân,
  đánh dấu cân lại, chọn kết quả, tạo/sửa/gửi giao dịch, manager xác nhận/trả
  lại/hủy có lý do, gắn xe và tạo loại hàng. Có lịch sử audit theo chuyến.
- Cân và giao dịch dùng `NUMERIC(14,3)`/Decimal, lưu UTC và hiển thị giờ VN.
  Cân nhập = trước − sau; cân xuất = sau − trước. Backend kiểm tra mốc được
  chọn, chiều/dương, cùng chuyến/cơ sở và chặn khoảng giao dịch chồng lấn.
  Idempotency key, khóa chuyến, version nháp và audit dùng cho các thao tác
  nhạy cảm. Bản cân thay thế không ghi đè số gốc và làm nháp cần rà soát.
- Tổng quan truy vấn dữ liệu thật theo facility/ngày `Asia/Ho_Chi_Minh`; chỉ
  cộng transaction confirmed, dùng nhãn lượng đã nhập/đã xuất, không gọi là
  tồn kho. Chuyến không có xe vẫn tồn tại/cân được nhưng không thể hoàn tất.

### Quyết định demo cần xác nhận với công ty

- Ma trận staff/manager/admin; admin chỉ đọc D02.
- Một chuẩn hóa biển số duy nhất trong từng cơ sở; không tự ghép hai bản ghi.
- Cần đủ hai lời xác nhận thủ công (vị trí xe và người đã xuống) mới chọn được
  kết quả cân.
- Chênh lệch giao dịch phải dương; khoảng pending/confirmed không được chồng
  lấn; khoảng kế tiếp được dùng chung đúng một mốc.
- Hủy có lý do và tạo bản thay thế giữ liên kết; trip chỉ hoàn tất khi có xe,
  không còn cân chờ và giao dịch nháp/chờ.

### Kết quả kiểm tra đến hiện tại

- **Đã chạy — thành công:** `npm run build` sau UI D02.
- **Đã chạy — thành công:** `./scripts/test-d02.py`; migration đầy đủ trên
  PostgreSQL tạm, 11 regression D01 + 9 test D02 (20 tổng) đạt. Các test có
  import/export, 2 loại hàng qua 3 mốc, reweigh, mixed trip, mốc thiếu xác nhận,
  giá trị 0/sai chiều, facility/trip boundaries, trùng/chồng lấn, role,
  sửa/hủy/thay thế, retry, song song confirm, version stale và ngày VN. Test DB
  được drop sau chạy; DB/volume ứng dụng không bị test chạm tới.
- **Đã chạy — thành công:** áp dụng migration `a4e0b078241b` lên Compose DB hiện
  có bằng DDL transaction, không reset volume; Alembic báo `head`. `db`, `api`,
  `web` healthy; `/api/health/live`, `/api/health/ready` và web trả HTTP 200.
  Xác nhận `users=0`, `auth_sessions=0`; không tạo tài khoản ở DB ứng dụng.
- **Đã chạy — thành công:** trên PostgreSQL nghiệm thu tạm riêng, trình duyệt
  staff đăng nhập, tạo chuyến chưa biết biển số, ghi hai lượt cân manual có xác
  nhận, tạo và gửi giao dịch nhập 5.000 kg; tạo chuyến xe đã biết biển số, ghi
  hai lượt cân manual, tạo và gửi giao dịch xuất 3.000 kg. Thời gian hiển thị là
  giờ Việt Nam. DB nghiệm thu và hai tiến trình UI/API tạm đã được xóa/dừng.
- **Đã kiểm tra:** giao diện desktop 1440×960 và mobile 390×844; không tràn
  ngang trên mobile (390 px). Ảnh mới: `output/playwright/d02-trip-detail-desktop.png`
  (desktop) và `output/playwright/d02-trips-list-mobile.png` (mobile).
- **Đã chạy — thành công:** `npm run build`, `py_compile` các module/migration D02,
  `git diff --check` và `./scripts/test-d02.py`; 11 regression D01 + 9 test D02
  (20 tổng) đạt trên database tạm riêng, tự xóa sau chạy. Cảnh báo duy nhất là
  deprecation alias `anyio.abc.BlockingPortal` của Starlette TestClient.

### Trạng thái bàn giao D02

- Compose local vẫn chạy tại web `http://localhost:5174`, API `http://localhost:8001`,
  PostgreSQL host port `5433`. Database ứng dụng chỉ nhận migration mới; volume
  được giữ và hiện chưa có tài khoản. Tạo Admin thủ công theo README khi bắt đầu
  sử dụng.
- Không tạo dữ liệu seed hoặc tài nguyên cloud; chưa bắt đầu D03.

## Nhánh S — Scale agent ingestion

S00: **phạm vi giao thức đã xác lập**. S01: **hoàn thành**. S02–S04: chưa bắt
đầu.

### S01 đã triển khai

- Thêm migration additive `d31a9c72b045` nối sau `a4e0b078241b`, tạo
  `scale_agents` và `scale_signals`; không sửa migration D00–D02, không seed.
  Token hash, scale code trong facility, unique event/sequence và index theo
  `(agent_id, observed_at_utc)` được giữ ở PostgreSQL. Tín hiệu là bảng riêng,
  không tự tạo hoặc sửa D02.
- Thêm `POST /api/scale-ingestion/batches` với Bearer token agent, kiểm tra
  is_active và facility theo mỗi request, UUID/sequence, timestamp UTC, Decimal,
  body/event/field limit, validation future skew cấu hình được. Cookie/CSRF không
  tham gia xác thực. Insert dùng unique constraints và conflict read-back trong
  một transaction; ACK chỉ sau commit.
- Thêm CLI agent create/disable/rotate-token; chỉ lưu hash trong DB, token được
  tạo ngẫu nhiên và ghi file Git-ignored với quyền 0600; lệnh chỉ in ID/path.
  Thêm simulator Mac có state/outbox bền vững, modes `valid`, `drop-ack`,
  `resend`; không có client Windows hay kết nối thiết bị.
- Tài liệu hợp đồng tại `docs/scale-ingestion-v1.md`, gồm ví dụ giả, ACK
  checkpoint và giới hạn về stale/unstable reading. Thêm nhánh S00–S04 bên cạnh
  task D.

### Kết quả nghiệm thu S01

- **Đã chạy — thành công:** `./scripts/test-d02.py` trên PostgreSQL tạm, migration
  đầy đủ từ đầu; D01 + D02 + S01 đạt **47 passed**, một deprecation warning
  Starlette TestClient. Các test S01 bao gồm bearer-only, agent/facility active,
  CLI standalone tạo agent/đổi token/disable và map host DB,
  batch/duplicate/mixed batch, decimal canonicalization, ID/sequence conflict,
  concurrent same-event, atomic rollback, backfill, future timestamp, database
  503, body size và D02 isolation. Test database được drop.
- **Đã chạy — thành công:** simulator smoke trên DB/API thử riêng. Gửi batch mới,
  giả lập bỏ qua ACK (outbox còn), gửi lại nhận duplicate ACK; database cuối có
  bốn signal (hai batch) không trùng. Token test và DB thử được xóa sau đó.
- **Compose:** migration S01 áp dụng thêm lên DB hiện có, không reset volume;
  kiểm tra app DB không có agent/signal do nghiệm thu. Stack giữ nguyên cổng
  web/API/PostgreSQL.
- **Giới hạn:** không có Windows .NET Framework client, không kết nối
  CANXE2015/COM/đầu cân/camera, không xác minh tín hiệu ổn định hoặc UI còn cập
  nhật, không ghép xe và không tích hợp signal vào lượt cân D02. Chưa triển khai
  S02 hay tài nguyên cloud.

## S03a — đối chiếu nguồn giả Windows → API → PostgreSQL

Trạng thái: **hoàn tất cho luồng nguồn giả Windows → API → PostgreSQL**.
Ngày 06/10/2026, tiêu chí timestamp được thống nhất là UTC/microsecond, bỏ
phần dư sau chữ số thứ 6, không làm tròn; so sánh bằng chính xác sau chuẩn hóa.
S03b đọc CANXE2015 và đo tài nguyên **chưa thực hiện**.

### Phạm vi và nguồn bằng chứng

- Đợt nguồn giả Windows ngày **06/10/2026, 08:30:14–08:30:21 giờ Việt Nam**,
  run `6ede5e9a-3a7c-4f7e-bd1b-1b808c36faee`, agent
  `06c70368-50a1-470d-bf26-45391cd05069`, endpoint
  `http://192.168.1.17:8001/api/scale-ingestion/batches`.
- Đã đọc ba file trong `/Users/nguyen_bao/Downloads/`: `MACBOOK-HANDOFF.md`,
  `event-ids-for-macbook.csv`, `macbook-check.sql`. SQL bàn giao chỉ có hai
  `SELECT`; đã đọc trước, kiểm tra schema và thực hiện trong transaction chỉ đọc.
- **Đã chạy — truy vấn thành công:** `docker compose --env-file .env -f
  compose.local.yml exec -T api python ...`, dùng trực tiếp `engine` của API
  đang chạy. Kết nối là host `db`, port `5432`, database `nhutung` của stack
  ứng dụng; migration `d31a9c72b045`. Mọi truy vấn chạy trong transaction
  `REPEATABLE READ, READ ONLY`, PostgreSQL xác nhận `transaction_read_only=on`.
  Snapshot đầu: **06/10/2026 08:41:06 giờ Việt Nam**; đối chiếu lại theo chuẩn
  microsecond trước/sau kiểm thử: **08:48:59 / 08:49:25 giờ Việt Nam**.
- Bằng chứng local (Git ignore, file 0600):
  `data/s03a-acceptance/postgresql-verification-2026-10-06.json` giữ nguyên
  lượt đối chiếu đầu khi tiêu chí độ phân giải chưa được thống nhất;
  `data/s03a-acceptance/postgresql-microseconds-final-2026-10-06.json` ghi
  kết luận mới theo chuẩn đã xác nhận, gồm manifest SHA-256, kết quả đọc DB,
  so sánh từng ID và dấu vân tay dữ liệu trước/sau kiểm thử. Không có token,
  hash token hoặc connection string chứa mật khẩu trong báo cáo.

### Kết quả đối chiếu

- CSV có **9 dòng / 9 event ID phân biệt**. PostgreSQL tìm thấy **9/9 ID**,
  mỗi ID đúng một bản ghi kể cả khi tìm trên mọi agent; tất cả thuộc đúng agent
  được yêu cầu. **ID thiếu: 0; ID thừa của agent: 0; ID nhiều bản ghi: 0**.
- Tổng dữ liệu của agent là **9 bản ghi**, 9 event ID và 9 sequence phân biệt,
  sequence 1–9; không có dữ liệu khác của agent, không có sequence trùng.
- Sequence, trọng lượng (so sánh bằng Decimal) và source khớp cả 9 dòng.
  Source `canxe2015_ui` là giá trị hợp đồng; đợt thử này vẫn là **nguồn giả**.
  Không có signal dưới 1.000 kg trong dữ liệu của agent.
- `observed_at_utc` khớp chính xác cả **9/9 dòng sau chuẩn hóa UTC/microsecond**,
  và khác `received_at_utc`: thời gian quan sát cũ được lưu khi nhận muộn.
  Có 8 timestamp nguồn với phần dư **0,2–0,9 microsecond**, ngoài độ phân giải
  đã thống nhất; phần dư bị bỏ, không làm tròn. Đây là chuẩn hóa độ phân giải,
  không phải lỗi mất dữ liệu theo hợp đồng. Sequence 3 có chữ số thứ 7 bằng 0.
  Đối chiếu dùng thuật toán bỏ phần dư độc lập và phép bằng chính xác; không
  dùng dung sai và không thay dữ liệu để làm khớp manifest.
- D02 hiện có **0 dòng** trong `trips`, `weigh_events`, `weigh_results`,
  `goods_transactions`, `business_audit_logs`, `vehicles`, `schedules`,
  `schedule_lines`, `goods_items`. Không có trigger người dùng trên
  `scale_signals`; route S01 chỉ ghi bảng signal. Không có dữ liệu D02 tồn tại
  do đợt nhận signal này.
- SHA-256 manifest vẫn khớp bàn giao ban đầu. Các trường signal đã truy vấn
  không đổi so với snapshot 08:41:06; dấu vân tay toàn bộ các bản ghi signal,
  dữ liệu D02 và metadata agent không đổi giữa snapshot trước/sau kiểm thử.
- ACK và số log HTTP không được dùng làm bằng chứng số hàng PostgreSQL.

### Làm rõ hợp đồng và kiểm thử hồi quy

- Code đang chạy đã đúng: validator dùng `datetime.fromisoformat` rồi chuẩn
  hóa UTC; bỏ chữ số thứ 7 thay vì làm tròn. Chống trùng so sánh datetime đã
  chuẩn hóa bằng `==`, không dùng dung sai. **Không sửa code API hoặc schema**;
  chỉ bổ sung hợp đồng `docs/scale-ingestion-v1.md` và kiểm thử.
- Thêm **11 trường hợp kiểm thử** trong `backend/tests/test_scale_ingestion.py`:
  `.1234561`/`.1234569` → `.123456`, `.9999999` → `.999999` cùng giây, cho cả
  `Z` và `+00:00`; xác nhận kết quả parse và giá trị PostgreSQL thực tế.
  Gửi lại timestamp 7 chữ số hoặc biểu diễn 6 chữ số tương đương đều nhận
  duplicate ACK, giữ nguyên thời gian quan sát/nhận đã lưu. Thay đổi timestamp
  đã chuẩn hóa ±1 microsecond trả 409 và rollback event mới cùng batch.
- Kiểm thử ranh giới tương lai xác nhận timestamp chuẩn hóa bằng ngưỡng được
  nhận, vượt 1 microsecond bị từ chối atomar. Giả lập lỗi commit xác nhận 503,
  không ACK, không bản ghi tồn tại; retry sau khôi phục commit mới nhận ACK.
- **Đã chạy — thành công:** `./scripts/test-d02.py`, migration đầy đủ trên
  database PostgreSQL tạm riêng; **58 passed, 1 warning, 10,61 giây**.
  Bao gồm regression D01/D02/S01 về future skew, concurrent/idempotency,
  atomic, backfill và ranh giới D02. Warning là deprecation alias
  `anyio.abc.BlockingPortal` của Starlette TestClient. DB tạm được drop sau chạy.
- **Đã chạy — thành công:** đối chiếu chỉ đọc bằng
  `python3 data/s03a-acceptance/verify-microsecond-contract.py
  postgresql-microseconds-final-2026-10-06.json
  postgresql-microseconds-before-tests-2026-10-06.json` trên engine của API
  ứng dụng; mọi kiểm tra đạt theo chuẩn mới, không có trường không khớp.
- `/api/health/ready` qua `192.168.1.17:8001` trả `{"status":"ok"}`; Compose
  API/web/PostgreSQL healthy. Migration ứng dụng vẫn `d31a9c72b045`; không cần
  migration mới, không sửa migration cũ hoặc chạy migration trên DB ứng dụng.

### Giới hạn và trạng thái bàn giao

- Manifest và snapshot cuối cho phép đối chiếu thời gian gốc với bản ghi đã
  nhận muộn; không có snapshot từng lần gửi lại để xác minh độc lập toàn bộ
  diễn biến trung gian của retry/mất ACK/restart. Checkpoint 9, next sequence 10,
  backlog 0 và các phase client là thông tin Windows bàn giao.
- Bàn giao không có ID/giá trị của 4 mẫu dưới ngưỡng, không có `vendor_text`
  hoặc `schema_version` trong CSV để so sánh từng trường, và không có snapshot
  D02 trước lượt thử để đối chiếu lịch sử thay đổi. Các bảng D02 nêu trên đều
  rỗng ở snapshot hiện tại.
- PostgreSQL chứng minh đủ 9 event đã lưu, mỗi ID/sequence duy nhất và timestamp
  đã chuẩn hóa đúng ở snapshot. Snapshot không chứng minh số request trùng;
  duplicate ACK và các nhánh lỗi được kiểm chứng trên DB tạm, kết quả phase
  Windows được ghi riêng là bằng chứng client. Không suy diễn từ ACK/log HTTP
  thành số hàng đã được đối chiếu độc lập.
- **S03a hoàn tất cho nguồn giả** theo tiêu chí timestamp UTC/microsecond được
  người dùng thống nhất. Kết luận này thay thế trạng thái chờ ở lượt đối chiếu
  đầu; báo cáo ban đầu được giữ nguyên để truy vết quyết định.
- **S03b đọc CANXE2015 và đo tài nguyên chưa thực hiện**. Không đổi cấu hình
  Windows, token, sequence hoặc mạng; giữ nguyên 9 event và agent. Không chạy
  simulator hoặc gửi lại event nghiệm thu. Kiểm thử chỉ ghi dữ liệu giả vào DB
  tạm riêng; không triển khai task tiếp theo.

## S03 — Theo dõi cân (06/10/2026)

### Phạm vi và thay đổi

- Dùng **S03 Giám sát/tra cứu tín hiệu và chẩn đoán nguồn** đã có trong kế
  hoạch. Trang `/scales` thêm vào điều hướng; không thay task đã lên kế hoạch
  bằng mã mới. S03a vẫn hoàn tất nguồn giả; S03b chưa nghiệm thu CANXE2015 và
  đo tài nguyên, `txtkq` trống theo thông tin người dùng.
- Backend thêm router chỉ đọc `modules/scale_ingestion/monitoring.py`: catalog
  agent kèm latest, latest theo agent, lịch sử theo cơ sở/agent/khoảng quan sát
  UTC và phân trang có giới hạn. Dùng session D01 và quyền được đọc lại mỗi
  request; admin xem cơ sở đang hoạt động, manager/staff xem cơ sở hoạt động
  được gán. Truy cập ID ngoài quyền trả 404, Bearer agent không thay session.
- Latest lấy `observed_at_utc DESC, id DESC`, không lấy received_at làm thứ tự
  quan sát. Trả thời gian nhận có thật từ schema, Decimal trọng lượng và
  sequence dạng chuỗi chính xác; không trả token/hash token/vendor text.
- Chú thích `is_acceptance_test` từ đúng 9 cặp agent/event trong bằng chứng S03a
  (manifest SHA-256 ghi trong `provenance.py`). UI ghi rõ nguồn giả; event khác
  của cùng agent không tự được gắn nhãn kiểm thử. Source và bản ghi không đổi;
  không có nhãn kiểm thử không phải bằng chứng nguồn cân thật.
- UI có chọn cơ sở/cân, latest, thời gian quan sát/nhận và khoảng cách mẫu,
  lọc thời gian, lịch sử 30 dòng/trang và đồ thị điểm rời. Card latest mọi thời
  gian độc lập bộ lọc lịch sử. Hiển thị giờ Asia/Ho_Chi_Minh; query API UTC.
- Poll tuần tự, đợi 5 giây sau lượt tải, timeout 8 giây; hủy timer/request khi
  tab ẩn hoặc rời trang. Có loading, empty, lỗi/thử lại; lỗi kết nối giữ dữ liệu
  cũ cùng bộ lọc và đánh dấu chưa cập nhật. Thu hồi quyền xóa snapshot.
- UI nêu ngưỡng đọc thành công ≥1.000 kg và giới hạn ý nghĩa; không báo
  offline/zero khi thiếu mẫu, không gọi mẫu là cân ổn định/đã chốt. Không nối
  các điểm hoặc suy luận khoảng giữa chúng. Mobile cuộn riêng bảng/đồ thị;
  menu đóng khi chọn trang.
- Kiểm tra image web phát hiện cấu hình Vite preview không được copy vào
  runtime (trước sửa, GET `/api/scale-monitoring/signals` qua web trả HTML 200).
  Thêm `vite.preview.config.js` không phụ thuộc plugin build, copy vào image,
  dùng script preview rõ ràng để proxy `/api` tới API. Không đổi cổng hoặc mạng.
- Không đổi schema/migration; index agent/facility và agent/observed_at hiện
  có đủ cho truy vấn phạm vi này. Không ghi signal/D02 hoặc tạo user/agent
  trên database ứng dụng để kiểm thử.

### Kiểm thử và vận hành thực tế

- **Đã chạy — thành công:** `./scripts/test-d02.py`, migrate head trên database
  PostgreSQL tạm, **68 passed, 1 warning, 11,51 giây** ở lượt cuối. 10 trường
  hợp S03 bao phủ admin/manager/staff, gọi trực tiếp trái cơ sở, thu hồi quyền,
  cơ sở/user ngừng hoạt động, token thực sự hợp lệ với S01 vẫn bị 401 ở S03,
  lọc/phân trang/giới hạn, latest theo quan sát và tie-breaker, empty, chỉ đọc
  và nhận diện chính xác cặp agent/event. Bao gồm hồi quy D01/D02/S01 về atomic,
  ACK sau commit, timestamp microsecond, duplicate và ranh giới D02. DB tạm
  được drop; warning deprecation alias anyio của Starlette TestClient.
- **Đã chạy — thành công:** `npm --prefix frontend run build` (TypeScript/Vite),
  `./scripts/dev.sh up`, rồi build/recreate riêng web với Compose sau bổ sung
  runtime proxy. GET signal qua web không đăng nhập trả 401 JSON sau sửa
  (không còn HTML 200); readiness qua web trả ok. Migration ứng dụng ở head `d31a9c72b045`, không có revision
  mới. API/web/PostgreSQL healthy; readiness qua LAN và proxy web trả ok.
- **Đã kiểm tra bằng Playwright/Chromium trên database tạm:** có 9 mẫu, agent
  chưa có mẫu (không hiện 0), cơ sở chưa có agent, khoảng lọc không có mẫu
  nhưng latest vẫn đúng, phân trang 35 mẫu thành 30 + 5, loading, lỗi đầu tiên,
  retry; lỗi API 503 giữ 9 hàng cũ và đánh dấu chưa cập nhật. Có kiểm tra bản
  production preview sau build trên cổng loopback riêng, dùng cùng DB QA tạm.
- Desktop 1440 px và mobile 390 px: document width bằng viewport, đồ thị có
  9 circle/0 đường nối dữ liệu, đồ thị mobile rộng 720 px cuộn trong panel.
  Mở menu/chuyển trang mobile xác nhận menu đóng và 9 hàng hiển thị. Đã xem
  ảnh để kiểm tra bố cục; ảnh sử dụng fixture trên DB QA, thời gian nhận fixture
  được dựng riêng, không dùng ảnh làm bằng chứng timestamp của DB ứng dụng.
- API giả lập chậm 6 giây: tối đa 1 request theo dõi đồng thời. Rời trang trong
  browser: 0 request thêm trong 6,5 giây. Kiểm thử visibilitychange với
  document.hidden mô phỏng: 0 request trong 6,5 giây khi ẩn, nhãn tạm dừng,
  hiển thị lại tải 2 request catalog/history. Chromium automation không đổi
  document.hidden khi thử chuyển tab thực tế; vì vậy kiểm chứng nhánh ẩn là
  mô phỏng sự kiện, chưa xác minh vòng đời tab ẩn trên browser Windows thật.
- Ảnh QA: `output/playwright/s03-desktop.png`, `s03-mobile.png`,
  `s03-empty.png`, `s03-api-error.png`. Script/log QA và fixture ở `data/s03-work`
  được Git ignore; dịch vụ/database QA tạm `nhutung_s03_browser_a108c66616`
  được dọn sau kiểm tra, bao gồm các cổng loopback 15174/15175/18001.

### Đối chiếu dữ liệu và giới hạn

- **Đã chạy — thành công:** truy vấn ứng dụng qua engine API trong transaction
  REPEATABLE READ READ ONLY trước và sau thay đổi. Bằng chứng local 0600:
  `data/s03a-acceptance/postgresql-s03-before-2026-10-06.json` (09:38:17) và
  `postgresql-s03-final-2026-10-06.json` (09:56:10, giờ Việt Nam).
  Lệnh cuối: `python3 data/s03a-acceptance/verify-microsecond-contract.py
  postgresql-s03-final-2026-10-06.json postgresql-s03-before-2026-10-06.json`.
  PostgreSQL nhutung xác nhận read_only=on: 9/9 ID đúng một bản ghi, sequence
  1–9, không thiếu/thừa/trùng hoặc trường không khớp chuẩn UTC/microsecond.
  Dấu vân tay toàn bộ trường signal, D02 và metadata agent không đổi. Các
  bảng D02 vẫn rỗng như snapshot trước; không gửi lại/seed DB ứng dụng.
  Đọc/serialize chỉ đọc trên image API mới xác nhận đúng 9/9 chú thích
  kiểm thử và source vẫn `canxe2015_ui`.
- Token, sequence, volume và cấu hình Windows giữ nguyên. Không mở router,
  không tắt firewall, không thay bind/port và PostgreSQL chỉ publish localhost.
  Không triển khai cloud/Redis/WebSocket/microservice/S04; không tự chốt cân,
  gán signal vào chuyến hoặc suy luận nhập/xuất.
- Kết quả PostgreSQL và bằng chứng phía client S03a giữ phân biệt như phần
  nghiệm thu trước: snapshot không chứng minh từng retry/mất ACK/restart hoặc
  4 mẫu bị loại. Trang này chỉ quan sát signal đã lưu, không bổ sung heartbeat,
  timestamp thiết bị hoặc chứng minh ổn định. Chưa kiểm thử tải lớn, số cân
  CANXE2015 thật hoặc tài nguyên/visibility thực tế trên PC Windows.
- **S03 hoàn thành** trong phạm vi màn hình theo dõi signal đã lưu.

## D05a — pipeline xe/biển số offline bước đầu (06/10/2026)

### Mã task, dữ liệu và chọn model

- Đã đọc requirements/architecture/tasks/progress trước triển khai. Chọn mã
  **D05a** mới dưới D05 còn chưa bắt đầu; giữ tên/tiêu chí D05, ghi D05 đang
  thực hiện vì chưa nghiệm thu đọc biển công ty. Không đổi S03, task D02 hoặc
  triển khai D06/D07.
- Tìm thấy file thực `Video_camera/camera_185_20261004_103800-104015.mp4` trong
  repository: HEVC 1920×1080, 132.281 giây, 3300 frame, 34.6 MB. Đã xem các
  frame 0/30/65/100 giây và ảnh bằng chứng; không giả định attachment trong
  chat tồn tại local. Screenshot UI không dùng làm camera dataset. Listing
  Downloads bị quyền macOS từ chối; không kết luận thiếu dữ liệu ở đó.
- MacBook Pro M2 Pro 10 core/16 GB, Python 3.12.7, FFmpeg/ffprobe 8.1.2. Có
  PyTorch/OpenCV global nhưng metadata OpenCV khác bản import; tạo venv riêng
  `edge-agent/.venv` với package đã khóa, không sửa dependency/backend env.
- Trước chọn model đã đọc model card, adapter và LICENSE chính thức OpenCV
  Zoo (nguồn/revision/checksum trong THIRD-PARTY-NOTICES). Code và weights của
  YOLOX-s COCO 2022nov, LPD YuNet 2023mar, CRNN_EN 2021sep được nhà phát hành
  ghi Apache-2.0 cho mọi file trong thư mục. Giữ attribution/license bản gốc.
  Tổng weights tải 73.8 MB, không dataset/GPU/cloud. Pin revision/SHA và kiểm
  hash lúc fetch/inference; không tự tải mạng trong inference/test.
- LPD YuNet trained biển Trung Quốc, CRNN EN là text OCR chung, chưa fine-tune
  biển Việt Nam. Giấy phép phù hợp dùng thương mại theo Apache-2.0, chất lượng
  nhận dạng phải nghiệm thu độc lập; không suy ra từ confidence model khác.

### Thay đổi và giới hạn có chủ ý

- Package `edge-agent/offline_vision` tách video, config/ROI, detector xe,
  tracking/phiên, frame/crop, plate detector, OCR/consensus, export và đánh giá.
  CLI `scripts/offline-vision.py` có fetch-models, fixture, run, evaluate.
  Không import backend/ORM, tạo service hoặc ghi offline result vào database.
- Hai config camera mẫu/camera-185; polygon chuẩn hóa lồi. Camera-185 được
  phác từ video và ghi chờ người vận hành xác nhận. Dùng bottom-center bbox;
  không kết luận toàn bộ xe trên bàn cân hoặc người/cabin trống.
- Detect 2 Hz theo decoder media PTS, không chạy model mỗi frame. Tracker
  ghép một-một IoU/khoảng cách; track giữ 3s, phiên 5s dropout/3s ngoài ROI,
  có thể gắn track mới vào phiên còn đang chờ khi track cũ vắng. Không gắn
  track_id vào danh tính xe/D02. Gap dài vẫn có thể phân đoạn một xe; lý do
  detection_gap_expired/EOF được giữ để người xem không hiểu nhầm xe rời cân.
- Chỉ chạy plate/OCR trong ROI: tối đa 12 plate attempts cách 3s, 8 neural OCR
  calls (hai dòng tính 2 calls), 4 plate crop lưu/phiên. Overview/crop xe chọn
  bằng sharpness/kích thước và giữ ảnh hữu ích ngay khi không có plate. OCR
  dừng sau >=3 thời điểm nhất quán, ratio>=0.8; mọi đề xuất cần xác nhận.
- Giữ raw/raw_lines/normalized/candidates/strategy/model/score riêng. Không
  đổi O↔0/I↔1/B↔8 hoặc ép chuỗi theo luật biển. Không so/cộng confidence giữa
  xe, plate, OCR. Unknown là null + trạng thái, không tạo bản ghi xe unknown.
- Output JSON/CSV, timeline detection, overview/annotated/crop xe, plate crop
  khi thực sự tìm thấy, HTML review và template nhãn thủ công. Fixture ghi rõ
  banner SCRIPTED và fixture=true; không coi là kết quả model camera thật.
  Video/models/evidence/data được Git ignore, output mới không ghi đè folder
  có sẵn. Không thêm image thực/model vào Git.

### Kiểm thử và kết quả chạy

- **Đã chạy — thành công:** `edge-agent/.venv/bin/python -m pytest -q
  edge-agent/tests`: **31 passed, 1,28 giây** ở lượt cuối. Kiểm tra no vehicle, outside ROI không gọi plate/OCR,
  enter/exit, short dropout, track đổi không nhân phiên, hai xe độc lập, gap
  dài, không có plate giữ overview/crop, OCR mâu thuẫn, budget/interval/crop,
  hai dòng tính neural calls, nhiều crop một frame không nhân vote, chuẩn hóa
  không sửa ký tự, config invalid, từ chối ghi đè, media/VFR đối chiếu ffprobe,
  RGB official preprocessing, CTC và OCR CPU smoke trên crop tự vẽ. Test không
  seed DB/download mạng; model smoke dùng weights local đã fetch rõ ràng.
- **Đã chạy — thành công:** CLI fixture + run với case short-dropout, config
  mẫu: 20/100 frame, 1 track/1 phiên, 3 lần OCR scripted ở ba timestamp, đề
  xuất `51C12345` cần xác nhận, 0 unknown. Lưu
  `data/offline-vision/runs/fixture-short-dropout/`. Đây là bằng chứng cơ chế,
  không phải độ chính xác model; accuracy vẫn null vì không có nhãn thủ công.
- **Đã chạy — thành công:** CLI model thật trên toàn bộ video camera-185, output
  `data/offline-vision/runs/camera-185-d05a-final/`. 265 lượt detect/3300 frame,
  184 frame có box xe, 195 box cộng qua các frame, **6 track** (không phải 6 xe
  thực), **1 phiên xe ROI**. Phiên s00001: media 69.000–117.520s, đóng vì mất
  detection vượt grace; không chứng minh xe rời cân. Overview chọn 104.520s.
- Báo riêng: **tìm plate bằng detector: 0 phiên/0 box trên 12 lần thử; đề xuất
  OCR: 0; unknown: 1; đọc đúng toàn bộ: chưa đánh giá**. Không có nhãn thủ công
  nên accuracy/fully_correct_plates null. Biển có trong ảnh crop khi xem bằng
  mắt nhưng model không tìm được, không thay bằng biển do người/AI tự đoán,
  không lấy chữ container làm biển hoặc tạo crop plate giả.
- Đã đối chiếu timeline video thật với ffprobe best_effort_timestamp_time,
  sai lệch float tối đa 1.8e-15 giây. Không dùng frame/fps, tên file hoặc overlay
  để suy ra UTC. Chưa cung cấp video-start-utc; kết quả chỉ có media time.
- Đo local ở lượt cuối: **33.216s** gồm init/media/evidence, loop **33.088s**;
  CPU process **155.444s**, trung bình **467.98% một core ≈4.68 core** hoặc
  **46.80% dung lượng 10 core**; peak RSS **785629184 byte ≈749.23 MiB**.
  DNN đặt 2 thread, decoder có thread riêng. CPU/time không gồm import, hash/
  report cuối hoặc ffprobe child; RAM dùng OS process lifetime high-watermark
  (có imports) cộng sampling 100ms, không phải RAM Docker/toàn máy; là một
  lượt MacBook đang chạy Compose, không benchmark cloud/GPU/RTSP.
- Lượt thăm dò đầu đã bị loại khỏi nghiệm thu do review code chính thức phát
  hiện cần RGB (không phải BGR); đã sửa và bổ sung regression cho channel order.
  Run `camera-185-first` có NOT-ACCEPTANCE.txt; chỉ output `camera-185-d05a-final`
  dùng làm kết quả cuối. Không sửa original video để làm đẹp kết quả.

### Bàn giao và bước sau

- Hướng dẫn CLI/config/label/evaluation/giới hạn:
  `docs/offline-vision-d05a.md`, `edge-agent/README.md`; license và version:
  `edge-agent/THIRD-PARTY-NOTICES.md`. Kết quả xem bằng HTML local và link ảnh.
- D05a hoàn thành bước pipeline offline có kiểm tra. **D05 nhận dạng camera
  công ty chưa nghiệm thu**: cần người vận hành xác nhận ROI, nhãn readable/
  đầy đủ biển, detector biển Việt Nam 1–2 dòng phù hợp giấy phép và test ngày/
  đêm/mờ/che khuất. Chưa đo pipeline live hoặc tài nguyên cloud.
- Đề xuất bước riêng: reviewer đọc/import artifact, phân quyền cơ sở, giữ raw/
  proposal/confirmed tách nhau; tiếp đó adapter RTSP có clock, reconnect, buffer
  và backpressure có giới hạn. Chưa triển khai UI/RTSP, chưa ghép signal/xe,
  chưa tự sửa dữ liệu D02 hoặc infer nhập/xuất.
- Không có backend/frontend/migration thay đổi trong bước này nên không build
  lại web hoặc áp migration. Không đổi Compose, volume, token, network/Windows.

- **Đối chiếu bảo vệ — đạt:** trước/sau task dùng transaction PostgreSQL
  REPEATABLE READ READ ONLY trên engine API ứng dụng, schema head vẫn
  d31a9c72b045; fingerprint toàn bộ scale_signals (9 dòng), scale_agents
  (gồm token hash, không in giá trị) và các bảng D02 hoàn toàn không đổi.
  Ledger SHA-256 của 1.474 file backend/frontend/env trước/sau không thay đổi
  (gồm cả file môi trường local). Bằng chứng ở data/d05a-work, quyền 0600,
  Git ignored. Readiness API qua web hiện trả ok; không đổi token/volume.

- **Report HTML — đã kiểm tra:** Chromium qua static preview loopback tạm,
  ảnh đều tải được; JSON/CSV/template/ảnh gốc trả 200. Desktop 1440px và
  mobile 390px có document width bằng viewport; đã xem ảnh QA, có nhãn model
  thật/fixture rõ, unknown và end reason. Ảnh QA ở output/playwright/d05a được
  Git ignore vì chứa ảnh camera thật. Preview chỉ dùng cho QA artifact, không
  phải service triển khai; dọn browser/server sau kiểm tra.

## D05b — chẩn đoán và chuẩn bị dữ liệu (06/10/2026)

### Phạm vi và chẩn đoán đã xác minh

- Đã đọc requirements/architecture/tasks/progress, D05a guide/code/result và
  các lần thử threshold/CRNN, CCPD YOLOv8n/HyperLPR ở project khác. Mã D05b mới,
  không ghi đè task D06/D07 đã lên kế hoạch. D05 vẫn chưa nghiệm thu nhận dạng.
- Xác minh hai video local camera-185, HEVC 1920×1080, SHA giữ trong manifest;
  thời lượng 132,281s/300,681s và 3.300/7.493 frame decode. Không dùng ảnh chat
  làm input hoặc suy ra UTC từ tên/overlay; vẫn dùng media PTS.
- Crop 130×41 cũ cắt từ ảnh gốc, OCR nhận slice trực tiếp; JPEG evidence và
  preview 4× không đi vào OCR. CRNN ép gray xuống 100×32; plate detector ép
  crop xe vào 320×240. Hai resize có thể giảm tín hiệu/đổi hình dạng ở model,
  dù crop evidence vẫn nguyên pixel decode. Seek 104,760 trả PTS 104,720;
  diagnostic PNG/metadata ở `data/offline-vision/diagnostics/crop130x41`.
- Phân biệt lỗi detector: miss ở threshold 0,75, nhầm khóa/thanh container khi
  hạ threshold, bbox hẹp; lỗi OCR: chữ nhỏ, input ép tỷ lệ, auto midpoint không
  bảo đảm hai dòng, domain khác. Chưa có bbox/text GT nên chưa có metric để
  quy kết từng lỗi hoặc khẳng định cần fine-tune OCR.

### Công cụ và dữ liệu bàn giao

- CLI thêm prepare-labels, import-labels, audit-labels, fetch-benchmark-model,
  benchmark-ocr. `dataset.py` chọn theo strata thời gian/novelty/sharpness,
  xuất PNG native/crop/provenance và template trống; gợi ý detector tách khỏi
  annotation manual. Không chép OCR vào GT.
- **Đã chạy:** prepare-labels hai video, count 40/interval 3s: 20 frame mỗi
  video từ 45+101 candidate, toàn ảnh 1920×1080. Có xe gần/xa/trước/sau và ảnh
  ngoài vùng/trống; nhiều frame cùng xe, không phải 40 mẫu độc lập. Folder
  `data/offline-vision/datasets/d05b-camera185`, ~159,3 MiB lúc extraction.
  Manifest, CSV chờ điền, HTML gán nhãn, full PNG/vehicle crop và contact sheets.
- HTML hỗ trợ native pixel zoom, bbox biển/xe/hard-negative, text thủ công,
  readability/layout/split_y thật, group xe/capture/split, export JSON/CSV/load.
  Ảnh gốc/SHA/PTS là immutable khi CLI validate. Không tự lưu khi reload; hướng
  dẫn lưu JSON thường xuyên. Sửa lỗi mất textarea khi chuyển control được
  phát hiện trong QA; cập nhật nhãn ngay qua input event.
- Benchmark giữ baseline CRNN + **một recognizer** PaddlePaddle PP-OCRv6 tiny
  ONNX CPU, weights 4,46 MB. Revision/SHA/config/card/license Apache-2.0 đã
  đối chiếu nguồn chính thức trước tải; PaddleX adapter Apache-2.0, ORT 1.23.2/
  PyYAML 6.0.3 MIT. Dependency chỉ thêm venv offline và requirements-benchmark,
  không cài vào backend hoặc project LPR khác. Model/attribution trong notices.
- Ba biến thể cố định: original, cubic 2×/pad, CLAHE; manual actual layout/
  split_y, raw prediction và score riêng, whole-plate exact + strict raw.
  Không sửa ký tự hoặc chọn best variant từng ảnh để tăng accuracy.
- **Đã chạy:** benchmark template 40 ảnh, **0 reviewed / 0 readable**, output
  `data/offline-vision/benchmarks/d05b-pending-final`: bảng pending, metrics rỗng,
  accuracy null; không thực hiện inference khi chưa có bbox/layout nhãn. Không
  tự đoán biển dù một số frame nhìn khá rõ.
- **Đã chạy:** audit nhãn template, 0 exact PNG / 140 scene-dHash suspect do
  nền cố định/cùng xe, chưa chia tập, training_ready=false. Audit chặn cùng
  source clip/capture/vehicle xuyên split và exact/unreviewed suspect trùng;
  không tự xóa ảnh hoặc split random từng frame. Cờ dHash cần người xem lại,
  không phải kết luận 140 ảnh trùng.

### Chọn frame/OCR và lượt chạy thật

- v0.2.0 giữ PNG pool bounded theo tuổi phiên media 0–8/8–20/>=20s, quality
  ranking và giảm near duplicate/time. Detector giữ lượt tới giai đoạn muộn,
  tăng khoảng cách thử; OCR deferred sau đọc hết clip, neural call quotas
  25%/25%/phần còn lại rồi dùng quota thừa. Giữ raw/conflict/unknown, consensus
  >=3 thời điểm/ratio>=0,8, tối đa 8 calls và 4 plate evidence/phiên. Hai dòng
  tính 2 calls. Chính sách này chưa đưa vào live/RTSP.
- **Đã chạy toàn bộ video thật**, cấu hình diagnostic local threshold plate
  0,25, các giới hạn mặc định giữ nguyên; file camera config 0,75 không sửa:

| Output `data/offline-vision/runs/` | Detect xe / frame có xe / box / track | Plate calls / box ứng viên | OCR observation / neural calls | ROI / proposal / unknown |
| --- | --- | --- | --- | --- |
| camera-185-d05b-video1 | 265 / 184 / 195 / 6 | 9 / 9 | 3 / 6 | 1 / 0 / 1 |
| camera-185-d05b-video2 | 601 / 511 / 523 / 6 | 12 / 8 | 7 / 8 | 1 / 0 / 1 |

- Video 1 chọn OCR muộn ở media104,000s; budget không hết vào ~69–74s như thử
  trước. Video 2 OCR từ 140,000–186,520s, raw khác nhau nên unknown. Không gọi
  tổng box hoặc track là số xe thực; box plate là ứng viên, chưa được xác minh
  bằng GT. **Đọc đúng toàn biển/accuracy camera đều null**.
- Đo MacBook local: video1 wall32,677s/CPU149,038s/peakRSS678,70MiB;
  video2 wall87,493s/CPU349,422s/peakRSS698,58MiB. Process CPU/wall gồm init/
  media/evidence/decoder, không gồm import/final hashing/report/ffprobe child;
  RSS lifetime high-watermark + interval sampling, không phải RAM toàn máy.
  Có Compose/browser/công việc khác trên máy; không suy diễn server/GPU/cloud.

### Kiểm tra và giới hạn còn lại

- **Đã chạy đạt:** `edge-agent/.venv/bin/python -m pytest -q edge-agent/tests`:
  **50 passed, 1,50s** cuối. Bao phủ D05a control-flow/ROI/tracking/unknown,
  phase/budget/quality/near duplicates, manual layout, GT/provenance/PNG checksum,
  uncertain không vào denominator, exact toàn biển không đổi O/0, clip/xe/group
  leakage, BGR/aspect/padding/CTC, native PNG extraction và real local CPU smoke.
  Test chỉ fixture/local weights đã fetch; không dùng application/test DB.
- **Browser QA đạt:** Chromium desktop1440/mobile390, document width bằng
  viewport và canvas vẫn1920×1080. Vẽ bbox, thiếu text không được mark reviewed,
  nhập text/layout, export/import JSON+CSV, crop native. Flow benchmark đầy đủ
  hai model/ba biến thể chạy trên ảnh chữ **synthetic riêng**, không đưa vào
  số camera. Ảnh QA ở `output/playwright/d05b`, Git ignored; browser/static
  server loopback tạm đã dọn, không thay cổng dịch vụ đang chạy.
- Khảo sát **VNLP + đúng một nguồn Việt Nam khác** (winter2897): type/labels/
  size/license/source commit trong `docs/offline-vision-d05b.md`. VNLP listing
  zip3,45GB; nguồn bổ sung chưa xác minh size/count. Chưa có breakdown xe tải/
  container và quyền thương mại rõ. Chỉ đọc docs/HTML metadata, không tải
  dataset archive, không training/thuê GPU/cloud.
- Kế hoạch: manual bbox/text + hard negatives khóa/thanh/chữ container trước;
  đánh giá detector riêng và OCR trên crop thủ công; fine-tune detector trước
  khi bbox miss/hẹp còn là nút thắt. Chỉ fine-tune OCR nếu benchmark crop đúng
  cho thấy cần. Thu thêm xe/capture độc lập, split theo group trước augmentation,
  audit duplicates và giữ test riêng; hai clip hiện có không đủ nghiệm thu.
- **Bảo vệ phạm vi đạt:** ledger 2.745 file backend/frontend/src/env/video
  trước/sau **0 thay đổi/thiếu**. Không sửa/import backend, không query/seed/write
  database, không đổi migration/Compose/volume/token/Windows hoặc 9 event S03a,
  D02. Git diff/no-index whitespace đạt; nguyên repo chưa có commit nên dùng
  snapshot trước thay đổi để kiểm tra. Ảnh/models/data/QA được git check-ignore
  xác nhận. Không commit hoặc sửa file người dùng ngoài phạm vi D05b.

Hướng dẫn, phân tích và lệnh tiếp tục gán nhãn/benchmark/audit:
`docs/offline-vision-d05b.md`. **D05b chuẩn bị hoàn tất; benchmark camera chờ
nhãn thủ công. D05 tổng thể và D06/D07 chưa hoàn tất/triển khai.**

## D05c — Chuẩn bị lần fine-tune detector biển số đầu tiên (07/10/2026)

**Tooling và preflight fixture đã đạt; audit và package Roboflow thật cập nhật
ở phần nghiệm thu bổ sung 07/10/2026 bên dưới. Nhãn 40 frame camera và nghiệm
thu detector vẫn chờ.**
Đọc requirements/architecture/tasks/progress, AGENTS và kết quả D05a/b trước
khi chọn mã D05c chưa sử dụng; giữ nguyên nhiệm vụ D06/D07 và nhánh S.

### Nguồn và dữ liệu

- Roboflow project datacar / `bien-so-xe-3w699-avdfe`, v1
  `2025-01-06 5:34pm`, source/link/license/attribution trong
  `docs/plate-detector-d05c.md`. Project công bố CC BY4.0,606train/173valid/
  85test,1class `biensoxehoi`, không preprocessing/augmentation. **864 là
  published count; actual usable count chưa biết**, chưa download archive.
- Export COCO JSON trong phiên in-app yêu cầu “Login or create a free account”.
  Đã gửi người dùng bước Datasetv1 → DownloadDataset → COCOJSON → DownloadZIP
  bằng browser đã đăng nhập, lưu `data/offline-vision/incoming/` và cung cấp
  filename. macOS chặn đọc Downloads; không đổi quyền/bypass đăng nhập.
- Audit tool giữ ZIP/raw, kiểm tra decode/missing/orphan/dimensions/class/bbox,
  duplicate SHA/pixels và pHash+dHash near suspects giữa splits, contact sheets,
  bbox size percentiles, review CSV/layout/vehicle metadata; normalized oneclass
  COCO chỉ tạo sau review. Có test fixture, **chưa audit864 ảnh thật**.
- 40PNG D05b được giữ nguyên,0reviewed/0manual plate boxes; review HTML/CSV riêng
  reuse công cụ cũ. Tạo3crop khóa/thanh ở v001media120s và box vàng nét đứt,
  origin assistant_visual_proposal,ground_truth=false; cần người dùng xem/vẽ
  lại xác nhận. Không đưa proposal vào annotations hoặc train, không coi
  missed plate là negative. `plate_unlocatable` bị loại tới khi có bbox.
- Prepare khóa provenance/image hashes, group xe/capture/source, exact dup và
  unresolved cross-split near dup, giữ original external test khỏi train/val;
  xuất manifest/counts/ceil(Ntrain/2) và COCOtrain/val/test. Manifest hiện
  `data/offline-vision/training/d05c-pending-real`:0accepted,0batch,
  training_ready=false. Hai clips phải group riêng; externalval để lựa chọn,
  camera test cần độc lập theo xe/capture, không báo accuracy toàn hệ thống.

### Model, runtime và preflight thực tế

- YOLOX-Nano official code Apache2, revision
  `6ddff4824372906469a7fae2dc3206c7aa4bbaee`, COCO release0.1.1rc0,
  weight7.694.953bytes/SHA khóa; source/license lưu local, notices trong
  edge-agent. Release không công bố restriction weights riêng. Head80→1,
  636tensor nạp/6classification tensor khởi tạo lại,896.754parameters.
  YuNetONNX giữ baseline, không dùng làm model có thể training tiếp.
- `.venv-training` Python3.12.7/arm64, torch2.8.0/torchvision0.23.0,
  ONNX1.19/ORT1.23.2, fulldependency lock riêng. Không sửa `.venv` D05a/b hoặc
  API dependencies. BGR raw0–255/currentYOLOX letterbox640pad114 đúng release.
- Batch2,CPU2threads,seed20261007, không mosaic/mixup/flip/oversampling hoặc
  infinite sampler. Preflight<=2totalsteps/2epochs, checkpoint lưu optimizer,
  cursor/epoch/RNG, data/config/source hashes; resume chặn config/data khác và
  giữ cumulative cap. Pilot config<=20epochs/1000totalsteps có lệnh nhưng
  **chưa chạy trên dữ liệu thật hoặc training dài**.
- **Đã chạy YOLOX thật trên fixture riêng4ảnh/3boxes**: 2batches/epoch.
  v2step1 wall1,421s/CPU2,371s/RSS observed956MiB; v2resume1step wall1,395s/
  CPU2,340s/RSS970MiB, cumulative2steps. Không lặp hai batch đã dùng.
  Loss hữu hạn; forward/backward, save/load mọi tensor bằng nhau đều đạt.
- Lần đầuLR1e-3 export decoded parity không đạt; giữ artifacts thất bại,
  v2LR1e-6 chạy lại trên fixture. Hai thử nghiệm ×2YOLOXoptimizersteps; không
  lấy loss/batch synthetic để chứng minh convergence hoặc accuracy.
- **ONNX export/checker/CPU parity đạt**: fixed640/opset11, decode trong graph,
  output[1,8400,6], maxcoordinate error0,026093pixel/probability0,00006551.
  Bounds absoluteFP32 tách0,05pixel và0,0001probability, rtol0. Không liên quan
  hợp đồng timestamp S01. Export metadata quality_accepted=false/synthetic.
  Detector adapter smoke37,23ms/0box trênfixture; không đo recognition accuracy.
- InterfaceDetector được giữ; optionalCLI`--plate-model-manifest` cùng threshold riêng có thể dùng
  model thật export sau này, từ chối synthetic trên video camera. Default
  YuNet unchanged. `compare` chấm manual recallIoU0,5/FPcontainer/cropcoverage/
  latency cùng ảnh, planhash và valselection/testfreeze; chưa có metrics thật.

### Kiểm tra và giới hạn

- **72tests đạt**, D05a/b50 +D05c22case, cuối3,17s (1warning do fixture ZIP cố ý trùng tên).
  Bao phủ malformed/missing labels, classmap/bbox/contact sheets, duplicates,
  group/testseal, explicit negatives, BGR/nativepreprocess, finitebatch/resume/
  cap/hash mismatch và scoring missedplate/containerFP; tinyfixture unitstate
  riêng, realYOLOX preflight riêng. Không test/seed application database.
- Browser QA review40 frame/frame120s native1920×1080,0reviewed,3vùng vàng,
  không consoleerror; ảnh `data/d05c-work/review-ui.jpg`. Staticserverloopback
  tạm, không đổi cổng ứng dụng. Original40PNG hashes đều khớp.
- OCR benchmark D05c trên template:0reviewed/readable, awaiting_manual,
  metrics[]/accuracy null, không inference hoặc tự đoán transcript. Có GT thì
  chạy lại CRNN/Paddle3variants/layoutmanual theo D05b; detector fine-tune
  trước, OCR chỉ khi crop chuẩn cho thấy cần.
- Protected before/after1937files backend/frontend/src/env/videos:
  **0changed/0missing**. Không importbackend/query/writeDB, không đổi migration,
  Compose, volume, token,9eventsS03a hoặcD02. Database không được đối chiếu lại
  trong D05c; ledger là bằng chứng file, không thay thế SQL snapshot.
- Ảnh/ZIP/data/weights/trainingvenv gitignored. Repository chưa có commit;
  kiểm tra snapshot/no-index diff và gitstatus, không ghi đè file người dùng.

Hướng dẫn/artifacts/config/commands và kế hoạch so baseline/fine-tuned:
`docs/plate-detector-d05c.md`. (Trạng thái đã cập nhật trong mục nghiệm thu bổ
sung 07/10/2026.)

### D05c cập nhật: audit export COCO và đóng gói (07/10/2026)

- Nhận export COCO đã giải nén tại
  `data/offline-vision/incoming/bien so xe.v1i.coco`; không có ZIP trong
  incoming. Giữ nguyên thư mục nguồn, tạo audit/processed/package riêng.
- Audit 864/864 ảnh decode được; categories `cars` (0 annotation),
  `biensoxehoi` (793 bbox hợp lệ, mỗi ảnh tối đa một bbox). 71 ảnh rỗng chưa rõ
  có biển không; giữ để người dùng xác nhận, không tạo negative. 32 ảnh có bbox
  bị giữ review-priority theo heuristic; không tự sửa/xóa. Không có exact hoặc
  near duplicate theo hash ngưỡng đã dùng; không tìm thấy leakage cặp cross-split.
- Subset package gồm 761 ảnh dương: train539/val147/test75; không có negative.
  Giữ publisher split và test sealed. Nguồn không có vehicle/capture IDs, do đó
  chưa thể khẳng định chia chống leakage đầy đủ theo xe/lượt quay. Không đưa 40
  frame camera hoặc 3 hard-negative proposal chưa xác nhận vào train.
- Package:
  `data/offline-vision/training-packages/d05c-first-train.zip`, SHA-256
  `921f9df5d5079c6f8464430768fcbae9e3c48285fc4fdd5e9119d02f2daf7b5d`, khoảng
  62 MB. Có portable dataset/manifest/hashes, code tối thiểu, YOLOX-Nano pinned
  source/weights, configs, lock, README, CC BY attribution, review bundle 103
  ảnh và manifest 40 frame camera cần gán. Không có secret hoặc dữ liệu ứng dụng.
- Batch2,270 batch/epoch, `drop_last=false`, last batch1. Không oversampling,
  augmentation hoặc infinite sampler. Pilot tối đa20 epochs/1000 optimizer step.
  Preflight real CPU sau giải nén: forward/backward2 bước, finite loss,
  checkpoint/save-load/resume đạt, 636 tensor pretrained nạp và 6 tensor class
  head COCO skip. Vẽ batch thật. Probe optimizer stub đi hết 270 batch/539 ảnh
  và kết thúc epoch cursor0; đây chỉ là xác minh vòng lặp hữu hạn.
- `pytest edge-agent/tests/test_plate_training.py -q`: **22 passed**, 1 cảnh báo
  fixture ZIP tạo tên lặp. CLI evaluate từ package giải nén có trong gói. CUDA
  preflight chờ GPU thuê; không có training dài/quality metrics.
- D05c hoàn tất chuẩn bị package cho subset Roboflow có điều kiện, chưa hoàn tất
  xác nhận nhãn đáng ngờ hoặc camera và chưa nghiệm thu detector. D05 tổng thể
  tiếp tục; không đổi DB/D02/S03, không chạy OCR do chưa có manual transcript.

## D05d — fine-tune detector đầu tiên trên GPU Vast (07/10/2026)

- Kết nối đúng instance Vast `54567374` bằng SSH key local đã tồn tại; xác minh
  RTX 3090 Ti 24 GB, driver550.163.01, compute8.6, CUDA tensor operation, disk
  trống42GB. Không nâng/cài driver. Workspace GPU là ephemeral. Tạo venv riêng:
  Python3.12.3, torch2.8.0+cu126, torchvision0.23.0+cu126, OpenCV4.12.0,
  ONNX1.19.0, ORT1.23.2. Package SHA trùng yêu cầu;
  dataset539/147/75, một class `license_plate`; pretrained hash khớp.
  Nạp636 tensors; sáu class-prediction tensors COCO được skip do shape và head
  một class được khởi tạo lại.
- CUDA preflight trên batch thật đạt: forward/backward loss hữu hạn, validation
  đầy đủ147 ảnh, checkpoint roundtrip, optimizer/scheduler resume và sampler
  hữu hạn; hai bước qua hai process khác nhau. Batch2/drop_last=false, 270 batch
  mỗi epoch, batch cuối1. Peak allocated CUDA519MB. FutureWarning API AMP của
  YOLOX upstream không ảnh hưởng kết quả.
- Pilot cấu hình seed20261007, input640, batch2, LR1e-5, SGD/cosine, không
  augmentation, max20 epochs/1000 optimizer steps/7200 giây; wrapper tmux giới
  hạn3 attempts và resume từ last. Hoàn thành đúng1000 bước trong65,17s: epoch1–3
  đủ270 batch, thêm190 batch ở epoch4; hết step cap bình thường, không tự dừng
  vì metric. Checkpoint best ở epoch3/step810; last ở step1000. Tổng optimizer
  batch time epoch1 21,28s (bước đầu4,02s warm-up); batch trung bình toàn lượt
  0,0578s. Phần epoch4 không được dùng để chọn model.
- Validation ở confidence0,25/NMS0,45/matchIoU0,5 chọn epoch3: 145/147
  annotations match (98,64%), unmatched prediction0,0204/ảnh, meanIoU0,8567.
  Sau khi khóa checkpoint, test chạy một lần: 75/75 match (100%), unmatched
  prediction0,0133/ảnh, meanIoU0,8461. Đây chỉ là annotation-relative trên
  Roboflow publisher labels chưa xác minh, positive-only; unmatched không được
  xác nhận là FP. Không khẳng định generalization hoặc chống leakage theo xe.
- Export YOLOX-Nano ONNX640/opset11, checker và CPU parity đạt: sai số tọa độ
  max0,04895px, xác suất max0,00005765, trong bounds0,05px/0,0001. Model vẫn
  `quality_accepted=false`. ONNX SHA-256
  `03fe0db1f9a77108d166a246770efff2dca0dfb4af3c2102bfe9057a012d932b`; best
  checkpoint SHA `a5fce8d542a0c438f6b162801f0b043a82246a89b20e2935b3ac5a8fd9d019d7`.
- Chạy cùng pipeline D05a trên cả hai clip với YuNet baseline và ONNX mới. Clip
  073000–073500 (601 frame mẫu): baseline0 plate boxes; YOLOX16 box/12 lần gọi,
  8 OCR reads. Clip 103800–104015 (265 frame mẫu): baseline0 boxes; YOLOX6
  box/9 lần gọi, 5 OCR reads. Cả hai vẫn `unknown`; xem crop cho thấy có crop
  không phải plate, OCR chưa đọc ổn định. Wall YOLOX72,18s và33,06s, peak
  process RSS xấp xỉ826MiB/840MiB; đây là lượt offline CPU Mac, không suy rộng
  sang server. Không có nhãn camera, không tính recall/precision/accuracy.
- Đã tải checkpoint best/last, ONNX, metadata, configs, log, metrics, preflight
  và bốn bộ review video về `data/offline-vision/runs/d05d-vast-54567374/`;
  kiểm tra SHA remote/local khớp19/19 artifacts. Dữ liệu/media artifacts được
  giữ local và Git-ignore. Instance vẫn bật nhưng tiến trình train đã xong, GPU
  idle; có thể stop để chấm dứt tính phí, không destroy instance.
- D05d hoàn thành cho bounded first-run/training/export/artifact handoff; D05
  tổng thể vẫn đang thực hiện. Bước tiếp theo cần người kiểm tra các crop, gán
  nhãn camera positives và hard negatives container-lock, chia theo xe/lượt
  quay, rồi đánh giá trên capture độc lập. Không đổi DB, D02, S03 hay D05a.
  Báo cáo chi tiết: `docs/plate-detector-d05d.md`.

## D05e — review crop detector và chuẩn bị OCR benchmark (07/10/2026)

- Dựng local review UI từ **đủ22 detector observations** trong hai run D05d:
  6 crop `103800–104015`, 16 crop `073000–073500`. D05d gốc chỉ có 8 JPEG
  evidence do giới hạn 4 crop/phiên; D05e tái-tạo từng crop PNG lossless từ
  media frame trùng timestamp và bbox ghi trong result, kiểm tra native width/
  height khớp observation. Trang có context+bbox, native crop, zoom4×, score,
  video/time, pending/sai vùng/cắt thiếu/đúng biển, text/layout/readability do
  người xem nhập; không hiển thị OCR. JSON/CSV tải riêng và browser localStorage.
- Dùng labeler D05b hiện có trên working copy, không ghi đè bộ cũ: 40 frame gốc
  cộng21 frame đúng timestamp plate calls D05d (tổng61). Trên40 frame gốc, model
  tạo18 proposal ở13 frame; 27 không có proposal, 33 có vehicle suggestion.
  Trên21 attempt frame D05d, có22 proposal ở18 frame và3 lần gọi không có box.
  Gộp hai nguồn:40 proposal trên31/61 frame, 30 frame không có proposal.
  Đây chưa phải số miss/FP; cần người đánh dấu biển thật và review đủ frame.
  Bảy frame gốc không có vehicle suggestion cũng cần rà detector xe bỏ sót.
- Mở rộng benchmark D05b để ghép manual bbox và detector proposal một-một theo
  IoU>=0,5; OCR cả crop manual và detector tương ứng khi match; detector miss/
  unmatched boxes báo riêng. Giữ CRNN/Paddle raw, fixed variants, model-specific
  resize/normalization/layout; accuracy chỉ trên readable manual transcript,
  không sửa ký tự. Tạo output pending CSV/JSON để bàn giao, không chạy OCR.
- Nhận `labels.manual (1).json` ngày 07/10/2026. File cùng dataset ID; có
  **60/61 frame reviewed**, 58 bbox xe, 48 bbox biển. Frame `v002-f001259`
  tại media 51s chưa reviewed và bị loại. Trong 60 frame hợp lệ có 47 biển:
  15 readable có transcript, 5 uncertain, 23 unreadable, 5 pending. Chỉ ba
  chuỗi transcript khác nhau, lặp ở các frame gần nhau.
- Trình duyệt làm tròn `scene_hash` 64-bit trong JSON; bản gốc giữ nguyên.
  Bản import đã phục hồi hash từ manifest sau khi xác nhận provenance khác
  không đổi. Bốn bbox unreadable bị chọn two-line nhưng thiếu `split_y` được
  giữ cho detection và bỏ khỏi OCR (không tự đoán đường tách).
- Đánh giá detector một-một IoU≥0,5 trên 60 frame: **24/47 match**, 23 miss,
  16/40 proposal unmatched; trong 13 frame reviewed không có biển có 5 proposal
  unmatched. Riêng 21 frame D05d attempt: 17/21 match, 4 miss, 5/22 proposal
  unmatched (v001 5/9, v002 12/12). IoU≥0,75 chỉ 14/47 match.
- OCR trên 37 crop manual và 23 crop detector. CRNN baseline đạt 0/15 manual,
  0/14 detector trên cả ba biến thể. PP-OCRv6 tiny đạt 4/15 manual ở cả ba;
  detector crop đạt 5/14 gốc, 6/14 cubic2× + padding, 3/14 CLAHE xám. Chấm
  exact cả biển sau chuẩn hóa trình bày, không sửa ký tự.
- Kết quả chỉ chẩn đoán hai video và ba chuỗi biển lặp, không đại diện độc lập
  cho từng xe/camera. Chưa có JSON review crop `d05e-crop-labels.manual.json`,
  nên 22 crop chưa được phân loại đúng biển/sai vùng/cắt thiếu đầy đủ; D05e còn
  mở. Báo cáo, predictions, crops và detection matches nằm trong
  `data/offline-vision/runs/d05e-review-20261007/ocr-benchmark-v2/`.
- Trang local chỉ bind `127.0.0.1:8765` trong phiên này. Thư mục output
  gitignored: `data/offline-vision/runs/d05e-review-20261007/`. Chi tiết và
  lệnh benchmark sau khi có nhãn: `docs/offline-vision-d05e.md`.
- Không training/GPU, không thay database, D02 hoặc S03.

## D05f — camera adaptation, train thứ hai (07/10/2026)

- Người dùng xác nhận 60 frame đã xem có đủ mọi bbox biển và biển v002 là
  `49C02655`; các timestamp được hỏi là cùng xe. Giữ JSON Downloads nguyên
  vẹn, sửa 7 transcript trong `labels.confirmed.json` có provenance riêng.
  `scene_hash` uint64 dùng chuỗi; export/import Node kiểm tra giá trị nguyên
  vẹn và từ chối hash làm tròn. Vẫn pending frame `v002-f001259` (51 s) và
  22 crop D05e, không dùng chúng làm mẫu âm/hard negatives.
- Public train/val/test giữ nguyên 539/147/75. Camera v002 train, v001 test
  độc lập với lần train này; gộp theo capture để giữ các xe không rõ danh
  tính cùng split. Loại bảo thủ 10 parent train frame cùng mọi biến thể nghi
  hash gần trùng qua split; file nguồn giữ nguyên. Public thiếu ID xe, hai
  capture và test v001 đã được xem trong D05e hạn chế kết luận leakage/generalization.
- Dataset lưu train581 ảnh/575 bbox/6 âm, val147/147/0, test104/97/7. Camera
  train42 biến thể từ21 frame, camera test29 frame/22 biển. Mỗi epoch public
  một lần, camera chọn1 biến thể/parent, 560 lượt/280 batch, batch 2,
  drop_last=false, camera3,75% dưới cap 20%. Không flip/mosaic/mixup; light
  photometric augmentation giữ bbox. Contact sheets/manifest ở
  `data/offline-vision/training/d05f-ready-20261007/`.
- Sử dụng SSH được người dùng cấp đến instance54567374, RTX 3090 Ti, venv
  D05d riêng PyTorch 2.8.0+cu126. ZIP upload/hash/extract939 file đạt. Init
  D05d best642 key strict, bỏ0; optimizer/scheduler mới. CPU camera smoke và
  CUDA camera/mixed smoke, forward/backward/loss hữu hạn/validation/resume đạt.
- Train tmux có giới hạn6 epoch/1.000 step/7.200 s/3attempt; thực tế1attempt,
  dừng đúng1.000 step sau61,61 s, 3 epoch đầy đủ +160 batch epoch4. Trung bình
  .05246 s/batch, peak allocated CUDA~495 MiB. Log sampler21 camera/epoch đầy
  đủ, phần epoch4 có15 camera; không có vòng lặp vô hạn.
- Public validation match145/147,145/147,146/147; best epoch3/step840,
  laststep 1.000. Frozen checkpoint/threshold trước test. Public test75/75
  bbox match,1unmatched theo nhãn nguồn chưa được rà thủ công, không gọi FP.
- Export default không đạt bound số học; giữ BatchNorm và tắt ORT fusion
  bằng metadata. Single-input raw parity đạt .05 pixel/1e-4; raw mở rộng7/8
  đạt tọa độ, một background anchor lệch.056152 pixel (báo riêng, không nới
  dung sai). Probability8/8 đạt. Qualified anchors8/8 và detection thực tế
  sau confidence/NMS/clip trên104/104 test đạt; maxnative.001617 pixel,
  score.000002265. Chưa nghiệm thu parity toàn tensor raw mở rộng.
- Cùng 29 frame camera v001/22 biển: full frame640 cả D05d/D05f match0,
  FP1. Cùng crop xe thủ công: D05d match7/miss15/FP4; D05f match10/miss12/FP5.
  Mean GT coverage84,54%→82,82%, crop phủ≥95% GT1/7→0/10; không kết luận
  bbox đã tốt hơn. Group capture được báo riêng; crop xe là oracle geometry,
  không đại diện detector xe tự động hoặc accuracy xưởng.
- PP-OCRv6 tiny cùng weights/preprocessing:0/2 manual và0/2detector đọc
  chắc ở nhóm giữ lại, cả ba biến thể/cả hai detector. Sửa split hai dòng
  detector dùng native split_y, không nội suy theo bbox. Thử Englishv5
  mobile weights chính thức/hash/license:manual upscale1/2; detector
  D05d0/2→D05f1/2. Không fine-tune OCR hoặc sửa ký tự cho khớp nhãn.
- Chẩn đoán trên15 transcript đã sửa: PPv6tiny tốt nhất8/15manual,8/14
  detector; Englishv5 12/15manual,13/14detector; CRNN0. Chỉ hai biển lặp,
  không dùng những số này chọn checkpoint hoặc báo độ chính xác độc lập.
  Kết quả D05e trước sửa nhãn được giữ và chú thích là lịch sử.
- Pipeline hiện có chạy cả hai video: v0019plate calls/7box,33,96 s/~725 MiB
  RSS; v00212calls/15box,74,78 s/~796 MiB. ROI/budget/OCR CRNN cũ giữ nguyên,
  cả hai phiên unknown. Video2 có dữ liệu train; số box không phải accuracy.
- Model/checkpoints/ONNX/config/log/metrics/bằng chứng đã tải về; 22 file kết
  quả và 12 file preflight remote hash khớp, tổng 34, thiếu 0/sai 0. GPU đã
  kiểm tra rảnh, không còn job train. Best SHA f0b6c1ef…469d368d;
  ONNX5233aa1b…6388794c.
  Root `data/offline-vision/runs/d05f-vast-54567374/`; review local8766, crop
  pending vẫn8765. Gói train gốc giữ nguyên; v2 chứa sửa export, cùng hash
  dataset/config,939 file. README có preflight/train/resume/export.
- `edge-agent/.venv-training/bin/python -m pytest edge-agent/tests -q`:
  **89 passed**, một warning ZIP fixture trùng tên có chủ đích. Tài liệu/
  kết quả/giới hạn và lệnh: `docs/plate-detector-d05f.md`. Git hiện toàn repo
  untracked, `git diff` không có baseline tracked; không commit dữ liệu/model.
- D05f đã chạy bounded pilot; chưa nghiệm thu chất lượng camera/OCR hoặc
  full raw ONNX parity mở rộng. Baseline giữ nguyên. Có thể dừng instance sau
  đối chiếu artifacts; không tự stop/destroy, không thuê instance mới.
  Không thay database, token, volume, 9 event S03a, Windows hoặc D02.

## 07/10/2026 — Điều chỉnh ưu tiên sau pilot D05f

- Theo phản hồi người dùng, ưu tiên **S03b → D06 → D07** để nối nguồn cân
  thật và camera vào luồng có người xác nhận. Khảo sát nguồn ảnh, thu video
  nhiều lượt và hoàn tất 1 frame/22 crop pending có thể làm song song.
  D05f giữ kết quả pilot; chưa lên lịch train tiếp.
- Đọc lại requirements/tasks và báo cáo D05f; kiểm tra
  `data/offline-vision/training/d05f-review-20261007/plate-resize.csv`:
  47 bbox biển native cao 9–29 px, median 18 px. Kết quả match 10/22 chỉ
  thuộc một capture với bbox xe thủ công, không chứng minh kết quả vận hành.
- Kế hoạch mới ưu tiên khảo sát camera/luồng/vị trí chụp trước, rồi đánh giá
  theo lượt trên crop xe tự động hoặc ROI ở độ phân giải gốc. Khoảng 50–100
  lượt là mục tiêu thu thập đề xuất, không là ngưỡng nghiệm thu. Báo số xe,
  lượt/capture và điều kiện ngày đêm; giữ lỗi track/crop/OCR trong mẫu số.
- Kiểm tra `edge-agent/offline_vision/consensus.py`: consensus hiện gộp các
  lần đọc trùng toàn chuỗi ở timestamp khác nhau, chưa bỏ phiếu ký tự.
  Tái sử dụng cơ chế này; vote ký tự nếu thử phải đánh giá trên validation
  trước, giữ raw/bất đồng và không ép khớp biển kỳ vọng.
- Bổ sung task đề xuất D05g (đánh giá theo lượt) và D05h (gợi ý top-k có
  người xác nhận), không ghi đè D06/D07. Danh sách xe/lịch phải là snapshot
  có sẵn lúc xe đến; đo coverage, top-3, độ đúng sau chấp nhận và thời gian
  thao tác, có nhập tay/unknown. Chưa triển khai UI/API hoặc chọn ngưỡng.
- Chi tiết: `docs/camera-vehicle-evaluation-plan.md`; cập nhật định hướng
  trong requirements, tasks và báo cáo D05f. Chỉ sửa tài liệu trong bước này;
  không chạy test hoặc train, không mua/cấu hình camera, không Stop/destroy
  instance và không thay database, D02, S03, token hay dữ liệu gốc.

## 07/10/2026 — D05i Phase 1: bộ crop chẩn đoán chờ nhãn khả năng đọc

- Đọc yêu cầu D05i, AGENTS/tasks, báo cáo D05f, kế hoạch camera và code OCR/
  benchmark/consensus. Giao task D05i riêng, giữ D05g/D05h và ưu tiên luồng lõi.
- Tái dùng crop-review D05e, thêm mode D05i và CLI prepare/import. Gom 47
  crop bbox manual đã xác nhận và 41 crop detector khớp GT, tổng 88 crop
  từ 47 frame/hai capture. Hai chuỗi transcript xác nhận, 32 bbox chưa có
  nội dung đọc chắc; không đoán số xe/biển cho phần chưa biết.
- Mọi crop mới pending; không kế thừa readability/text từ frame hoặc OCR.
  Cho đánh dấu full/partial/unreadable, dòng đọc chắc, ghi chữ riêng và split
  tùy chọn. PNG native/nearest-neighbor 8×, localStorage nháp, JSON/CSV và
  import bất biến nguồn/bbox/hash; scene_hash uint64 vẫn là chuỗi. Nhãn cũ
  giữ nguyên, ảnh/nhãn mới nằm dưới data gitignore.
- Một frame thiếu xác nhận và 22 crop detector D05e pending được ghi riêng,
  không tính là crop đã xác nhận/âm. Crop trùng geometry gộp reference,
  không coi các crop/frame tương quan là lượt xe độc lập.
- CLI prepare và server loopback 8767 đã chạy; 8765/8766 giữ nguyên. Mở
  `http://127.0.0.1:8767/review.html`, xác nhận 88 pending, 12 mục/trang và
  zoom native đúng 8×; giữ trang để người dùng review.
- Toàn bộ test edge-agent **99 passed, 0 failed**, 1 warning ZIP fixture có
  chủ đích, 3,80 s. Kiểm tra pixel/hash/HTTP ghi `verification.json` trong
  `data/offline-vision/runs/d05i-readability-20261007/`.
  Pixel native và nearest8 đều 88/88 đạt, hash nguồn nguyên vẹn; 268/268
  asset HTTP đạt, không lỗi. Tất cả readability vẫn pending.
- `git status` còn toàn repo untracked; `git diff --check` không báo lỗi,
  không có baseline tracked. Tài liệu/lệnh/giới hạn: `offline-vision-d05i.md`.
- **Dừng đúng Phase 1, chờ d05i-readability.manual.json từ người dùng.**
  Chưa chạy Phase 2–4, tải model/VLM, dùng API ngoài, GPU hoặc training;
  không sửa database, D02, S03, signal, token, volume hoặc dữ liệu nguồn.

## 07/10/2026 — D05i Phase 2: nhãn readability và benchmark CPU

- Import CSV Downloads nguyên vẹn: 88/88 ID/source/media time khớp template,
  26 full, 7 partial bottom, 55 unreadable. CSV thiếu fingerprint/hash/review
  time: gắn metadata từ template, ghi giới hạn và 32 line-flag conversions
  từ trạng thái/layout/transcript người dùng; không sửa ký tự. Một partial
  có full_text được giữ nhưng không dùng chấm toàn biển.
- Khóa plan trước inference: split/whole × original/upscale2, 3 recognizer,
  33 readable crop, 396 case × 3 lần đo, CPU process riêng/2 threads. Model
  licenses/revisions/config/weights hash đã kiểm tra, attribution trong
  THIRD-PARTY-NOTICES. VLM không được duyệt, không tải/chạy.
- Native toàn biển English mobile 22/26 (CER 4/208), Paddle server 24/26
  (2/208), FastPlate CCT-S v2 26/26 (0/208). Tất cả 26 thuộc một biển một
  dòng/13 frame, không phải accuracy xưởng. Bottom split native 7/7, 7/7,
  5/7; top thiếu GT. Whole hai dòng không có row boundary, không chấm suffix.
- Upscale2: full 22/26, 23/26, 26/26; bottom split 4/7, 7/7, 5/7. Không chọn
  prediction/variant thắng bằng nhãn/test. Giữ primary policy cố định trước
  kết quả; không thay recognizer runtime. Đề xuất FastPlate nguyên biển và
  English mobile theo dòng để chẩn đoán tiếp; server tham chiếu offline.
- CPU/crop primary: 29,09 / 148,34 / 32,16 ms; wall 14,62 / 73,75 / 16,04
  ms; peak process RAM 107,22 / 430,95 / 106,89 MiB. Báo preprocessing/input
  shape và scope đo; không nhầm process peak với peak RAM mỗi crop.
- CLI scripts/d05i-ocr-benchmark.py, bảng ảnh/GT/raw/predictions.csv và plan/
  summary/verification ở data/offline-vision/runs/d05i-phase2-20261007.
  Trang loopback 8768 phục vụ parent runs để ảnh relative hoạt động; giữ
  8765/8766/8767. Hướng dẫn/12 biến thể ở docs/offline-vision-d05i.md.
- Full edge-agent: **107 passed, 0 failed**, 1 warning duplicate ZIP fixture
  có chủ đích, 3,93 s (lần chạy lại cuối). Hash CSV/template/upstream/native/plan/code/models
  khớp, đủ 396 case, repetitions giống nhau. Git toàn untracked, diff check
  không báo lỗi, không có tracked baseline. Không commit dữ liệu/models.
- Dừng Phase 2 theo yêu cầu; Phase 3/4 chưa làm. Không GPU/training/API ảnh
  ngoài, không đổi database, D02/S03, token, volume, signal hoặc Windows.

## 07/10/2026 — D05i Phase 3 và chuẩn bị D05j theo chỉ đạo tiếp

- Phase 2 giữ mọi hash/file; thêm observation riêng từ transcript D05f:
  FastPlate whole/original đúng 29K52755 ở 5/7 partial, chỉ hai thời điểm.
  Không đổi readability hoặc gộp vào metric full Phase 2.
- Phase 3 chọn FastPlate chính, English đối chứng theo chỉ đạo. Parser tập
  con theo TT79 Điều37/Phụ lục04 có nguồn, không xác minh mã tỉnh pháp lý;
  slot beam FastPlate không gọi CTC; English CTC prefix beam/blank/repeat.
  Giữ raw, candidate định dạng, gate loss/margin đã khóa trước inference.
- Alignment vote ký tự cần ≥3 timestamp riêng/track, support≥2/ratio≥2/3,
  giữ histogram/insertion/deletion/empty/conflict; không gộp crop cùng frame
  hoặc khác track, không đưa GT vào ranking/vote. Consensus toàn chuỗi giữ.
- Full FastPlate 26/26→26/26; English 22/26→24/26 và 2 unknown, CER all
  4/208→16/208 vì unknown tính rỗng (accepted CER 0/192), không cherry-pick.
  Track v002 13 frame/nguồn đều 49C02655 trước/sau; v001 chỉ 2 frame vẫn
  unknown. 8 model/source/track row không phải 8 xe, temporal association
  từ frozen session chưa độc lập chứng minh bbox/tracking, không accuracy.
- Phase3 v2 chạy CPU 6,05s, đủ 66 predictions/NPZ, raw khớp Phase2; root
  data/offline-vision/runs/d05i-phase3-20261007-v2. Bản đầu giữ riêng, v2
  bổ sung reject unknown track identity. Không sửa baseline/Phase2/runtime.
- D05j mã mới chưa dùng: kiểm kê ảnh người dùng đã đưa vào incoming,
  944 CarTGMT +1.748 GreenParking đọc được, không ảnh lỗi. 82 cặp trùng
  file/pixel, 1.266 cặp dHash≤4 (triage, chưa kết luận cùng xe); không phát
  hiện cross-source theo phép kiểm này, chưa chứng minh hết leakage.
- Chọn64 ảnh/64 duplicate components, 32/source, stratify brightness và
  dHash novelty, không OCR chọn ảnh. Native PNG/hash/scene_hash string,
  ảnh tĩnh timestamp/frame_index null. Tái dùng labeler D05b, sửa adapter
  caption/dropdown null timestamp; xác nhận browser render 1/64, 0 reviewed.
  Hai thư mục 61.775/71.275 ký tự rời không dùng đánh giá toàn biển.
- Người dùng cung cấp nguồn thigiacmaytinh.com/tai-nguyen-xu-ly-anh/tong-hop-data-xu-ly-anh/
  và cho phép dùng local. Nguồn mô tả mẫu để thử chương trình; ghi attribution
  và phạm vi thay vì suy ra quyền phân phối lại/train thương mại rõ ràng.
  Source report/filename/location chỉ reference chưa xác nhận, không GT.
- D05j chờ bbox/transcript/condition/vehicle/capture labels; split unassigned,
  chưa benchmark có nhãn hoặc fine-tune. Cần thêm camera xưởng nhiều biển/
  vàng/container che; kiểm tra trùng/cùng xe trước chia val/test. Tài liệu
  offline-vision-d05j.md và review loopback8768, giữ tất cả cổng đang chạy.
- Toàn edge-agent **132 passed,0 failed**, 1 warning ZIP fixture chủ đích,
  3,52s; includes exhaustive CTC path oracle test (fixture, không camera GT),
  parser/vote/unknown and D05j native/null-UI. Phase2 hashes bất biến, D05j
  2.692 original hash/64 native pixels và HTTP64 ảnh đạt. Git toàn untracked,
  diff check không lỗi nhưng không có tracked baseline. Không commit data.
- Dừng Phase3, D05j chuẩn bị chờ nhãn; Phase4/fine-tune chưa làm. Không GPU,
  DB/D02/S03, token, volume, 9 event, Windows hoặc API camera ngoài.

## 07/10/2026 — D05j điều chỉnh review và Phase D augmentation

- Giữ CSV gốc/hash, import riêng: 64 frame /53 đã xem, 49 bbox readable
  (29 CarTGMT /20 motorcycle). Hai bbox readable trên frame chưa xác nhận
  giữ pending trong eligibility. CSV thiếu completeness, màu và mức che.
- CarTGMT: 476 dòng có chuỗi, 18 ảnh thiếu, 458 ảnh đọc được, gộp 39 bản
  trùng pixel nhưng giữ references →419 ảnh. 14 frame cũ chuyển bằng SHA,
  12 có transcript readable; 32 frame CarTGMT cũ vẫn review riêng. Không
  cộng mẫu số giữa hai trang có ảnh trùng; GreenParking motorcycle riêng.
- Tái dùng editor D05b và detector D05f: gợi ý nguồn tách GT, bbox proposal,
  native crop preview, 20 ảnh/trang, phím tắt, autosave, JSON/uint64 và
  validation inventory. visible_text?, màu/mức che ghi theo từng bbox;
  mọi mục chưa xác nhận vẫn pending, thiếu bbox không suy thành mẫu âm.
- Camera185: 101 candidate từ 9 temporary truck tracks, chọn 3 frame native.
  v001 tại 24s/105s có manual bbox reference cần rà trên frame trích mới;
  v002 tại 109,52s chỉ shape proposal, có thể sai vùng/khác bố cục. Cả 3
  pending; không suy ra 3 xe hoặc 3 biển hai dòng. Không chép transcript.
- OCR policy chốt trước inference: FastPlate whole/original và English
  split/original. 98 case trên 49 crop human GT. CarTGMT 28/29 và 19/29:
  một dòng 18/19 và 11/19, hai dòng 10/10 và 8/10. Motorcycle riêng 16/20
  và 13/20. CER CarTGMT 1/230 và 25/230; motorcycle 4/173 và 7/173.
  29/20 chuỗi khác nhau chưa chứng minh 49 xe/capture độc lập. Màu/che
  pending, chưa đánh giá xác nhận biển vàng/container bị che hoặc xưởng.
- Phase D: module online train-only, seed theo sample/epoch/draw; 7 nhóm,
  7 contact sheets, 140 preview không tạo training dataset. Đo luma/contrast
  trên 47 bbox camera; glyph-height proxy 9/10/11px trên 15 readable crop.
  Thời tiết/đêm/pose vẫn là stress presets, chưa hiệu chỉnh thực nghiệm.
  Val/test giữ nguyên pixel/transcript; inward bbox jitter, ? hoặc empty
  transcript không eligible cho native FastPlate. Không đoán glyph/row map.
- HEVC roundtrip thật libx265 một frame đạt, không mô phỏng temporal stream.
  FastPlate pinned1.1.0/MIT nhận Albumentations YAML; exported2.0.8/MIT,
  save/load + actual transform parity đạt. Native loader resize và tạo y
  trước transform(image), không hỗ trợ ?/masked loss; YAML không giữ RNG
  Compose seed. Cần nối adapter/RNG và kiểm chứng riêng trước training.
- Trang vào: loopback8768/d05j-expanded-20261007/index.html. Root có audit,
  source references, JSON/native crops, raw/GT table, configs, contact sheets
  và verification. Giữ cổng cũ, originals, models/baseline/Phase2. Chưa có
  train, GPU hoặc thay database/D02/S03/token/volume/event nghiệm thu.
- Full edge-agent: 149 passed, 0 failed, 1 warning duplicate ZIP fixture
  có chủ đích, 3,65s. Node chạy editor JS thật kiểm tra pending/confirm,
  autosave restore, JSON export/import uint64/tamper; augmentation tests.
  Browser kiểm tra paging/autosave và confirm trên fixture riêng. IAB
  download event timeout: không báo native-download end-to-end đã đạt.
  Git diff check sạch; repo vẫn toàn untracked, không tracked baseline.
- Chờ người dùng hoàn tất review và condition tags; chưa fine-tune.


## 08/10/2026 — D05k: dữ liệu silver/synthetic và bounded FastPlate fine-tune

- Đã đọc AGENTS/tasks/D05i/D05j, tái dùng augmentation, benchmark, detector
  D05f và FastPlate MIT pinned9ce7a5b. Người dùng cho phép GPU đã cấp, không thuê mới.
- Khóa evaluation trước inference mới: camera88 (26 full/7partial/55unreadable)
  +public gold49; Car val12/test17, motorcycle val8/test12 theo nhóm chuỗi và
  exact/near crop. Gold train=0, camera toàn test. Public capture IDs chưa biết.
- 419 CarTGMT →150 silver/110chuỗi,252review,17loại. Ba raw/source normalize
  đồng thuận +format hợp lệ;1proposal score≥.75; không tự ép ký tự hoặc gọi silver gold.
  Heldout source/crop hashes, dHash≤4 và string groups được loại khỏi train.
- Synthetic1024chuỗi,512một/512hai dòng,342trắng/341vàng/341xanh. Font OFL,
  ghi nguồn chính thức; glyph9–11px trước native blur/HEVC. Cover<1/3 và không
  giao glyph; không ?, không flip. Chỉ train augmentation, không sửa test pixel.
- CUDA preflight2batch thật, finite loss, optimizer/checkpoint resume nguyên vẹn,
  val18/20, peakVRAM~4,19GiB. FFmpeg/SIGTTIN sửa bằng detached stdin trước timeout.
- Train8epoch,19batch/epoch,152update,79,268s, natural epochs_complete; caps
  240step/1200s/0autorestart. Batch16,cuối12,drop_lastfalse. 150silver+150synthetic
  mỗi epoch, finite sampler. Bestepoch1 bằng validation/tie policy; last epoch8.
- Keras/PyTorch ONNX export lỗi tương thích; không retrain, chuyển checkpoint
  portable qua Keras/TensorFlowCPU2.20 +tf2onnx1.17. ONNX và TF/Keras khớp Torch
  137/137raw, maxprob error3,07e-6. Tải48artifacts/hash ZIP/file đều khớp.
- Test trước/sau: camera26/26 CER0/208 (1uniqueplate,13frame,2crop/frame);
  Car17/17 CER0/134; motorcycle9/12 CER3/104. Không cải thiện →giữ pretrained.
  Partial7rawkhôngđổi,5/7khớptranscriptD05f chỉchẩnđoán,khônggộpexact;
  unreadable55vàmàu/chependingkhôngchấmđủbiển. Sáu rawunreadablethayđổi không chứng minh tốt hơn.
- Gói train thựcv3 giữ nguyên;v4 bổ sung runner/export/dependencies, dataset/config/
  pretrained/testhashkhớpv3, giải nén1407file, inspect và export replay đạt.
  Trang loopback8768/d05k-20261008/index.html có baseline/so sánh/review/synthetic.
- Full edge-agent 164 passed / 0 failed, 3,82 giây; warning ZIP duplicate fixture có chủ đích;
  gitdiffcheck sạch,repovẫnuntracked. Không đổiDB/D02/S03/token/volume/Windows.
- Kết thúc D05k ở thử nghiệm có giới hạn, chưa đạt tiêu chí thay runtime; không
  tự tăng epoch/tune theo test. ArtifactsđãvềMac, người dùngcóthểStopGPU;
  agentkhôngStop/Destroy. Chi tiết/hash/lệnh: `offline-vision-d05k.md`.

## 09/10/2026 — D05m: local/replay đã triển khai; API thật và thiết bị còn chờ

- Phạm vi Local + API đã được duyệt trong `local-api-vehicle-pilot-plan.md`;
  chia nhỏ D05m1–m5, giữ D05g/D05h/D06/D07 riêng và không khởi động lại D05l.
- D05m1 thêm migration additive `e7a31c9d0f42` và migration retention
  `e7a31c9d0f43`, API visit/evidence/prediction/confirmation/audit/AI mock cùng
  heartbeat riêng S01. ACK sau commit; idempotent/conflict; evidence private,
  quota và 30 ngày retention. Không sửa D02 hoặc migration cũ.
- D05m2 nối CLI replay D05a với detector D05f export và FastPlate pinned vào
  persistence/UI. Replay camera-185 đoạn media 65–122s tạo trong DB thử riêng
  1 visit, 7 evidence, 1 local prediction. Retry cùng bundle thêm 0 visit,
  phát hiện 9 phần tử trùng idempotent. Đăng nhập UI xem được đủ 7 ảnh qua API
  riêng tư; D02 Trips/WeighEvents/GoodsTransactions đều 0 trong E2E database.
- Toàn bộ kiểm thử tự động chạy trên PostgreSQL DB tạm và đã drop. Sau khi người
  dùng bật Docker, `./scripts/dev.sh up` chạy thành công trên volume ứng dụng
  hiện có; migration `e7a31c9d0f43` ở head, không reset volume. API live/ready
  và web trả 200. Dữ liệu replay chỉ có trong DB test, không seed DB ứng dụng.
- `ipconfig getifaddr en0` xác nhận IP LAN hiện tại `192.168.1.13`; `.env` local
  đổi `API_BIND_IP` từ `.17` cũ sang `.13` sau khi lần up đầu không bind được.
  API hiện bind `192.168.1.13:8001`, web `127.0.0.1:5174`, PostgreSQL
  `127.0.0.1:5433`; không mở router/firewall. UI E2E kiểm tra riêng dùng API
  8002, Vite 5175 và DB tạm. Desktop 1440×960/mobile 390×844 đạt; phát hiện và
  sửa tràn mobile do hash dài; đo lại `scrollWidth=390` trên viewport 390.
- Kiểm thử: 7 test D05m + 68 regression D01/D02/S01/S03 đạt trên PostgreSQL
  test; `npm run build`, CLI help, `docker compose config --quiet` và
  `git diff --check` đạt. Edge-agent: 162 passed, 3 deselected do optional
  `torch` không có. Một warning deprecation từ Starlette TestClient.
- TrollLLM `GET /v1/models` trả 401 cả lần kiểm tra có User-Agent theo tài liệu;
  không gửi ảnh hoặc gọi model, không usage/chi phí. Key TrollLLM đã dán trong
  chat phải được thu hồi/thay mới. Gemini Models API hiện xác thực được, nhưng
  D05m3 chưa chọn/xác minh provider model cho image inference, image/structured-
  output contract hoặc giá/downstream retention. Budget dự trù 2 USD/request
  thật chưa được code nối; inference thật bị khóa.
- Người dùng yêu cầu lưu Gemini key trong `.env`; đã ghi một mục `GEMINI_API_KEY`
  vào `.env` local mode `0600`, file Git ignored, không expose qua Compose.
  `GET https://generativelanguage.googleapis.com/v1beta/models` với header
  `x-goog-api-key` trả HTTP 200 và 50 model; có model Gemini hỗ trợ
  `generateContent`. Chỉ xác nhận Models API, chưa xác minh image request, model
  cụ thể, giá, structured output hoặc downstream retention. Không gửi ảnh và
  không gọi inference. Key đã xuất hiện trong chat, nên thu hồi/thay sau khi
  kiểm tra. D05m3 vẫn chưa bật provider job hoặc nối dự trù/đối soát ngân sách.
- Khi mở web pilot, DevTools báo `ERR_CONNECTION_REFUSED` tới `localhost:8001`.
  Nguyên nhân là `VITE_API_BASE_URL` trong `.env` trỏ host loopback, trong khi
  API bind `192.168.1.13`; URL cũng thiếu prefix `/api`. Đã đổi sang `/api` và
  rebuild/recreate web để thay giá trị Vite nhúng lúc build. Web root và
  `/api/health/live` qua proxy cùng origin trả 200; `/api/auth/me` trả 401 hợp lệ
  khi chưa đăng nhập. Các container API/DB/web healthy. Đây không phải lỗi cache
  gốc; sau rebuild, trình duyệt có thể cần tải lại trang để lấy asset mới.
- Chưa kết nối camera live/NVR hoặc cân CANXE2015, chưa heartbeat Windows,
  không có bằng chứng S03b. Cần quản lý xác nhận quyền camera sau 401 cũ.
  Backup/restore và retention sweep trên volume chạy dài chưa thử.
- Không có nhãn cho replay; visit để unknown/cần người xem, không tính độ chính
  xác. Thời gian là media time vì không có anchor UTC rõ. Không có D02 mutation.

## 09/10/2026 — Tài khoản local để thử vai trò D01

- Database local ban đầu không có user; chỉ có cơ sở `DEMO` đang hoạt động.
- Đã tạo `pilot.admin` bằng bootstrap admin; tạo `pilot.manager` và `pilot.staff`
  qua API quản trị, cùng gán vào cơ sở demo. Ba tài khoản đều đăng nhập qua web
  API thành công (HTTP 200) và API trả đúng role tương ứng.
- Mật khẩu được sinh ngẫu nhiên, lưu ngoài repository tại
  `/Users/nguyen_bao/.config/nhu-tung-demo/role-test-accounts-20261009.json`
  với quyền file `0600`, thư mục `0700`. Không ghi password vào log/tài liệu.
- Bộ user này đủ để đăng nhập xem giao diện từng role trên cơ sở demo. Database
  hiện chỉ có một cơ sở, nên kiểm tra cách ly giữa hai cơ sở cần dùng test suite
  hiện có hoặc thêm cơ sở demo riêng sau này.

## 09/10/2026 — D05m4a heartbeat PC cân v1

- Tái sử dụng `scale_agent_heartbeats` và `/api/scale-ingestion/heartbeat` đã
  được chuẩn bị trong D05m1; không tạo bảng lịch sử hoặc endpoint heartbeat thứ
  hai. Migration additive `e7a31c9d0f44` thêm schema v1, heartbeat UUID/sequence,
  hash payload, trạng thái reader/agent, thời gian đọc/ACK và safe error code.
  Snapshot cũ được giữ ở schema 0. S02 batch/API, token, outbox và checkpoint
  không đổi.
- Heartbeat v1 xác thực Bearer agent/facility S01. Heartbeat sequence mới hơn
  cập nhật một snapshot; gửi lại ID/nội dung hiện tại nhận duplicate ACK mà
  không làm mới thời gian; sequence cũ nhận stale ACK và không ghi đè. Server
  khóa theo agent, ghi `received_at_utc`, commit rồi mới ACK. Không ghi signal,
  lượt cân, trip hoặc giao dịch D02. Không gửi heartbeat thử vào DB ứng dụng.
- GET pilot áp dụng scope facility D01. Admin nhận telemetry đầy đủ; manager/
  staff chỉ nhận trạng thái liên lạc/reader trong cơ sở được gán. UI phân biệt
  đang liên lạc (<=90s), chậm (>90–180s), mất (>180s), chưa từng nhận và
  snapshot legacy; reader empty/error riêng. Khi poll lỗi, giữ snapshot cuối có
  thời gian cập nhật và báo không thể cập nhật, không kết luận PC offline.
  Timestamp UI dùng `Asia/Ho_Chi_Minh`.
- Hợp đồng Windows v1 và cấu hình mẫu tại
  `docs/windows-scale-heartbeat-handoff.md` và
  `docs/examples/windows-scale-heartbeat.config.example.json`; chu kỳ 30s độc
  lập threshold, sequence local tăng bền vững, không replay heartbeat cũ.
  Chưa sửa/cài client Windows và chưa nghiệm thu CANXE2015.
- Kiểm thử PostgreSQL tạm: `python3 scripts/test-d05m.py` — 9 passed, gồm ACK
  sau commit, duplicate/id conflict, late sequence, không tạo `scale_signals`/
  D02, quyền manager/staff và fake clock tại 90/90.001/180/180.001 giây.
  Regression `python3 scripts/test-d02.py` — 68 passed (D01/D02/S01/S03).
  Cả hai DB thử đã được drop. Do host không cài `uv`, hai runner dùng
  `backend/.venv/bin/python` nếu có; test-d02 runner được bổ sung fallback này.
  Một Starlette TestClient deprecation warning.
- `npm run build` đạt; `./scripts/dev.sh up` build/restart local, migration lên
  head `e7a31c9d0f44` trên volume hiện có, không reset volume. Health API live/
  ready và web trả 200; GET heartbeat user-route không session trả 401. API
  hiện bind LAN theo cấu hình sẵn có `192.168.1.13:8001`, web vẫn
  `127.0.0.1:5174`, PostgreSQL vẫn `127.0.0.1:5433`.

## 10/10/2026 — D05m4 camera .185 preflight

- Đọc lại `AGENTS.md`, kế hoạch `local-api-vehicle-pilot-plan.md`,
  `offline-vision-d05m.md`, tasks/progress và source live/replay. D05a replay
  → backend → web/private evidence đã có; API provider thật chưa bật. Chưa có
  RTSP worker hoặc preview live trong source. Không tạo endpoint/pipeline thứ
  hai và không sửa heartbeat đã được người dùng xác nhận.
- Xác minh lại IP hiện tại bằng `ipconfig getifaddr en0`: `192.168.1.13`.
  Compose API `192.168.1.13:8001` trả `/api/health/ready` HTTP 200; web vẫn
  `127.0.0.1:5174`, DB vẫn chỉ bind loopback `127.0.0.1:5433`; Alembic head
  `e7a31c9d0f44`. Không khởi động lại container hoặc đổi cổng/cấu hình mạng.
- Chỉ thử đúng địa chỉ camera đã cung cấp, TCP RTSP port 554 reachable. Probe
  main stream không credentials qua RTSP/TCP nhận `401 Unauthorized` từ
  `OPTIONS`. Không thử password, không coi đây là kết quả CGI, và chưa có
  DESCRIBE/SDP, PLAY, codec, độ phân giải, FPS, bitrate hay frame giải mã.
- Kiểm tra các Keychain labels `192.168.1.185`, `camera-185`,
  `dahua-camera-185`, `nhu-tung-camera-185` và mục Internet server cùng host;
  các mục này không tồn tại. Không kết luận về label khác và không dùng lại
  password từng xuất hiện trong chat.
- Tạo `edge-agent/config/camera-185.live.json` bằng cấu hình D05a hiện có,
  nhịp đề xuất 3 Hz; ROI vẫn provisional. Xuất
  `data/offline-vision/local-camera-185-review/roi-proposed-20261010.png` từ video replay đã có
  (`camera_185_20261004_073000-073500.mp4`, media 65s, 1920×1080), ghi rõ cần
  người vận hành xác nhận; ảnh này không phải luồng live.
- Do credential chưa sẵn sàng, không thể xác minh RTSP auth/giải mã, chạy
  capture worker, preview, inference hoặc visit/evidence live; cũng chưa thể
  chạy giám sát 10–15 phút hay restart worker. Không gửi ảnh tới AI provider,
  không tạo dữ liệu DB và không có nghiệm thu xe thật.

## 10/10/2026 — D05m4 xác minh main stream camera .185

- Người dùng xác nhận tài khoản có quyền live/playback. Credential được lưu
  ngoài repo tại `~/.config/nhu-tung-demo/camera-185-credentials.json`, quyền
  thư mục/file `0700/0600`; nội dung không mã hóa. Không lưu secret trong Git.
- Lần gọi PyAV đầu truyền user/password như AVOptions riêng và nhận 401. Sau
  khi kiểm tra option RTSP của FFmpeg, dùng lại PyAV/FFmpeg với credential đọc
  từ file trong process để chạy đúng một phiên 60 giây; không đưa credential
  vào shell argv/history, logs hay output. Kỹ thuật này tạo URI có userinfo
  trong bộ nhớ, trái với yêu cầu nghiêm ngặt “không đặt credential trong URL”;
  không dùng cách đó cho worker lâu dài. Cần client hỗ trợ Digest với trường
  credential riêng hoặc proxy localhost an toàn.
- Camera trực tiếp `.185`, channel 1/subtype 0, TCP: HEVC 1920×1080, nominal
  25 fps; OSD `2026-10-10 11:08:33` khớp giờ Mac lúc bắt đầu. Capture remux
  Matroska 62,2 giây/1.555 frame; FFprobe đếm và PyAV giải mã lại đủ 1.555
  frame. SHA-256 `1b8a88f274f08b3c60a6265c60a11ab15641cf98090a99751ed12baf5ccc9507`,
  file mode `0600` ngoài repo. Bitrate remux khoảng 2,12 Mbps.
- D05f detector chạy 181 frame ở nhịp xấp xỉ 3 Hz; 0 detection, 0 OCR. Ảnh
  đầu/giữa cho thấy bàn cân không có xe; đây không phải phép đo accuracy.
  Một overlay cho thấy ROI được cấu hình còn provisional. CPU 30,54 giây và
  peak RSS 327 MiB gồm giải mã hậu kiểm clip, không đại diện benchmark worker.
- Chưa có worker live/preview/reconnect tích hợp, kiểm tra restart, visit hay
  evidence DB, provider AI, xe thật hoặc camera `.172`; không sửa Compose,
  API, DB, heartbeat, cân, D02 hay S03. D05m4 tiếp tục mở.

## 10/10/2026 — D05m4 worker camera live liên tục

- Đọc AGENTS/kế hoạch/requirements/architecture/tasks/source trước triển khai.
  Tái sử dụng PyAV đã giải mã main .185, `pipeline.process_frame`, Tracker,
  SessionManager, CandidatePool, D05f và FastPlate pretrained (hash khóa trong
  config); không tạo pipeline/RTSP proxy hay microservice mới.
- Runtime credential từ Keychain bằng helper native/pipe riêng. URI xác thực
  chỉ trong bộ nhớ theo phê duyệt mới; libav QUIET, exception chỉ mã an toàn.
  Không đặt secret vào argv/env/config/ảnh QA; scan các file đổi không có literal
  mật khẩu. File/runtime/evidence/data và `.env` được Git ignore.
- Worker độc lập API/web, latest-frame queue 2, nhịp detect cấu hình 3 Hz,
  timeout 5s/reconnect backoff 1–30s. State/outbox SQLite bền vững; visit UUID
  giữ qua restart, không dùng stream dropout làm xe rời; ACK outbox sau commit
  PG và fingerprint audit phát hiện same-ID/different-body conflict. Không
  ghi đè prediction/xác nhận hay tạo D02.
- Migration additive `e7a31c9d0f45` (camera_runtime/camera_diagnostics) đã
  áp dụng vào volume hiện có. Preview D01/cơ sở 640×360 ~1 Hz; health nhận/giải
  mã/xử lý riêng mỗi 30s, queue/FPS/latency/reconnect/outbox/evidence/AI. UI
  giữ stale data khi mất API; heartbeat PC/reader/signal vẫn riêng.
- Diagnostic native snapshot + ROI tối đa 1/10 phút (cadence durable), giữ 24h,
  quota 128 MiB; clip nút UI ~15s riêng, không gọi AI, không ghi video vô hạn.
  Evidence xe giữ 30d qua storage/retention hiện có, quota cơ sở 5 GiB. Bind
  mount live bổ sung dưới existing storage; không xóa named volume.
- Phiên giám sát 2026-10-10T04:33:22.782582+00:00 → 2026-10-10T04:48:39.922744+00:00:
  **917.14s (15.29 phút)**; snapshot cuối ghi nhận
  22,428 frame giải mã và
  2,311 frame xử lý cộng qua các
  process trong phiên. Counter chốt theo health 30s, không phải đếm chính xác
  tại từng millisecond của mốc kết thúc. 2 lần restart có kiểm soát: một lần
  kiểm tra phục hồi, một lần áp dụng sửa outbox/health; gọi start khi đang chạy
  không tạo process thứ hai. PID 14543 là worker ở mốc chốt phiên giám sát.
  Sau phiên có thêm 2 restart triển khai sửa metadata/ID gián đoạn; worker
  cuối PID 15356 tiếp tục chạy, health 12:00 VN vẫn receiving/processing,
  queue 0/outbox 0. Không phát sinh visit trùng khi không có xe.
- FPS nhận theo packet/giây: [18.55, 25.81]; FPS xử lý
  [1.81, 2.74] (gồm startup, bình thường ~2,5–2,7 Hz).
  Queue max 2, outbox 0, reconnect tự động 0. CPU sample
  5s: 111.4% theo thang một core; RSS
  cuối 513.0 MiB, max quan sát
  679.3 MiB. Không thấy queue/RAM tăng liên tục.
- Clip lần đầu `4e0b2a8f…` interrupted do đặt quyền trước khi encoder tạo file;
  đã sửa. Clip `8fa6718b…` stored, H.264 960×540, giải mã đủ 40 frame, media
  13,333s trong ~15s tường; không phải remux main. Hai snapshot cách nhau
  ~10 phút; overlay ROI còn provisional.
- Khi kiểm tra service cuối thấy evidence-retention bị reconnect nhầm
  127.0.0.1:5433 trong container; sửa chọn DATABASE_URL nội bộ Docker riêng
  ở retention. Service đã chạy ổn định và lệnh `--once` exit 0; không thay
  hợp đồng S01/heartbeat hoặc reset DB.
- Backend tests PostgreSQL tạm cuối: **12 pass / 0 fail**; edge/live source + offline
  pipeline + FastPlate adapter: **35 pass / 0 fail**. `npm --prefix frontend run
  build` đạt; migration/readiness đạt. Test phân quyền/CSRF/anonymous/agent token,
  private preview, clip duplicate, clock stage/worker, outbox restart/duplicate/
  conflict/commit và no-D02. Bổ sung test ID interrupted riêng cho restart và
  shutdown trong cùng process, opened payload bất biến, metadata bbox/crop native
  và config runtime truy vết được. DB tạm đã xóa riêng sau chạy.
- UI Chrome với session Pilot Test Admin đã xem live/health/heartbeat và bấm
  thu clip. Anonymous preview HTTP 401; staff cross-facility HTTP 404 trong test.
  PC heartbeat seq 140 trước restart → 162 cuối,
  reader empty/pending 0; vẫn là đang liên lạc, không gọi PC offline. Kiểm tra
  cuối 11:59:39 VN seq 184 vẫn cập nhật, vendor process đang chạy; source live
  và xử lý đang tốt, không ảnh hưởng heartbeat/API/web.
- Kiểm tra UI cuối phát hiện thông báo clip giữ chữ queued sau khi đã stored;
  sửa hiển thị theo trạng thái diagnostic được polling, build lại frontend đạt.
  Bấm clip `664f9c38…` trên web: trạng thái chuyển đang chờ → đã lưu;
  giải mã độc lập đủ 42 frame H.264 960×540, 14s media/~15s tường.
  Handoff cuối `data/pilot/camera-185/handoff-final.json`: heartbeat seq 189
  nhận 12:02:09 VN, 9 signal và 0 bản ghi D02/visit/evidence xe/AI job.
- Đối chiếu PG chỉ đọc: **9 signal S03a còn nguyên**, trips/weigh_events/goods
  transactions đều 0; camera visit/evidence/AI job 0. Không có xe vào ROI trong
  phiên, không chạy OCR/API AI hay tạo dữ liệu giả. Chưa nghiệm thu xe thật,
  manual review trên xe thật, chất lượng OCR/API, ROI xác nhận hoặc S03b/cân thật.
- API/web/PG/retention đang chạy, Mac IP en0 hiện tại 192.168.1.13. Bàn giao
  `docs/camera-live-pilot.md`, config worker/ROI và script start/stop/status/restart.
  Git repository hiện toàn bộ source untracked; `git diff` không có baseline
  tracked để so sánh, `git diff --check` đạt; không tự stage/commit.


## 10/10/2026 — D05m4b: rà D02, camera theo sự kiện

- Đọc source D02/signal/heartbeat/worker và ghi bảng hành vi thực tế trong
  `camera-event-driven-pilot.md`: manual event/result, chọn before/after,
  nhập trước−sau/xuất sau−trước, reweigh/replace, hàng trung gian, chống khoảng
  chồng pending/confirmed, idempotency transaction và liên hệ camera chỉ theo
  thời gian. Không đổi quy tắc chưa chốt. Nêu thiếu idempotency POST cân và
  acknowledge có thể reset selected; để công ty quyết định, chưa sửa workflow.
- Thêm task D05m4b chưa dùng; mặc định event_driven, continuous vẫn lựa chọn.
  Idle đóng RTSP/không decode/detect/OCR/API; mẫu observed đủ mới ≤10s và
  ≥1.000kg hoặc manual mở cửa sổ 20s; 4 ảnh native ≥4s/crop, ≤30 inference,
  ≤6 plate calls/≤4 OCR calls. Coalesce signal chain/restart, gap120s chỉ rearm
  photo window, không chứng minh xe rời/xe mới. Không tự chốt D02.
- Tái dùng D05m4/PyAV/modelhash/outbox và CameraDiagnostic, không schema/service
  mới. Preview opt-in ≤120s có quyền/CSRF, expiry+manual stop; ảnh native không
  lấy từ preview640×360. Nút process/photo/preview trên /pilot. Scale contact và
  reader hiển thị riêng, manual dùng khi nguồn cân lỗi; health idle_unchecked
  không coi ảnh cũ là online. Windows không cần đổi S02/heartbeat.
- 5 đợt .185 main: frame đầu1,429–2,604s, ảnh đầu1,603–2,733s từ request; mỗi
  đợt4ảnh/27–28inference. Không xe trong ROI, không visit/OCR/API giả. CPU
  baseline continuous166,8%, idlemedian1,4%/cuối1,7%, processingmedian~98%,
  preview-only~25% (100%=1core). RAM peak~591MiB; idle RSS biến động, mẫu cuối78,7MiB; chưa
  chứng minh không leak dài hạn. Decode vẫn~25FPS khi source mở, idle0.
- Sửa manual photo recapture trước DB commit: capturing→saving trước ghi,
  outbox/recovery→stored; file immutable/hash. Giữ record lỗi cũ interrupted;
  2request mới stored và decode/hash1920×1080 đạt. Vehicle evidence có file
  outbox riêng khỏi diagnostic24h. Restart riêng nhiều lần phục vụ fix/deploy,
  không worker/process con trùng; queue/outbox về0, counters dừng khi idle.
- Backend PG tạm16pass/0fail, edge liên quan38pass/0fail, frontendbuild đạt.
  Một fixture encoder thiếu bufferAPI đã sửa/chạy lại; Starlette có1warning
  anyio. Không mở rộng test không liên quan. Migration đầu-cuối vẫn e7a31c9d0f45;
  không có migration mới. ReadinessLAN192.168.1.13:8001 đạt200, localhost8001
  không bind theo config hiện tại; webproxy5174/sessionManager vẫn hoạt động.
- DB chỉ đọc cuối:9S03a signal,0trip/weigh/transaction/visit/AIjob. Heartbeat
  agent06c70368… seq421 nhận13:58:12VN, readerempty/pending0, UIđangliênlạc.
  Worker cuốiPID20584 chạy event-driven, idle nguồn đóng. Cân≥1.000kg thật,
  xe/nhận diện/OCR/API và ROI người dùng xác nhận vẫn chờ.
- Bàn giao `camera-event-driven-pilot.md`, configworker, nútPilot, Windows
  handoff supplement và `output/pilot-event-driven-ui.jpg`. Git toàn repo
  untracked, diff không có baseline tracked; không stage/commit.


## 11/10/2026 — D05m4c: chụp theo chất lượng biển, dọn ứng viên

- Tái dùng worker live/PyAV, CandidatePool, D05f/FastPlate, outbox/visit và D01.
  Policy tối đa 120s/1Hz/120 vehicle calls/40 plate calls/4 OCR calls. Dừng sớm
  sau ≥15s khi có 2 crop native ≥96×24, sharpness ≥20, score ≥0,35, bbox đủ mép,
  cách ≥3s và một session không đa xe. Đây là heuristic, không xác nhận đọc rõ
  đầu/đuôi hoặc OCR đúng.
- Giữ tối đa 8 bộ scene/vehicle/plate cùng frame (24 file); dọn crop/context tạm
  kém/trùng khi thay thế và sau khi outbox đã lưu bền vững. Không xóa evidence
  đã ACK; nếu thiếu crop, một scene/visit giữ để review bỏ sót. Health/UI có tiến
  độ tìm biển, reason timeout/success và timestamp evidence. D02/S02/heartbeat
  không đổi, không migration mới; quota/retention giữ nguyên.
- 16 test backend DB tạm đạt; 39 test camera liên quan đạt; TypeScript/Vite và
  Compose web build/deploy đạt. Git toàn repo vẫn untracked, diff không có
  baseline; không stage/commit, không ghi đè secret hoặc reset volume.
- Preflight 4 scene camera thật đã lưu, lặp 3 lần/scene cho tracker fixture:
  3 plate calls/3 proposal, chọn 2 bộ/6 file, decode/hash/native bbox đạt,
  candidate còn 0. Không DB write/API/GT mới, không gọi là benchmark live.
- Worker PID35040 chạy config mới. Manual live 14:10:51–14:12:51 VN:
  2.995 frame decode/114 inference, frame đầu 1,546s, timeout 120,017s;
  0 plate/OCR/visit mới/AI. Cuối idle/nguồn đóng/queue0/outbox0/reconnect0/error
  null, RSS45,6MiB. UI hiển thị reader empty và agent liên lạc được riêng.
  Chưa xác minh hiệu quả chọn biển trên lượt xe tiếp theo.
- Bàn giao `camera-event-driven-pilot.md` phần D05m4c, ảnh web
  `output/pilot-plate-guided-ui.jpg`, báo cáo `output/capture-selection-preflight/`.
  Giới hạn: model không phân loại đầu/đuôi, ROI còn provisional; tăng thời gian
  không khắc phục góc không thấy biển. Quota 5GiB có thể không đủ nếu 100 lượt/
  ngày ×8 bộ ×30 ngày; cần số đo thực.


## 11/10/2026 — D05m6: thu gọn giao diện theo dõi

- Đọc hướng dẫn repository, requirements/architecture và source D02, heartbeat,
  scale signals, camera visit/evidence, API và UI trước khi sửa. Giữ nguyên D02,
  migrations, dữ liệu thật, worker/outbox, heartbeat, quota và retention.
- Thêm cấu hình điều hướng tập trung. Menu vận hành hiện chỉ có Tổng quan,
  Lượt xe, Tín hiệu cân; code/routes cũ vẫn còn. Trang Tổng quan bỏ thẻ D02 và
  hiển thị số camera visit, biển chưa xác định/cần xem lại, camera, heartbeat
  và trạng thái reader tách riêng.
- Trang Lượt xe lọc theo ngày, cơ sở, biển và trạng thái review; hiển thị riêng
  gợi ý AI với xác nhận người dùng. Chi tiết ưu tiên biển/trạng thái/thời gian,
  3 ảnh đại diện, thư viện ảnh thêm, ảnh gốc, nội dung kỹ thuật/audit thu gọn.
  Giữ version check, CSRF, audit và quyền cơ sở. Link `/pilot` tiếp tục hoạt động.
- Tín hiệu thô vẫn không gắn tự động với xe hay D02. Chi tiết chỉ nêu mẫu trong
  khoảng thời gian để đối chiếu, gồm giờ quan sát/nhận khi có. Mẫu gần nhất cũ
  được ghi là lịch sử, không phải trọng lượng hiện tại khi reader trống.
- Build frontend thành công; `scripts/test-d05m.py`: **17 pass / 0 fail** trên
  DB test tạm; `git diff --check` đạt. Đã build/deploy riêng API và web; health
  API và web HTTP 200. PostgreSQL volume không reset, worker camera không restart.
- Browser với session Manager hợp lệ: menu 3 mục, 5 lượt camera trong danh sách,
  chi tiết có 3 ảnh đại diện + 6 ảnh bổ sung thu gọn. Trang tín hiệu hiển thị
  timestamp observed/received và lịch sử phân trang. Tổng quan thực tế đọc 5
  visit hôm nay, 5 biển chưa xác định, 5 cần review; camera “Chưa kiểm tra gần
  đây”, PC `WIN-TEST-01` “Đang liên lạc”, reader “Nguồn trống”. Trạng thái camera
  không được suy ra online từ ảnh cũ.
- UI xác nhận/sửa không được submit trong DB thật. Không có dữ liệu nhập/xuất,
  không có quan hệ thủ công camera_visit–scale_signal; không kết luận biển đúng,
  cân đã ổn định, lượt cân hoặc giao dịch. Không stage/commit. Chi tiết và giới
  hạn xem `vehicle-monitoring-ui.md`.

## 11/10/2026 — Khôi phục heartbeat khi Mac đổi mạng

- Agent xác định từ snapshot/cấu hình đang vận hành:
  `06c70368-50a1-470d-bf26-45391cd05069`, scale code `WIN-TEST-01`.
  Snapshot trước sửa: seq2685, server nhận 18:20:38.720226 giờ VN,
  reader empty/vendor running/pending0. API log trước mất liên lạc trả 200
  mỗi khoảng 30s, không thấy 401/403.
- Mac hiện IP LAN192.168.1.13 nhưng Docker API còn publish192.168.1.9:8001;
  Tailscale Serve cũng proxy tới192.168.1.9. HTTP qua hostname tailnet trả502,
  trong khi API container healthy và Tailscale tới gateway100.117.137.90
  direct14.230.95.113:1038, ping6ms. Nguyên nhân xác minh: đích proxy/bind LAN
  cũ không còn truy cập được sau đổi mạng; không phải reader empty hay cacheUI.
- Đổi `.env` local API_BIND_IP=127.0.0.1 và recreate riêng API; giữ DB/volume,
  token/sequence/outbox/worker. Tailscale Serve đổi upstream127.0.0.1:8001,
  tailnet-only. Local và tailnet readiness đều200. PostgreSQL vẫn chỉ publish
  loopback127.0.0.1:5433; không chạy AI hay gửi heartbeat giả.
- Heartbeat Windows tự phục hồi. DB chỉ đọc: seq2842 nhận19:46:40.798818 VN;
  seq2844 nhận19:47:37.689825 VN (tăng2 trong56.891s). Cả hai reader empty,
  pending0; snapshot sau vendor_process_running=true, last_error_code=null.
  Chỉ giữ snapshot gần nhất; không tuyên bố đối chiếu mọi heartbeat bị gián đoạn.
- Bổ sung endpoint VPN và lệnh Serve trong `windows-scale-heartbeat-handoff.md`.
  Hostname ổn định là `nkb-mb-pm2p-1.tail54c504.ts.net:8001`; URL IP thuần của
  Tailscale Serve có thể404 do định tuyến Host. Không sửa source/payload heartbeat
  hoặc schema nên kiểm tra tập trung readiness/bind và heartbeat thật; không
  chạy lại bộ test nghiệp vụ. Git toàn repo untracked, không stage/commit.

## 12/10/2026 — S03c / D06a: trang tín hiệu và khảo sát người

- Đối chiếu DB read-only event sequence12876: observed `2026-10-11 17:16:00.314137Z`
  = `12/10 00:16:00.314137` VN; received `2026-10-11 20:41:35.358634Z`
  = `12/10 03:41:35.358634` VN. Delay khoảng 3 giờ 25 phút 35 giây. Các sequence liền kề tăng đều ở observed nhưng nhận
  gần như cùng lúc, phù hợp gửi batch bù/backlog, không phải lỗi múi giờ. Schema chỉ lưu timestamp normalized observed,
  server received và vendor_text, không có bản timestamp gốc thứ ba độc lập.
- Snapshot PC cân đọc trước deploy: heartbeat sequence4344, reader empty,
  pending801, `SIGNAL_SENDER_PAUSED`; sau khi deploy API/web snapshot sequence4355,
  reader empty, pending801, cùng mã lỗi, received09:24:09 VN. Không có signal
  mới trong 3 phút gần nhất. Heartbeat tiếp tục, sender signal vẫn pause; không
  sửa Windows/outbox hoặc xóa backlog. Sự cố gửi signal chưa được sửa ở task này.
- `/api/scale-monitoring/signals/chart` trả chuỗi ascending trong toàn khoảng,
  độc lập với page bảng; CTE PostgreSQL giới hạn mặc định1.200 điểm/tối đa2.000
  và giữ first/last/min/max từng bucket. UI đường thẳng, ngắt khoảng >60s,
  tooltip observed/received/weight/sequence, zoom kéo, filter 1h/24h/7d/tháng/
  khoảng tùy chọn/mọi thời gian, tự trình bày kg/t. 60s là ngưỡng hiển thị sơ
  bộ, không phải ngưỡng ổn định cân.
- Endpoint summary đếm raw sample theo observed time; ngày/tháng dùng boundary
  Asia/Ho_Chi_Minh. UI báo delay riêng, không SUM trọng lượng. DB D02 có
  WeighEvent/WeighResult manual nhưng không có “lượt cân quan sát” độc lập;
  KPI observed/confirmed/review đang unavailable, không thay bằng sample hay
  camera_visit. Đề xuất mô hình observation → nhiều stable segments cùng raw IDs,
  threshold/version/recompute và người xác nhận được ghi trong
  `scale-monitoring-and-person-prep.md`; chưa tạo schema/logic.
- COCO YOLOX-s 80 class checksum đã kiểm tra, person class0. Thử CPU thưa 2s:
  video .185 thứ nhất151 frame/81 frame có person/113 bbox sau NMS, max score
  0,9156; thứ hai66/35/61, max0,8830, khoảng38s tổng. Ảnh candidate/bbox xem
  `output/d06-person-review/camera185-person-candidate.jpg`. Đây không phải
  precision/recall; score không hiệu chuẩn. Chỉ một view .185 có video local;
  không tìm thấy clip/capture .172. ROI weighbridge hiện vẫn provisional; chưa
  tạo ROI cabin/vùng xuống xe hoặc bật person detection runtime.
- Build frontend `npm run build` đạt. `scripts/test-d02.py`: **72 passed, 1
  deprecation warning** trên PostgreSQL DB tạm (bao gồm duplicate/backfill,
  permissions, chart bounded/extrema, VN day boundary, empty signal/KPI); DB tạm
  đã drop. Không migration. `git diff --check` sạch.
- `docker compose ... up -d --build api web` hoàn tất; API readiness/web trả200.
  Chart/summary unauthenticated trả401 (route tồn tại và session auth còn bật).
  Log sau recreate có heartbeat ingestion200. DB/volume không reset; không gọi
  AI, không chạy training, không thay Windows agent. Browser smoke sau deploy
  bằng session Manager tại `/scales` đạt: chọn đúng cơ sở/agent, summary hiển thị
  mẫu theo ngày/tháng và trạng thái lượt cân chưa đủ dữ liệu; chart 24h hiển thị
  8.325 mẫu, trả 869 điểm giảm mẫu; bảng vẫn phân trang 30 dòng độc lập. UI cho
  thấy observed 00:16:53 và received 03:41:35 ngày 12/10. Snapshot này xác nhận
  luồng hiển thị, không chứng minh sender đã tiếp tục gửi signal mới.
- Cần nhận video native camera .172 với kênh/OSD và xác nhận overlay ROI .185,
  .172 trước khi biến person detector thành bằng chứng runtime. Git checkout
  đang hiện toàn bộ repository dạng untracked; không stage/commit.


## 12/10/2026 khoảng 13 giờ — S03d sửa biểu đồ và chẩn đoán sender paused

- Xác nhận biểu đồ trước sửa có marker che đường và gap dựa trên dữ liệu sau
  giảm mẫu. Nay segment được tính từ raw từng agent trước sampling; time
  bucket first/last/min/max giữ giới hạn điểm. Bỏ marker dày, thống nhất trục
  tấn/giờ VN, tooltip/tap, selection zoom và nút xem đoạn tín hiệu cuối.
- Preset tự cập nhật tới hiện tại; custom/zoom cố định và có nhãn rõ. Reuse
  `/api/vehicle-pilot/heartbeat/scale-agents` để hiển thị paused/pending cho
  staff/manager theo cơ sở, chi tiết kỹ thuật vẫn admin-only.
- Read-only agent06c70368-50a1-470d-bf26-45391cd05069: lúc12:52:23 heartbeat4765
  nhận12:52:17, pending1309; lúc13:11:50 heartbeat4804 nhận13:11:47,
  pending1483. Cả hai SIGNAL_SENDER_PAUSED/reader empty; last successful read
  mới nhất13:10:49. DB signal count/latest seq đều12982, observed00:16:53,
  received03:41:35 ngày12/10. API/VPN healthy và heartbeat đi được; chưa có
  signal mới được commit. Source/config pause Windows chưa có trên Mac.
- Bàn giao prompt trong `windows-scale-sender-recovery-20261012.md`; chưa sửa
  agent, token, outbox hoặc timestamp. Chưa tuyên bố đã khôi phục sender.
- `scripts/test-d02.py`:74 passed/1 warning; `scripts/test-d05m.py`:18 passed/
  1 warning trên hai DB tạm độc lập, đã drop. Frontend build đạt. Deploy riêng
  API/web, readiness local/tailnet/web200. Không migration/reset volume.
- Browser session Manager đạt: 1h trống, 24h có dữ liệu, đoạn cuối149/149
  trong00:15:09–00:17:23, tap tooltip observed/received/weight/sequence; kéo
  zoom00:15:41–00:16:27 trả92/92. Ảnh lưu
  `output/scale-monitoring-20261012/chart-fixed.png`. Git untracked, diff
  trước/sau kiểm tra từ bản lưu tạm; không stage/commit.


## 13/10/2026 — S03e tổng quan điểm đại diện / zoom

- Thêm view raw/overview/auto cho chart, API mặc địnhraw tương thích cũ,
  UI mặc địnhauto: trên3giờ dùngoverview. Mỗi đoạn raw gap60s có một event
  weight xuất hiện nhiều nhất, tie gần midpoint rồiID. Metadata giữ raw ID,
  sequence, weight, observed/received, bounds/count; không persist lượt cân.
- Overview nối điểm theo thứ tự cách đều, ghi rõ khoảng cách không theo thời
  lượng và đây chưa phải lượt/số cân đã chốt. Raw giữ thời gian/gap thật.
  Bounded1.200/2.000; quá nhiều đoạn giảm representatives giữ cực trị có nhãn.
- Thêm nhấp đúp điểm, kéo chọn, nútphóngto/thu nhỏ, quay lại/đặt lại với
  history20; các nút vẫn có khi khoảng dữ liệu trống. Không tải all raw.
- Frontend build đạt; scripts/test-d02.py77passed/1warning trên DB tạm riêng
  đãdrop. Scope/backfill/bounded/representative thật/no newWeighEvent/empty
  đạt. DeployAPI/web healthy; không migration/reset volume/stage/commit.
- BrowserManager trên7ngày:63điểm từ12.982raw. Nhấp đúp→199mẫu
  11/10 10:23:11–10:25:50; +→160mẫu, −→199, quay lại→160,
  đặt lại→63điểm. Kéooverview→17điểm/3239raw, đặt lạiđạt. Ảnh
  output/scale-monitoring-20261013/overview.png. Báo cáo đầy đủ S03e trong
  scale-monitoring-and-person-prep.md.
- UI vẫn báo sender Windowspaused/pending8755, latestraw00:16:53 ngày12/10.
  Chưa xử lý Windows trong task giao diện này, không báo đã nhận cân mới.

## 13/10/2026 — Tinh gọn giao diện Quản lý (Tổng quan, Chuyến xe xuất/nhập) và tích hợp Google AI OCR

- Nghiệp vụ: Khách hàng chưa đồng bộ trước lịch xe/ERP, vận hành dựa trên nhận diện biển số camera và 2 lượt cân cùng biển trong ngày. Tinh gọn thanh điều hướng Manager còn 2 trang nghiệp vụ cốt lõi:
  1. **Tổng quan**: KPI sản lượng nhập (tấn/kg), sản lượng xuất (tấn/kg), xe đang trong xưởng (chờ cân lần 2), chuyến hoàn tất (đã đủ 2 lượt cân), bảng chuyến xe gần nhất và trạng thái trạm cân/camera gọn nhẹ.
  2. **Chuyến xe xuất / nhập**: Danh sách chuyến xe đã ghép cặp (Cân 1, Cân 2, chiều Nhập/Xuất, hàng ròng), kèm chế độ xem Dòng sự kiện (Timeline), xem ảnh phóng to, chỉnh sửa nhanh biển số và kích hoạt Google AI OCR.
- Backend:
  - Cập nhật `backend/app/core/config.py` và `compose.local.yml`: hỗ trợ `GEMINI_API_KEY`.
  - Thêm endpoint `GET /api/vehicle-pilot/visits/trips`: ghép cặp các lượt xe cùng biển số trong ngày (Asia/Ho_Chi_Minh), suy đoán hướng xe từ chênh lệch trọng lượng ($W_1 > W_2$: Nhập hàng, $W_1 < W_2$: Xuất hàng, 1 lượt cân: Đang trong xưởng), tính khối lượng hàng ròng và tổng hợp KPI.
  - Thêm endpoint `POST /api/vehicle-pilot/visits/{id}/gemini-ocr`: gọi Google Gemini 2.5 Flash Vision API với ảnh crop bằng chứng để đọc biển số, lưu `VehiclePrediction` (source `api`) và ghi audit log.
- Frontend:
  - Cập nhật `navigation-config.ts`: tinh giản menu vận hành thành "Tổng quan" (`home`) và "Chuyến xe xuất / nhập" (`visits`).
  - Cập nhật `VehiclePilotPage.tsx` và `VehiclePilotPage.css`: hiển thị thẻ KPI, bảng chuyến xe paired trực quan, nút gọi Google AI OCR, modal sửa nhanh biển số và modal xem phóng to ảnh.
  - Cập nhật `OperationalOverview` trong `App.tsx`: hiển thị 4 KPI sản lượng, bảng chuyến xe gần nhất và trạng thái thiết bị thu gọn.
- Kiểm tra nghiệm thu:
  - `npm run build` (frontend): thành công, 0 lỗi TypeScript, Vite build đạt.
  - `python3 scripts/test-d05m.py`: 19 passed, 1 warning (deprecation anyio), database test tạm được tạo và dọn dẹp sạch sẽ.
  - Docker Compose: đã chạy `build api web` và `up -d api web`; cả `api` (8001) và `web` (5174) đã được build mới và khởi chạy lại thành công, đạt trạng thái `healthy`; volume dữ liệu PostgreSQL được bảo toàn nguyên vẹn.
  - Không thay đổi schema database; không commit secret/.env.

## 30/10/2026 — Kích hoạt lại các trang nghiệp vụ, tích hợp module Trông trống cà và vai trò drum_operator

- Nghiệp vụ:
  1. Chức năng cân tạm hoãn hoàn thiện sâu nhưng giữ nguyên hiển thị trên UI; kích hoạt lại toàn bộ các trang sẵn có trong mã nguồn (`Tín hiệu cân`, `Chuyến xe`, `Lịch hàng`, `Cần xác nhận`).
  2. Bổ sung vai trò mới: `drum_operator` (Trông trống cà) chuyên trách:
     - Quản lý vòng mẻ sấy: Ghi nhận ngày/giờ vào trống (`entry_time`) và ngày/giờ ra trống (`exit_time`).
     - Đo kiểm định kỳ trong trống: Nhập độ ẩm cà (`moisture_percent`) và nhiệt độ luồng hơi thổi vào (`temperature_celsius`) theo chu kỳ (mặc định 30 phút).
     - Kết quả xả trống: Nhập độ ẩm của cà khi đã ra khỏi trống (`final_moisture_percent`).
     - Đánh giá tuân thủ giờ giấc (KPI): Dựa trên thời điểm máy chủ ghi nhận thực tế (`recorded_at_utc`) so với chu kỳ kế hoạch (`scheduled_time`) và giờ đo (`measured_at`) để đánh giá đúng hạn (`on_time`) hoặc trễ hạn (`late`), ngăn chặn gian lận ghi dồn cuối ca.
     - Thanh tra ngẫu nhiên (`drum_inspections`): Cho phép Quản lý / Thanh tra lấy mẫu đột xuất tại hiện trường, tự động tính chênh lệch sai số $\Delta$ độ ẩm và $\Delta$ nhiệt độ đối chiếu với thợ trống, phát hiện sai sót kỹ thuật hoặc gian dối.
- Backend:
  - Mở rộng ràng buộc vai trò `Role = Literal["admin", "manager", "staff", "drum_operator"]` trong `backend/app/modules/accounts`.
  - Tạo module mới `backend/app/modules/drum_processing` gồm:
    * `models.py`: Bảng `drums`, `drum_runs`, `drum_periodic_logs`, `drum_inspections`.
    * `schemas.py`: Các schema Pydantic xác thực độ ẩm ($0 - 100\%$), nhiệt độ ($0 - 350^\circ\text{C}$), chu kỳ phút.
    * `router.py`: Đầy đủ endpoint `/api/drum-processing/drums`, `/runs`, `/runs/{id}/logs`, `/runs/{id}/discharge`, `/runs/{id}/inspections`, `/audit/kpi`.
  - Migration Alembic: `e7a31c9d0f46_drum_processing_and_operator_role.py` (down_revision `e7a31c9d0f45`).
- Frontend:
  - Cập nhật `navigation-config.ts`: Mở lại các trang `home`, `drums` (icon Flame), `visits`, `scales`, `trips`, `schedules`, `pending`.
  - Tạo trang mới `DrumProcessingPage.tsx` và `DrumProcessingPage.css`: Dashboard giám sát trạng thái trống, thẻ KPI tuân thủ, lưới thiết bị sấy, timeline chi tiết mẻ sấy, các modal nạp mẻ, ghi nhật ký chu kỳ, xả trống và thanh tra ngẫu nhiên.
  - Cập nhật `App.tsx`: Khai báo role `drum_operator` (Trông trống cà), tích hợp router `/drums` và cập nhật form quản lý tài khoản.
- Kiểm tra nghiệm thu:
  - `python3 scripts/test-d02.py`: 81 passed, 1 warning (anyio deprecation) trên database tạm thời tạo mới và xóa sạch sau test.
  - `alembic upgrade head`: Áp dụng thành công migration `e7a31c9d0f46` trên database local PostgreSQL.
  - `npm run build` (frontend): Biên dịch thành công, 0 lỗi TypeScript, Vite build đạt.
  - Docker Compose: Build và khởi chạy `api` và `web` thành công (`healthy` trên cổng 8001 và 5174).

## 16/11/2026 — Thêm các loại cà phê nạp trống (Cà quả, Cà lụa, Cà quả trộn lụa kèm % tỷ lệ) và Nhiệt độ ban đầu

- Nghiệp vụ:
  1. **3 loại cà phê nạp vào trống chính**:
     - `Cà quả sấy ráo`: 100% cà quả tươi đã sấy ráo nước.
     - `Cà lụa sấy ráo`: 100% cà vỏ lụa đã sấy ráo nước.
     - `Cà quả trộn cà lụa đã sấy ráo`: Cho phép thợ trống chỉ định tỷ lệ phối trộn % từng loại (% Cà quả và % Cà lụa). Giao diện trực quan gồm thanh tỷ lệ hai màu, hai ô nhập số tự động liên kết cân bằng tổng 100%, và các nút chọn nhanh phổ biến (50/50, 60/40, 70/30, 80/20).
     - Cho phép tùy chọn "Tùy chỉnh khác" nếu xưởng có loại cà phê đặc thù ngoài 3 loại chính.
  2. **Nhiệt độ ban đầu (°C)**:
     - Bổ sung trường nhập nhiệt độ ban đầu của buồng sấy/luồng hơi trước khi nạp cà (thường từ 65°C - 85°C).
     - Giúp theo dõi tương quan giữa nhiệt độ khởi điểm với chất lượng hạt ra lò (cà đẹp hay cà xấu) để hoàn thiện chiến lược sấy cho từng trống.
  3. **Hiển thị trực quan toàn diện**:
     - Hiển thị loại cà phê, tỷ lệ phối trộn mẻ trộn và nhiệt độ ban đầu tại tiêu đề chi tiết mẻ sấy.
     - Thêm thẻ KPI "Nhiệt độ ban đầu" trong màn hình vận hành mẻ sấy.
     - Cập nhật bảng Lịch sử mẻ sấy của từng trống: hiển thị loại cà phê, tỷ lệ phối trộn và nhiệt độ ban đầu của từng mẻ trong quá khứ để người trông trống đối soát kinh nghiệm.
- Backend & Database:
  - Migration Alembic: `backend/migrations/versions/e7a31c9d0f48_drum_coffee_types_and_initial_temp.py` thêm 3 cột:
    - `initial_temperature_celsius`: Numeric(5, 2), nullable=True
    - `blend_ratio_qua_percent`: Numeric(5, 2), nullable=True
    - `blend_ratio_lua_percent`: Numeric(5, 2), nullable=True
  - Models: Cập nhật `DrumRun` trong `backend/app/modules/drum_processing/models.py`.
  - Schemas: Cập nhật `DrumRunCreate`, `DrumRunItemOut`, `DrumRunDetailOut`, `DrumRunSummaryItem` trong `backend/app/modules/drum_processing/schemas.py`.
  - Router: Cập nhật `start_drum_run`, `get_drum_run_detail`, `list_runs`, `get_drum_analytics` trong `backend/app/modules/drum_processing/router.py`.
- Frontend:
  - Cập nhật `frontend/src/DrumProcessingPage.tsx` và `frontend/src/DrumProcessingPage.css`:
    - Modal 1 ("Nạp mẻ cà vào trống"): thiết kế lại với bộ nút chọn thẻ loại cà, bảng tùy chỉnh tỷ lệ % mẻ trộn với thanh tỷ lệ trực quan và nút preset nhanh, ô nhập "Nhiệt độ ban đầu (°C)".
    - Màn hình chi tiết mẻ sấy: bổ sung thẻ KPI "Nhiệt độ ban đầu", hiển thị loại cà phê và tỷ lệ trong header.
    - Modal Chiến lược & Lịch sử: hiển thị loại cà và nhiệt độ ban đầu trong bảng lịch sử mẻ sấy.
- Kiểm tra & Nghiệm thu:
  - `python3 scripts/test-d02.py`: Tất cả **82 tests** đều passed (100%), áp dụng migration thành công trên cơ sở dữ liệu tạm thời.
  - `npm --prefix frontend run build`: TypeScript check và Vite build thành công không có lỗi.
  - Áp dụng migration `e7a31c9d0f48` vào database container thực tế `nhu-tung-demo-db-1`.
  - Rebuild và cập nhật các container `nhu-tung-demo-api-1` và `nhu-tung-demo-web-1` (cả 2 đều `healthy`).
  - Chạy kịch bản tích hợp API end-to-end với vai trò `trong.ca`: tạo mẻ sấy phối trộn 60% quả / 40% lụa với nhiệt độ ban đầu 75.5°C, ghi nhật ký định kỳ, tắt nhiệt ủ mẻ, xả mẻ đạt "Cà đẹp" và kiểm tra trích xuất chiến lược phân tích thành công 100%.


- Nghiệp vụ:
  1. **Phân quyền hiển thị theo Role (Tuyệt đối không để lộ các trang không liên quan)**:
     - `drum_operator` (Thợ trông trống cà): Menu bên trái chỉ hiển thị duy nhất "Trông trống cà" (`/drums`). Khi đăng nhập hoặc truy cập bất kỳ đường dẫn nào khác (`/`, `/visits`, `/scales`, ...) sẽ được tự động điều hướng sang `/drums`. Ẩn toàn bộ các nút cân hàng, xe cộ, tổng quan và thẻ trợ giúp D02.
     - `staff` (Nhân viên cân): Chỉ thấy các trang vận hành cân và chuyến xe: Tổng quan (`home`), Chuyến xe xuất/nhập (`visits`), Tín hiệu cân (`scales`), Chuyến xe (`trips`), Lịch hàng (`schedules`), Cần xác nhận (`pending`). Ẩn hoàn toàn trang trông trống cà (`drums`) và tài khoản (`accounts`).
     - `manager` (Quản lý chi nhánh): Quản lý cơ sở của mình, có quyền tạo trống sấy, thanh tra đột xuất, xem chiến lược/lịch sử sấy của từng trống và tạo/quản lý tài khoản cho nhân viên cân (`staff`) và thợ trông trống (`drum_operator`) trong chi nhánh.
     - `admin` (Quản trị viên hệ thống): Chỉ quản lý tình hình vận hành web, tạo chi nhánh xưởng (`POST /api/admin/facilities`) và tạo tài khoản Quản lý chi nhánh (`manager`).
  2. **Quy trình Ủ nhiệt sau khi tắt buồng đốt**:
     - Phân biệt rõ thời điểm tắt nhiệt (`heat_off_at`), thời điểm tắt quay trống (`rotation_off_at`) và thời điểm xả trống (`exit_time`).
     - Thợ trông trống thường tắt nhiệt khi độ ẩm còn khoảng 15-16% rồi ủ trong trống một khoảng thời gian (`incubation_minutes`); trong giai đoạn ủ, hơi nóng tích tụ giúp hạt cà chín đều từ trong ra ngoài và độ ẩm tiếp tục giảm xuống mức chuẩn (~12.5%).
     - Bổ sung nút thao tác "Tắt nhiệt & Bắt đầu ủ" ghi nhận độ ẩm lúc tắt nhiệt (`moisture_at_heat_off`).
     - Khi xả mẻ ra trống, ghi nhận độ ẩm cuối (`final_moisture_percent`), tự động tính thời gian ủ và mức giảm độ ẩm khi ủ.
     - Ghi nhận đánh giá chất lượng mẻ: Cà đẹp (`ca_dep`), Đạt chuẩn (`dat_chuan`), Cà xấu (`ca_xau`) kèm nhận xét chất lượng.
  3. **Cơ chế thống kê lịch sử & đúc kết chiến lược sấy riêng cho từng trống**:
     - Do mỗi trống có dung tích, vật liệu và đặc tính bảo ôn riêng, nhiệt độ luồng hơi và thời gian ủ để ra "Cà đẹp" khác nhau.
     - Endpoint `GET /api/drum-processing/drums/{drum_id}/analytics` tự động phân tích dữ liệu các mẻ sấy đạt "Cà đẹp" của riêng trống đó để đưa ra chiến lược tối ưu: Nhiệt độ luồng hơi khuyến nghị, độ ẩm nên ngắt nhiệt, thời gian ủ khuyến nghị, mức giảm độ ẩm dự kiến và tóm tắt hướng dẫn vận hành.
     - Giao diện có nút "Chiến lược & Lịch sử" trực quan ngay trên từng trống và trong chi tiết mẻ sấy.
- Backend:
  - Migration Alembic: `e7a31c9d0f47_drum_incubation_and_quality.py` bổ sung các cột `heat_off_at`, `rotation_off_at`, `moisture_at_heat_off`, `incubation_minutes`, `quality_assessment`, `quality_note` cho bảng `drum_runs`.
  - Cập nhật `accounts/router.py`: Bổ sung endpoint `POST /api/admin/facilities` (Admin tạo chi nhánh), nới quyền cho `manager` tạo/quản lý tài khoản `staff` và `drum_operator` thuộc chi nhánh phụ trách.
  - Cập nhật `drum_processing/router.py`: Bổ sung endpoint `POST /runs/{id}/stop-heat` và `GET /drums/{id}/analytics`.
- Frontend:
  - Cập nhật `navigation-config.ts`: Cung cấp hàm `getOperationalNav(role)` và `getAdministrationNav(role)`, `getDefaultPageForRole(role)`, `isPageAllowedForRole(page, role)` để lọc sạch menu theo vai trò người dùng.
  - Cập nhật `App.tsx`: Thực thi điều hướng bảo vệ route chặt chẽ theo role; cập nhật `AccountsPage` hỗ trợ Admin quản lý chi nhánh và Manager quản lý nhân viên trạm.
  - Cập nhật `DrumProcessingPage.tsx` và `DrumProcessingPage.css`: Bổ sung modal "Tắt nhiệt & Bắt đầu ủ", chọn đánh giá chất lượng (Cà đẹp / Đạt chuẩn / Cà xấu) khi xả mẻ, và modal hiển thị Chiến lược sấy tối ưu cùng bảng đối soát lịch sử từng trống.
- Kiểm tra nghiệm thu:
  - `python3 scripts/test-d02.py`: 82 passed, 1 warning (anyio deprecation) trên database tạm thời tạo mới và xóa sạch sau test.
  - Áp dụng migration `e7a31c9d0f47` vào database PostgreSQL thực tế trong container.
  - `npm run build` (frontend): Biên dịch thành công, 0 lỗi TypeScript, Vite build đạt.
  - Đã seed thử nghiệm mẻ hoàn tất trên `TRONG-01` với chất lượng "Cà đẹp" và kiểm tra tính toán analytics chiến lược tự động thành công.
  - Docker Compose: Build và khởi chạy `api` và `web` thành công (`healthy` trên cổng 8001 và 5174).




## 16/11/2026 — Đặc tính thiết bị & Tùy biến giao diện đo ẩm 2 đầu trống sấy

- Nghiệp vụ:
  1. **Đặc tính cơ học & Lỗi kỹ thuật của từng trống sấy**:
     - Do kết cấu cơ khí, độ kín buồng sấy và tình trạng cánh đảo của từng trống khác nhau, hệ thống cho phép cấu hình chi tiết đặc tính riêng của từng thiết bị:
       - `has_moisture_imbalance`: Trống bị lệch độ ẩm cà 2 đầu nặng (đầu buồng cấp gió và đuôi buồng sấy chênh lệch nhiệt/ẩm lớn).
       - `has_blade_issue`: Trống bị lỗi cánh đảo cà khiến cà bên trong buồng đảo không đều, dẫn đến hạt ra lò không đồng nhất dù ở cùng một mặt cắt.
       - `characteristics_notes`: Ghi chú lưu ý kỹ thuật, kinh nghiệm xử lý riêng cho thợ trực.
     - Phương thức đo độ ẩm (`measurement_mode`):
       - `center_only`: Đo tại tâm giữa buồng sấy (chế độ tiêu chuẩn cho trống sấy hoạt động bình thường).
       - `two_ends`: Đo tại cả 2 đầu buồng sấy (áp dụng cho các trống bị lệch nhiệt/ẩm 2 đầu, bắt buộc thợ phải lấy mẫu và đo tại cả đầu trống và đuôi trống).
  2. **Tuỳ biến giao diện vận hành theo đặc tính từng trống**:
     - **Ghi nhật ký chu kỳ (Periodic Log)**:
       - Nếu trống đo 2 đầu (`two_ends`): Form tự động hiển thị 2 ô nhập riêng biệt: "Độ ẩm đầu trống (%)" và "Độ ẩm đuôi trống (%)". Hệ thống tính toán trực tiếp và hiển thị thẻ thông số: `Độ ẩm trung bình` và `Chênh lệch 2 đầu (Δ)`. Cảnh báo nổi bật nếu mức chênh lệch đầu - đuôi vượt quá 1.5%.
       - Nếu trống đo giữa (`center_only`): Form giữ ô nhập đơn tiêu chuẩn "Độ ẩm giữa trống (%)".
       - Tự động hiển thị các cảnh báo nhắc nhở thợ trực tương ứng với lỗi của trống: nhắc đo kỹ 2 đầu nếu trống lệch ẩm, nhắc xáo sâu lấy mẫu lõi nếu cánh đảo bị lỗi.
     - **Xả mẻ ra trống (Discharge)**:
       - Trống đo 2 đầu cho phép nhập độ ẩm cuối ở cả đầu và đuôi buồng sấy (`final_moisture_head_percent`, `final_moisture_tail_percent`), tự động tính độ ẩm xuất xưởng trung bình.
     - **Bảng nhật ký mẻ sấy**:
       - Cột độ ẩm hiển thị chi tiết số liệu: Độ ẩm TB kèm theo thông số chi tiết `Đầu: X% · Đuôi: Y% (Δ Z%)`.
     - **Thẻ thiết bị & Cấu hình đặc tính**:
       - Hiển thị huy hiệu chế độ đo (`📍 Đo 2 đầu` / `📍 Đo giữa`).
       - Hiển thị các thẻ cảnh báo lỗi cơ học (`⚠️ Lệch ẩm 2 đầu`, `⚠️ Lỗi cánh đảo cà`) và ghi chú đặc tính.
       - Quản lý / Quản trị viên có nút Cấu hình (Settings) trực tiếp trên từng thẻ trống để cập nhật phương thức đo và lỗi cơ học bất kỳ lúc nào (`PATCH /drums/{id}`).
     - **Chiến lược sấy tối ưu**:
       - Tự động bổ sung các khuyến nghị an toàn vào tóm tắt chiến lược cho thợ trống nếu thiết bị có lỗi cơ học hoặc lệch ẩm 2 đầu.
- Backend & Database:
  - Migration Alembic: `backend/migrations/versions/e7a31c9d0f49_drum_characteristics_and_measurement_points.py` bổ sung:
    - Bảng `drums`: `measurement_mode` (mặc định `'center_only'`), `has_moisture_imbalance` (Boolean), `has_blade_issue` (Boolean), `characteristics_notes` (Text/String).
    - Bảng `drum_periodic_logs`: `moisture_head_percent`, `moisture_center_percent`, `moisture_tail_percent`, `moisture_diff_ends`.
    - Bảng `drum_runs`: `final_moisture_head_percent`, `final_moisture_tail_percent`.
    - Bảng `drum_inspections`: `sample_moisture_head_percent`, `sample_moisture_center_percent`, `sample_moisture_tail_percent`.
  - Cập nhật Models, Schemas và Router trong `backend/app/modules/drum_processing`:
    - Thêm endpoint `PATCH /api/drum-processing/drums/{drum_id}` cho phép Quản lý cập nhật đặc tính trống.
    - Endpoint ghi nhật ký tự động tính trung bình độ ẩm và độ lệch giữa 2 đầu buồng sấy khi nhận dữ liệu đầu/đuôi.
- Frontend:
  - Cập nhật `frontend/src/DrumProcessingPage.tsx` và `frontend/src/DrumProcessingPage.css`:
    - Modal thêm trống mới và Modal cập nhật đặc tính trống: hỗ trợ chọn phương thức đo bằng thẻ trực quan (`center_only` vs `two_ends`), checkbox chọn các lỗi cơ học và ô nhập ghi chú.
    - Tự động thay đổi linh hoạt các trường nhập trong modal Ghi nhật ký chu kỳ và Xả trống theo chế độ đo của trống.
    - Hiển thị banner đặc tính và thẻ cảnh báo trên chi tiết mẻ sấy và trên danh sách trống.
- Kiểm tra & Nghiệm thu:
  - `python3 scripts/test-d02.py`: Tất cả **83 tests** đều passed (100%).
  - `npm --prefix frontend run build`: TypeScript check và Vite build thành công với 0 lỗi.
  - Áp dụng migration `e7a31c9d0f49` vào database PostgreSQL `nhu-tung-demo-db-1`.
  - Rebuild và cập nhật thành công các container Docker `nhu-tung-demo-api-1` và `nhu-tung-demo-web-1`.
  - Kiểm thử end-to-end với tài khoản Quản lý: tạo trống đo 2 đầu có lỗi lệch ẩm và lỗi cánh đảo, cập nhật ghi chú qua PATCH API, chạy mẻ sấy, nhập độ ẩm 2 đầu (hệ thống tự động tính độ ẩm trung bình và độ lệch 2.5%), tắt nhiệt ủ và xả mẻ thành công 100%.

## 16/11/2026 — Cho iPhone thử web qua Tailscale

- DB/API/web hiện chạy healthy trên Mac, host bind loopback. Tailscale Serve
  thêm HTTP tailnet-only `:5174` → `127.0.0.1:5174`; giữ Serve API `:8001`
  hiện có. Không dùng Funnel, không mở cổng PostgreSQL ra ngoài.
- Vite preview từ chối hostname Tailscale (403); bổ sung allowlist đúng hostname
  Mac, rebuild/recreate riêng web, không reset volume hoặc thay API/agent.
- Kiểm tra từ Mac qua hostname MagicDNS: web200 HTML, `/api/health/ready`200,
  `/api/auth/me`401 khi chưa login, `/api/auth/csrf`200. Ping Tailscale tới
  iPhone XS Max có pong. Chưa kiểm tra thao tác Safari/đăng nhập từ iPhone.
- Web chạy Vite preview cho demo, không phải hệ thống production. Mac/Docker và
  Tailscale phải chạy; máy sleep làm gián đoạn. Compose hiện không cấu hình
  restart policy cho db/api/web; sau restart Mac có thể cần chạy lại Compose.

## 16/11/2026 — Tạm tắt khóa đăng nhập cho demo Mac

- Tài khoản thợ trống `trong.ca` active; đối chiếu read-only mật khẩu người
  dùng cung cấp với hash hiện tại cho kết quả không khớp. Không ghi mật khẩu
  hoặc hash vào báo cáo, không đổi/reset mật khẩu hay tài khoản.
- Thêm cấu hình `LOGIN_LOCKOUT_ENABLED`, mặc định true; `.env` riêng của demo
  đặt false theo yêu cầu. Khi false không áp dụng khóa cũ và không tạo bộ đếm
  thất bại mới; mật khẩu sai vẫn 401, CSRF/session/phân quyền vẫn áp dụng.
  Bật lại bằng sửa `.env` thành true và recreate API; khóa cũ chưa hết hạn
  có thể còn hiệu lực. Việc tắt giới hạn là tạm thời cho tailnet demo.
- `python3 scripts/test-d02.py` 84 passed, một warning Starlette/anyio trên DB
  kiểm thử tạm, migrations tới head đạt; DB tạm đã xóa. Test mới kiểm tra
  khóa đang tồn tại, thử sai nhiều lần, sau đó mật khẩu đúng vào được.
- Rebuild/recreate riêng API; xác nhận runtime false, API healthy, web/API
  readiness qua Tailscale200, DB/web healthy. Không xóa volume hoặc test
  mật khẩu thật qua request. Chưa xác minh đăng nhập iPhone sau khi đặt lại
  hoặc nhập mật khẩu đúng. `git diff --check` sạch; toàn checkout untracked.

## 16/11/2026 — Giao diện thông tin chi tiết từng trống & Lịch sử vào trống chi tiết

- Nghiệp vụ:
  1. **Trang / Giao diện thông tin chi tiết từng trống (Drum Detail View)**:
     - Cho phép người dùng và quản lý truy cập vào xem toàn diện hồ sơ của từng trống sấy bằng cách bấm vào tiêu đề trống hoặc nút "Chi tiết trống" trên từng card ở màn hình chính.
     - Header hiển thị đầy đủ mã trống (`drum_code`), tên trống (`drum_name`), sức chứa (`capacity_kg`), phương thức đo ẩm (`measurement_mode`), trạng thái hoạt động (Đang sấy mẻ nào hoặc Sẵn sàng nạp mẻ mới).
     - Điều hướng linh hoạt: Cung cấp nút quay lại danh sách tất cả trống sấy hoặc chuyển đổi mượt mà giữa chi tiết mẻ sấy và chi tiết trống.
  2. **Khối đặc tính kỹ thuật & Tình trạng thiết bị**:
     - Hiển thị chi tiết mã thiết bị, sức chứa thiết kế, phương thức đo độ ẩm (Đo tâm giữa trống vs Đo 2 đầu buồng sấy).
     - Hiển thị trực quan tình trạng cơ học: Huy hiệu cảnh báo nổi bật khi trống bị lỗi lệch độ ẩm 2 đầu nặng hoặc lỗi cánh đảo cà; hiển thị xác nhận khi buồng sấy và cánh đảo bình thường.
     - Hiển thị khối lưu ý kinh nghiệm vận hành riêng cho thợ trực từ ghi chú kỹ thuật (`characteristics_notes`).
  3. **Chức năng sửa thông tin trống**:
     - Nút "Sửa thông tin trống" được tích hợp trực tiếp trên Header trang chi tiết trống, trên Thẻ đặc tính kỹ thuật và trên card thiết bị ngoài dashboard.
     - Quản lý / Admin có thể chỉnh sửa: Tên trống, Sức chứa thiết kế, Phương thức đo độ ẩm (`center_only` vs `two_ends`), Cờ lỗi cơ học (Lệch ẩm 2 đầu, Lỗi cánh đảo cà) và Ghi chú kinh nghiệm vận hành.
     - Dữ liệu cập nhật qua API `PATCH /api/drum-processing/drums/{drum_id}`, lưu vào database và cập nhật ngay lập tức giao diện người dùng mà không cần reload trang.
  4. **Bảng Lịch sử vào trống chi tiết (Detailed Batch Run History)**:
     - Liệt kê toàn bộ các mẻ sấy từng vào trống này (cả mẻ đang chạy và các mẻ đã hoàn tất).
     - Thanh công cụ lọc & tìm kiếm thông minh:
       - Các tab lọc nhanh theo trạng thái: Tất cả mẻ, Đang sấy, Cà đẹp, Đạt chuẩn, Cà xấu kèm bộ đếm số lượng mẻ thực tế.
       - Ô tìm kiếm tức thời theo mã mẻ (`batch_code`), loại cà phê (`coffee_type`), hoặc thợ phụ trách (`operator_name`).
     - Bảng dữ liệu hiển thị chi tiết:
       - Mã mẻ & ngày vào trống (có thể click để mở thẳng chi tiết toàn bộ mẻ sấy).
       - Loại cà phê & tỷ lệ phối trộn (% Quả / % Lụa).
       - Khối lượng nạp (kg) & nhiệt độ luồng hơi ban đầu (°C).
       - Thời gian cấp nhiệt (phút) và thời gian ủ trong trống (phút).
       - Độ ẩm khi ngắt nhiệt (%) và độ ẩm thành phẩm khi ra trống (%) (kèm số liệu đầu & đuôi trống nếu đo 2 đầu).
       - Mức giảm độ ẩm thực tế trong giai đoạn ủ (-X%).
       - Đánh giá chất lượng thành phẩm (Cà đẹp / Đạt chuẩn / Cà xấu / Đang sấy) và nhận xét của thợ.
       - Tên thợ trông trống phụ trách mẻ và số lượt đo / thanh tra.
       - Nút thao tác "Chi tiết mẻ" để mở xem đầy đủ toàn bộ nhật ký chu kỳ đo, biểu đồ và kết quả thanh tra của mẻ.
- Backend & Database:
  - Bổ sung endpoint `GET /api/drum-processing/drums/{drum_id}` trong `backend/app/modules/drum_processing/router.py` trả về `DrumOut`.
  - Cập nhật schema `DrumRunItemOut` trong `backend/app/modules/drum_processing/schemas.py` và endpoint `GET /api/drum-processing/runs` bổ sung các trường: `moisture_at_heat_off`, `final_moisture_head_percent`, `final_moisture_tail_percent`, `quality_note`.
- Frontend:
  - Cập nhật `frontend/src/DrumProcessingPage.tsx` và `frontend/src/DrumProcessingPage.css`:
    - Thêm `renderDrumDetailView()` hiển thị chi tiết trống sấy, thẻ đặc tính cơ học, KPI, chiến lược đúc kết và bảng lịch sử vào trống chi tiết có lọc và tìm kiếm.
    - Tối ưu hóa kiến trúc modal: Tách `renderModals()` dùng chung để mọi modal (Sửa thông tin trống, Nạp mẻ mới, Ghi nhật ký chu kỳ, Tắt nhiệt ủ, Xả trống, Thanh tra) có thể mở từ bất kỳ màn hình nào.
    - Cập nhật thẻ trống ngoài Dashboard: Click vào tên trống hoặc nút "Chi tiết trống" sẽ chuyển sang xem chi tiết trống.
- Kiểm tra & Nghiệm thu:
  - `python3 scripts/test-d02.py`: Tất cả **84 tests** đều passed (100%).
  - `npm --prefix frontend run build`: TypeScript check và Vite build thành công 0 lỗi.
  - Đồng bộ backend và rebuild container `web` thành công (`healthy`).
  - Chạy kịch bản tích hợp end-to-end: Gọi `GET /drums/{id}`, sửa thông tin trống qua `PATCH /drums/{id}`, tra cứu lịch sử mẻ `GET /runs?drum_id={id}` đầy đủ các trường mới thành công 100%.

## 2026-11-16: Nâng cấp Quản trị Chi nhánh, Bố cục Điều hướng Trái và Giám sát Trạng thái Chức năng Hệ thống

- Yêu cầu người dùng:
  1. Chuyển "Nhật ký thao tác" sang thanh điều hướng bên trái (thay vì tab ngang phía trên).
  2. Thêm nút "Sửa thông tin chi nhánh" và nút "Xem chi tiết chi nhánh" để tra cứu danh sách nhân viên của chi nhánh và số lượng trống cà đang hiện hữu.
  3. Hiển thị trực quan trạng thái hoạt động của các phân hệ chức năng: Trống sấy (Trông trống cà), Camera giám sát, và Trạm cân hàng.
- Backend API & Quản lý dữ liệu:
  - Bổ sung endpoint `PATCH /api/admin/facilities/{facility_id}` trong `backend/app/modules/accounts/router.py`:
    - Cho phép Quản trị viên cập nhật tên chi nhánh (`name`) và trạng thái hoạt động (`is_active`).
    - Tự động ghi nhật ký kiểm toán hệ thống `facility_updated` vào bảng `account_audit_logs`.
  - Bổ sung endpoint `GET /api/admin/facilities/overview`:
    - Trả về danh sách chi nhánh kèm tổng số nhân sự (`employees_count`), số lượng trống cà (`drums_count`), số trống đang sấy (`running_drums_count`), số camera (`cameras_count`), số đầu cân (`scales_count`) và trạng thái hoạt động của từng phân hệ (`drum_status`, `camera_status`, `scale_status`).
  - Bổ sung endpoint `GET /api/admin/facilities/{facility_id}/detail`:
    - Trả về chi tiết toàn diện của chi nhánh: Thông tin chung, danh sách toàn bộ nhân viên được gán vào chi nhánh (`employees`), danh sách toàn bộ trống cà đang hiện hữu (`drums` kèm mã trống, tên trống, sức chứa, chế độ đo 2 đầu/giữa trống, cờ lỗi cơ khí lệch ẩm/cánh đảo, trạng thái rảnh/đang sấy) và thẻ trạng thái 3 phân hệ hệ thống (`drum_processing_status`, `camera_status`, `scale_status`).
  - Cập nhật các schema Pydantic tương ứng trong `backend/app/modules/accounts/schemas.py`.
- Frontend & Giao diện người dùng:
  - Tái cấu trúc thanh điều hướng bên trái (`sidebar`):
    - Thêm mục **Nhật ký thao tác** (`FileClock`) vào nhóm menu "QUẢN TRỊ HỆ THỐNG" cùng với "Tài khoản" và "Chi nhánh".
    - Nhấp chọn trực tiếp tại sidebar để chuyển view mượt mà, loại bỏ tab "Nhật ký thao tác" ở thanh tab ngang phía trên giúp giao diện gọn gàng và phân cấp chuẩn mực.
  - Nâng cấp bảng danh sách Chi nhánh (`tab === 'facilities'`):
    - Cột **MÃ CHI NHÁNH** và **TÊN CHI NHÁNH**.
    - Cột **TRẠNG THÁI**: Hiển thị trạng thái Hoạt động / Tạm ngừng.
    - Cột **QUY MÔ**: Thống kê số lượng nhân sự và số lượng trống cà của từng chi nhánh.
    - Cột **CHỨC NĂNG HỆ THỐNG**: Hiển thị các badge màu sắc thể hiện rõ tình trạng hoạt động:
      * 🛢️ Trống sấy: Badge vàng nếu có mẻ đang chạy (`Đang chạy (x/y)`), badge xanh nếu sẵn sàng (`Sẵn sàng (y trống)`), hoặc badge xám (`Chưa có`).
      * 📷 Camera giám sát: Badge xanh dương nếu có camera kết nối (`Đang kết nối (x camera)`), hoặc badge xám (`Chưa kết nối`).
      * ⚖️ Trạm cân hàng: Badge tím nếu trạm cân đang online (`Cân: Hoạt động`), hoặc badge xám (`Chưa kết nối`).
    - Cột **THAO TÁC**:
      * Nút **Xem chi tiết chi nhánh** (Icon Eye): Mở modal `FacilityDetailDialog`.
      * Nút **Sửa thông tin chi nhánh** (Icon Pencil): Mở modal `EditFacilityDialog`.
  - Xây dựng Modal **Chi tiết chi nhánh (`FacilityDetailDialog`)**:
    - Header hiển thị Tên cơ sở, Mã định danh, Trạng thái.
    - Grid 3 thẻ trạng thái phân hệ:
      * Trông trống cà: Trạng thái, số trống rảnh/chạy, số thợ trông trống được gán.
      * Camera giám sát: Trạng thái kết nối, mã camera (như `camera-185`).
      * Trạm cân hàng: Trạng thái trạm cân điện tử.
    - Bảng danh sách **Trống cà đang hiện hữu**: Liệt kê chi tiết từng trống sấy, mã trống, tên trống, sức chứa (kg), vị trí đo ẩm (đo giữa / đo 2 đầu), đặc tính khiếm khuyết cơ khí (lệch ẩm 2 đầu, lỗi cánh đảo, chuẩn bình thường) và trạng thái hiện tại (rảnh / đang sấy / bảo trì).
    - Bảng danh sách **Nhân sự chi nhánh**: Liệt kê họ tên, username, vai trò phân quyền (Quản lý chi nhánh, Nhân viên cân, Thợ trông trống cà) và trạng thái tài khoản.
    - Nút thao tác nhanh "Sửa chi nhánh" ngay trong modal.
  - Xây dựng Modal **Sửa chi nhánh (`EditFacilityDialog`)**:
    - Hiển thị Mã chi nhánh (readonly, giữ tính toàn vẹn hệ thống).
    - Cho phép chỉnh sửa Tên chi nhánh / Cơ sở.
    - Cho phép bật/tắt trạng thái hoạt động ("Đang hoạt động").
- Kiểm tra & Nghiệm thu:
  - `python3 scripts/test-d02.py`: **84/84 tests** passed (100%).
  - `npm --prefix frontend run build`: TypeScript check và Vite build thành công 0 lỗi.
  - Kiểm tra end-to-end API: `PATCH /api/admin/facilities/{id}`, `GET /api/admin/facilities/overview`, `GET /api/admin/facilities/{id}/detail` hoạt động chính xác và ghi nhận audit log đầy đủ.
  - Container Docker `web`, `api`, `db` đều đang chạy ổn định ở trạng thái `healthy`.

## 19/11/2026 — Bổ sung bước đầu dữ liệu đầu vào trống cà (chưa hoàn tất đặc tả)

- Đã thêm migration `e7a31c9d0f50` cho dữ liệu lô nguồn, giờ xay/bắt đầu sấy, tiếp xúc nước và vị trí đo nhiệt; dữ liệu cũ để trống. Thêm API đọc/ghi thông tin đầu vào theo mẻ, kiểm tra quyền cơ sở và thứ tự thời gian cơ bản; nhật ký nhiệt nhận thêm vị trí đo.
- Chưa hoàn thành giao diện, sự cố, QC và báo cáo đối chiếu; không coi đặc tả đã nghiệm thu. Mã lô hiện mới là chuỗi tham chiếu và chưa có chức năng đối chiếu liên cơ sở.
- `python3 -m compileall -q backend/app/modules/drum_processing backend/migrations/versions/e7a31c9d0f50_drum_source_metadata.py`: thành công. `docker compose --env-file .env -f compose.local.yml ps`: thất bại vì Docker daemon không kết nối được. Chưa chạy migration, health/readiness hoặc kiểm thử API. Frontend chưa thay đổi nên chưa chạy build.
- Git hiện báo toàn bộ nội dung dự án là untracked; `git diff` không hiển thị các tệp đó. Cần kiểm tra migration và các luồng thực tế trước khi sử dụng.

## 19/11/2026 — Trông trống cà: đầu vào, sự cố và QC

- Bổ sung API/UI cho dữ liệu đầu vào sau xay, sự cố từng mẻ và một kết quả QC chính sau xả; mẫu chưa chấm thành phần giữ null, số 0 giữ riêng. Thêm vị trí đo nhiệt ban đầu/định kỳ; hỗ trợ ghi một đầu ẩm mà không suy ra chênh lệch.
- Bổ sung báo cáo QC cơ bản theo cơ sở, ngày xả, trống và phương pháp; nhóm theo đơn vị và điểm lấy mẫu. Chưa có màn hình đối chiếu liên xưởng/cùng lô hay phân tích các yếu tố chờ và sự cố. Không hỗ trợ sửa QC trong phiên bản này.
- PostgreSQL tạm tại cổng 55439: `alembic upgrade head` thành công tới `e7a31c9d0f52`. `DATABASE_URL=<DB tạm> .venv/bin/pytest -q tests/test_drum_processing.py`: 7 passed, 1 cảnh báo deprecation; bao gồm kiểm tra readiness, quyền cơ sở, đầu vào, đo, sự cố và tỷ lệ gộp 32,5%. `npm --prefix frontend run build`: thành công. Docker daemon không kết nối được, chưa áp migration vào DB ứng dụng hoặc kiểm tra trên dịch vụ đang triển khai; chưa kiểm tra UI qua trình duyệt.
- Git status: toàn bộ dự án được báo untracked; `git diff` không bao gồm các tệp này. Không thay đổi DB ứng dụng.

## 19/11/2026 — Triển khai giao diện và đối chiếu lô

- Thêm API và màn hình đối chiếu mã lô theo các cơ sở được cấp quyền, hiển thị thời gian chờ, QC, nhiệt quan sát theo vị trí, chênh ẩm và sự cố. Chưa có biểu đồ nhiệt, lọc khoảng chờ hay tính chênh lệch tự động giữa các xưởng.
- `npm --prefix frontend run build` và `docker compose --env-file .env -f compose.local.yml build api web`: thành công. `docker compose ... run --rm --no-deps api .venv/bin/alembic upgrade head`: nâng DB local từ f49 lên f52 thành công. `docker compose ... up -d api web`: thành công; db, api, web healthy, `/api/health/ready` trả `{"status":"ok"}`, web HTTP 200 tại cổng 5174.
- PostgreSQL tạm: `DATABASE_URL=<DB tạm> backend/.venv/bin/pytest -q backend/tests/test_drum_processing.py`: 7 passed, 1 cảnh báo deprecation; kiểm tra tài khoản cơ sở khác không thấy mẻ qua đối chiếu. Chưa kiểm tra trình duyệt và chưa nghiệm thu đối chiếu bằng dữ liệu thật của hai xưởng.
- Đã xem `git diff --stat` và `git status --short`; toàn bộ dự án vẫn untracked nên diff không hiển thị nội dung.

## 19/11/2026 — Mở rộng trông trống cà: Nguồn cà sàn tĩnh & Module trông sàn sấy tĩnh

Trạng thái: **hoàn thành**.

### Đã làm
- **Cơ sở dữ liệu & Migration**:
  - Tạo migration Alembic `e7a31c9d0f53_static_drying_beds_and_drum_source.py`:
    * Tạo bảng `static_drying_beds` (quản lý sàn tĩnh theo cơ sở, số sàn, tên sàn, sức chứa, trạng thái hoạt động).
    * Tạo bảng `static_bed_batches` (quản lý mẻ trên sàn: mã mẻ, tình trạng ráo nước `drained`/`wet`, tình trạng nguyên liệu `fresh`/`spoiled`, tỷ lệ úng ước tính `estimated_spoiled_percent`, trạng thái `on_bed`/`discharged`, tình trạng ra sàn `even`/`uneven`, ghi chú ra sàn, tổng thời gian trên sàn).
    * Tạo bảng `static_bed_stirrings` (quản lý từng lượt đảo cà: giờ bắt đầu, kết thúc, thời lượng phút, người đảo, ghi chú).
    * Bổ sung cột vào `drum_runs`: `source_type` (`indoor`/`outdoor`), `source_bed_id`, `source_bed_number`, `source_bed_batch_id`.
    * Khởi tạo sẵn các sàn sấy mẫu (Sàn 1, Sàn 2, Sàn 3, Sàn 4) cho cơ sở hiện có, đảm bảo không hardcode số sàn trong logic nghiệp vụ.
  - Áp dụng migration thành công vào PostgreSQL database container (`alembic upgrade head`).
- **Backend & Nghiệp vụ (FastAPI + SQLAlchemy)**:
  - Cập nhật models và schemas trong `backend/app/modules/drum_processing/`:
    * Thêm schema `SourceBedBatchInfo`, `StaticDryingBedOut`, `StaticDryingBedCreate`, `StaticBedBatchCreate`, `StaticBedStirringCreate`, `StaticBedBatchDischarge`, `StaticBedBatchDetailOut`.
    * Cập nhật `DrumRunCreate`, `DrumRunDetailOut`, `DrumRunItemOut` hỗ trợ thông tin nguồn sàn tĩnh.
  - Thêm các endpoint router cho sàn sấy tĩnh:
    * `GET /api/drum-processing/static-beds`: Lấy danh sách sàn sấy theo cơ sở được phân quyền.
    * `POST /api/drum-processing/static-beds`: Thêm sàn sấy mới.
    * `GET /api/drum-processing/static-bed-batches`: Lấy danh sách mẻ sàn (lọc theo trạng thái `on_bed` hoặc `discharged`, số sàn, tình trạng ra sàn).
    * `POST /api/drum-processing/static-bed-batches`: Ghi nhận mẻ cà vào sàn (lưu tình trạng ráo nước Ráo/Ướt, nguyên liệu Tươi/Úng, tỷ lệ úng 0-100%).
    * `GET /api/drum-processing/static-bed-batches/{id}`: Chi tiết mẻ sàn kèm danh sách lượt đảo.
    * `POST /api/drum-processing/static-bed-batches/{id}/stirrings`: Ghi nhận lượt đảo cà thực tế.
    * `POST /api/drum-processing/static-bed-batches/{id}/discharge`: Ra sàn với đánh giá bắt buộc "Ráo đều" (`even`) hoặc "Chưa ráo đều" (`uneven`), tự động tính thời gian trên sàn.
  - Xác thực và liên kết mẻ trống (`POST /api/drum-processing/runs`):
    * Khi chọn `indoor` (Sàn tĩnh xưởng trong): Bắt buộc chọn số sàn đang hoạt động; cho phép liên kết mẻ đã ra sàn thuộc đúng sàn đó và đã hoàn tất trước/đúng lúc nạp trống; nếu chưa có bản ghi mẻ sàn vẫn cho nạp với số sàn đã chọn.
    * Khi chọn `outdoor` (Sàn tĩnh xưởng ngoài): Chỉ lưu `source_type='outdoor'`, không yêu cầu số sàn hay bản ghi mẻ sàn.
    * Một mẻ sàn có thể chia cho nhiều trống; liên kết với một trống không làm mẻ sàn biến mất khỏi danh sách chọn của các trống khác.
    * Mẻ trống cũ không có nguồn hiển thị "Chưa ghi nhận nguồn".
    * Báo cáo QC (`GET /qc-report`) bổ sung bộ lọc theo nguồn (`source_type`), số sàn (`source_bed_number`) và tình trạng ráo đều (`discharge_drain_status`).
- **Frontend & Giao diện người dùng**:
  - Bổ sung thanh tab chính điều hướng trên `/drums`: **Trống sấy cà** và **Trông sàn sấy tĩnh**.
  - Hộp thoại "Nạp mẻ cà vào [mã trống]":
    * Thêm trường "Nguồn cà vào trống" với 2 lựa chọn trực quan: **Sàn tĩnh xưởng trong** và **Sàn tĩnh xưởng ngoài**.
    * Khi chọn xưởng trong: Hiển thị bộ chọn sàn tĩnh từ dữ liệu động cấu hình, kèm danh sách các mẻ đã ra sàn để liên kết hoặc tùy chọn "Chưa có bản ghi mẻ sàn".
    * Khi chọn xưởng ngoài: Ẩn trường chọn sàn, lưu nguồn gọn gàng.
  - Giao diện "Trông sàn sấy tĩnh":
    * Grid các thẻ sàn sấy hiển thị trực quan trạng thái sàn (Rảnh / Đang trên sàn), thời gian nằm sàn, số lượt đảo đã thực hiện, tình trạng ráo nước và nguyên liệu (tươi/úng, % úng).
    * Các nút thao tác nhanh: Đưa cà vào sàn, Ghi lượt đảo, Đưa cà ra sàn, Thêm sàn mới.
    * Bảng lịch sử các mẻ đã ra sàn với thanh tìm kiếm và bộ lọc nhanh (Tất cả, Ráo đều, Chưa ráo đều, Cà úng).
  - Chi tiết mẻ trống và lịch sử:
    * Thẻ thông tin nguồn cà vào trống hiển thị đầy đủ tình trạng cà vào sàn (Ráo/Ướt, Tươi/Úng, % úng ước tính) và kết quả ra sàn (Ráo đều/Chưa ráo đều, thời gian nằm sàn) lấy từ bản ghi nguồn mà thợ không cần nhập lại.
    * Nâng cấp báo cáo QC với bộ lọc nguồn và badge đối chiếu tình trạng úng/ráo đều.

### Kiểm tra & Nghiệm thu
- **Kiểm tra Unit/Integration backend**:
  - Chạy `python3 scripts/test-d02.py`: **86/86 tests** passed (100%), bao gồm bộ test mới `test_static_drying_beds_and_drum_source_acceptance_criteria`.
- **Kiểm tra Frontend Build**:
  - Chạy `npm --prefix frontend run build`: TypeScript `tsc -b` và Vite build hoàn tất thành công 0 lỗi.
- **Nghiệm thu toàn diện trên môi trường live container (`localhost:8001`, `localhost:5174`)**:
  - Tài khoản `trong.ca` đăng nhập thành công qua cơ chế cookie session + CSRF token, mở được tính năng "Trông sàn sấy tĩnh" trong phạm vi cơ sở DEMO.
  - Tiêu chí 2: Tạo mẻ vào Sàn 2 với "Ướt", "Úng", 20% úng; ghi nhận lượt đảo; hoàn tất ra sàn với "Ráo đều". Bản ghi lịch sử và chi tiết lưu trữ chính xác 20% úng và "Ráo đều" (thời gian nằm sàn: 720 phút).
  - Tiêu chí 3: Nạp mẻ vào TRONG-01, chọn "Sàn tĩnh xưởng trong" -> bắt buộc chọn sàn. Chọn Sàn 2 và liên kết mẻ vừa ra sàn -> chi tiết mẻ trống hiển thị chính xác dữ liệu nguồn, tình trạng 20% úng và kết quả Ráo đều.
  - Tiêu chí 4: Nạp mẻ vào TRONG-02 với "Sàn tĩnh xưởng ngoài" -> không yêu cầu số sàn. Tải lại trang/gọi API chi tiết mẻ trống vẫn hiển thị đúng nguồn `outdoor`.
- Docker containers `nhu-tung-demo-db-1`, `nhu-tung-demo-api-1`, `nhu-tung-demo-web-1` đều hoạt động ổn định ở trạng thái `healthy`.

## 19/11/2026 — Dọn dẹp thiết bị & Bổ sung chức năng Xóa trống sấy

- Đã xóa sạch 3 trống sấy cũ tại XƯỞNG HOÀI ĐỨC (`TRONG-01`, `TRONG-02`, `TRONG-TEST-02`) cùng các mẻ sấy/nhật ký liên quan trong cơ sở dữ liệu theo yêu cầu người dùng để chuẩn bị tạo 3 trống mới.
- Bổ sung endpoint backend `DELETE /api/drum-processing/drums/{drum_id}`: Chỉ tài khoản Manager/Admin có quyền xóa trống thuộc phạm vi cơ sở, tự động dọn dẹp các mẻ sấy và dữ liệu liên quan.
- Bổ sung nút **"🗑️ Xóa trống này"** trong hộp thoại cấu hình thiết bị (`editDrumModal`) trên frontend kèm cảnh báo xác nhận `window.confirm`, giúp quản lý có thể chủ động xóa trống trực tiếp từ giao diện sau này.
- Bổ sung endpoint backend `DELETE /api/drum-processing/static-bed-batches/{batch_id}` và nút **"🗑️ Xóa mẻ sàn này"** trong hộp thoại chi tiết mẻ sàn, cho phép Quản lý xóa mẻ sàn và toàn bộ nhật ký đảo liên quan khi cần dọn dẹp.
- Đã xóa sạch toàn bộ lịch sử các mẻ ra sàn của hệ thống sàn sấy tĩnh theo yêu cầu người dùng (`DELETE FROM static_bed_batches WHERE status = 'discharged'`).
- Tạm ẩn 2 khối báo cáo "Báo cáo QC theo cơ sở & Đối chiếu nguồn sấy tĩnh" và "Đối chiếu các mẻ cùng lô" trên giao diện trang `/drums` để tinh giản màn hình làm việc, giúp giao diện tập trung trực tiếp vào các chỉ số vận hành và các thẻ trống sấy. Mã nguồn các component được bảo lưu nguyên vẹn để kích hoạt lại khi có nhu cầu.
- Kiểm tra & Nghiệm thu: `python3 scripts/test-d02.py` đạt 86/86 tests (100%), `npm --prefix frontend run build` thành công 0 lỗi. Containers `web`, `api`, `db` hoạt động bình thường.

## 19/11/2026 — Mở rộng không gian giao diện & Bổ sung đánh giá khô vỏ khi ra sàn tĩnh

- **Alembic Migration (`e7a31c9d0f54_static_bed_dry_status.py`)**:
  - Bổ sung trường `dry_status` (`sa.String(32)`, nullable=True) vào bảng `static_bed_batches` để lưu trữ tình trạng khô vỏ / quá nhiệt của mẻ cà sau giai đoạn làm ráo trên sàn tĩnh.
  - Áp dụng thành công vào cơ sở dữ liệu live PostgreSQL (`alembic upgrade head`).
- **Nâng cấp Backend Domain Sàn sấy tĩnh**:
  - `StaticBedBatchDischarge` schema bổ sung trường `dry_status: Literal["not_dry", "dry"] | None`.
  - Cập nhật router endpoint `POST /static-bed-batches/{batch_id}/discharge` lưu trữ đánh giá khô hạt.
  - Đồng bộ `SourceBedBatchInfo` để truyền tình trạng khô hạt sang chi tiết mẻ trống sấy khi liên kết nguồn.
- **Nâng cấp Giao diện Frontend (`DrumProcessingPage.tsx` & CSS)**:
  - Mở rộng kích thước toàn bộ các hộp thoại thao tác: `.dp-modal` mở rộng từ 580px lên 640px, `.dp-modal-lg` mở rộng từ 780px lên 820px, khoảng đệm thoải mái 24px/28px, loại bỏ cảm giác chật chội.
  - Thiết kế lại hộp thoại **"Chi tiết mẻ sàn"**:
    * Sử dụng hệ thống thẻ thông số dạng lưới `.dp-specs-card` với 5 chỉ số trực quan: Trạng thái mẻ, Tình trạng ráo vào sàn, Tình trạng nguyên liệu (Tươi/Úng, % úng), Kết quả ráo nước (Ráo đều/Chưa ráo đều), và Tình trạng khô hạt (Không bị khô / Bị khô).
    * Hộp thời gian thực tế, thời lượng nằm sàn và bảng nhật ký các lượt đảo thoáng mắt, dễ đọc.
  - Bổ sung bộ chọn trong hộp thoại **"Đưa cà ra sàn"**:
    * Mục **"Tình trạng cà có bị khô không? (Bắt buộc)"** với 2 nút chọn nhanh: `[✅ Không bị khô (Vỏ mềm, ráo nước đạt chuẩn)]` và `[⚠️ Bị khô (Cà bị khô vỏ / quá nhiệt trên sàn)]`.
    * Kèm chú thích nghiệp vụ rõ ràng: Sàn tĩnh chỉ làm ráo nước bề mặt, cần xác nhận xem cà có bị khô quắt/quá nhiệt trước khi nạp vào trống sấy hay không.
  - Hiển thị huy hiệu tình trạng khô hạt tại bảng Lịch sử ra sàn và trong Thẻ thông tin nguồn cà của mẻ trống sấy.
- **Kiểm tra & Nghiệm thu**:
  - Chạy `python3 scripts/test-d02.py`: **86/86 tests passed** (100%).
  - Chạy `npm --prefix frontend run build`: 0 lỗi TypeScript / Vite.
  - Các container `nhu-tung-demo-api-1`, `nhu-tung-demo-web-1`, `nhu-tung-demo-db-1` hoạt động ổn định ở trạng thái `healthy`.

## 19/11/2026 — Tạm thời tinh giản & ẩn chức năng đo nhiệt định kỳ theo chu kỳ

- **Trang danh sách trống sấy (`/drums` - Tab "Trống sấy cà")**:
  - Thay thế 2 thẻ KPI cảnh báo vi phạm chu kỳ (`Tuân thủ giờ chu kỳ: 0%` và `Lượt đo trễ hạn: X lần`) cùng thẻ thanh tra bằng các thẻ thiết thực phục vụ vận hành:
    * **Trống đang sấy**: Thống kê số trống đang sấy / tổng số trống của xưởng.
    * **Trống sẵn sàng**: Thống kê số trống rảnh sẵn sàng nạp mẻ cà mới.
    * **Sàn sấy tĩnh xưởng**: Thống kê số lượng sàn và số sàn đang có mẻ làm ráo.
    * **Trạng thái thiết bị**: Báo hiệu thiết bị sẵn sàng vận hành ổn định.
  - Cập nhật thẻ trống đang hoạt động: Thay dòng chữ nhắc nhở chu kỳ đo bằng trạng thái sấy buồng thực tế; đổi nút hành động chính từ `Chi tiết & Đo` thành **`Chi tiết mẻ sấy`** với icon trực quan.
- **Hộp thoại "Nạp mẻ cà vào trống"**:
  - Tạm ẩn trường chọn `Chu kỳ kiểm tra (phút)` (chuyển sang giá trị mặc định gửi ngầm 30 phút), giúp người vận hành không phải bận tâm về chu kỳ đo khi nạp mẻ.
- **Màn hình "Chi tiết mẻ sấy"**:
  - Tạm ẩn nút `Ghi nhật ký chu kỳ` và nút `Thanh tra ngẫu nhiên`. Giữ lại đầy đủ các nút nghiệp vụ thiết yếu: `Tắt nhiệt & Bắt đầu ủ`, `Xả trống / Ra trống`, `Thông tin trống`, `Chiến lược`.
  - Tinh giản 4 thẻ KPI trong mẻ: Hiển thị Nhiệt độ ban đầu, Khối lượng nạp (kg), Thời gian vào trống, và Độ ẩm ra trống / Kết quả thành phẩm.
  - Tạm ẩn bảng trống "Nhật ký chu kỳ trong trống" khi mẻ chưa ghi nhận lượt đo chu kỳ nào; tự động kích hoạt hiển thị bảng tra cứu nếu đã có dữ liệu lịch sử.
- **Bảo lưu hạ tầng backend**:
  - Giữ nguyên toàn bộ schema, database models và API endpoints liên quan đến nhật ký chu kỳ (`/runs/{run_id}/logs`) để sẵn sàng kích hoạt lại bất kỳ lúc nào khi xưởng triển khai quy trình đo nhiệt định kỳ.




