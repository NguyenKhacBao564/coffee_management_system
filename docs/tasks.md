# Task và tiêu chí nghiệm thu

| ID | Task | Trạng thái | Tiêu chí hoàn tất |
| --- | --- | --- | --- |
| D00 | Nền tảng dự án | Hoàn thành | Tài liệu, Compose, DB/migration, health endpoints, giao diện trạng thái; build, outage/recovery, volume và responsive đã kiểm tra. |
| D01 | Đăng nhập, tài khoản, phân quyền, phạm vi cơ sở | Hoàn thành | Session phía server, CSRF, quản lý tài khoản/audit, quyền role và ranh giới cơ sở được kiểm tra bằng API và trình duyệt. |
| D02 | Lịch hàng, chuyến xe, nhiều lượt cân thủ công, giao dịch hàng | Hoàn thành | Dữ liệu tách biệt; phân quyền facility; cân manual và cân lại; tính Decimal; xác nhận quản lý có audit; chống trùng/chồng lấn; UI và test API riêng DB. |
| D03 | Ảnh bằng chứng và audit | Chưa bắt đầu | Metadata/tham chiếu ảnh, quyền truy cập, lịch sử thao tác có thể truy vết. |
| D04 | Bộ mô phỏng tín hiệu đầu cân | Chưa bắt đầu | Sự kiện cân mô phỏng có ID; gửi lại không tạo dữ liệu trùng. |
| D05 | Detect biển số/OCR ngoại tuyến và đánh giá | Đang thực hiện — D05a hoàn tất pipeline, chưa nghiệm thu nhận dạng camera công ty | Đánh giá bằng dữ liệu được phép; tách dự đoán khỏi xác nhận thủ công. |
| D05a | Pipeline xe/biển số offline và bằng chứng kiểm tra bước đầu | Hoàn thành bước đầu | CLI riêng; ROI theo camera, tracking/phiên chịu dropout, plate/OCR theo budget, raw/candidates/unknown và ảnh/HTML; chạy video local thật + fixture, đo CPU/RAM; chưa có độ chính xác camera công ty hoặc kết nối DB/RTSP. |
| D05b | Chẩn đoán detector/OCR và chuẩn bị dữ liệu gán nhãn | Công cụ và chuẩn bị hoàn tất — chờ nhãn thủ công | 40 frame gốc từ hai video; manifest/bbox/layout/readability và giao diện gán nhãn; benchmark CRNN/Paddle CPU có phiên bản/giấy phép, ngân sách OCR theo giai đoạn và kiểm tra trùng/chia tập. Chưa tính accuracy camera hoặc training; xem `offline-vision-d05b.md`. |
| D05c | Chuẩn bị fine-tune detector biển số lần đầu | Đã audit và đóng gói tập Roboflow v1 có điều kiện; chờ xác nhận nhãn và camera | COCO 864 ảnh đã audit; 761 bbox dương qua sàng lọc cấu trúc, giữ 32 bbox đáng ngờ + 71 ảnh trống để người dùng xem; camera 40 frame chưa có nhãn xác nhận. Gói YOLOX-Nano, manifest/hash, split nguồn, license và CPU preflight/resume/epoch hữu hạn đạt. Chưa train dài/CUDA/đánh giá chất lượng; xem `plate-detector-d05c.md`. |
| D05d | Fine-tune detector biển số lần đầu trên GPU thuê | Hoàn thành — bounded pilot, chưa nghiệm thu chất lượng camera | CUDA preflight/resume, train có giới hạn, best theo validation, test chỉ sau chọn, ONNX parity và thử hai video offline; nhãn external chưa xác minh, chưa có ground truth camera, không báo accuracy xưởng. Artifacts/bằng chứng trong `plate-detector-d05d.md`. |
| D05e | Review crop detector và benchmark OCR sau D05d | Đang thực hiện — 60/61 frame được xác nhận đủ bbox; còn chờ review 22 crop detector | Bằng chứng D05e giữ nguyên. Người dùng xác nhận biển v002 là 49C02655; sau sửa 7 transcript và lỗi split dòng, benchmark chẩn đoán PP-OCRv6 tiny tối đa 8/14 crop detector; hai chuỗi biển lặp. Không báo accuracy xưởng. Xem `offline-vision-d05e.md` và phần cập nhật D05f. |
| D05f | Fine-tune detector lần hai với camera đã xác nhận | Đã chạy pilot có giới hạn — chưa nghiệm thu chất lượng xưởng | Dataset/hash, split theo capture, cap camera, CPU/CUDA preflight/resume đạt; train 1.000 step, best public validation epoch3/step840; model và ONNX tải/hash đạt. Camera held-out crop xe thủ công match 7→10/22, FP 4→5; PP-OCRv6 tiny 0/2. ONNX detection parity 104/104 đạt, toàn tensor mở rộng còn lệch một anchor nền; còn 1 frame/22 crop pending. Xem `plate-detector-d05f.md`. |
| D05g | Đánh giá camera/OCR theo lượt xe | Đề xuất — chưa triển khai | Khảo sát nguồn ảnh, tập nhiều lượt/xe/ngày đêm, crop xe tự động/ROI native, chọn frame và consensus; split theo xe/capture, kết quả theo lượt và nguyên nhân thất bại. 50–100 lượt là mục tiêu thu thập, chưa là ngưỡng nghiệm thu. Xem `camera-vehicle-evaluation-plan.md`. |
| D05h | Gợi ý top-k biển số có người xác nhận | Đề xuất — chưa triển khai | Ứng viên từ xe/lịch của cơ sở tại thời điểm xe đến, quyền server, raw OCR tách khỏi tìm gần đúng, tối đa 3 gợi ý/nhập tay/unknown; đo top-3, coverage, chấp nhận/độ đúng và thời gian thao tác. Không tự gán xe/chuyến/cân; cần giao triển khai riêng. |
| D05i | Chẩn đoán/cải thiện OCR trên crop camera rõ, chạy local | Phase 3 hoàn tất chẩn đoán — dừng; Phase 4 chưa làm | Phase 2 khóa nguyên vẹn, quan sát D05f 5/7 partial ghi riêng. FastPlate whole/original chính, English mobile đối chứng; format beam đúng loại heads, vote ký tự/consensus theo track, unknown khi yếu. Full trước/sau FastPlate 26/26→26/26, English 22/26→24/26 +2 unknown; hai nhóm track chưa gain, không accuracy xưởng. 132 test đạt. Xem `offline-vision-d05i.md`. |
| D05j | Dataset đa dạng và chuẩn bị augmentation OCR | Review chính 419 CarTGMT + nhãn CSV đã import; Phase D chuẩn bị, chờ review/conditions | Tái dùng D05b/D05f: gợi ý nguồn riêng, bbox proposal, phân trang/shortcuts/autosave/JSON; motorcycle riêng, 3 camera frame pending. Fixed OCR CarTGMT FastPlate28/29, English19/29 (29 biển GT khác nhau); màu/che chưa xác nhận. Augmentation train-only/seed/7 contact sheets, native YAML có giới hạn; 149 test đạt. Chưa train/GPU; xem `offline-vision-d05j.md`. |
| D05k | Đa dạng OCR và fine-tune FastPlate bounded | Hoàn tất thử nghiệm; chưa đạt tiêu chí thay runtime | Gold khóa 137 crop, silver150 + synthetic pool1024; GPU hiện có train8epoch/152step/79,27s. CUDA resume và ONNX parity137/137 đạt, tải48file hash khớp. Test camera26/26, Car17/17, motorcycle9/12 trước/sau không đổi; giữ pretrained. Camera chỉ1biển rõ, partial/màu/che còn giới hạn. Gói v4 và báo cáo `offline-vision-d05k.md`. |
| D05m | Pilot Local + API theo lượt xe có người xác nhận | Đang triển khai; D05m1/m2 và nguồn live D05m4 đã đạt; API AI thật và lượt xe/cân thật chưa nghiệm thu | Tái dùng D05f/FastPlate; evidence theo visit, API độc lập, định danh riêng và fallback. Heartbeat Windows/DB/UI đã xác minh. Không thay phạm vi D05g/D05h/D06/D07 hoặc khởi động lại D05l. |
| D05m1 | Hợp đồng, persistence, private evidence và API mock | Hoàn thành; migration additive đã áp dụng tới head trên volume local hiện có | Schema additive cho visit/evidence/prediction/confirmation/audit/AI job/usage/heartbeat; idempotency/conflict; ACK sau commit; quota, private storage, phân quyền D01; mock không gửi ảnh và D02 không đổi. Dự trù/đối soát tiền provider thật chưa nối. |
| D05m2 | Replay → backend → web review | Hoàn thành E2E trong DB/UI tạm; Compose local đã chạy và healthcheck đạt | Tái dùng pipeline D05a với detector D05f và FastPlate pinned; bundle replay idempotent vào DB, xem 7 ảnh riêng tư qua UI D01; prediction/confirmation riêng và signal gần thời gian chỉ tham khảo. Không tính accuracy khi thiếu nhãn. |
| D05m3 | Provider AI thật trên tập phát triển giới hạn | Chưa bật — TrollLLM key trả 401; Gemini `GET /v1beta/models` trả 200 (50 model); chưa gửi ảnh/gọi inference | Key Gemini ở `.env` local mode 0600, Git ignored; nên thu hồi vì đã xuất hiện trong chat. Trước inference cần chọn model vision, xác minh image/structured-output contract, giá và downstream retention; giữ ngân sách 2 USD/ngày, 300 attempt/ngày, tối đa 3 attempt/visit. |
| D05m4 | Camera live và trạng thái agent cân | Đã nghiệm thu phần nguồn chạy liên tục/preview/health/restart; lượt xe thật còn chờ | PyAV/TCP .185 main HEVC 1920×1080/25 fps; Keychain/URI trong bộ nhớ, queue 2, D05f/FastPlate chung pipeline; health 30s, preview D01, snapshot/clip diagnostic riêng. Giám sát 15,29 phút, không có xe vào ROI, không gọi AI. Xem `camera-live-pilot.md`; ROI còn cần xác nhận. |
| D05m4a | Heartbeat agent PC cân v1 | Đã xác minh heartbeat Windows → API → PostgreSQL → UI cho pilot; reader empty được hiển thị riêng | Tái sử dụng POST heartbeat/S01 và một dòng snapshot/agent; chu kỳ client 30s độc lập threshold, UUID + sequence, ACK sau commit, duplicate idempotent, heartbeat cũ không ghi đè. D01 scope; admin telemetry, manager/staff trạng thái cơ sở; mốc 90/180s và API unavailable không suy offline. S02 batch giữ nguyên. Xem `windows-scale-heartbeat-handoff.md`. |
| D05m4b | Rà D02 và camera theo sự kiện cân/thủ công | Đã triển khai và đo trigger/chụp/idle/preview/restart trên .185; cân/xe thật còn chờ | Preview mặc định tắt, RTSP đóng khi idle; mẫu observed mới ≥1.000 kg hoặc thao tác thủ công mở cửa sổ 20s/4 ảnh native, inference/OCR hữu hạn. Không đổi D02; dùng mô hình/worker/outbox hiện có. Xem `camera-event-driven-pilot.md`. |
| D05m4c | Kéo dài tìm biển, chọn ảnh theo chất lượng và dọn ứng viên | Đã triển khai/deploy; kiểm tra chọn ảnh camera đã lưu và timeout live đạt; hiệu quả trên lượt xe tiếp theo chưa nghiệm thu | Thay policy 20s bằng tối đa 120s/1Hz; dừng sớm sau ≥15s khi có 2 crop native đạt tiêu chí cùng phiên rõ liên hệ. Tối đa 8 bộ toàn cảnh/xe/biển; dọn file ứng viên tạm, giữ một toàn cảnh khi detector thất bại. Không tự xác nhận đọc rõ đầu/đuôi hoặc xóa evidence đã lưu. 16 test backend + 39 test camera liên quan đạt. Xem cập nhật D05m4c trong `camera-event-driven-pilot.md`. |
| D05m6 | Thu gọn giao diện theo dõi xe, tín hiệu cân và bằng chứng | Hoàn thành phần UI/API và triển khai local; dữ liệu nghiệp vụ nhập/xuất chưa được cấp | Menu vận hành chỉ Tổng quan, Lượt xe, Tín hiệu cân; D02 giữ nguyên nhưng ẩn tập trung. Lượt xe có lọc ngày/cơ sở/biển/trạng thái, xác nhận riêng gợi ý, ảnh đại diện + thư viện, metadata/audit thu gọn. Tổng quan chỉ đếm camera_visit và trạng thái camera/heartbeat; signal vẫn thô, không ghép/chốt. API kiểm tra phạm vi cơ sở. 17 kiểm thử D05m + frontend build đạt. Xem `vehicle-monitoring-ui.md`. |
| D05m5 | Liên thông cân thật có xe | Chưa thực hiện | Chỉ nghiệm thu khi đọc thành công, so txtkq, signal thật ≥1.000 kg bền vững không mất/trùng sau restart/mạng, đo CPU/RAM và xác nhận không ảnh hưởng CANXE2015. |
| D06a | Khảo sát COCO person cho camera bàn cân | Khảo sát sơ bộ hoàn tất; chưa nghiệm thu runtime/ROI | Hai video .185 đã thử YOLOX-s COCO class person CPU thưa 2s; score chưa hiệu chuẩn, không phải precision/recall. ROI person .185/.172 cần người vận hành xác nhận; .172 chưa có video. Không train/GPU. Xem `scale-monitoring-and-person-prep.md`. |
| D06 | RTSP, vùng cân, detect xe/người và trạng thái bàn cân | Chưa bắt đầu | Polygon theo camera; không suy diễn cabin trống từ việc không thấy người. |
| D07 | Ghép sự kiện camera với cân, xác nhận và chống trùng | Chưa bắt đầu | Tracking ID không làm khóa chuyến; ghép có thể xác nhận và idempotent. |
| D08 | Mẫu chất lượng và Excel | Chưa bắt đầu | Quy trình/ngưỡng đã được xác nhận; mẫu nhập/xuất được nghiệm thu. |
| D09 | Giám sát, backup/restore và nghiệm thu demo | Chưa bắt đầu | Quy trình khôi phục được kiểm tra; nghiệm thu trên phạm vi đã thống nhất. |

D00 không triển khai D02–D09. D01 hoàn tất schema xác thực/tài khoản/cơ sở;
không triển khai nghiệp vụ chuyến xe, cân, OCR, camera, Excel hoặc chất lượng.

## Nhánh S — Scale agent ingestion

| ID | Task | Trạng thái | Tiêu chí hoàn tất |
| --- | --- | --- | --- |
| S00 | Hợp đồng tín hiệu và ranh giới dữ liệu | Phạm vi đã xác lập | Quan sát UI được phân biệt với timestamp/độ ổn định thiết bị; không ghép xe từ biển số payload. |
| S01 | API ingestion, agent token, chống trùng và ACK | Hoàn thành | Batch bền vững, atomic, idempotent trên PostgreSQL; CLI agent; simulator; test tích hợp riêng DB. |
| S02 | Client Windows .NET Framework và durable outbox | Luồng nguồn giả đã nghiệm thu phía Windows | Chỉ đọc control txtkq, ghi outbox bền vững, gửi lại event ID/sequence và tiến checkpoint theo ACK. |
| S03 | Giám sát/tra cứu tín hiệu và chẩn đoán nguồn | Hoàn thành; bổ sung S03c | Trang Tín hiệu cân; API chỉ đọc theo quyền cơ sở; latest/lọc theo observed_at, bảng phân trang độc lập với chuỗi chart bounded; timestamp/summary theo Asia/Ho_Chi_Minh; không chốt lượt cân. 72 kiểm thử DB tạm và frontend build đạt; xem `scale-monitoring-and-person-prep.md`. |
| S03c | Đồ thị signal theo toàn khoảng và KPI quản lý an toàn | Hoàn thành phần UI/API; chưa có entity lượt cân quan sát | Chart tối đa 1.200 mặc định/2.000 điểm, giữ first/last/min/max theo khoảng thời gian; gap 60s xác định trên raw trước giảm mẫu, series riêng từng agent/đoạn. Filter nhanh tự chạy tới hiện tại, custom cố định; zoom/tooltip/nút xem đoạn cuối. Summary theo observed time VN, không SUM weight. Không migration. |
| S03d | Sửa biểu đồ và điều tra cân mới chưa gửi | UI/API đã sửa; sender Windows chưa khôi phục | Bỏ chấm dày, trục tấn/giờ VN, giữ gap raw khi giảm mẫu. Reuse heartbeat để staff/manager thấy paused/pending. 74 test D01/D02/S01/S03 + 18 pilot đạt, browser Manager kiểm tra filter/zoom/tooltip thật. DB seq12982 không tăng; heartbeat4765→4804, pending1309→1483, SIGNAL_SENDER_PAUSED. Prompt Windows: windows-scale-sender-recovery-20261012.md. |
| S03e | Điểm đại diện ở khoảng dài và thao tác zoom | Hoàn thành UI/API, chưa xác nhận lượt cân nghiệp vụ | Tự động tổng quan >3 giờ; một mẫu thật có weight xuất hiện nhiều nhất mỗi đoạn gap60s, nối theo thứ tự cách đều. Raw vẫn có trục giờ/gap thật. Nhấp đúp/kéo/+−/quay lại/đặt lại zoom; bounded và đúng scope. 77 test DB tạm + build + browser Manager đạt. Không tạo lượt cân hoặc sửa raw. |
| S03a | Nghiệm thu nguồn giả Windows → API → PostgreSQL | Hoàn thành — nguồn giả | 06/10/2026: PostgreSQL đối chiếu 9/9 ID đúng một bản ghi, đúng agent, sequence/weight/source và timestamp UTC/microsecond khớp chính xác sau bỏ phần dư, không làm tròn/dùng dung sai; 58 kiểm thử đạt trên DB tạm. Snapshot và bằng chứng client được phân biệt trong `docs/progress.md`. |
| S03b | Đọc CANXE2015 và đo tài nguyên client | Chưa thực hiện | Nghiệm thu nguồn CANXE2015 thực tế và đo tài nguyên; không được suy ra từ nguồn giả S03a. |
| S04 | Nối quy trình xác nhận sử dụng signal | Chưa bắt đầu | Ghép có bước người xác nhận; tín hiệu không tự tạo/cập nhật lượt cân D02. |

Nhánh S độc lập với task D. Simulator nhỏ trong S01 chỉ kiểm tra hợp đồng HTTP
và retry trên dữ liệu test; không phải client Windows hoặc quy trình đọc thiết
bị, và không thay thế task D04 nếu cần bộ mô phỏng nghiệp vụ rộng hơn.

Vận hành heartbeat cập nhật 11/10/2026: đã khôi phục nhận Windows qua Tailscale
sau khi Mac đổi IP. API bind loopback và Serve proxy loopback cố định;
snapshot thật tăng seq2842→2844, reader empty/pending0. Hợp đồng và endpoint
VPN trong `windows-scale-heartbeat-handoff.md`; không đổi S02/agent token/outbox.

S02 được ghi theo bàn giao và nghiệm thu luồng nguồn giả Windows; mã client không
nằm trong repository Mac. S03b còn thiếu số cân thật do `txtkq` trống theo thông
tin người dùng, chưa nghiệm thu nguồn CANXE2015 hoặc đo tài nguyên. S03 dùng mã
task giám sát đã có trong kế hoạch; không triển khai S04 hoặc các task D tiếp theo.

D05a là mã mới cho phần pipeline offline được giao ngày 06/10/2026; D05 giữ
tiêu chí nhận dạng/đánh giá tổng thể và chưa hoàn tất. Cấu hình polygon offline
trong D05a không phải nghiệm thu D06 RTSP/trạng thái bàn cân. S03/D02 không đổi.

D05b là mã mới cho bước chẩn đoán/chuẩn bị dữ liệu được giao riêng. Bộ 40 frame
chưa có nhãn biển xác nhận; không đánh dấu D05 nhận dạng tổng thể hoàn tất.

D05c là mã mới cho chuẩn bị fine-tune. Cập nhật 07/10/2026: người dùng đã cung
cấp COCO đã giải nén trong `data/offline-vision/incoming/`; xem audit và giới
hạn hiện tại trong `plate-detector-d05c.md`. 40 frame camera vẫn chưa có nhãn
xác nhận; preflight không thay thế nghiệm thu nhận dạng D05.

## Ưu tiên điều chỉnh ngày 07/10/2026

Ưu tiên **S03b → D06 → D07** cho luồng cân thật. Khảo sát nguồn ảnh/thu clip
và hoàn tất review D05e có thể làm song song. D05f dừng ở pilot hiện tại;
D05g/D05h là kế hoạch đề xuất, không tự bắt đầu task chưa được giao.
Đánh giá theo lượt xe và mức hỗ trợ nhân viên trước khi quyết định train tiếp.
OCR chính xác 100% không phải điều kiện chặn luồng có xác nhận thủ công.
Chi tiết và cách tính mẫu số: `camera-vehicle-evaluation-plan.md`.
