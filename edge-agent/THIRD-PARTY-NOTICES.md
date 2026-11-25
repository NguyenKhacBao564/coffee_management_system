# D05a — nguồn, giấy phép và phiên bản model

Đã đối chiếu nguồn chính thức ngày 06/10/2026 trước khi chọn model. Không lấy
nhãn giấy phép của một wrapper để suy ra giấy phép weights. Ba model dưới đây
được nhà phát hành OpenCV Zoo ghi Apache 2.0 cho mọi file trong thư mục model,
bao gồm weights ONNX và mã tham khảo. Apache 2.0 cho phép sử dụng thương mại
với các điều kiện của giấy phép; giữ LICENSE, attribution/NOTICE khi phân phối.
Xem [FAQ của Apache](https://www.apache.org/foundation/license-faq.html).

| Bước | Model/file và revision đã khóa | Nguồn chính thức | Code/weights |
| --- | --- | --- | --- |
| Xe | YOLOX-s COCO, `object_detection_yolox_2022nov.onnx`; `78c368f74ce73ee28fc7a1be418a598c71b58b52` | [Model card](https://huggingface.co/opencv/object_detection_yolox), [LICENSE ở revision](https://huggingface.co/opencv/object_detection_yolox/blob/78c368f74ce73ee28fc7a1be418a598c71b58b52/LICENSE), [demo](https://huggingface.co/opencv/object_detection_yolox/blob/78c368f74ce73ee28fc7a1be418a598c71b58b52/demo.py) | Apache-2.0 / Apache-2.0 |
| Biển số | LPD YuNet, `license_plate_detection_lpd_yunet_2023mar.onnx`; `962e8d8849878106cb84039dab61cf97bb683b31` | [Model card](https://huggingface.co/opencv/license_plate_detection_yunet), [LICENSE ở revision](https://huggingface.co/opencv/license_plate_detection_yunet/blob/962e8d8849878106cb84039dab61cf97bb683b31/LICENSE), [adapter gốc](https://huggingface.co/opencv/license_plate_detection_yunet/blob/962e8d8849878106cb84039dab61cf97bb683b31/lpd_yunet.py) | Apache-2.0 / Apache-2.0 |
| OCR | CRNN_EN, `text_recognition_CRNN_EN_2021sep.onnx`; `6487ac545965a2c277aff293e2fdded8b0e6f9b9` | [Model card](https://huggingface.co/opencv/text_recognition_crnn), [LICENSE ở revision](https://huggingface.co/opencv/text_recognition_crnn/blob/6487ac545965a2c277aff293e2fdded8b0e6f9b9/LICENSE), [adapter gốc](https://huggingface.co/opencv/text_recognition_crnn/blob/6487ac545965a2c277aff293e2fdded8b0e6f9b9/crnn.py) | Apache-2.0 / Apache-2.0 |

`offline_vision/detectors.py` và `ocr.py` có phần tiền/hậu xử lý được viết lại từ
những adapter trên, được đánh dấu Apache-2.0. Thay đổi gồm interface nhỏ,
RGB/letterbox và NMS xywh đúng cho xe; NMS bằng bbox bao quanh bốn corner cho
biển số; CTC/raw/score theo từng lần đọc và tùy chọn chia hai dòng cho OCR.

Attribution: OpenCV Zoo; YOLOX contributor Sri Siddarth Chakaravarthy;
LPD YuNet contributor Dong Xu, Watrix.ai. CRNN source giữ thông báo:
Copyright (C) 2021, Shenzhen Institute of Artificial Intelligence and Robotics
for Society; third-party copyrights remain with their respective owners.
Không ngụ ý các tổ chức này xác nhận pipeline Như Tùng.

Bản Apache 2.0 nằm trong `licenses/OpenCV-Zoo-APACHE-2.0.txt`. CLI fetch lưu
LICENSE riêng cho từng model cạnh weights. Không đưa weights vào Git.
SHA-256 cụ thể được khóa trong `MODELS` và ghi trong manifest/result.
Tổng weights: 73.8 MB; không tải dataset hoặc train model.

## Phạm vi chất lượng

YOLOX cung cấp lớp xe COCO; adapter chỉ chọn car/bus/truck, không coi nó có
lớp biển số. LPD YuNet là detector biển số riêng, huấn luyện bằng biển Trung
Quốc; cần đánh giá biển Việt Nam độc lập. CRNN EN nhận chữ Latin/số, là OCR
văn bản tổng quát, chưa fine-tune biển Việt Nam. Chia hai dòng hiện là heuristic
bằng tỉ lệ crop, chưa có rectification phối cảnh hay bộ phân tích layout.
Các score không phải cùng một thang đo và không chứng minh xác suất đọc đúng.

Runtime khóa riêng trong requirements-offline.txt. Không phân phối binary
FFmpeg của Homebrew: CLI dùng ffprobe đã có trên máy. Giấy phép binary/dependency
cần đi cùng chúng nếu đóng gói runtime ở bước sau; bản local không thêm chúng
vào image API/web hoặc tạo dịch vụ mới.

## D05b — recognizer so sánh CPU

- Weights: [PaddlePaddle/PP-OCRv6_tiny_rec_onnx model card tại revision](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_rec_onnx/blob/2612ab37152ae0a677521bae4e1e3d4fb4cf7c30/README.md),
  revision `2612ab37152ae0a677521bae4e1e3d4fb4cf7c30`, khai báo Apache-2.0.
  `inference.onnx` 4.462.639 byte, SHA-256
  `9ef676d6ed3c88256a2d92c640c44f25b0c40947e111b14b8be8f594091563e6`.
  `inference.yml` SHA-256
  `66170210bad538e83fff3c4a3867e547d6bf20b50d64b20347c4b913f3034ea1`;
  model card cũng khóa checksum trong `recognizer.py`. CLI từ chối file khác
  checksum, giữ model card/manifest cạnh weights local. Đây là recognizer văn
  bản có từ điển Latin/số, không phải detector hoặc model biển Việt Nam đã đạt.
- Code preprocess/CTC tham khảo [PaddleX processors.py](https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/text_recognition/processors.py),
  revision `c50f5da858020db473a2285f089bb8c7bbd6afdc`, Apache-2.0.
  Copyright (c) 2024 PaddlePaddle Authors. Bản license giữ ở
  `licenses/PaddleX-APACHE-2.0.txt`; adapter local dùng ONNX Runtime, input BGR,
  resize theo tỷ lệ cao 48px, pad phải và CTC; không dùng lexicon sửa ký tự.
- Runtime ONNX Runtime **1.23.2**, MIT ([LICENSE chính thức](https://github.com/microsoft/onnxruntime/blob/v1.23.2/LICENSE));
  PyYAML **6.0.3**, MIT ([nguồn chính thức](https://github.com/yaml/pyyaml/blob/6.0.3/LICENSE)).
  `requirements-benchmark.txt` khóa dependency bổ sung. Chỉ cài venv offline,
  không đóng gói vào app image. Giữ thông báo của dependency nếu phân phối sau.

Điều khoản Apache-2.0 của code/weights được chọn phù hợp mục đích thương mại
với nghĩa vụ giấy phép. Điều này không cấp quyền cho các dataset bên thứ ba.
VNLP/nguồn Việt Nam khảo sát trong D05b chưa có điều khoản thương mại rõ;
không tải archive, không dùng để train trong bước này. Chi tiết nguồn và giới
hạn bằng chứng ở `docs/offline-vision-d05b.md`.

## D05c — YOLOX-Nano training và dataset dự kiến

- [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX),
  source revision `6ddff4824372906469a7fae2dc3206c7aa4bbaee`, Apache-2.0.
  Attribution: Megvii BaseDetection / YOLOX contributors. Bản LICENSE nguyên
  văn trong `licenses/YOLOX-APACHE-2.0.txt`. Source ZIP SHA256
  `647bba7d16cc7e13feb5f2beca0296f86186c944f5a8fa9ccefc2629758bccba`.
- Official pretrained checkpoint [release0.1.1rc0 yolox_nano.pth](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.pth),
  7.694.953bytes, SHA256 đo local
  `cd28f55fbbc1829f99d9ac9b38a16d259a22889739c8728ea877610201feff7b`.
  Official project phân phối checkpoint theo Apache2 của project; release
  không nêu hạn chế weights riêng. Không có model card weights riêng để suy
  ra thêm quyền dữ liệu COCO. Giữ license/source/weights provenance cạnh model;
  không phân phối weights/source tree trong Git. Python tree official được
  đọc trực tiếp từ cache pinned; không sửa code upstream. Head80→1 và adapter
  BGR/letterbox/NMS/export decode là thay đổi cấu hình/wrapper local.
- Dataset dự kiến [biển số xe / datacar v1](https://universe.roboflow.com/datacar-my0w7/bien-so-xe-3w699-avdfe/dataset/1),
  `2025-01-06 5:34pm`, project công bố CC BY4.0. Attribution datacar / Roboflow
  Universe, link nguồn + [license](https://creativecommons.org/licenses/by/4.0/),
  ghi thay đổi classmap/filter/split khi thực hiện. **Chưa tải ZIP**, chưa phân
  phối hoặc xác minh ảnh/nhãn thực. 864 là con số công bố, không phải approved
  training samples. Audit/manual review phải đi trước training.
- PyTorch2.8.0/torchvision0.23.0 cài từ PyPI trong venv riêng; dependencies khóa
  ở `requirements-training.lock.txt`. Runtime/export local CPU, không thêm
  training/inference dependencies vào container API/web.

## D05i Phase 2 — recognizer CPU chẩn đoán

Nguồn/giấy phép được kiểm tra trước inference; không có upload ảnh camera.
Manifest và weights nằm dưới `data/offline-vision/benchmark-models/`, không Git.

| Model | Revision / nguồn chính thức | Giấy phép | Weights byte / SHA-256 |
| --- | --- | --- | --- |
| English PP-OCRv5 mobile (baseline D05f) | [PaddlePaddle card](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec_onnx/blob/3fafbc3b5dcf93dd72add9f48368be8a3a2cd33b/README.md), revision `3fafbc3b5dcf93dd72add9f48368be8a3a2cd33b` | Card weights Apache-2.0; adapter PaddleX Apache-2.0 | 7.848.423 / `b5f833dfc5d0eb71da397b4efa06ebeee9b431b690a47d6af40d77d8eabc557f` |
| PP-OCRv5 server rec | [PaddlePaddle card](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_rec_onnx/blob/b70df217f4fd99d14f970bad092cebe7d74cc4d1/README.md), revision `b70df217f4fd99d14f970bad092cebe7d74cc4d1` | Card weights Apache-2.0; adapter PaddleX Apache-2.0 | 84.503.027 / `d9dc333c9c7b042c6dffb8e33d72b6f65c9c1d463d0a3c2f78174fea55e94752` |
| FastPlateOCR CCT-S v2 global | [Official project](https://github.com/ankandrew/fast-plate-ocr/tree/9ce7a5b64a939aa421c243b331d42e6bc25ffd44), code `9ce7a5b64a939aa421c243b331d42e6bc25ffd44`; [author's release](https://github.com/ankandrew/fast-plate-ocr/releases/tag/arg-plates), asset ID `373528983`, updated 2026-03-14 | MIT official model-author project/release; no separate weights restriction published. This is the model author's release, not license inference from an unrelated wrapper. | 5.262.230 / `384bbbd2cea3ef54761d3df70822ef3a349ee1a112aeafddbe0e3ba06bc6e47b` |

- PP server config SHA `2c719dba044c4e2228aef8ff92f5f575394d75d24c16de096a33b7cfd902f66d`,
  card SHA `806a481f4c15a38feb7103a64ec0e14f83f6a211abb4b0a345bdc3b13145c821`.
  Weights hash matched the official Hugging Face LFS checksum. Both Paddle
  adapters keep BGR/aspect-height48/right-zero-pad and unrestricted CTC from
  the pinned PaddleX preprocessing already attributed above; server may emit
  Chinese/Japanese characters. No charset filtering to make scores improve.
- FastPlate config asset ID `373528962`, SHA
  `0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6`;
  weights/config verified against SHA256 in official GitHub release metadata.
  Pre/postprocessing adapted from [official process.py](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/fast_plate_ocr/core/process.py).
  Copyright (c) 2024 ankandrew; original [MIT LICENSE](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/LICENSE)
  retained in `licenses/FastPlateOCR-MIT.txt` and beside local weights.
  RGB/linear stretch128×64/NHWC uint8; normalization is embedded in the model.
  Ten position heads use digits/A–Z/underscore training pad, not CTC; only
  trailing padding is removed, repeated characters remain. Config lists
  Vietnam among region labels, not a guarantee for Vietnam two-line plates.
  The released metadata has no explicit two-line performance claim.
- Code/weights licenses do not grant rights to the upstream private datasets
  or establish camera recognition quality. Dependencies already installed
  in the separate local venv: no fast-plate-ocr training/Keras install or GPU.

## D05j — dữ liệu sample người dùng cung cấp, đánh giá local

Attribution: THỊ GIÁC MÁY TÍNH / GreenParking; [trang nguồn do người dùng xác nhận](https://thigiacmaytinh.com/tai-nguyen-xu-ly-anh/tong-hop-data-xu-ly-anh/),
[GreenParking được nguồn dẫn](https://github.com/thigiacmaytinh/DataThiGiacMayTinh/blob/main/GreenParking.zip),
[CarTGMT được nguồn dẫn](https://drive.google.com/file/d/1U5ebTzW2c_sVVTCSX1QH-ZJFpLijMdUv/view).
Nguồn mô tả sample để thử chương trình; người dùng cho phép dùng local.
Không thấy giấy phép dataset cụ thể cho phân phối lại/train thương mại;
không tự áp MIT của FastPlate cho ảnh này. Không tải lại, phân phối hoặc
train trong D05j bước chuẩn bị. Giữ bản incoming, manifest/hash nguồn và
ảnh native dẫn xuất riêng. Filename/report/location không tự trở thành GT.
GreenParking ký tự rời chưa dùng đánh giá toàn biển. Xem `docs/offline-vision-d05j.md`.

## D05j Phase D — cấu hình augmentation local

- Albumentations **2.0.8**, metadata package khai báo MIT; tác giả Vladimir
  Iglovikov, Alexander Buslaev, Alexander Parinov. Chỉ cài venv augmentation
  riêng, không đưa vào runtime/API image. Giữ license nếu phân phối sau.
- FastPlateOCR pinned `9ce7a5b64a939aa421c243b331d42e6bc25ffd44` (1.1.0,
  MIT, attribution đã ghi ở trên) cung cấp CLI `--augmentation-path` nhận
  YAML từ `Albumentations.save`. Bản tham khảo/hashes và license lưu local
  cạnh cấu hình, không đưa weights hoặc dữ liệu camera vào Git.
- Module augmentation local là code chuẩn bị riêng. Không mặc định các
  transform label-aware/HEVC/native-size đã hỗ trợ trong upstream loader;
  masked labels `?` chưa dùng train. Chi tiết ở docs/offline-vision-d05j.md.
