# Demo quản lý chuyến xe và cân hàng · Như Tùng

Nền tảng nội bộ cho Công ty TNHH Như Tùng. Phạm vi hiện tại gồm **D00 — nền
tảng dự án**, **D01 — đăng nhập/tài khoản/phân quyền**, **D02 — lịch hàng,
chuyến xe, cân thủ công và giao dịch nhập/xuất**, cùng **S01 — nhận tín hiệu cân
qua agent token**. D02 chỉ lưu nguồn cân `manual`; S01 lưu riêng quan sát UI
`canxe2015_ui`. Chưa có camera, OCR, client Windows hoặc đọc cân trực tiếp từ
thiết bị.

## Điều kiện môi trường

- macOS Intel hoặc Apple Silicon; Docker Desktop đang chạy và `docker compose`
  hoạt động.
- Git, Node.js 20.19.4+ và npm 10+ nếu kiểm tra frontend ngoài Docker.
- Python 3.12–3.14 nếu chạy API ngoài Docker; dependency được khóa trong
  `backend/uv.lock`.
- Các cổng mặc định là web `5174`, API `8001`, PostgreSQL `5433` trên máy host.
  Có thể đổi trong `.env`; PostgreSQL trong container luôn dùng cổng 5432.

## Chạy local

```bash
cp .env.example .env
# Đổi POSTGRES_PASSWORD thành mật khẩu chỉ dùng local.
# DATABASE_URL phải dùng cùng user/mật khẩu với PostgreSQL.
./scripts/dev.sh up
```

Lệnh `up` build image, khởi động PostgreSQL, chờ healthcheck, chạy migration
rồi mới bật API và web. Mở [http://localhost:5174](http://localhost:5174). API có tài liệu tại
[http://localhost:8001/docs](http://localhost:8001/docs).

Sau lần chạy đầu tiên, tạo tài khoản quản trị viên bằng lệnh tương tác sau.
Mật khẩu được nhập ẩn trong terminal, không truyền trên dòng lệnh:

```bash
docker compose --env-file .env -f compose.local.yml exec api \
  python -m app.modules.accounts.bootstrap_admin
```

Lệnh chỉ tạo admin đầu tiên; chạy lại không ghi đè tài khoản hiện có. Admin
đăng nhập tại trang web và có thể tạo manager/staff, đặt vai trò và gán cơ sở.
Đổi mật khẩu hoặc vô hiệu hóa tài khoản sẽ kết thúc các session cũ.

```bash
./scripts/dev.sh status       # trạng thái và health container
./scripts/dev.sh logs         # theo dõi log tất cả dịch vụ
./scripts/dev.sh logs api     # log riêng API
./scripts/dev.sh migrate      # áp dụng migration mới
./scripts/dev.sh down         # dừng container, giữ nguyên dữ liệu volume
```

`down` không xóa dữ liệu. Không dùng `docker compose down -v` trừ khi chủ động
xóa toàn bộ database local. Volume `postgres_data` lưu dữ liệu PostgreSQL bền
vững giữa các lần dừng và khởi động.

## Chạy kiểm tra ngoài Docker

Frontend:

```bash
cd frontend
npm ci
npm run build              # gồm kiểm tra TypeScript (tsc -b)
npm run dev -- --port 5174
```

Backend (cần một PostgreSQL local riêng cho demo):

```bash
cd backend
uv sync --frozen --dev
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/nhutung'
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Khi Compose local đang chạy, có thể chạy regression D01+D02+S01 trên database
tạm riêng; script tạo và xóa đúng database kiểm thử, không đụng database ứng
dụng hoặc volume:

```bash
./scripts/test-d02.py
```

Nếu Compose đang chạy, dừng container bằng `./scripts/dev.sh down` trước khi
dùng các cổng host 5174/8001 cho lệnh chạy trực tiếp. Volume PostgreSQL được giữ.

Kiểm tra `GET /api/health/live` cho trạng thái tiến trình và
`GET /api/health/ready` cho readiness tổng quát, không trả chi tiết DB cho
người dùng. Admin xem trạng thái API/database trong giao diện quản trị. Readiness trả HTTP 503
khi database mất kết nối. Chỉ lưu `.env` cục bộ; không đưa mật khẩu, URL có
credential, ảnh, model weights hoặc dữ liệu công ty vào Git.

## Tài liệu

- [Yêu cầu và câu hỏi nghiệp vụ](docs/requirements.md)
- [Kiến trúc](docs/architecture.md)
- [Chức năng Trông trống cà](docs/drum-processing.md)
- [Hợp đồng Scale ingestion v1](docs/scale-ingestion-v1.md)
- [Danh sách task và nghiệm thu](docs/tasks.md)
- [Tiến độ D00–D02 và S00–S04](docs/progress.md)
