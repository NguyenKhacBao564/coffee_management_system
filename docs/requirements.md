# Yêu cầu demo quản lý chuyến xe và cân hàng

## Mục tiêu

Hỗ trợ ghi nhận chuyến xe, lượt cân và giao dịch hàng cho Công ty TNHH Như
Tùng. Demo chạy trên MacBook trước; triển khai cloud là giai đoạn riêng.

## Vai trò dự kiến

- **Admin:** tài khoản, phân quyền, theo dõi hoạt động hệ thống.
- **Quản lý:** lịch nhập/xuất, lịch sử chuyến xe, xác nhận giao dịch và audit.
- **Nhân viên:** thao tác chuyến xe, xác nhận biển số/số cân, nhập hàng và chất
  lượng.

### D01 đã xác nhận cho tài khoản và phạm vi cơ sở

- Tài khoản có vai trò `admin`, `manager` hoặc `staff`. Admin quản lý tài khoản
  và cơ sở được phép chọn; D01 không tự cấp quyền nghiệp vụ chuyến xe/cân cho
  các task chưa triển khai.
- Manager và staff phải được gán ít nhất một cơ sở đang hoạt động. API chỉ trả
  về và cho chọn các cơ sở đang hoạt động đã gán. Admin xem được mọi cơ sở đang
  hoạt động.
- Vai trò, trạng thái tài khoản và phạm vi cơ sở được đọc từ database ở từng
  request; thay đổi có hiệu lực ở request kế tiếp. Vô hiệu hóa kết thúc phiên;
  kích hoạt lại không khôi phục phiên cũ.
- Admin không thể tự hạ quyền hoặc vô hiệu hóa khi là quản trị viên cuối cùng
  đang hoạt động. Tạo quản trị viên bổ sung sau bootstrap là thao tác quản trị
  riêng.
- Phiên dùng cookie opaque HttpOnly, SameSite=Lax, thời hạn cấu hình được; token
  phiên chỉ lưu dạng SHA-256 trong database. Cookie đặt Secure khi môi trường
  không phải local/development/test. Mọi thao tác thay đổi dữ liệu cần CSRF
  synchronizer token gửi trong header.
- Mật khẩu dùng Argon2id. API không trả hash mật khẩu hoặc token phiên. Audit
  quản trị chỉ lưu sự kiện và thay đổi không chứa mật khẩu hay session secret.
- Bootstrap quản trị viên đầu tiên chạy tương tác, đọc mật khẩu ẩn, không nhận
  mật khẩu qua tham số dòng lệnh và không ghi đè hoặc tạo thêm admin khi đã có.
- Đăng nhập sai dùng thông báo chung và giới hạn 5 lần trong cửa sổ 15 phút theo
  tên đăng nhập đã chuẩn hóa. Dịch vụ trả thông báo 429 chung trong thời gian
  khóa.

## Phạm vi demo dự kiến

- Một chuyến xe có nhiều lượt lên cân; có thể cân lại hoặc giao nhận nhiều loại
  hàng.
- Ghi nhận thủ công, tín hiệu cân mô phỏng, ảnh bằng chứng, audit, Excel và
  backup/restore.
- OCR biển số/hình ảnh ngoại tuyến; có bước xác nhận thủ công khi độ tin cậy
  thấp hoặc dữ liệu chưa đủ.
- Tích hợp đầu cân thật phụ thuộc khảo sát model, giao thức và phần mềm thiết
  bị; chưa được xác nhận.
- Quy trình chất lượng và các ngưỡng phần trăm chưa được xác nhận; không tự đặt
  validation nghiệp vụ.

## Quy tắc đã được yêu cầu giữ trong thiết kế

1. Phân biệt chuyến xe, lượt lên cân, kết quả cân và giao dịch hàng; một chuyến
   có nhiều lượt cân. Cân lại không tự tạo giao dịch hàng.
2. Chênh lệch cân chỉ là đề xuất nhập/xuất; nhân viên xác nhận trước khi ghi
   giao dịch.
3. Biển số chưa nhận dạng dùng `null` và trạng thái riêng, không tạo xe chung
   tên “unknown”. Lưu riêng dữ liệu gốc, dự đoán AI và kết quả đã xác nhận.
4. Tracking ID chỉ theo dõi ảnh, không làm khóa chính chuyến xe. Không thấy
   người trong ảnh không chứng minh cabin trống.
5. Vùng cân là polygon cấu hình theo camera. Số cân lấy từ thiết bị/phần mềm
   cân; demo cho nhập tay hoặc mô phỏng. Sự kiện thiết bị có ID để chống tạo
   trùng khi gửi lại.
6. Thời gian lưu UTC, hiển thị `Asia/Ho_Chi_Minh`. Trọng lượng và tỷ lệ dùng
   kiểu chính xác, không dùng float làm giá trị nghiệp vụ chính thức.
7. Ảnh lưu ngoài database; database chỉ lưu metadata và tham chiếu.
8. Chất lượng chưa chốt; kết nối đầu cân thật chờ khảo sát thiết bị.

## Quyết định demo đã áp dụng trong D02

- Ma trận quyền demo: staff nhập lịch/chuyến/cân/giao dịch nháp và gửi duyệt;
  manager có thêm xác nhận, trả lại và hủy có lý do; admin chỉ xem nghiệp vụ.
  Backend kiểm tra cả role lẫn facility, không dựa vào lựa chọn giao diện.
- Xe được chuẩn hóa biển số để tìm kiếm nhưng vẫn dùng ID nội bộ; biển số
  chuẩn hóa chỉ duy nhất trong một cơ sở. Không tự ghép bản ghi trùng; chuyến
  chưa nhận dạng giữ `vehicle_id = null` và chưa thể hoàn tất.
- Lịch có thể có dòng hàng dự kiến nhưng không sinh giao dịch. Chuyến có thể
  phát sinh không lịch, có nhiều lần cân và giao dịch.
- Mỗi lần cân có thứ tự/thời gian riêng và các kết quả sửa bất biến. Ghi cân
  manual được chọn rõ ràng sau lời xác nhận của người thao tác về vị trí xe và
  người đã xuống. Không tự lấy lần mới nhất/lớn nhất.
- Dùng cân nhập `trước - sau`, cân xuất `sau - trước`; khối lượng phải dương.
  Chỉ khoảng cân không chồng lấn đang chờ/đã xác nhận mới được gửi duyệt; hai
  giao dịch liền kề có thể dùng chung mốc.
- Giao dịch xác nhận không sửa trực tiếp. Quản lý hủy có lý do; giao dịch thay
  thế tham chiếu bản đã hủy. Số cân được sửa bằng bản kết quả mới và lý do; các
  nháp đã tham chiếu số cũ được đánh dấu cần rà soát.
- Tổng quan chỉ cộng giao dịch đã xác nhận trong ngày Việt Nam; số liệu ghi rõ
  “lượng đã nhập/đã xuất”, không diễn giải thành tồn kho.
- Camera, OCR, ảnh bằng chứng, chất lượng, Excel, kế toán và thiết bị cân thật
  vẫn ngoài phạm vi D02.

## Định hướng camera/OCR điều chỉnh ngày 07/10/2026

- Khảo sát nguồn ảnh/vị trí chụp biển và đánh giá theo lượt xe trước khi
  fine-tune tiếp. Mục tiêu thu thập ban đầu khoảng 50–100 lượt khác nhau là
  đề xuất coverage, chưa là ngưỡng nghiệm thu hoặc bảo đảm độ chính xác.
- OCR hỗ trợ nhân viên bằng raw/candidates và gợi ý top-k từ xe/lịch dự kiến
  của cơ sở. Tìm khớp gần đúng chỉ xếp hạng, không sửa raw OCR hoặc tự gán
  xe/chuyến/cân. Có thể nhập biển ngoài danh sách hoặc giữ chưa nhận dạng.
- Kết quả cần đo theo lượt: biển đúng trong top-3, coverage danh sách, mức
  chấp nhận/độ đúng sau xác nhận và thời gian thao tác so với nhập tay. Ngưỡng
  đạt và thiết kế UI/API sẽ được chốt khi task tương ứng được giao.
- Luồng người xác nhận không phụ thuộc exact OCR 100%. Ưu tiên S03b/D06/D07;
  quy tắc D02 và ranh giới signal/dự đoán/xác nhận tiếp tục áp dụng.
- Kế hoạch chi tiết: `docs/camera-vehicle-evaluation-plan.md`. D05g/D05h mới
  là đề xuất, chưa có triển khai top-k hoặc thay đổi schema/API.

## Câu hỏi còn mở

- Quy tắc xác định chuyến xe và biển số trùng/thiếu; một chuyến kết thúc khi
  nào, ai được sửa hoặc hủy?
- Loại giao dịch nhập/xuất, danh mục hàng, cách xác định khối lượng tịnh, dung
  sai và đơn vị đo được dùng là gì?
- Các cơ sở/kho/bàn cân, phạm vi quyền và trường hợp nhân viên làm thay cơ sở
  khác?
- Quy trình chất lượng, mẫu biểu, ngưỡng và người có quyền xác nhận?
- Thiết bị cân/camera cụ thể, giao thức kết nối và điều kiện khảo sát tại hiện
  trường?
- Các cột, công thức, mẫu Excel và báo cáo đang sử dụng?
- Loại ảnh/chứng từ, chính sách lưu trữ, backup và thời hạn xóa?
- Điều kiện nghiệm thu, dữ liệu demo được phép sử dụng và môi trường triển khai
  cloud về sau?

D00 dựng nền tảng; D01 bổ sung schema tài khoản, cơ sở, phiên và audit quản trị.
Các quy tắc nghiệp vụ chuyến xe, cân, giao dịch hàng và chất lượng ở trên vẫn
chờ task tương ứng và không được suy diễn thành workflow D01.
