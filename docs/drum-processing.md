# Chức năng Trông trống cà

Tài liệu này mô tả hành vi hiện có của module quản lý trống sấy trong ứng dụng. Nội dung được đối chiếu với backend `backend/app/modules/drum_processing`, giao diện `frontend/src/DrumProcessingPage.tsx`, cấu hình điều hướng và các ghi nhận triển khai trong `docs/progress.md`.

Các con số/ngưỡng nêu dưới đây là hành vi đang được cài trong mã nguồn. Không xem chúng là quy trình sản xuất hay tiêu chuẩn chất lượng đã được người dùng nghiệp vụ phê duyệt nếu chưa xác nhận riêng.

## Mục đích và phạm vi

Chức năng hỗ trợ theo dõi thiết bị trống sấy cà tại từng cơ sở và ghi nhận vòng đời một mẻ: nạp cà, đo độ ẩm/nhiệt độ định kỳ, tắt nhiệt và ủ, xả trống, đánh giá chất lượng, thanh tra đối chiếu, xem lịch sử và thống kê. Dữ liệu được gắn với cơ sở hoạt động của phiên đăng nhập.

Đây là ghi nhận vận hành bằng người dùng. Module hiện không điều khiển máy sấy, không đọc cảm biến/PLC tự động, không quản lý tồn kho hoặc giao dịch hàng, và không thay thế quy trình chất lượng đã được phê duyệt.

## Vai trò và quyền truy cập

Người dùng cần đăng nhập. API yêu cầu CSRF token cho thao tác tạo/cập nhật dữ liệu và giới hạn dữ liệu theo cơ sở đang chọn hoặc `facility_id` được phép truy cập.

| Vai trò | Hành vi giao diện | Quyền API trong module |
| --- | --- | --- |
| `drum_operator` | Mặc định chỉ vào trang Trông trống cà | Được ghi nhận/chạy mẻ, nhật ký chu kỳ, tắt nhiệt và xả trống |
| `manager` | Có trang Trông trống cà và các trang quản lý | Được tạo/sửa cấu hình trống, ghi nhận mẻ và thanh tra |
| `admin` | Điều hướng chính không hiển thị trang vận hành trống | API cho phép tạo/sửa trống, ghi nhận mẻ và thanh tra; phạm vi cơ sở có thể là mọi cơ sở hoạt động |
| `staff` | Điều hướng chính hiện không liệt kê trang Trông trống cà | API hiện vẫn cho phép thao tác mẻ và nhật ký như operator; không được tạo/sửa trống hoặc thanh tra |

Quyền phía API là nguồn kiểm soát thực tế; ẩn mục điều hướng không đồng nghĩa endpoint bị khóa. `_operator` hiện cho phép `drum_operator`, `staff`, `manager`, `admin`; `_inspector` chỉ cho phép `manager`, `admin`.

## Màn hình và thao tác chính

### Bảng điều khiển

Trang chính hiển thị các trống đang hoạt động ở cơ sở, trạng thái rảnh/đang chạy, mã mẻ hiện tại và các KPI tổng hợp. Có thể mở hồ sơ từng trống, mở chi tiết mẻ đang chạy, nạp mẻ mới hoặc mở chiến lược/lịch sử.

KPI hiện có gồm tổng mẻ, mẻ đang chạy/hoàn tất, số lần đo, số lần đo đúng hạn/trễ và tỷ lệ đúng hạn, cùng tổng lượt thanh tra đạt/cảnh báo/không đạt. Các KPI được tính theo toàn bộ dữ liệu của cơ sở; API hiện không lọc theo khoảng ngày.

### Hồ sơ thiết bị trống

Mỗi trống có mã, tên, cơ sở, sức chứa tùy chọn, trạng thái hoạt động và đặc tính vận hành:

- Chế độ đo: `center_only` (giữa), `two_ends` (đầu và đuôi), hoặc `three_points` (đầu/giữa/đuôi trong schema dữ liệu).
- Cờ lệch độ ẩm hai đầu và lỗi cánh đảo cà.
- Ghi chú kỹ thuật/kinh nghiệm riêng, tối đa 500 ký tự.

Mã trống được chuẩn hóa chữ hoa và duy nhất trong cùng cơ sở. Giao diện cho phép quản lý/admin tạo trống và sửa tên, sức chứa, chế độ đo, cờ lỗi và ghi chú. API danh sách chỉ trả trống `is_active = true`; module hiện chưa có thao tác giao diện/API riêng để ngừng hoạt động hoặc chuyển thiết bị sang bảo trì.

### Vòng đời mẻ sấy

1. **Nạp mẻ:** chọn trống rảnh, nhập mã mẻ, loại cà, khối lượng tùy chọn, nhiệt độ ban đầu tùy chọn, thời điểm vào trống và chu kỳ đo. Giao diện chọn cà quả, cà lụa, cà trộn (các ô tỷ lệ trong UI tự bù để tổng bằng 100%) hoặc loại khác. Chu kỳ mặc định 30 phút; API nhận 5–240 phút. Mỗi trống chỉ được có một mẻ `in_progress` tại thời điểm kiểm tra.
2. **Đo định kỳ:** nhập thời điểm đo, nhiệt độ luồng hơi, độ ẩm và ghi chú. Dữ liệu ghi lại người thao tác, thời điểm máy chủ nhận, số thứ tự, thời điểm dự kiến và trạng thái tuân thủ.
3. **Tắt nhiệt/ủ:** ghi thời điểm tắt nhiệt, thời điểm tắt quay tùy chọn và độ ẩm tại lúc tắt nhiệt. Nếu bỏ trống độ ẩm, backend lấy giá trị độ ẩm của nhật ký cuối cùng (nếu có). Mẻ vẫn `in_progress`; giao diện thể hiện giai đoạn ủ.
4. **Xả trống:** ghi thời điểm ra trống và độ ẩm thành phẩm; có thể nhập số liệu đầu/đuôi theo biểu mẫu hiện tại, đánh giá chất lượng `ca_dep`, `dat_chuan`, `ca_xau`, nhận xét chất lượng và ghi chú xả. Khi xả thành công mẻ thành `completed` và trống trở lại rảnh.
5. **Thanh tra:** quản lý/admin ghi nhận mẫu độc lập và thời điểm thanh tra. Backend so sánh mẫu với nhật ký định kỳ gần thời điểm đó, lưu chênh lệch và kết quả đánh giá.

Trang chi tiết mẻ hiển thị thông tin đầu vào, trạng thái/giai đoạn, tiến trình, nhật ký chu kỳ và lịch sử thanh tra. Hồ sơ trống hiển thị lịch sử các mẻ, lọc trạng thái/chất lượng và tìm theo mã mẻ, loại cà hoặc người phụ trách.

## Quy tắc tính toán hiện có

### Độ ẩm

- Các trường độ ẩm được xác thực trong khoảng 0–100%, độ chính xác tối đa hai chữ số thập phân.
- Schema API giới hạn mã mẻ 2–64 ký tự sau khi loại khoảng trắng và chuyển chữ hoa; tên loại cà tối đa 120 ký tự; khối lượng không âm với tối đa 2 chữ số thập phân; nhiệt độ 0–350°C với tối đa 2 chữ số thập phân; tỷ lệ phối trộn mỗi trường 0–100%. API chưa kiểm tra tổng hai tỷ lệ bằng 100% (đó là hành vi của form UI). API cũng chưa áp giới hạn sức chứa trống lên khối lượng nạp.
- Với phép đo hai đầu, giao diện tính trung bình `(đầu + đuôi) / 2`, làm tròn 2 chữ số, rồi gửi làm độ ẩm hiệu dụng. Backend cũng tính chênh lệch tuyệt đối hai đầu để lưu `moisture_diff_ends`.
- Khi xả, nếu có cả độ ẩm đầu và đuôi mà không gửi giá trị trung bình, backend tính trung bình hai đầu.
- Với thanh tra, nếu có cả đầu và đuôi nhưng không có giá trị tổng hợp, backend lấy trung bình; nếu không, có thể dùng điểm giữa.
- Backend schema hỗ trợ các trường đầu/giữa/đuôi. Tuy nhiên giao diện nhập nhật ký hiện phân nhánh thành giữa hoặc hai đầu; biểu mẫu thanh tra hiện gửi một giá trị độ ẩm và nhiệt độ, chưa nhập các điểm đo riêng.

### Lịch chu kỳ và tuân thủ

Với nhật ký thứ `n`, giờ dự kiến được tính là `entry_time + n × cycle_minutes`, trong đó nhật ký đầu tiên là `n = 1`. Độ trễ là `recorded_at - scheduled_time` tính bằng giây.

- `late`: thời điểm ghi nhận trễ hơn giờ dự kiến trên 15 phút.
- Nếu chưa bị phân loại `late`, `anomalous`: giờ đo do người dùng nhập cách giờ máy chủ ghi nhận trên 2 giờ.
- Các trường hợp còn lại là `on_time`.

Tỷ lệ tuân thủ hiện tính `on_time / tổng số nhật ký`. Nhật ký `anomalous` nằm trong mẫu số nhưng không nằm trong số đúng hạn. KPI không suy ra nhật ký bị bỏ lỡ từ các chu kỳ chưa có bản ghi.

### Đối chiếu thanh tra

Backend tìm nhật ký có `measured_at` gần thời điểm thanh tra nhất. Chênh lệch được tính theo `mẫu thanh tra - số đo nhật ký gần nhất` cho độ ẩm và nhiệt độ.

- `failed` nếu chênh lệch tuyệt đối độ ẩm > 2.0 điểm phần trăm hoặc nhiệt độ > 5.0°C.
- `warning` nếu chưa `failed` nhưng độ ẩm > 1.0 điểm phần trăm hoặc nhiệt độ > 3.0°C.
- Còn lại là `passed`.
- Nếu chưa có nhật ký để so sánh, chênh lệch để trống và backend hiện vẫn gán `passed`.

Các ngưỡng trên là hằng số trong triển khai hiện tại, không phải kết luận về sai số thiết bị đo hay tiêu chuẩn kiểm định.

### Phân tích chiến lược

API phân tích lấy tối đa 100 mẻ đã hoàn tất gần nhất trên từng trống. Tỷ lệ “Cà đẹp” dùng số mẻ `ca_dep` chia tổng mẻ hoàn tất trong tập này. Để tính gợi ý, ưu tiên mẻ `ca_dep`; nếu chưa có mẻ loại đó, dùng mẻ `ca_dep` và `dat_chuan`.

Các gợi ý hiện là trung bình số học đơn giản từ dữ liệu mẻ được chọn: nhiệt độ nhật ký, độ ẩm lúc tắt nhiệt, thời gian ủ, độ ẩm cuối; độ giảm ẩm dự kiến là độ ẩm lúc tắt nhiệt trừ độ ẩm cuối. Kết quả phụ thuộc dữ liệu ghi nhận và không phải mô hình dự báo đã được kiểm chứng. Nếu thiếu dữ liệu, API trả lời tóm tắt thông tin; giao diện có một số giá trị minh họa mặc định khi trường gợi ý trống.

## API hiện có

Base path: `/api/drum-processing`. Các API cần đăng nhập và giới hạn cơ sở.

| Method | Path | Mục đích |
| --- | --- | --- |
| `GET` | `/drums` | Danh sách trống đang hoạt động trong cơ sở |
| `POST` | `/drums` | Tạo trống (manager/admin) |
| `GET` | `/drums/{drum_id}` | Chi tiết thiết bị và mẻ đang chạy |
| `PATCH` | `/drums/{drum_id}` | Cập nhật cấu hình trống (manager/admin) |
| `GET` | `/runs` | Danh sách tối đa 100 mẻ mới nhất; lọc tùy chọn theo `status`, `drum_id`, `facility_id` |
| `POST` | `/runs` | Nạp mẻ mới (operator/staff/manager/admin) |
| `GET` | `/runs/{run_id}` | Chi tiết mẻ, nhật ký, thanh tra và tóm tắt tuân thủ |
| `POST` | `/runs/{run_id}/logs` | Thêm nhật ký chu kỳ |
| `POST` | `/runs/{run_id}/stop-heat` | Ghi nhận tắt nhiệt và bắt đầu giai đoạn ủ |
| `POST` | `/runs/{run_id}/discharge` | Xả trống, ghi độ ẩm cuối và hoàn tất mẻ |
| `POST` | `/runs/{run_id}/inspections` | Ghi thanh tra (manager/admin) |
| `GET` | `/drums/{drum_id}/analytics` | KPI chất lượng, chiến lược và lịch sử mẻ của trống |
| `GET` | `/audit/kpi` | KPI vận hành toàn cơ sở |

Mutation dùng CSRF header `X-CSRF-Token`. Các trường thời gian trong payload là datetime; frontend chuyển giờ nhập theo `Asia/Ho_Chi_Minh` sang UTC để gửi và định dạng giờ Việt Nam khi hiển thị.

## Mô hình dữ liệu

| Bảng | Nội dung chính |
| --- | --- |
| `drums` | Cấu hình thiết bị, cơ sở, trạng thái và đặc tính kỹ thuật |
| `drum_runs` | Mẻ sấy, loại/khối lượng cà, mốc vào/tắt nhiệt/xả, người phụ trách, độ ẩm cuối và đánh giá chất lượng |
| `drum_periodic_logs` | Các lần đo theo mẻ, vị trí đo, nhiệt độ, giờ đo/ghi nhận, tuân thủ chu kỳ |
| `drum_inspections` | Mẫu thanh tra, người thanh tra, chênh lệch với nhật ký gần nhất và kết quả đánh giá |

Khối lượng, nhiệt độ và độ ẩm lưu bằng kiểu `Numeric`/`Decimal`; mốc thời gian lưu datetime có timezone. Các bản ghi nhật ký và thanh tra gắn vào mẻ; xóa mẻ ở tầng dữ liệu sẽ xóa các bản ghi con theo cascade. Mẻ tham chiếu trống theo `RESTRICT`.

## Trạng thái và giới hạn hiện tại

- Trạng thái trống trong schema: `idle`, `running`, `maintenance`; trạng thái đang chạy trong danh sách cũng được suy ra từ mẻ `in_progress`. Giao diện hiện chủ yếu thao tác rảnh/đang chạy, chưa có quy trình bảo trì.
- Trạng thái mẻ trong schema: `in_progress`, `completed`, `cancelled`; giao diện/API hiện không có thao tác hủy mẻ.
- Không có API sửa/xóa nhật ký hoặc thanh tra, cũng chưa có luồng sửa/xóa mẻ đã hoàn tất.
- Chưa có constraint duy nhất cho `batch_code` trong cơ sở; tính duy nhất của mã mẻ không được API hiện tại đảm bảo.
- Schema cho phép `three_points`, nhưng giao diện cấu hình chỉ cho chọn giữa `center_only` và `two_ends`; luồng tổng hợp độ ẩm ba điểm chưa được triển khai đầy đủ.
- Màn hình thanh tra hiện ghi một giá trị độ ẩm; schema có thêm các trường đầu/giữa/đuôi nhưng chưa được UI sử dụng.
- Ghi nhận mẻ và phân loại chất lượng không tự tạo giao dịch hàng, tồn kho hoặc dữ liệu D02.

## Câu hỏi nghiệp vụ còn cần xác nhận

Các mục sau chưa nên được coi là quy tắc đã chốt chỉ dựa trên mã nguồn:

- Định nghĩa chính thức của “Cà đẹp”, “Đạt chuẩn”, “Cà xấu”; ai là người có quyền chốt và có cần quy trình duyệt hay không.
- Chu kỳ lấy mẫu theo loại cà/trạng thái máy; cách xử lý mẫu bị lỡ, ghi bù hoặc số đo bất thường.
- Ngưỡng chênh lệch thanh tra, sai số thiết bị và cách đánh giá khi không có nhật ký đối chiếu.
- Có cho phép sửa/hủy mẻ, sửa số liệu đã lưu hoặc chuyển thiết bị sang bảo trì hay không; ai được làm và cần audit gì.
- Cách xử lý đồng thời khi hai người thao tác nạp cùng một trống; quy tắc duy nhất của mã mẻ.
- Có cần đo ba điểm thực tế không, và nếu có thì cách tính giá trị đại diện/chênh lệch.
- Ý nghĩa chuẩn của nhiệt độ “ban đầu”, nhiệt độ luồng hơi, độ ẩm theo vị trí, thời điểm tắt quay và thời gian ủ.
- Cách diễn giải gợi ý chiến lược và điều kiện đủ mẫu trước khi hiển thị như khuyến nghị sản xuất.

## Tệp mã nguồn liên quan

- Backend: `backend/app/modules/drum_processing/models.py`, `schemas.py`, `router.py`.
- Frontend: `frontend/src/DrumProcessingPage.tsx`, `DrumProcessingPage.css`.
- Phân quyền/điều hướng: `frontend/src/navigation-config.ts`, `backend/app/modules/accounts`.
- Lịch sử triển khai: các mục Trông trống cà trong `docs/progress.md`.

## Bổ sung ghi nhận đầu vào, sự cố và QC (19/11/2026)

> Phần này cập nhật mô tả phía trên: module đã có các API và biểu mẫu bổ sung dưới đây. Các mẻ cũ giữ dữ liệu mới ở trạng thái chưa ghi nhận.

Trong chi tiết mẻ, người vận hành có thể bổ sung mã truy xuất lô gốc, đánh dấu lô chưa rõ hoặc mẻ trộn, giờ xay và giờ bắt đầu sấy lần đầu, tuyến sấy, tình trạng giờ ước tính và tiếp xúc nước. API tính phút chờ từ hai mốc; sấy tĩnh không được bắt đầu sau giờ vào trống. Mã lô là chuỗi truy xuất do người nhập cung cấp; thống nhất mã giữa các xưởng là trách nhiệm vận hành. Hiện chưa có danh mục lô hay màn hình đối chiếu liên xưởng.

Có thể ghi nhiều sự cố cánh đảo, dừng quay, gián đoạn nhiệt hoặc khác, với mốc tùy chọn và người ghi. Nhật ký nhiệt lưu vị trí đo tùy chọn; giá trị cũ không có vị trí. Nếu chỉ nhập một đầu trống, độ ẩm đại diện là số đo tại đầu đó và chênh lệch hai đầu để trống.

Sau xả, chi tiết mẻ hiển thị Chờ QC cho tới khi quản lý hoặc admin nhập một kết quả QC chính. Nhập mẫu theo gram hoặc số hạt, điểm và thời điểm lấy mẫu, tổng lỗi, đen đặc và cháy tùy chọn. Backend kiểm tra cỡ mẫu, giới hạn lượng lỗi, số nguyên với mẫu đếm hạt và tính tỷ lệ theo toàn mẫu. Kết quả QC hiện không có chức năng sửa; muốn sửa cần thiết kế lịch sử sửa và quyền riêng.

Báo cáo QC cơ bản tại trang trống lọc theo cơ sở đang chọn, ngày xả, ID trống và phương pháp. Nhóm cùng đơn vị và điểm lấy mẫu, cộng lượng lỗi chia tổng cỡ mẫu; từng lỗi thành phần chỉ tính những mẫu đã chấm thành phần ấy. Mẻ chờ QC hiển thị riêng. Báo cáo chưa có đối chiếu cùng lô giữa các xưởng, phân tích thời gian chờ/sự cố hoặc biểu đồ dải nhiệt; chưa thực hiện các tiêu chí đối chiếu liên xưởng. Khi lọc phương pháp, các mẻ chưa QC vẫn hiển thị là chờ, vì chưa biết phương pháp của chúng.

API mới: `GET`/`PUT /runs/{id}/source`, `GET`/`POST /runs/{id}/incidents`, `GET`/`POST /runs/{id}/qc`, và `GET /reports/qc`. Các API áp dụng kiểm tra cơ sở; sửa đầu vào và ghi sự cố dùng quyền vận hành, ghi QC chỉ dành cho manager/admin. Các lần ghi nhiệt ban đầu và định kỳ có vị trí đo tùy chọn.

### Cập nhật đối chiếu lô

Trang trống có mục đối chiếu theo mã lô gốc; API `/reports/lot-comparison` chỉ tìm mẻ có `traceability = known` trong các cơ sở hoạt động mà tài khoản được cấp quyền. Mỗi dòng hiển thị thời gian chờ, tiếp xúc nước, QC, dải nhiệt quan sát theo vị trí, chênh ẩm và sự cố; có thể mở mẻ để xem nhật ký. Chưa có bộ lọc khoảng thời gian chờ, tính chênh lệch tự động hay biểu đồ nhiệt/sự cố. Dải nhiệt chỉ dựa trên các số đo đã ghi; so sánh cần cùng phương pháp và điểm lấy mẫu.
