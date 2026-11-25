# Kế hoạch camera, đánh giá theo lượt xe và gợi ý có người xác nhận

Điều chỉnh ngày 07/10/2026 theo phản hồi người dùng. Đây là kế hoạch triển
khai tiếp theo, không phải xác nhận các tính năng đã có hoặc ngưỡng nghiệm
thu đã chốt. D05f dừng ở kết quả pilot hiện tại; fine-tune tiếp chỉ được xem
xét sau khi đánh giá chỉ ra model là nút thắt.

## Ưu tiên của dự án

Ưu tiên luồng cân thật **S03b → D06 → D07**. OCR hỗ trợ nhân viên; đọc sai
hoặc unknown phải vẫn có đường nhập/xác nhận thủ công. D05 không là điều kiện
buộc phải đạt exact OCR 100% trước khi nối các phần lõi.

- S03b: xác minh nguồn CANXE2015 thật, đọc `txtkq`, retry/outbox và đo tài
  nguyên client khi nguồn đã hoạt động. S03a nguồn giả không thay bằng chứng này.
- D06: camera/RTSP, polygon, quan sát xe/người và trạng thái bàn cân. Khảo sát
  nguồn ảnh và thu clip có thể tiến hành song song S03b. Không thấy người không
  chứng minh cabin trống; track_id không phải danh tính nghiệp vụ.
- D07: đề xuất ghép camera/signal có xác nhận, thời gian và chống trùng. Phải
  kiểm chứng đồng hồ/độ lệch/độ trễ; video offline chưa có mốc giờ thật chỉ
  dùng timestamp media. Signal không tự tạo/sửa cân hay giao dịch D02.

Các task giữ tiêu chí hiện có. Công cụ đánh giá/top-k bên dưới là phần việc
đề xuất chưa triển khai, sẽ được giao riêng theo quy ước repository.

## 1. Khảo sát nguồn ảnh và hoàn tất review

Dữ liệu đã kiểm lại: 47 bbox biển reviewed trong D05e có chiều cao native
9–29 px, median 18 px. Phóng crop hay thay detector không khôi phục chi tiết
chữ bị thiếu trong nguồn ảnh. Số 10/22 D05f đến từ một capture và bbox xe thủ
công; chưa đủ kết luận hiệu quả nhận dạng khi vận hành.

Khảo sát trước khi chọn mua hoặc đổi thiết bị:

- Camera/luồng hiện có: nguồn chính/phụ, native resolution, codec/bitrate,
  FPS và độ sắc nét khi xe di chuyển; crop từ ảnh gốc trước resize model.
- Thử vị trí chụp tại làn vào cân: khoảng cách, zoom, chiều cao/góc gần thẳng,
  biển trước/sau và điểm xe đi chậm. Camera thấp hơn chỉ là phương án khảo sát,
  cần kiểm tra xe/người/đồ vật che khuất và việc lắp đặt thực tế.
- Thử shutter/exposure/ánh sáng, khả năng IR ban đêm và phản xạ biển; đánh giá
  bằng clip ngày/đêm có xe thật, không mặc định IR hoặc shutter nhanh tự đủ.
- So sánh luồng hiện tại với vị trí/luồng chuyên chụp biển nếu có điều kiện.
  Ghi kích thước biển/ký tự native, tỷ lệ lượt có frame đọc được thủ công,
  blur/cháy sáng/góc và điều kiện thất bại. Chưa ấn định thông số phần cứng
  hoặc ngưỡng pixel khi chưa đo hiện trường.

Hoàn tất 1 frame và 22 crop pending bằng công cụ D05e/D05f hiện có song song.
Không dùng prediction làm nhãn, không coi ảnh có biển thiếu bbox là negative.
Các mẫu khóa/thanh container cần được xác nhận để làm hard negatives.

## 2. Bộ đánh giá theo lượt xe (D05g đề xuất)

Mục tiêu thu thập ban đầu **khoảng 50–100 lượt khác nhau** do người dùng đề
xuất, nhiều xe/biển, ngày/đêm và điều kiện ánh sáng. Đây là mục tiêu coverage,
không phải bảo đảm thống kê hoặc ngưỡng nghiệm thu. Báo số xe duy nhất, capture,
lượt lặp và phân bố điều kiện thực tế; không coi nhiều frame là nhiều mẫu độc lập.

Mỗi lượt có `pass_id` gán thủ công, camera/capture, media start/end, biển
đối chiếu hoặc unknown, nguồn xác nhận và khả năng đọc ảnh. Nếu ground truth
không đọc được từ video, chỉ dùng xác nhận độc lập được phép; không đoán từ
OCR/lịch xe. Phân biệt nhãn biển thật với mức ảnh có đủ thông tin để đọc.

Giữ cùng xe/capture và ảnh gần trùng cùng split. Validation riêng để chọn
ngưỡng/chính sách; test chỉ chạy sau khi khóa kế hoạch. Nếu chưa đủ nhóm thì
báo giới hạn và đánh giá mô tả, không dùng test để chọn cấu hình.

Tái dùng CLI/ROI/tracking/frame selection/OCR/export D05a:

1. So sánh **bbox xe tự động** với **crop ROI cố định ở độ phân giải gốc**,
   trên cùng lượt. ROI chọn/cấu hình trên validation; giữ mọi lượt thất bại
   của vehicle detector/track trong mẫu số. Bbox xe thủ công chỉ chẩn đoán.
2. Chọn vài frame sắc nét và khác thời điểm trong track, giới hạn số crop/lần
   OCR, tránh đếm nhiều crop cùng frame thành nhiều bằng chứng độc lập.
3. Nhận dạng Latin/số với bố cục dòng đúng; lưu raw, normalized và evidence.
4. Tái dùng consensus. Code hiện tại bỏ phiếu **toàn chuỗi trùng**, chưa bỏ
   phiếu từng ký tự. Có thể thử alignment/vote ký tự như phương án bổ sung
   trên validation, giữ đọc gốc và bất đồng; không ép chuỗi khớp biển kỳ vọng.
5. Báo một kết quả/các ứng viên/unknown cho mỗi lượt. Track bị đứt/gộp hai xe
   phải được đối chiếu với pass_id; không dùng track_id làm khóa chuyến xe.

Báo riêng các lỗi: không thấy xe/track, ROI/crop mất biển, detector biển miss/
nhận nhầm, thiếu dòng/ký tự, OCR và consensus sai. IoU/mAP/crop coverage vẫn
giúp chẩn đoán, không thay kết quả theo lượt hoặc mức hỗ trợ người vận hành.

## 3. Gợi ý top-k có người xác nhận (D05h đề xuất)

Xếp hạng biển từ dữ liệu xe và lịch dự kiến **của cơ sở được phép**, giới hạn
ngày giờ Việt Nam. Chụp snapshot danh sách tồn tại **tại thời điểm xe đến**;
không thêm biển sau khi biết ground truth để nâng metric. Lịch không đầy đủ
hoặc xe ngoài danh sách phải vẫn nhập được thủ công.

- Tìm khớp gần đúng là bước xếp hạng ứng viên riêng. Giữ raw OCR nguyên vẹn,
  không viết lại prediction thành biển trong danh sách hoặc gọi similarity
  là xác suất OCR. Không trộn confidence khác model thành một thang chung.
- Hiển thị tối đa 3 ứng viên cùng ảnh bằng chứng và phân biệt raw OCR/gợi ý
  từ danh sách. Cho chọn ứng viên, sửa/nhập biển khác hoặc giữ chưa nhận dạng.
  Luôn có bước người xác nhận; không tự gán xe/chuyến/lượt cân.
- Kiểm tra quyền facility phía server, kể cả truy cập trực tiếp. Dùng cơ chế
  phiên người dùng hiện có; scale-agent token không cấp quyền đọc danh sách xe.
- Việc ghi lựa chọn cần người dùng thực hiện qua service/quyền/audit hiện có.
  Tách biển được xác nhận với dự đoán; gợi ý không làm thay đổi D02 hoặc quy
  tắc chọn số cân, chốt cân, giao dịch.

## 4. Chỉ tiêu theo nghiệp vụ

Các ngưỡng phần trăm/thời gian được thống nhất sau pilot vận hành, chưa mã
hóa thành validation/workflow. Luôn công bố tử số, mẫu số, unknown và coverage.

| Chỉ tiêu | Cách tính/đo |
| --- | --- |
| Biển đúng trong top-3 theo lượt | Số lượt có biển xác nhận nằm trong top-3 / mọi lượt đủ ground truth; không chỉ những lượt OCR thành công |
| Coverage của danh sách xe/lịch | Số lượt có biển thật trong snapshot danh sách / mọi lượt có ground truth; báo top-3 riêng trên phần có coverage và trên toàn bộ |
| Gợi ý được nhân viên chấp nhận | Số lượt chọn một gợi ý / lượt được hiển thị gợi ý; kèm tỷ lệ có gợi ý trên mọi lượt |
| Độ đúng sau chấp nhận | Đối chiếu lựa chọn với ground truth độc lập; chấp nhận không tự chứng minh gợi ý đúng |
| Thời gian thao tác | Median/p95 từ lúc hiển thị đến xác nhận, so với luồng nhập tay trên điều kiện tương đương; không tính chờ xe/cân là thời gian nhập biển |
| Sửa/unknown/không gợi ý | Số và tỷ lệ trên mọi lượt, phân theo xe/capture/ngày đêm và nguyên nhân |

Nếu tổng hợp frame chọn/vote + danh sách nhỏ đã giúp vận hành, chưa cần
fine-tune tiếp. Nếu lỗi chủ yếu nguồn ảnh thì sửa vị trí/cấu hình; nếu crop
thủ công rõ đọc tốt nhưng crop tự động kém thì sửa crop; nếu crop rõ vẫn OCR
sai thì mới xem xét recognizer/dữ liệu OCR đa dạng. Augmentation nhẹ phù hợp
góc/ánh sáng/blur/compression chỉ bổ sung cho ảnh thật có nhãn chắc, không tạo
độ đa dạng xe/biển từ vài chuỗi lặp hoặc khôi phục thông tin đã mất.

## Trạng thái và vận hành GPU

D05f model/baseline/bằng chứng đã lưu trên Mac. Lần kiểm tra gần nhất GPU rảnh,
không có job train; có thể Stop instance trong khi khảo sát/thu thập/review.
Stop không được ghi là đã thực hiện nếu chưa có xác nhận trạng thái. Không
cần thuê hoặc train tiếp cho các bước chuẩn bị trên Mac ở kế hoạch này.
