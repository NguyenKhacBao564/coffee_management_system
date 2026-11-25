# D05m4b / D05m4c — Rà cân D02 và camera theo sự kiện

Ngày 10/10/2026. Phạm vi: nhận signal, nhận diện xe, vài ảnh native và người xác nhận.
Không thay quy tắc D02. Chế độ mới là `event_driven`; vẫn hỗ trợ `continuous`.

**Policy hiện hành từ 11/10/2026 là D05m4c bên dưới.** Các số 20s/4 ảnh trong
báo cáo D05m4b là cấu hình và bằng chứng đo trước thay đổi, không phải runtime hiện tại.

## Logic cân hiện có — đọc từ source

| Khâu | Hành vi thực tế | Ví dụ / giới hạn |
| --- | --- | --- |
| Tạo lượt cân | Staff/Manager nhập `WeighIn`, nguồn `manual`; khóa trip đang mở để tăng sequence. Tạo event và result riêng, không có idempotency key cho POST lượt cân. | Nhập lại cùng số 30.000 kg hai lần tạo hai lượt; unique trip/sequence chỉ ngăn sequence trùng. |
| Xác nhận/chọn cân | Cần lời xác nhận vị trí xe và người xuống xe; sau đó chọn result rõ ràng. Một event có tối đa một result selected qua service. Admin D02 chỉ đọc. | `pending` → `ready` → `selected`. Đây là xác nhận người vận hành, chưa phải cờ ổn định đầu cân. |
| Cặp cân | Người dùng chọn loại hàng, chiều và before/after. Backend kiểm tra cùng trip/facility, sequence và thời gian tăng, cả hai event/result selected. Nhập = trước − sau; xuất = sau − trước; phải dương. | Nhập 30.000 → 12.000 = 18.000 kg; xuất 12.000 → 30.000 = 18.000 kg. Không tự chọn cặp hoặc chiều. |
| Cân lại | `reweigh_of_event_id` liên kết một event mới với event cũ trong cùng trip. Không tự bỏ/chọn lại event cũ, không tạo giao dịch. | 30.000 → 12.000 rồi cân lại 12.100: chọn lại cặp 30.000 → 12.100 = 17.900; phải xử lý giao dịch/cặp cũ trước để tránh overlap. |
| Sửa số cân | Tạo result mới với lý do, giữ result cũ `replaced`; các draft/pending dùng kết quả cũ bị `needs_review`. Nếu đã confirmed, phải hủy giao dịch có lý do trước. | 12.000 sửa thành 12.100: số nhập đề xuất 18.000 → 17.900; không tự sửa giao dịch đã duyệt. |
| Nhiều loại hàng | Mỗi giao dịch một goods_item, một khoảng cân. Các khoảng kề nhau được phép dùng chung mốc. Không chia hai hàng trong một khoảng chênh đã submit/confirm. | 30.000 → 20.000 → 12.000: hàng A nhập 10.000, hàng B nhập 8.000. 30.000 → 12.000 không đủ biết tỷ lệ A/B. |
| Chống tính trùng | Giao dịch có Idempotency-Key theo cơ sở; cùng nội dung/actor trả lại bản ghi, khác nội dung conflict. Submit/confirm khóa trip và từ chối khoảng chồng lấn với pending/confirmed. Version bảo vệ chỉnh nháp/duyệt. Confirm lặp trả cùng giao dịch. | Khoảng 1→2 và 2→3 được phép; 1→3 chồng cả hai nên bị chặn. Hai draft chồng nhau có thể tồn tại nhưng không cùng submit/confirm. |
| Chốt nghiệp vụ | Giao dịch draft → pending → manager confirmed. Hoàn tất trip cần vehicle, không còn draft/pending hoặc cân pending/ready. Tổng quan chỉ cộng confirmed. | Chọn cân không đồng nghĩa duyệt giao dịch. Hoàn tất trip không tự tạo hàng/giao dịch. |
| Signal / heartbeat / xe | Signal lưu riêng, UUID + sequence chống trùng, ACK sau commit. Heartbeat một snapshot/agent, chu kỳ 30s, độc lập trọng lượng. Camera chỉ hiển thị tối đa 10 signal trong ±5 phút, liên hệ bằng thời gian chưa ghép. | Signal 30.000 kg không tạo WeighEvent/Trip. Heartbeat reader empty không đồng nghĩa PC offline. |

Source: `backend/app/modules/trips/router.py`, `weighings/models.py`,
`goods/models.py`, `scale_ingestion/router.py`, `vehicle_pilot/router.py`.

### Các quyết định nghiệp vụ cần công ty chốt

1. Lúc nào nhân viên chọn một signal thành số cân nghiệp vụ; xác nhận ổn định,
   vị trí xe và người xuống xe lấy từ đâu. Hiện nguồn chưa có stability flag.
2. Cân lại là thay mốc nào; giữ/hủy giao dịch cũ ra sao. Hiện liên kết reweigh
   không tự thay thế kết quả được chọn.
3. Hàng hỗn hợp có dùng cân trung gian theo từng loại hay nhập phân bổ riêng;
   D02 hiện không hỗ trợ chia cùng một khoảng chênh cho nhiều loại.
4. Ai xác nhận ghép camera_visit/signal/trip; phân biệt biển đầu kéo/rơ-moóc,
   chữ sơn và container. Hiện chưa có liên kết nghiệp vụ D07.
5. Có cần idempotency cho nhập lượt cân thủ công và bảo vệ acknowledge lại
   một event đã selected/được giao dịch dùng. Source hiện cho acknowledge chuyển
   event về ready; đây là rủi ro thao tác lặp, chưa sửa workflow trong task này.

## Điều khiển camera

Tái dùng PyAV/TCP main, model D05f + FastPlate pretrained/hash cũ, tracker,
CandidatePool, persistence/outbox và D01. Không thêm service/migration.
`camera_diagnostics` đã có kind/status/requested_by/metadata/TTL nên được tái dùng
cho command hữu hạn; command không có object_key không được trả như file.

- Idle: socket RTSP đóng, không demux/decode/detect/OCR/API. Model giữ nóng trong
  tiến trình để tránh nạp lại mỗi lần. Worker vẫn gửi health và đọc DB khoảng 1s.
- Mapping cân chỉ dùng `scale_agent_id` đã xác nhận ở config, kiểm tra cơ sở khi
  khởi động. Không chọn agent dựa trên dữ liệu mới nhất toàn hệ thống.
- Trigger cân: weight ≥1.000 kg, tuổi `observed_at_utc` ≤10s, dung sai future 2s;
  nhận muộn/backlog không kích hoạt chỉ vì `received_at_utc` mới.
- Cùng chuỗi signal không mở lại/không kéo dài cửa sổ. Chỉ re-arm sau khoảng
  quan sát >120s giữa các signal đủ mới. Đây là heuristic cửa sổ chụp, không
  phải xác nhận một xe mới hay xe đã rời; người dùng vẫn kích hoạt thủ công.
- Cửa sổ 20s, tối đa 30 lượt vehicle inference, tối đa 6 plate model calls và
  4 OCR model calls trên toàn cửa sổ; tối đa 4 ảnh native cách nhau ≥4s.
- Preview mặc định tắt. Bật theo request tối đa 120s, tự tắt; preview-only không
  chạy detect/OCR/API. Nút chụp ảnh native không chạy AI. Clip 15s cần nguồn
  đang cung cấp frame: bật preview trước nếu camera đang idle.
- Hết cửa sổ là `capture_window_expired_not_proof_of_departure`, visit cần review;
  không tự chốt cân/giao dịch. Không có xe thì không tạo visit giả; ảnh kiểm tra
  vẫn được lưu riêng 24h. Ảnh gắn visit thật theo retention evidence 30 ngày.
- AI thật vẫn disabled vì task D05m3 chưa nghiệm thu; điều khiển camera không tự
  mở API. Ngân sách/attempt hiện có giữ nguyên.
- Preview/file dùng quyền D01/cơ sở và CSRF khi điều khiển. Request UUID trùng
  nội dung trả cùng command, khác nội dung 409; camera row lock coalesce request.
  Command queued quá 30s bị interrupted; restart không kéo dài deadline/capture.
- LiveSource dùng một thread duy nhất, enable/disable đóng container; queue 2
  ưu tiên mới. TCP timeout 5s, reconnect backoff 1–30s; 401 dừng thử account.
- Giảm inference 3→1,5Hz trong cửa sổ **không giảm decode FPS**: khi RTSP mở vẫn
  giải mã main 25FPS. Tiết kiệm idle đến từ đóng luồng thực sự.

Config: `edge-agent/config/camera-185.worker.json`; đổi `mode` thành `continuous`
và restart để dùng chế độ cũ. `event_policy` nằm ngoài code. Preview vẫn opt-in
trong cả hai chế độ.

```bash
python3 scripts/camera-worker.py start
python3 scripts/camera-worker.py status
python3 scripts/camera-worker.py restart
python3 scripts/camera-worker.py stop
```

UI: <http://127.0.0.1:5174/pilot>. Nút **Chụp và nhận diện xe**, **Chụp ảnh native**,
**Bật preview 2 phút / Tắt preview**. `POST /api/vehicle-pilot/cameras/{camera}/actions`
nhận `request_id` UUID, `action=process|photo|preview|preview_stop`, duration 10–120s
chỉ áp dụng preview; processing lấy 20s từ worker config.

Health tách worker reporting (≤75s), source idle_unchecked/starting/receiving/
reconnecting/error/stopped, processing idle/preview_only/processing/error.
Idle không bị coi là camera online từ ảnh cũ; API preview từ chối khi hết lease
hoặc không có frame decode mới. Reader/heartbeat cân hiển thị riêng, nút thủ công
vẫn dùng được khi nguồn cân mất liên lạc.

## Hợp đồng Windows

Không cần đổi S02 hoặc heartbeat để chạy chế độ này. Windows giữ observed UTC
thật lúc đọc UI và sequence signal riêng, đồng bộ đồng hồ; batch retry không
thay observed time. Heartbeat không dùng làm trigger và không mang trọng lượng.
Windows hiện chỉ gửi mẫu ≥1.000 kg, không có start/end session hoặc số cân về 0;
server không thể chứng minh xe rời từ sự im lặng.

Nếu cần phân biệt hai lượt liên tiếp cách nhau <120s hoặc xe đứng lâu, task kế
sau có thể bổ sung `capture_request_id`/`weigh_observation_session_id` do người
vận hành khởi tạo và sự kiện kết thúc thao tác rõ ràng. Không suy đoán start/end
bằng PID, sequence heartbeat hay tracking ID; chưa sửa client PC trong task này.

## Bằng chứng đo / giới hạn

Đo .185 main vào 13:35–13:58 VN ngày 10/10/2026. Không có xe trong ROI;
5 request process đều kết thúc đúng cửa sổ và lưu 4 ảnh mỗi request, không tạo
visit giả hoặc gọi OCR/API. Độ trễ gợi ý trên xe thật chưa đo được. Chưa kiểm
chứng auto-trigger bằng cân thật ≥1.000 kg; freshness/dedupe/restart dùng đồng
hồ giả, không seed database ứng dụng. ROI vẫn cần người vận hành xác nhận.

### Tài nguyên trước/sau

CPU theo % một core (100% = một core); mẫu baseline 5s, event samples 1s, stage
từ health nên một số mẫu ở ranh giới trễ nhãn. Đây là số worker trên Mac đang
chạy nhiều ứng dụng, không phải benchmark server hay toàn bộ máy.

| Chế độ | CPU | RSS worker | Decode / inference |
| --- | --- | --- | --- |
| Continuous trước đổi | 166,8% trong mẫu 5s | 469,8 MiB | ~25fps / 2,71fps |
| Event idle | median 1,4%; mẫu cuối 5s 1,7% | Khởi động ~73–143 MiB; idle sau xử lý biến động ~79–591 MiB | 0 / 0; socket đóng |
| Event processing 20s | median khoảng 98%; mẫu xử lý thường 76–138% | peak khoảng 591 MiB | Main ~25fps khi mở / tối đa 1,5Hz, thực tế 27–28 inference |
| Preview-only | median khoảng 25% | Tùy cache; lần cuối ~212–219 MiB trước inference, lần trước ~500–568 MiB | Main vẫn decode; 0 inference/OCR |

RSS không lập tức trở về mức startup; model/allocator/cache giữ nóng và RSS
biến động theo thời gian. Hai vòng đầu
peak tăng khoảng 554→591 MiB, do đó **chưa có bằng chứng leak-free dài hạn**.
Đã giải phóng tham chiếu PyAV khi đóng luồng. Worker cuối PID 20584 qua photo,
preview bật/tắt và process: không có process con, queue/outbox 0; decode counter
dừng ở idle. RSS sau đợt cuối ~579 MiB trong các mẫu idle đầu, sau đó giảm ~334 MiB và
mẫu bàn giao cuối 78,7 MiB. Đây là RSS tại từng thời điểm, không bảo đảm chỉ cần
79 MiB để vận hành; phải dự trù peak khoảng 600 MiB và theo dõi dài hơn.
Không nhầm giảm inference Hz với giảm decode: phần tiết kiệm chủ yếu ở thời
gian đóng nguồn. Preview mặc định tắt thực sự, không chỉ ẩn hình.

Docker snapshot gần cuối: API 73 MiB/0,21%, web 83,66 MiB/0,20%, PostgreSQL
90,15 MiB/0,22%, retention 56,4 MiB/0%. Tổng RAM container khoảng 303 MiB;
chưa gồm Docker VM/engine, browser, Codex và bộ nhớ host khác. Không cộng %
Docker vào % worker Mac như cùng một phép đo.

### Độ trễ yêu cầu manual process → ảnh

| Request (tiền tố UUID) | Frame native đầu | Ảnh đầu lưu/enqueue | Inference / ảnh |
| --- | ---: | ---: | ---: |
| 1376bde8 | 2,385s | 2,625s | 28 / 4 |
| 02f44e0e | 1,968s | 2,151s | 28 / 4 |
| 28f3e389 | 2,604s | 2,733s | 27 / 4 |
| a20be094 | 1,917s | 2,103s | 28 / 4 |
| 9e2a0902 (worker cuối) | 1,429s | 1,603s | 27 / 4 |

Mốc đầu là command `created_at` commit phía API; worker cộng cả thời gian poll
tới trigger, mở RTSP và decode. Mốc ảnh là ghi file/enqueue, chưa đo riêng DB
ACK latency. Đã đối chiếu tất cả command completed và file/metadata lưu được.
Chưa đo độ trễ cho weigh signal thật hoặc gợi ý OCR. Baseline continuous có
luồng sẵn nhưng không có bộ trigger tương ứng để đo trước/sau cùng điều kiện;
không dựng con số latency baseline giả. Mở nguồn 1,4–2,6s hiện phù hợp cửa sổ
20s; nếu xe đi nhanh hoặc signal đến muộn cần thử xe thật rồi cân nhắc kết nối
nhẹ/snapshot xác thực, chưa cần decode main liên tục mặc định.

### Kiểm tra phục hồi và lỗi đã sửa

- Restart riêng worker có lock; preview deadline và capture deadline/cursor
  giữ nguyên, không kéo dài window; không có worker/capture process trùng.
- Preview 120s tự chuyển completed; test clock xác nhận expiry. Bật/tắt thủ
  công lần cuối đóng nguồn lại, processed counter không tăng trong preview.
- Native photo từng bị recapture cùng request trước khi sender commit DB,
  immutable-file conflict. Sửa capturing→saving trước ghi; sender và recovery
  hoàn tất stored. Một record lỗi cũ `81134338…` được giữ interrupted. Hai
  request mới stored; file decode 1920×1080/hash metadata khớp. Request cuối
  `25a5c93a…` có trigger_id đúng UUID của chính ảnh (không mượn process cũ).
- Ảnh không có xe trong đợt xử lý là diagnostic 24h; không tự tạo evidence
  visit, AI job hay WeighEvent. Vehicle evidence khi có xe có bản riêng bền
  vững qua outbox, không bị diagnostic cleanup xóa trước ACK.
- PostgreSQL chỉ đọc cuối: 9 signal, 0 trip/weigh event/transaction/visit/AI job.
  Heartbeat agent đã cấu hình seq 421 lúc 13:58:12 VN, reader empty/pending 0.
  UI session Manager: đang liên lạc và reader trống riêng; ảnh cũ không làm
  camera hiện online. API readiness tại LAN192.168.1.13:8001 HTTP200. API chỉ
  bind IP LAN theo config, localhost:8001 không phải endpoint hiện tại.

### Lệnh kiểm tra / bàn giao

```bash
python3 scripts/test-d05m.py
edge-agent/.venv/bin/python -m pytest -q edge-agent/tests/test_event_gate.py edge-agent/tests/test_live_source.py edge-agent/tests/test_offline_pipeline.py
npm --prefix frontend run build
python3 scripts/camera-worker.py status
```

Backend cuối **16 pass / 0 fail** trên PG tạm rồi xóa riêng; edge liên quan
**38 pass / 0 fail**. Build frontend đạt. Test mới có coalesce/scope/CSRF/idle
health, signal backlog/dedupe/restart/deadline, OCR budget với frozen config,
file outbox riêng và photo claim/resume. Có một warning anyio deprecated từ
Starlette; không ảnh hưởng kết quả. Một lần test photo fixture thiếu buffer API
đã sửa fixture bytes và chạy lại đạt; đây không phải lỗi encoder live.

Số đo/raw commands: `data/pilot/camera-185/event-driven-measurements.json`,
`event-driven-commands.json`; file local private ngoài Git. Ảnh UI bàn giao:
`output/pilot-event-driven-ui.jpg`. Worker vẫn đang chạy event-driven idle,
không phải chạy inference thường trực. Không thay database schema, D02, token,
volume hoặc 9 event S03a. Chưa nghiệm thu xe thật/biển/API/trọng lượng thật.


## D05m4c — Tìm biển lâu hơn và chỉ lưu bộ ảnh hữu ích (11/10/2026)

### Policy đã áp dụng

- Vẫn trigger bằng signal observed mới ≥1.000 kg hoặc nút **Tìm và chụp biển xe**;
  không đổi freshness, mapping agent, rearm hay D02. Preview mặc định tắt.
- Cửa sổ tối đa **120 giây**, vehicle inference **1 Hz / tối đa 120 lượt**;
  tối đa **40 plate detector calls**, **4 OCR calls** toàn cửa sổ. Plate attempts
  cách nhau ≥3s, không tăng backoff ở phase muộn để còn cơ hội lúc xe đổi vị trí.
- Dừng sớm sau ít nhất **15 giây** khi có ít nhất **2 crop** cách nhau ≥3s,
  thuộc đúng một session trong cửa sổ, không có bằng chứng nhiều xe. Crop native
  ≥96×24px, Laplacian variance ≥20, detector score ≥0,35 và bbox không sát mép
  crop xe. Các ngưỡng này là heuristic kỹ thuật ban đầu, chưa hiệu chỉnh bằng
  nhiều lượt xe; không đồng nghĩa biển đọc chắc hoặc OCR đúng.
- Model hiện tại chưa phân loại đầu/đuôi xe. Biển được detect/crop và chất lượng
  crop là chỉ dấu để chọn ảnh; không tuyên bố đã nhận đúng đầu/đuôi. Không thấy
  biển ở góc .185 thì tăng thời gian vẫn có thể thất bại.
- Giữ tối đa **8 bộ** toàn cảnh native + crop xe + crop biển cùng frame/timestamp
  (tối đa 24 file khi đầy đủ), có bbox native, crop origin và hash. Chọn theo
  chất lượng và khoảng cách thời gian; các crop yếu hơn vẫn có thể giữ để review
  lúc hết thời gian, nhưng không làm điều kiện dừng sớm.
- CandidatePool giữ tối đa 4 candidate/phase, 3 phase. Crop tạm dùng PNG; context
  scene/xe native JPEG. Thay candidate kém/trùng thì dọn cả crop và context. Sau
  ghi payload/file outbox bền vững, dọn candidate còn lại. Startup dọn candidate
  không còn được session recovery tham chiếu; không dọn file evidence outbox.
- Không có crop biển: giữ **một toàn cảnh xe tốt nhất mỗi visit** để kiểm tra
  bỏ sót, không coi ảnh đó là âm và không xóa evidence đã ACK trong database.
  Hết cửa sổ ghi `capture_time_limit_requires_review`; có crop đủ điều kiện ghi
  `plate_quality_target_reached_requires_review`. Cả hai không chốt cân/xe rời.
- Vẫn RTSP main 1920×1080/25fps khi cửa sổ mở: **giảm inference không giảm decode**.
  Hết cửa sổ đóng nguồn nếu không còn preview/photo/clip. Queue 2 ưu tiên frame mới.
- OCR/model giữ D05f + FastPlate pretrained; API AI thật vẫn khóa.

### Dọn dữ liệu / dung lượng

Dọn tự động chỉ áp dụng file ứng viên chưa commit. Evidence xe giữ 30 ngày,
diagnostic 24 giờ theo retention hiện có; không xóa ảnh cũ chỉ vì detector
không tìm thấy biển. Đĩa/quota lỗi vẫn báo lỗi và giữ outbox để phục hồi.
Quota evidence hiện 5GiB không đổi. Nếu 100 lượt/ngày, mỗi lượt chọn đủ 8 bộ
ảnh native trong 30 ngày, dung lượng có thể vượt quota; cần đo dung lượng mỗi
lượt thực rồi điều chỉnh quota/retention rõ ràng, không âm thầm xóa evidence.

### Bằng chứng kiểm tra

- `python3 scripts/test-d05m.py`: **16 passed**, database PostgreSQL tạm tạo/xóa
  riêng, migrations đến head; 1 warning Starlette đã có. Không reset app volume.
- `PYTHONPATH=backend:edge-agent edge-agent/.venv/bin/python -m pytest -q
  edge-agent/tests/test_event_gate.py edge-agent/tests/test_offline_pipeline.py
  edge-agent/tests/test_live_capture_selection.py`: **39 passed**. Bao phủ
  crop/context native cùng frame, điều kiện dừng, nhiều session/nhiều xe không
  dừng sớm, không crop không dừng sớm, cap evidence, candidate cleanup không
  chạm file evidence và recovery representation.
- Build TypeScript/Vite và rebuild riêng Compose web đạt. Worker PID35040
  khởi động lúc sessions/outbox đều0; worker lock ngăn chạy trùng.
- Preflight ảnh thật đã lưu: 4 scene native camera .185 của visit 11:30, mỗi
  scene lặp3 lần cho tracker warmup (12 lượt), **3 plate calls/3 proposals**,
  chọn2 bộ/6file, decode/hash/transform đạt, candidate tạm còn0. Đây là kiểm tra
  kỹ thuật trên dữ liệu đã lưu với timestamp giả phục vụ fixture; không phải
  benchmark mới hay nghiệm thu xe live. Báo cáo `output/capture-selection-preflight/report.json`.
- Live manual request **14:10:51–14:12:51 VN, 11/10/2026**: first frame1,546s
  từ gate trigger; **2.995 frame decode /114 lượt inference**, 0 plate/OCR calls,
  0 visit mới, không AI. Timeout sau120,017s, `capture_active=false`, source
  `idle_unchecked`, processing `idle`, queue/outbox0, reconnect0, error null.
  Idle RSS sau phiên47.824.896byte (~45,6MiB). Không detect xe trong ROI ở phiên
  kiểm tra này; không suy ra mọi ảnh đều không có xe từ số liệu detector.
- UI có bộ đếm crop đạt tiêu chí, trạng thái kết thúc và timestamp từng evidence;
  PC cân vẫn đang liên lạc, reader empty hiển thị riêng.

### Chạy / giới hạn nghiệm thu

Config: `edge-agent/config/camera-185.worker.json` (`event_policy`) và
`edge-agent/config/camera-185.live.json` (plate attempts/session grace). Các
lệnh start/status/stop/restart ở phần trước giữ nguyên. Chỉ restart lúc không
còn phiên đang xử lý. Nút web <http://127.0.0.1:5174/pilot> dùng quyền D01/CSRF.

Cần quan sát lượt xe tiếp theo để chốt crop sớm có đủ chi tiết và biển có đúng
xe đang cân. Không yêu cầu OCR đúng mới dừng vì OCR có thể sai khi ảnh đã rõ.
Nếu hết120s hoặc không có góc thấy biển, vẫn cho chụp thủ công; cần camera/góc
phụ đã xác minh nếu ảnh chỉ thấy cabin/container. Chưa tích hợp .172 và chưa
đổi logic nghiệp vụ/heartbeat Windows.
