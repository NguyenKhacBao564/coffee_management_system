import csv
import html
import json
from pathlib import Path

import cv2
import numpy as np

from .geometry import clip_box
from .selection import vehicle_crop


def prepare_output(path: Path):
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    (path / "evidence").mkdir(mode=0o700)


def save_jpeg(path: Path, image):
    if not image.size or not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 94]):
        raise ValueError("Could not save evidence image")
    path.chmod(0o600)


def save_overview(output: Path, session, frame, box, roi, timestamp):
    folder = output / "evidence" / session.session_id
    folder.mkdir(exist_ok=True, mode=0o700)
    save_jpeg(folder / "overview.jpg", frame)
    annotated = frame.copy()
    points = (np.asarray(roi) * [frame.shape[1], frame.shape[0]]).astype(np.int32)
    cv2.polylines(annotated, [points], True, (20, 170, 210), 3)
    x1,y1,x2,y2 = clip_box(box, frame.shape)
    cv2.rectangle(annotated, (x1,y1), (x2,y2), (40,200,60), 3)
    cv2.putText(annotated, f"{session.session_id} media {timestamp:.3f}s; ROI provisional", (25,45), cv2.FONT_HERSHEY_SIMPLEX, 1, (40,200,60), 2)
    save_jpeg(folder / "annotated.jpg", annotated)
    save_jpeg(folder / "vehicle.jpg", vehicle_crop(frame, box)[0])
    session.evidence.update({"overview": f"evidence/{session.session_id}/overview.jpg", "annotated": f"evidence/{session.session_id}/annotated.jpg",
                             "vehicle_crop": f"evidence/{session.session_id}/vehicle.jpg", "overview_media_seconds": timestamp,
                             "vehicle_box_native": list(box), "native_pixels": [frame.shape[1], frame.shape[0]]})


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_report(output: Path, report: dict):
    write_json(output / "result.json", report)
    with (output / "sessions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["camera_id", "session_id", "start_media_seconds", "end_media_seconds", "proposed_plate", "status", "decision"])
        writer.writeheader()
        for session in report["sessions"]:
            writer.writerow({key:session[key] for key in writer.fieldnames})
    (output / "sessions.csv").chmod(0o600)
    cards = []
    for session in report["sessions"]:
        evidence = session["evidence"]
        imgs = [(evidence.get("annotated"), "Toàn cảnh, ROI và box xe"), (evidence.get("vehicle_crop"), "Crop xe")]
        imgs += [(crop["path"], f"Biển số · {crop['media_seconds']:.3f}s") for crop in evidence.get("plate_crops", [])]
        gallery = "".join(f'<figure><a href="{html.escape(path)}"><img loading="lazy" src="{html.escape(path)}" alt="{html.escape(label)}"></a><figcaption>{html.escape(label)}</figcaption></figure>' for path,label in imgs if path)
        rows = "".join(f"<tr><td>{read['media_seconds']:.3f}s</td><td><pre>{html.escape(read['raw'])}</pre></td><td>{html.escape(read['normalized'])}</td><td>{html.escape(read['model'])} · {html.escape(read['strategy'])}</td></tr>" for read in session["raw_ocr"])
        cards.append(f'''<article><h2>{html.escape(session['session_id'])} · {html.escape(session['proposed_plate'] or 'unknown')}</h2>
<p>{session['start_media_seconds']:.3f}–{session['end_media_seconds']:.3f}s · {html.escape(session['decision'])} · cần xác nhận</p>
<p>Kết thúc phiên: {html.escape(session['end_reason'])}. Gap/EOF không xác nhận xe đã rời cân. <a href="{html.escape(evidence.get('overview', ''))}">Ảnh toàn cảnh gốc</a>.</p>
<p>Track trong lượt chạy: {html.escape(', '.join(session['track_ids']))}. Không phải danh tính xe lâu dài.</p>
<div class="gallery">{gallery}</div><h3>Ứng viên</h3><pre>{html.escape(json.dumps(session['candidates'],ensure_ascii=False,indent=2))}</pre>
<div class="table"><table><thead><tr><th>Media</th><th>OCR gốc</th><th>Chuẩn hóa</th><th>Model/chiến lược</th></tr></thead><tbody>{rows}</tbody></table></div></article>''')
    stats = report["statistics"]
    provenance = "FIXTURE SCRIPTED: chỉ kiểm tra cơ chế pipeline; không phải inference model hoặc nghiệm thu camera công ty." if report["fixture"] else "VIDEO LOCAL / MODEL THẬT: kết quả thử nghiệm cần người xem xác nhận; chưa nghiệm thu độ chính xác camera công ty."
    page = f'''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kiểm tra pipeline offline · {html.escape(report['camera_id'])}</title>
<style>body{{font:15px system-ui;background:#f3f7f4;color:#213d2c;margin:0;padding:24px;max-width:1200px;margin:auto;overflow-wrap:anywhere}}h1{{font-size:27px}}article,.summary{{background:white;border:1px solid #dce5df;border-radius:12px;padding:20px;margin:20px 0}}.gallery{{display:flex;flex-wrap:wrap;gap:16px}}figure{{margin:0;width:min(100%,520px);min-width:0}}img{{max-width:100%;max-height:360px;object-fit:contain}}figcaption{{color:#66786d}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #e5ece7}}.table{{overflow:auto}}a{{color:#22754c}}@media(max-width:600px){{body{{padding:12px}}article{{padding:12px}}}}</style>
<h1>Kiểm tra offline · {html.escape(report['camera_id'])}</h1>
<div class="summary"><strong>{html.escape(provenance)}</strong></div>
<p>Kết quả chưa xác nhận. Thời gian trong video; chỉ có giờ thực khi cung cấp mốc bắt đầu. ROI đang ở trạng thái: {html.escape(report['config']['roi_status'])}.</p>
<div class="summary">{stats['tracks_created']} track · {stats['roi_sessions']} phiên ROI · {stats['sessions_with_plate_detection']} phiên tìm thấy biển số · {stats['unknown_sessions']} unknown.
<p>Không có nhãn đối chiếu: không tính độ chính xác. <a href="result.json">JSON đầy đủ</a> · <a href="sessions.csv">CSV</a> · <a href="review-labels.template.json">Mẫu nhãn thủ công</a></p></div>
{''.join(cards) or '<article>Không có phiên xe vào ROI. Xem sampled-detections.jsonl để kiểm tra detection ngoài ROI.</article>'}
<h2>Thống kê xử lý (MacBook/local, không dự báo cloud)</h2><pre>{html.escape(json.dumps(stats,ensure_ascii=False,indent=2))}</pre>
<details><summary>Model / cấu hình của lượt chạy</summary><pre>{html.escape(json.dumps({'models':report['models'],'config':report['config']},ensure_ascii=False,indent=2))}</pre></details></html>'''
    (output / "review.html").write_text(page, encoding="utf-8"); (output / "review.html").chmod(0o600)
    write_json(output / "review-labels.template.json", {"run_id":report["run_id"], "label_origin":"manual_review_required",
        "roi_ground_truth_sessions":[], "notes":"Fill only after reviewing source video. Empty list is not a negative label. Use evaluate with a separate completed file."})
