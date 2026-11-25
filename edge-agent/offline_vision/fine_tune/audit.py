"""Preserve raw exports; audit geometry, pixels, splits and manual review metadata."""
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import stat
import zipfile
import unicodedata

import cv2
import numpy as np

from ..export import write_json
from ..sampling import image_hash, hash_distance

SPLITS = {"train": "train", "valid": "val", "val": "val", "test": "test"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
REVIEW_FIELDS = ["sample_id", "image_path", "original_split", "annotation_review", "plate_presence",
                 "layout", "vehicle_type", "vehicle_group_id", "capture_group_id", "split", "notes"]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def contained(root, relative):
    root = Path(root).resolve(); path = (root / relative).resolve()
    if not path.is_relative_to(root): raise ValueError("Path escapes dataset root")
    return path


def extract_archive(archive, output):
    """No execution; bounded ZIP extraction, no symlinks or path traversal."""
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 20000 or sum(e.file_size for e in entries) > 2 * 1024**3:
            raise ValueError("Archive exceeds 20,000 files / 2 GiB uncompressed bound")
        paths = set()
        for entry in entries:
            target = contained(output, entry.filename)
            key = unicodedata.normalize('NFC',str(target)).casefold()
            if key in paths or stat.S_ISLNK(entry.external_attr >> 16) or '\\' in entry.filename:
                raise ValueError("Duplicate archive path or symlink")
            paths.add(key)
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        for entry in entries:
            target = contained(output, entry.filename)
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True, mode=0o700); continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with bundle.open(entry) as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination)
            target.chmod(0o600)
    return {"archive_sha256": file_hash(archive), "archive_bytes": archive.stat().st_size,
            "extracted_files": len(entries), "raw_root": str(output.resolve())}


def perceptual_hash(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    values = cv2.dct(cv2.resize(gray, (32, 32)).astype(np.float32))[:8, :8].reshape(-1)
    median = np.median(values[1:])
    return sum(int(v > median) << i for i, v in enumerate(values))


def valid_box(box, width, height):
    return (len(box) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in box)
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)


def parse_coco(root, classes):
    records, issues, inventories = [], [], []
    for labels in sorted(root.rglob("*coco*.json")):
        data = json.loads(labels.read_text())
        if not all(k in data for k in ["images", "annotations", "categories"]): continue
        categories = {c["id"]: c["name"] for c in data["categories"]}
        inventories.append({"path": str(labels.relative_to(root)), "sha256": file_hash(labels), "categories": categories})
        ids, annotation_ids, annotations = set(), set(), {}
        for annotation in data["annotations"]:
            if annotation.get('id') in annotation_ids:issues.append({'file':str(labels),'reason':'duplicate_coco_annotation_id','id':annotation.get('id')})
            annotation_ids.add(annotation.get('id'))
            annotations.setdefault(annotation["image_id"], []).append(annotation)
        for item in data["images"]:
            if item["id"] in ids: issues.append({"file": str(labels), "reason": "duplicate_coco_image_id", "id": item["id"]})
            ids.add(item["id"])
            try: path = contained(root, str((labels.parent / item["file_name"]).relative_to(root)))
            except ValueError:
                issues.append({"file": str(labels), "reason": "image_path_outside_root"}); continue
            boxes, errors = [], []
            for a in annotations.get(item["id"], []):
                name = categories.get(a.get("category_id"))
                if name not in classes: errors.append("unexpected_class"); continue
                box = a.get("bbox", [])
                if len(box) != 4 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in box):
                    errors.append("invalid_bbox_values"); continue
                x, y, w, h = box
                boxes.append({"bbox": [x, y, x + w, y + h], "class": "license_plate", "original_class": name})
            records.append({"image_path": str(path), "original_split": next((SPLITS[p] for p in labels.parts if p in SPLITS), "unassigned"),
                "declared_width": item.get("width"), "declared_height": item.get("height"), "boxes": boxes,
                "errors": errors, "label_path": str(labels), "original_image_id": item["id"]})
        for image_id in annotations.keys() - ids:
            issues.append({"file": str(labels), "reason": "annotation_without_image_id", "id": image_id})
    return records, issues, inventories


def parse_yolo(root, classes):
    import yaml
    configuration = next(iter(sorted(root.rglob("data.yaml"))), None)
    if configuration is None: return [], [], []
    cfg = yaml.safe_load(configuration.read_text()); names = cfg["names"]
    names = {int(k): v for k, v in names.items()} if isinstance(names, dict) else dict(enumerate(names))
    records, issues = [], []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in IMAGE_SUFFIXES or "images" not in path.parts: continue
        label = Path(str(path).replace("/images/", "/labels/")).with_suffix(".txt")
        boxes, errors = [], []
        image = cv2.imread(str(path)); h, w = image.shape[:2] if image is not None else (0, 0)
        if not label.is_file(): errors.append("missing_label_file")
        else:
            for line in label.read_text().splitlines():
                fields = line.split()
                if len(fields) != 5: errors.append("invalid_yolo_row"); continue
                try:
                    kind = int(fields[0]); cx, cy, bw, bh = map(float, fields[1:])
                    if names.get(kind) not in classes: errors.append("unexpected_class"); continue
                    boxes.append({"bbox": [(cx-bw/2)*w, (cy-bh/2)*h, (cx+bw/2)*w, (cy+bh/2)*h],
                                  "class": "license_plate", "original_class": names[kind]})
                except ValueError: errors.append("invalid_yolo_values")
        records.append({"image_path": str(path.resolve()), "original_split": next((SPLITS[p] for p in path.parts if p in SPLITS), "unassigned"),
            "boxes": boxes, "errors": errors, "label_path": str(label), "declared_width": w, "declared_height": h})
    return records, issues, [{"path": str(configuration.relative_to(root)), "sha256": file_hash(configuration), "categories": names}]


def contact_sheets(records, output, *, per_page=24):
    pages = []
    for start in range(0, len(records), per_page):
        canvas = np.full((6*240, 4*360, 3), 246, np.uint8)
        for offset, record in enumerate(records[start:start+per_page]):
            image = cv2.imread(record["image_path"])
            if image is not None:
                for a in record["boxes"]:
                    if valid_box(a["bbox"], image.shape[1], image.shape[0]):
                        x1,y1,x2,y2 = map(round,a["bbox"]);cv2.rectangle(image,(x1,y1),(x2,y2),(0,210,50),2)
                scale = min(352/image.shape[1], 197/image.shape[0]);thumb=cv2.resize(image,(round(image.shape[1]*scale),round(image.shape[0]*scale)))
                y,x = (offset//4)*240,(offset%4)*360;canvas[y:y+thumb.shape[0],x:x+thumb.shape[1]]=thumb
            else: y,x = (offset//4)*240,(offset%4)*360
            caption=f"{record['sample_id']} {record['original_split']} boxes={len(record['boxes'])}"
            cv2.putText(canvas,caption,(x+4,y+215),cv2.FONT_HERSHEY_SIMPLEX,.4,(20,20,20),1)
            cv2.putText(canvas,','.join(record['errors'])[:50],(x+4,y+233),cv2.FONT_HERSHEY_SIMPLEX,.35,(20,20,180),1)
        name=f"contact-{start//per_page+1:03d}.jpg";path=output/name
        cv2.imwrite(str(path),canvas);path.chmod(0o600);pages.append(name)
    return pages


def audit_dataset(raw_root, output, *, source, version, license_name="CC-BY-4.0", classes=("biensoxehoi", "license_plate")):
    raw_root=raw_root.resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    records, issues, inventories=parse_coco(raw_root,set(classes))
    if not records:records,issues,inventories=parse_yolo(raw_root,set(classes))
    if not records:raise ValueError("No supported COCO JSON or YOLO image/label inventory found")
    image_inventory={str(p.resolve()) for p in raw_root.rglob('*') if p.suffix.lower() in IMAGE_SUFFIXES}
    for extra in sorted(image_inventory-{r['image_path'] for r in records}):
        issues.append({'image_path':extra,'reason':'image_not_in_label_inventory'})
    for index,r in enumerate(records):
        r['sample_id']=f"external-{index+1:05d}";r['file_sha256']=file_hash(r['image_path']) if Path(r['image_path']).is_file() else None
        image=cv2.imread(r['image_path'])
        if image is None:r['errors'].append('image_decode_failed');continue
        h,w=image.shape[:2];r.update(width=w,height=h,pixel_sha256=hashlib.sha256(f'{w}x{h}:'.encode()+image.tobytes()).hexdigest(),
                                    phash=perceptual_hash(image),dhash=image_hash(image))
        if (r['declared_width'],r['declared_height'])!=(w,h):r['errors'].append('declared_dimensions_mismatch')
        for a in r['boxes']:
            b=a['bbox']
            if not valid_box(b,w,h):r['errors'].append('bbox_outside_or_degenerate');continue
            a['pixels']=[b[2]-b[0],b[3]-b[1]];a['relative_area']=(b[2]-b[0])*(b[3]-b[1])/(w*h)
        if len({tuple(a['bbox']) for a in r['boxes']})!=len(r['boxes']):r['errors'].append('duplicate_bbox_annotation')
        if not r['boxes']:r['errors'].append('empty_annotations_not_confirmed_negative')
        r['structurally_usable']=not r['errors'];r['manual_review']='pending'
    pairs=[]
    for i,a in enumerate(records):
        if 'pixel_sha256' not in a:continue
        for b in records[i+1:]:
            if 'pixel_sha256' not in b:continue
            exact=a['pixel_sha256']==b['pixel_sha256'];pd=hash_distance(a['phash'],b['phash']);dd=hash_distance(a['dhash'],b['dhash'])
            if exact or (pd<=6 and dd<=8):
                pairs.append({'sample_ids':[a['sample_id'],b['sample_id']],'kind':'exact_pixels' if exact else 'near_duplicate_suspect',
                              'phash_distance':pd,'dhash_distance':dd,'cross_split':a['original_split']!=b['original_split']})
    counts={s:{'images':sum(r['original_split']==s for r in records),'boxes':sum(len(r['boxes']) for r in records if r['original_split']==s),
        'structurally_usable':sum(r.get('structurally_usable',False) for r in records if r['original_split']==s)} for s in ['train','val','test','unassigned']}
    manifest={'schema_version':1,'purpose':'external dataset audit; semantic labels and vehicle/capture groups await human review',
        'raw_root':str(raw_root),'source':source,'version':str(version),'license':license_name,'class_map':{n:'license_plate' for n in classes},
        'label_inventories':inventories,'records':records,'issues':issues,'duplicate_pairs':pairs,'counts':counts,
        'manual_metadata':{'layout':'unknown until reviewed; aspect ratio is not ground truth','vehicle_type':'unknown; not present in plate class labels','vehicle_capture_groups':'unknown until reviewed'},
        'training_ready':False}
    write_json(output/'audit.json',manifest)
    with (output/'review.template.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=REVIEW_FIELDS);writer.writeheader()
        for r in records:writer.writerow({'sample_id':r['sample_id'],'image_path':r['image_path'],'original_split':r['original_split'],
            'annotation_review':'pending','plate_presence':'unreviewed','layout':'unknown','vehicle_type':'unknown','split':r['original_split']})
    (output/'review.template.csv').chmod(0o600)
    pages=contact_sheets(records,output);write_json(output/'contact-pages.json',pages)
    sizes=[a['pixels'] for r in records for a in r['boxes'] if 'pixels' in a]
    summary={'counts':counts,'issue_count':len(issues),'images_with_errors':sum(bool(r['errors']) for r in records),
        'exact_duplicate_pairs':sum(p['kind']=='exact_pixels' for p in pairs),'near_duplicate_suspect_pairs':sum(p['kind']=='near_duplicate_suspect' for p in pairs),
        'cross_split_pairs':sum(p['cross_split'] for p in pairs),'plate_width_percentiles':np.percentile([s[0] for s in sizes],[0,25,50,75,100]).tolist() if sizes else [],
        'plate_height_percentiles':np.percentile([s[1] for s in sizes],[0,25,50,75,100]).tolist() if sizes else [],
        'one_two_line_and_vehicle_type_counts':None,'manual_reviewed_images':0,'training_ready':False,'contact_sheets':pages}
    write_json(output/'summary.json',summary);return manifest
