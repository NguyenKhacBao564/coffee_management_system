# Quy ước dự án Như Tùng

## Phạm vi và cấu trúc

- Làm theo từng task trong `docs/tasks.md`; task sau D00 cần được giao riêng.
- Giữ backend modular monolith: `backend/app/core` chứa hạ tầng chung,
  `backend/app/modules/<domain>` sở hữu logic và dữ liệu của miền đó.
- Frontend gọi API; không kết nối database trực tiếp.
- `edge-agent` là tiến trình riêng cho camera/OCR/đầu cân khi task tương ứng bắt
  đầu; không thêm nó vào API web.
- Trong D00 không tạo schema nghiệp vụ; dùng Alembic cho mọi thay đổi schema.

## Nghiệp vụ và dữ liệu

- Giữ nguyên các quy tắc nền đã ghi trong `docs/requirements.md`; câu hỏi chưa
  xác nhận phải để mở, không tự biến thành validation hoặc quy trình.
- Một chuyến xe có thể có nhiều lượt cân. Phân biệt chuyến xe, lượt cân, kết
  quả cân và giao dịch hàng. Cân lại không tự tạo giao dịch.
- Chênh lệch cân chỉ đề xuất nhập/xuất; nhân viên phải xác nhận trước khi ghi
  nhận giao dịch. Không suy diễn tồn kho từ tổng lượng đã cân.
- Trọng lượng/tỷ lệ dùng kiểu chính xác; thời gian lưu UTC, giao diện hiển thị
  `Asia/Ho_Chi_Minh`. Ảnh nằm ngoài database, chỉ metadata/tham chiếu lưu trong
  database.
- Dữ liệu gốc, dự đoán AI và dữ liệu đã xác nhận phải tách biệt. Sự kiện thiết
  bị có ID để xử lý gửi lại an toàn; tracking ID không phải khóa chuyến xe.

## Bảo mật và vận hành

- Không commit `.env`, mật khẩu, token, URL RTSP có credential, ảnh thật, dữ
  liệu sản xuất hoặc model weights. `.env.example` chỉ chứa giá trị minh họa.
- Log dễ đọc; không ghi secrets, payload nhạy cảm hoặc ảnh.
- Không dừng dịch vụ đang chạy để lấy cổng; đổi host port trong `.env` nếu bị
  chiếm. Không xóa volume trong lệnh dừng thông thường.
- Chỉ tạo/bật hạ tầng cloud sau yêu cầu rõ ràng. Thiết kế phải chạy được trên
  Linux, không phụ thuộc NVIDIA/CUDA ở demo local.

## Migration và kiểm tra

- Thay đổi schema đi qua Alembic revision mới; không sửa migration đã áp dụng ở
  môi trường chia sẻ.
- Trước bàn giao task backend, chạy build frontend/TypeScript nếu frontend đổi,
  chạy migration và kiểm tra health/readiness phù hợp với phạm vi. Ghi rõ lệnh,
  kết quả thực tế và giới hạn môi trường trong `docs/progress.md`.
- Kiểm tra `git diff` và trạng thái Git trước bàn giao; không ghi đè thay đổi
  người dùng đang có.
