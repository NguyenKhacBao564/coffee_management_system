# D05m6 — Giao diện theo dõi xe, tín hiệu cân và bằng chứng

Ngày triển khai: 11/10/2026

## Phạm vi đã làm

- Điều hướng vận hành lấy từ `frontend/src/navigation-config.ts`: Tổng quan,
  Lượt xe và Tín hiệu cân. Các route/module D02 và nghiệp vụ cũ vẫn còn nguyên,
  nhưng không xuất hiện trong menu hoặc trang Tổng quan. Backend tiếp tục kiểm
  tra role và facility; ẩn menu không cấp thêm quyền.
- Trang Lượt xe dùng API hiện có, bổ sung bộ lọc thời gian, cơ sở, biển số và
  cần xem lại. Biển dự đoán được gắn nhãn đề xuất; chỉ xác nhận của nhân viên
  mới được trình bày là biển đã xác nhận. Link `/pilot` cũ chuyển sang Lượt xe.
- Chi tiết lượt đặt biển/trạng thái/thời gian lên đầu, hiển thị tối đa một ảnh
  toàn cảnh, crop xe và crop biển đại diện; ảnh khác và metadata/audit được thu
  gọn. Ảnh giữ tỷ lệ, mở được ảnh gốc qua endpoint riêng tư. Luồng xác nhận/sửa
  vẫn dùng version check, CSRF, audit và kiểm tra facility sẵn có.
- Tổng quan dùng summary theo camera visit và hiển thị trạng thái camera riêng
  với heartbeat PC cân/reader. Nó không truy vấn số liệu nghiệp vụ D02. Khi
  heartbeat mới nhưng reader trống, giao diện báo hai trạng thái riêng.
- Tín hiệu cân vẫn là mẫu thô. Trong chi tiết lượt xe, chỉ tìm tín hiệu theo
  khoảng thời gian quan sát; giao diện nêu rõ chưa xác nhận thuộc xe. Hiển thị
  thời điểm quan sát và thời điểm server nhận khi có dữ liệu nhận muộn. Trang
  Theo dõi cân gọi mẫu mới nhất là dữ liệu lịch sử khi nguồn đang trống.
- Danh sách và summary được giới hạn theo cơ sở và phân trang; polling không
  chồng request và dừng khi tab ẩn. UI không bật preview RTSP hoặc thêm tải xử
  lý camera.

## Kiểm tra đã chạy

- `npm run build` trong `frontend`: thành công (TypeScript + Vite).
- `python scripts/test-d05m.py`: **17 passed, 0 failed** trên database test tạm.
  Bổ sung kiểm tra filter biển/trạng thái và summary theo facility; test xác
  nhận phạm vi facility. Database test tạm được dọn sau lượt chạy, DB ứng dụng
  không reset.
- `git diff --check`: đạt.
- Đã build/deploy lại riêng API và web bằng `docker compose --env-file .env -f
  compose.local.yml up -d --build --no-deps api web`; API health và web trả 200.
  PostgreSQL volume không reset; worker camera không bị restart.
- Dùng session Manager hợp lệ trên trình duyệt: menu chỉ có ba mục vận hành;
  trang Lượt xe hiển thị 5 lượt, bộ lọc và chi tiết hoạt động. Mỗi chi tiết có
  3 ảnh đại diện và 6 ảnh khác trong “Xem thêm bằng chứng”; phần kỹ thuật/audit
  đang thu gọn. Trạng thái hiện tại: camera-185 “Chưa kiểm tra gần đây” vì
  health decode gần nhất là 14:12:51; PC `WIN-TEST-01` “Đang liên lạc”, reader
  “Nguồn trống”. Đây là số liệu thực đọc từ DB lúc kiểm tra, không phải fixture.

## Giới hạn còn lại

- Không có dữ liệu nghiệp vụ nhập/xuất được cấp trong task này. Camera visit
  không phải chuyến hàng, lượt cân đã chốt hay giao dịch.
- Không có quan hệ xác nhận camera_visit ↔ scale_signal. Mẫu cùng thời gian chỉ
  giúp đối chiếu; người dùng không nên coi đó là cân của xe.
- “Chưa xác định biển” là trạng thái cần nhân viên kiểm tra. Không có nhãn
  ground truth thì không thể kết luận độ chính xác detector/OCR.
- Thao tác xác nhận không được gửi trên dữ liệu đang chạy trong lần kiểm tra;
  quyền, version conflict và audit giữ nguyên trong backend, còn thao tác thật
  có thể được người dùng thực hiện ở trang Lượt xe.
- Ảnh chụp giao diện đã xem trực tiếp qua tab Chrome đã đăng nhập; ảnh không
  được lưu thành file bàn giao trong lượt này.
