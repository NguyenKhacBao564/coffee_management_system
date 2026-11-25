# D05m — Local + API theo lượt xe

Ngày 09/10/2026. **Phạm vi đã được người dùng duyệt để triển khai local.**
Tài liệu này là baseline yêu cầu; trạng thái triển khai và bằng chứng nghiệm thu
được cập nhật tại [`offline-vision-d05m.md`](offline-vision-d05m.md).

Triển khai theo các lát cắt D05m1–D05m5; không coi API mock, replay hay camera
đã lưu là nghiệm thu live/cân thật. Nhật ký triển khai và các điều kiện còn thiếu
được ghi trong `docs/offline-vision-d05m.md`.

## 1. Mục tiêu và phạm vi

Hỗ trợ nhân viên xác nhận biển/nhận diện phương tiện nhanh hơn bằng detector local,
OCR local và API đọc ảnh. Đánh giá trên mỗi lượt xe thực tế, bao gồm lượt khó,
lượt không nhận dạng được và lượt detector bỏ sót.

Một `camera_visit` là một lần phương tiện đi vào rồi rời vùng quan sát bàn cân.
Nó khác chuyến hàng, lượt cân nghiệp vụ và giao dịch. Xe cân lại có thể tạo visit
mới; việc ghép vào cùng chuyến hàng cần người xác nhận trong D07 về sau.

Thử nghiệm có hai phần: chạy lại video offline đã xác minh, sau đó chạy live
song song để nhân viên review. Kết quả thử nghiệm lưu riêng; không tự tạo/sửa
xe, chuyến, lượt cân, signal hay giao dịch D02. Nhân viên tiếp tục thao tác D02
theo quy trình hiện có. S03b/D06/D07 vẫn là các phần việc riêng.

D05m được chia thành D05m1–m5. Giữ D05g (đánh giá theo lượt), D05h (gợi ý theo
lịch), D06 (camera/trạng thái vùng cân), D07 (ghép cân) và D05l đã được giao
trước đó; không khởi động lại training D05l.

## 2. Điểm xuất phát và điều kiện còn thiếu

- D05f detector biển đã có model/ONNX; tái dùng interface detector, tracking,
  chọn frame, OCR và export bằng chứng của D05a–D05k.
- OCR chính: FastPlate CCT-S v2 pretrained, whole/original, pin/hash như D05k.
  Model fine-tuned D05k không cải thiện test đã khóa nên chưa thay runtime.
- Kết quả 26/26 crop readable_full chỉ đại diện một biển số, không phải độ
  chính xác trên 26 xe. Không dùng con số này để dự báo tỷ lệ vận hành.
- Camera chính .185, camera phụ .172; NVR .170 do người dùng xác định là
  DHI-NVR4232-4KS3. Có file mẫu H.265 1080p giải mã được từ trước.
- Lần kiểm tra 09/10: HTTP CGI chưa xác thực thành công (401); chưa đủ bằng
  chứng kết luận mật khẩu sai hay lỗi quyền/client Digest. Phải xác nhận truy
  cập trước khi thử xác thực tiếp. Không dùng thành công từ phiên cũ để chứng
  minh credential/firmware/quyền hiện tại. Secret lưu Keychain, không chép vào doc.
- Model/firmware camera, danh sách kênh NVR, giờ/múi giờ và quyền playback còn
  cần xác minh. Tên file ghi “NVR” không tự chứng minh nguồn/kênh đúng.
- Người dùng chỉ ra chữ trên cản là `29R52755`, khác transcript cũ `29K52755`.
  Trước benchmark mới cần rà ảnh/video đúng capture, ghi correction có bằng
  chứng và phiên bản nhãn mới. Giữ báo cáo/test khóa cũ cùng chú thích đính chính;
  rà ảnh hưởng tới metric chẩn đoán và holdout identity (giữ cả hai alias tránh
  leakage). Crop bị che vẫn là partial dù danh tính xe đã biết.

## 3. Luồng tổng thể

```text
Video live hoặc replay có nguồn/thời gian rõ
  → giải mã native + trạng thái chất lượng nguồn
  → detect xe / ROI / phiên camera_visit
  → chọn frame khác thời điểm và vùng có chữ
       ├─ detector biển D05f → FastPlate → raw OCR local
       └─ ảnh xe + crop biển/thân/cản → API vision → raw trích xuất
  → đối chiếu theo cùng phương tiện và cùng loại định danh
  → gợi ý / bất đồng / chưa đọc được + ảnh bằng chứng
  → nhân viên xác nhận, sửa, giữ chưa xác định hoặc tách phiên bị ghép nhầm
  → báo cáo hiệu quả theo lượt xe
```

API nhận ảnh được chọn theo lượt, không nhận video liên tục. AI không được
thực hiện lệnh từ chữ trong ảnh. Danh sách xe/lịch không đưa vào bước đọc ảnh
độc lập; nếu bổ sung D05h, chỉ dùng sau bước trích xuất để xếp hạng ứng viên.

## 4. Từng khâu triển khai và đầu ra

### Khâu A — Xác minh nguồn và thu mẫu

1. Quản lý xác nhận credential áp dụng cho từng camera/NVR và quyền live;
   NVR cần search/playback/download. Sai xác thực cuối cùng thì dừng thiết bị đó.
2. Đọc định danh, firmware, cổng, giờ/múi giờ và mapping tên/IP/kênh. Dùng đúng
   IP đã cấp, không dò mạng hoặc mở cổng Internet.
3. Thu thử live trực tiếp .185 qua RTSP TCP; .172 là nguồn bổ sung. Luồng chính
   được ưu tiên lấy chi tiết; subtype và độ phân giải phải đo thực tế.
4. Thu đoạn ngắn có giới hạn, đếm frame và giải mã toàn bộ; xem ảnh đầu/cuối,
   OSD, codec, độ phân giải, FPS theo PTS, bitrate, gián đoạn và đồng hồ lệch.
5. Playback là adapter/mode riêng. Chỉ tải lịch sử khi đã xác minh API/SDK,
   channel và StartTime/EndTime. Giữ DAV gốc, remux và kiểm tra file nếu cần.
6. Nếu chưa vào được camera, tiếp tục replay trên file đã kiểm chứng; không
   ghi replay là live. Video offline chỉ có media time khi chưa có mốc giờ thật.

**Đầu ra:** bảng nguồn, clip ngắn, frame đầu/cuối, metadata/hash và trạng thái
đủ dùng/chưa đủ dùng. Live đến được không tự nghiệm thu playback.

### Khâu B — Phát hiện xe và tạo phiên quan sát

- ROI bàn cân và vùng chờ được cấu hình cho từng camera, có ảnh overlay duyệt.
  Detect xe tại nhịp cấu hình; điểm bắt đầu thử là 3 Hz, đo lại tải và số lượt sót.
- Mở visit khi xe vào ROI theo nhiều quan sát liên tiếp. Dùng UUID bền vững;
  track_id chỉ là tham chiếu tạm. Lưu camera/track history và cấu hình phiên.
- Xe đứng lâu, lùi nhẹ hoặc mất detection ngắn không tạo visit mới liên tiếp.
  Dự kiến giữ phiên qua dropout 3 giây, đóng khi xác nhận ra khỏi ROI và vắng
  5 giây. Đây là tham số pilot, phải chọn trên tập phát triển rồi khóa.
- Mất stream không được diễn giải là xe đã rời. Restart lưu phiên dang dở và
  đánh dấu cần đối chiếu; không tự nối hai track chỉ vì biển OCR giống nhau.
- Hai xe cùng vùng hoặc không rõ track: trạng thái nhiều xe/chưa phân biệt,
  giữ evidence riêng và yêu cầu nhân viên tách. Không gộp OCR khác xe.
- .185 là nguồn chính tạo visit. .172 chỉ bổ sung khi mapping ROI, độ lệch
  đồng hồ và tương ứng phương tiện đã được xác nhận. Trùng thời gian là một
  tín hiệu, không đủ để gộp. Nếu chưa chắc, giữ observation riêng để review.
- Nhân viên có nút ghi nhận lượt bị bỏ sót/chọn ảnh từ buffer. Bộ đánh giá có
  danh sách lượt thủ công độc lập để detector miss vẫn nằm trong mẫu số.

**Đầu ra:** visit mở/đang quan sát/đã rời/gián đoạn/cần tách, kèm bằng chứng;
không suy ra cân ổn định, cabin trống hoặc nhập/xuất từ trạng thái hình ảnh.

### Khâu C — Chọn ảnh và crop

- Giữ frame gốc trước resize của detector. Bbox trả về phải quy đổi đúng tọa
  độ native, chặn biên và lưu transform để truy vết crop thiếu.
- Giữ tối đa 12 ứng viên mỗi camera/visit, phân bổ lúc vào, quan sát trên cân
  và lúc rời. Không dùng hết ngân sách ngay đầu lượt.
- Chọn tối đa 3 frame khác thời điểm/góc cho mỗi bộ gửi API, xét độ nét vùng
  chữ, kích thước native, chói, che khuất và khác biệt ảnh. Không dùng chuỗi
  OCR mong muốn để chọn frame; dHash/sharpness chỉ là heuristic.
- D05f tìm biển nhỏ. Bổ sung vùng sau xe/thân/cản từ bbox xe hoặc ROI cấu hình
  để không phụ thuộc detector biển tìm được chữ sơn. Có ảnh toàn xe làm ngữ cảnh.
- Mỗi bộ gửi tối đa 7 ảnh: 1 ảnh ngữ cảnh + tối đa 3 crop biển + 3 crop thân/cản.
  Bỏ crop rỗng/trùng; model API chọn sau phải đáp ứng giới hạn ảnh/pixel này.
- Dự kiến buffer video nén local 30 giây, giới hạn dung lượng; trích clip ngắn
  bằng chứng theo visit khi có lỗi/bất đồng. Không giữ vô hạn frame thô.
- Phóng ảnh chỉ để xem/đáp ứng preprocess, không gọi là tăng chi tiết thật.

**Đầu ra:** bộ evidence với source/camera/visit, media PTS, thời gian nhận,
bbox native, kích thước, hash, quality flags và lý do lựa chọn.

### Khâu D — OCR local

- Giữ FastPlate whole/original và preprocess cố định theo D05k. D05f dùng
  weights/hash đã có; detector xe dùng adapter/baseline đang dùng trong pipeline.
- Lưu raw, normalized, ứng viên và score nguyên bản; chỉ normalize chữ hoa,
  khoảng trắng/chấm/gạch nối. Không tự đổi R/K, O/0 hoặc điền ký tự bị che.
- Dùng consensus toàn chuỗi/vote ký tự có điều kiện của D05i. Nhiều frame gần
  giống nhau không được coi là nhiều bằng chứng độc lập.
- Chưa có crop, ký tự không đủ rõ hoặc bất đồng phải được giữ lại. Detector
  score, OCR score và API tự báo confidence không dùng chung một thang xác suất.

**Đầu ra:** dự đoán local độc lập theo vùng ảnh và visit, kể cả unknown.

### Khâu E — API đọc ảnh mỗi lượt

- Pilot gọi API cho mọi visit có bộ ảnh hữu ích, kể cả local đang đồng thuận,
  để đo trường hợp local sai nhất quán. Visit không có ảnh dùng được ghi
  `no_usable_evidence`, không gửi ảnh rỗng và vẫn tính trong mẫu số vận hành.
- Gửi bộ đầu khi có đủ ảnh sau cửa sổ chọn 5–10 giây, không đợi xe rời.
  API chậm/lỗi không chặn màn hình nhập tay hoặc OCR local.
- Một request chính; tối đa một lần gọi bổ sung nếu có ảnh mới tốt hơn hoặc
  cần giải quyết bất đồng. Tổng tối đa 3 attempt/visit, tính cả retry; retry
  tối đa 1 lần cho lỗi tạm thời. Không tự chuyển sang model đắt hơn.
- Đọc độc lập: prompt không chứa prediction local hoặc biển trong lịch. Trả
  JSON được kiểm tra schema, tham chiếu `image_id`, vùng chữ và loại thông tin:
  biển gắn trên xe, chữ sơn thân/cản, mã container, chữ khác/chưa rõ loại.
- Ghi raw text, phần nhìn thấy, ký tự chưa rõ và trạng thái che/chói. Không
  buộc API đoán một biển hoàn chỉnh hoặc biến mọi chuỗi số thành biển xe.
- Chọn một provider/model hỗ trợ ảnh và structured output sau thử nhỏ trên
  tập phát triển. Ghi model ID/version nếu có, prompt hash, giới hạn ảnh,
  token, timeout, giá đã kiểm tra và chính sách dữ liệu trước khi khóa test.
- API key chỉ ở secret store phía worker/server; camera secret chỉ trên edge.
  Ảnh được gửi tới nhà cung cấp là một quyết định cần duyệt của pilot.

**Giới hạn đề xuất, chưa phải số đo:** 2 USD/ngày, tối đa 300 attempt/ngày,
1 request đang chạy và hàng đợi tối đa 20. Dự trù chi phí trước gửi dưới khóa
ngân sách, đối chiếu usage sau trả; timeout có thể vẫn bị tính phí và phải giữ
khoản dự trù. Model/pricing chưa chốt nên đây là ngân sách duyệt, không phải
báo giá hay bảo đảm tuyệt đối về hóa đơn provider.

Timeout đề xuất 12 giây/attempt, kết quả quá 30 giây chuyển trạng thái chậm;
không tự hiện lên lượt xe khác. Job cũ quá hạn chỉ chạy lại trong chế độ review
có thao tác rõ ràng. 401/403 dừng API; 429/5xx áp backoff trong giới hạn trên.
Quá tải/hết ngân sách vẫn cho local + nhập tay và ghi lý do bỏ API.

**Đầu ra:** raw response hợp lệ, evidence refs, model/prompt version, usage,
chi phí, latency và lỗi; không ghi secret hay ảnh/payload vào log thông thường.

### Khâu F — Đối chiếu và đưa gợi ý

- Nhóm kết quả theo cùng phương tiện và cùng loại định danh. Biển đầu kéo,
  biển rơ-moóc và mã container là các trường riêng; chưa rõ vai trò thì giữ
  `vehicle_role=unknown` thay vì tự gán từ một ký tự hoặc format.
- Local/API đồng thuận trên cùng crop chỉ là đồng thuận thuật toán, chưa
  phải xác nhận thực tế. Chữ trên cản là nguồn hỗ trợ và vẫn có thể sai/cũ.
- Mẫu đang bàn: biển nhỏ nhìn rõ `52755`, hàng trên bị che; cản đọc
  `29R-527.55` → gợi ý `29R52755` với nhãn “dựa trên chữ sơn trên cản”.
  Không ghi rằng biển nhỏ đã được OCR đầy đủ.
- Nếu biển gắn và chữ sơn rõ nhưng khác nhau: hiển thị hai nguồn, trạng thái
  bất đồng; không bỏ phiếu ép lấy một. Sai loại định danh thì không so như
  hai prediction của cùng biển.
- Hiển thị tối đa 3 ứng viên có chứng cứ, có thể ít hơn hoặc không có. Format
  chỉ hỗ trợ kiểm tra/xếp hạng; không đủ để khẳng định chuỗi đúng.
- D05h theo lịch là bước tùy chọn sau pilot đọc ảnh. Nếu bật, hiển thị riêng
  “gợi ý theo lịch”, cho phép xe ngoài lịch; không dùng lịch làm ground truth.

**Đầu ra:** các ứng viên với lý do, raw bất đồng, evidence, trạng thái
`suggested / conflicting / unreadable / pending / confirmed`.

### Khâu G — Nhân viên review

- Một thẻ/visit: camera và thời gian, ảnh xe, crop native/phóng, chữ local,
  chữ API, nguồn gợi ý, cảnh báo che/chói và biển thuộc bộ phận nào.
- Nút chọn ứng viên, sửa/nhập tay, chưa xác định, sai xe/tách phiên; ảnh từ
  camera phụ luôn ghi rõ nguồn. Không mặc định chọn gợi ý đầu.
- Kết quả đã xác nhận giữ riêng dự đoán; lưu người/thời gian/lý do sửa và
  evidence version. API trả muộn chỉ thêm evidence, không ghi đè xác nhận.
- Prototype đầu dùng review local tái sử dụng công cụ hiện có, export nhãn.
  Khi đưa vào web nhiều người: áp D01/CSRF/quyền cơ sở phía server và ảnh cùng
  quyền truy cập; thêm migration/module evidence theo task D03 được giao.
- Pilot chỉ xác nhận annotation của thử nghiệm. Nút ghi vào chuyến/lượt cân
  D02 cần thiết kế và triển khai D07 riêng sau nghiệm thu.

**Đầu ra:** nhãn xác nhận có provenance và thời gian thao tác; bấm chấp nhận
không tự trở thành bằng chứng gợi ý đúng trong benchmark độc lập.

### Khâu H — Lưu trữ và khả năng phục hồi

- Pilot giữ manifest SQLite/local cùng ảnh/clip ngoài database ứng dụng;
  raw evidence, prediction và confirmed label là ba lớp riêng. Không secrets
  trong manifest, URL, argv, environment, history hoặc báo cáo.
- Visit UUID và khóa job = visit + evidence hash + model/prompt version tránh
  gửi lại do refresh/restart. Timeout chưa biết kết quả có thể tạo lần gọi
  tính phí lặp; không tuyên bố API có exactly-once nếu provider không hỗ trợ.
- Đồng hồ: lưu PTS, thời gian nhận UTC, device time/offset khi xác minh được;
  giao diện giờ Việt Nam. Offset chưa rõ thì không tự ghép camera/signal.
- Đề xuất giữ evidence pilot 30 ngày, buffer chỉ 30 giây; dữ liệu được khóa
  làm benchmark có thời hạn riêng sau người dùng duyệt. Quota đĩa có cảnh báo
  và ngừng thu mới có lý do, không tự xóa bộ test hay bằng chứng đang giữ.
- Quyền file giới hạn tài khoản vận hành, ảnh không public, dữ liệu/model
  không commit Git. Chính sách giữ ảnh của API phải kiểm tra riêng với provider;
  xóa file local không đồng nghĩa đã xóa phía provider.

## 5. Những tình huống cần xử lý ngay trong pilot

| Tình huống | Hành vi dự kiến | Bằng chứng cần giữ |
|---|---|---|
| Xe không được detector phát hiện | Nhân viên tạo observation/chọn frame; tính detector miss | Lượt thủ công, video/ROI gốc |
| Biển che, cản đọc được | Gợi ý từ cản, giữ biển partial | Hai crop và nguồn từng chuỗi |
| Biển/cản đều không đọc được | Unknown, cho nhập tay/xác minh độc lập | Ảnh tốt nhất, nguyên nhân thiếu chi tiết |
| Ban đêm/cháy sáng đèn | Chọn thời điểm/góc khác; không hứa phục hồi phần cháy | Crop ngày/đêm native, mức lỗi theo điều kiện |
| Mất detection ngắn, xe lùi | Giữ visit có điều kiện, ghi track fragment | Timeline bbox và ROI |
| Hai xe sát nhau | Tách evidence, yêu cầu review khi không chắc | Toàn cảnh và track association |
| Xe quay lại cân | Visit mới, đề xuất liên hệ chứ không tự ghép chuyến | ID và mốc vào/ra |
| Camera .172 và .185 khác xe | Không gộp chỉ dựa timestamp | Tham chiếu camera/xe và độ lệch clock |
| Biển đầu kéo khác rơ-moóc | Lưu hai vai trò, nhân viên chọn trường cần dùng | Vị trí biển trên phương tiện |
| Mã container giống chuỗi biển | Giữ loại container/unknown | Ngữ cảnh và raw text |
| Mất mạng/API lỗi/quá ngân sách | Local + nhập tay; trạng thái chưa có API | Mã lỗi, attempt/cost, không secrets |
| API trả sau khi đã xác nhận/xe khác đến | Gắn đúng visit, không ghi đè | Request ID, version, thời gian |
| Camera mất stream hoặc lặp frame | Cảnh báo nguồn gián đoạn/stale, không coi vùng cân trống | Decode/PTS/frame hashes và thời gian nhận |
| NVR trả sai khoảng/kênh | Loại khỏi pilot cho đến khi đối chiếu | Search metadata, OSD/frame đầu cuối |
| Worker restart/đĩa đầy | Khôi phục job có ID, chặn thu/gửi vượt giới hạn | Job state, quota, audit |

## 6. Kế hoạch thực hiện theo mốc duyệt

| Mốc | Công việc và sản phẩm để xem | Điều kiện chuyển tiếp |
|---|---|---|
| P0 — Chốt phạm vi | Duyệt tài liệu này, định danh cần gợi ý, gửi ảnh API/budget/retention; xác nhận truy cập thiết bị | Đủ quyền/kết nối cho live; thiếu thì replay trước |
| P1 — Replay và sửa nhãn | Kiểm tra nguồn, version nhãn 29R/29K, 10–20 lượt phát triển; CLI + review tái sử dụng | Frame decode/nguồn đúng, evidence không lẫn xe, thông số chọn ảnh có thể review |
| P2 — Thử API nhỏ | Tối đa 10 lượt phát triển đa điều kiện; local/API độc lập, bảng chi phí/latency/raw so ảnh | Chọn provider/model/prompt; kiểm tra dữ liệu gửi ra và ngân sách |
| P3 — Live có giám sát | .185 trước, .172 bổ sung sau khi mapping đạt; nhật ký lượt độc lập của nhân viên | Session/gián đoạn/retry/late response đạt, thao tác review dùng được |
| P4 — Đánh giá khóa | Thu mục tiêu 50–100 lượt ở nhiều xe/ngày, chọn tập test độc lập; local/API/kết hợp cùng input | Báo đủ mẫu số/nhóm điều kiện, kết quả người xác minh và quyết định đi tiếp |

Các mốc là thứ tự triển khai, không cam kết số ngày khi chưa có API key, quyền
camera và lịch xe. P1/P2 dùng tập phát triển; không điều chỉnh prompt/ngưỡng
bằng test P4. Khi số nhóm quá ít, chỉ báo chẩn đoán, chưa tuyên bố nghiệm thu.

## 7. Bộ đánh giá và tiêu chí duyệt thử nghiệm

Thu nhiều lượt có biển khác nhau, xe tải/container, 1/2 dòng, ngày/đêm, che/chói,
xe không lịch và nhiều xe cùng khung. Mục tiêu 50–100 lượt là thu thập coverage,
không phải ước lượng độ chính xác chắc chắn. Báo số biển/xe/capture duy nhất;
lượt lặp của một xe không tính như các mẫu độc lập hoàn toàn.

Chia phát triển/test theo xe/biển/capture và kiểm tra ảnh trùng/gần trùng.
Nhãn thật lấy từ người xác nhận độc lập trên ảnh/video rõ hoặc hồ sơ được xác
minh; không lấy OCR/API hay một gợi ý lịch làm đáp án. Nhóm partial lưu cả
visible_text và identity nếu được xác nhận độc lập. Thiếu GT giữ unknown và
báo tỷ lệ thiếu, không loại im lặng khỏi tổng lượt vận hành.

So ba nhánh trên cùng lượt: local, API và kết hợp. Đánh giá hệ thống đầy đủ
dùng bbox/track tự động; crop thủ công chỉ là nhánh chẩn đoán. Nếu thiếu sáng
hoặc container che không đủ mẫu, chưa kết luận cho các nhóm đó.

| Chỉ tiêu | Mẫu số/cách tính |
|---|---|
| Tạo đúng visit | Lượt phát hiện / tất cả lượt do người ghi nhận; thêm số tách/ghép nhầm |
| Đúng top-1 / top-3 | Lượt đúng / mọi lượt có GT độc lập, kể cả không gợi ý |
| Coverage | Lượt có gợi ý / mọi lượt; tỷ lệ có ảnh đủ đọc do người xác nhận |
| CER/chữ partial | Sai ký tự / tổng ký tự có GT; partial chỉ chấm phần biết được |
| API giúp/sửa thành sai | Local sai→kết hợp đúng và local đúng→kết hợp sai, cùng mẫu số |
| Nhân viên chấp nhận/sửa | Số chọn gợi ý, nhập tay, unknown; kiểm tra đúng bằng GT độc lập |
| Thời gian | Median/p95 đến gợi ý và thời gian thao tác so nhập tay ở điều kiện tương đương |
| Chi phí và vận hành | USD/lượt/ngày, số ảnh/attempt, timeout/retry, CPU/RAM/đĩa/băng thông |

**Mốc mục tiêu đề xuất để duyệt, chưa là kết quả:** top-3 ≥95% trên lượt có
GT; p95 gợi ý ≤15 giây từ khi đủ evidence; median thao tác giảm ≥30% so nhập tay.
Báo tử số/mẫu số và riêng ngày/đêm, đầu kéo/rơ-moóc, partial/full. Pilot nhỏ
đạt mục tiêu không chứng minh tỷ lệ tương tự ở quy mô lớn.

Điều kiện kỹ thuật bắt buộc: không ghi đè xác nhận bằng API muộn, không gán
nhầm evidence giữa visit/cơ sở trong các kiểm tra, không có ghi tự động D02,
giới hạn job/chi phí hoạt động; mọi lỗi vẫn có đường nhập tay. Lỗi lẫn xe hoặc
lộ quyền ảnh chặn mở rộng pilot dù OCR tổng cao.

Nếu kết hợp không hơn local hoặc làm tăng gợi ý sai, giữ local + review và
phân tích lại; không mặc định tăng model/training. Nếu camera không có ảnh
đọc được, khảo sát vị trí/ánh sáng trước. Nếu API đọc tốt nhưng workflow chậm,
ưu tiên UI/chọn ảnh. Chỉ cân nhắc sửa model sau khi xác định lỗi ở detector/OCR.

## 8. Kiểm tra khi triển khai

- Replay fixture và clip có nhãn: vào/ra, đứng lâu, lùi, dropout, hai xe,
  camera lệch giờ, mất stream và lặp frame.
- Kiểm tra bbox/native crop, provenance và nhãn bị che; ngăn ghép nhầm vai trò
  đầu kéo/rơ-moóc/container. Rà các ví dụ 29R/29K bằng evidence version mới.
- API mock: schema sai, text trong ảnh yêu cầu đổi lệnh, timeout/429/401/5xx,
  retry, quota, kết quả muộn, restart và job trùng. Sau đó kiểm tra API thật
  giới hạn trên tập phát triển, ghi usage thực.
- Review local export/import; khi có web chung kiểm tra quyền facility,
  đường ảnh trực tiếp, CSRF, xác nhận cạnh tranh, desktop/mobile.
- Chạy regression edge-agent liên quan và toàn suite theo scope triển khai;
  báo số pass/fail thực, build frontend nếu đổi UI; dữ liệu test riêng.
- Bàn giao CLI/config, model/prompt/data hashes, bảng so sánh theo lượt, ảnh
  trước/sau, lỗi tồn tại và hướng dẫn tắt API/quay về local + nhập tay.

## 9. Các quyết định xin duyệt

1. Pilot hỗ trợ nhân viên; xác nhận ở review riêng, chưa ghi tự động vào D02.
2. Giữ D05f + FastPlate pretrained; gọi API mỗi visit có evidence, giới hạn
   3 attempt/visit và 300/ngày, ngân sách đề xuất 2 USD/ngày.
3. Cho gửi ảnh xe/crop được chọn tới provider được chốt ở P2; giữ evidence
   local 30 ngày, ảnh khóa benchmark quản lý riêng.
4. .185 là nguồn chính, .172 bổ sung có kiểm chứng cùng xe; playback tách live.
5. Đề xuất mặc định gợi ý biển xe tải/đầu kéo; biển rơ-moóc giữ thêm trường riêng.
   Người dùng cần chốt: thao tác trạm cân có cần chọn biển rơ-moóc làm định danh
   chính ở một số chuyến không? Cho phép để vai trò chưa xác định trong pilot.
6. Duyệt P1–P4 và mục tiêu đánh giá nêu trên; chưa coi 50–100 lượt hay ≥95%
   là bảo đảm chất lượng sản phẩm. D05h theo lịch và D07 ghép cân là bước sau.

Tài liệu tham chiếu: `requirements.md`, `architecture.md`, `tasks.md`,
`camera-vehicle-evaluation-plan.md`, `offline-vision-d05i.md`,
`offline-vision-d05k.md` và kết quả khảo sát thiết bị trao đổi ngày 09/10.

## Cập nhật thực thi 10/10/2026 — D05m4

Nguồn .185 live main đã xác thực/giải mã và worker chạy riêng trên Mac.
Theo phê duyệt mới, credential lấy từ Keychain; URI xác thực chỉ tạo trong bộ
nhớ PyAV, không cần proxy. Health stage riêng mỗi 30s; preview D01, snapshot
1/10 phút và clip kiểm tra 15s không gọi AI. Xem `camera-live-pilot.md`.
API AI thật, ROI xác nhận và lượt xe/cân thật vẫn là các cửa nghiệm thu riêng.
