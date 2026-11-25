"""CUDA training entry point with bounded time, epoch validation and resumable state."""
import argparse
import json
import math
import os
import random
import signal
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .assets import make_model
from .audit import file_hash
from .engine import batch, configuration, load_manifest
from .adaptation import load_policy, epoch_order, transform, initialize


CONFIDENCE = 0.25
NMS_IOU = 0.45
MATCH_IOU = 0.50


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_torch_save(torch, value, path):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        torch.save(value, name)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def iou(a, b):
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (aa + bb - inter) if aa + bb > inter else 0.0


def validate(model, records, size, device):
    """Fixed-threshold validation; unmatched means annotation-relative, not verified FP."""
    import torch

    previous = model.training
    decode = model.head.decode_in_inference
    model.eval()
    model.head.decode_in_inference = True
    true_plates = true_positive = unmatched = 0
    matched_ious = []
    per_image = []
    try:
        with torch.inference_mode():
            for record in records:
                image = cv2.imread(record["image_path"])
                if image is None or image.shape[:2] != (record["height"], record["width"]):
                    raise ValueError(f"Validation image changed: {record['sample_id']}")
                images, _, _ = batch([record], size)
                scale = min(size / record["height"], size / record["width"])
                predictions = model(images.to(device, non_blocking=True))[0].float().cpu().numpy()
                scores = predictions[:, 4] * predictions[:, 5]
                keep = np.flatnonzero(scores >= CONFIDENCE)
                boxes = []
                selected_scores = []
                for index in keep:
                    cx, cy, width, height = predictions[index, :4]
                    x1 = max(0.0, (cx - width / 2) / scale)
                    y1 = max(0.0, (cy - height / 2) / scale)
                    x2 = min(float(record["width"]), (cx + width / 2) / scale)
                    y2 = min(float(record["height"]), (cy + height / 2) / scale)
                    if x2 > x1 and y2 > y1:
                        boxes.append([x1, y1, x2 - x1, y2 - y1])
                        selected_scores.append(float(scores[index]))
                if boxes:
                    chosen = cv2.dnn.NMSBoxes(boxes, selected_scores, CONFIDENCE, NMS_IOU, top_k=300)
                    indices = np.asarray(chosen).reshape(-1).tolist() if len(chosen) else []
                else:
                    indices = []
                detected = [[boxes[i][0], boxes[i][1], boxes[i][0] + boxes[i][2], boxes[i][1] + boxes[i][3]] for i in indices]
                gt = [item["bbox"] for item in record["boxes"]]
                truth = len(gt)
                true_plates += truth
                available = set(range(len(gt)))
                matched = 0
                for pred in sorted(detected, key=lambda box: max((iou(box, target) for target in gt), default=0), reverse=True):
                    best = max(available, key=lambda item: iou(pred, gt[item]), default=None)
                    overlap = iou(pred, gt[best]) if best is not None else 0
                    if best is not None and overlap >= MATCH_IOU:
                        available.remove(best)
                        matched += 1
                        matched_ious.append(overlap)
                true_positive += matched
                extra = max(0, len(detected) - matched)
                unmatched += extra
                per_image.append({"sample_id": record["sample_id"], "ground_truth": truth,
                                  "matched": matched, "unmatched_predictions": extra})
    finally:
        model.head.decode_in_inference = decode
        model.train(previous)
    return {"split_images": len(records), "true_plates": true_plates,
            "matched_plates_iou_050": true_positive,
            "annotation_relative_recall_iou_050": true_positive / true_plates if true_plates else None,
            "unmatched_predictions_per_image": unmatched / len(records) if records else None,
            "mean_matched_iou": float(np.mean(matched_ious)) if matched_ious else None,
            "confidence_threshold": CONFIDENCE, "nms_iou": NMS_IOU,
            "match_iou": MATCH_IOU,
            "interpretation": "Published annotations are unverified. Unmatched predictions are annotation-relative and are not confirmed false positives; validation has no confirmed negative images.",
            "images": per_image}


def checkpoint_state(torch, model, optimizer, scheduler, *, total, epoch, cursor, config,
                     dataset_sha, config_sha, metadata, started_utc, best_rank,
                     best_metrics, val_history, policy_sha=None):
    return {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(), "steps": total, "epoch": epoch, "cursor": cursor,
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
            "seed": config["seed"], "dataset_sha256": dataset_sha,
            "config_sha256": config_sha, "model_revision": metadata["source_revision"],
            "weights_sha256": metadata["weights_sha256"], "purpose": "d05f_cuda_training" if policy_sha else "d05d_cuda_training",
            "policy_sha256": policy_sha, "initialization": metadata['initialization'],
            "training_started_utc": started_utc, "best_rank": best_rank,
            "best_validation": best_metrics, "validation_history": val_history,
            "validation_policy": {"confidence": CONFIDENCE, "nms_iou": NMS_IOU, "match_iou": MATCH_IOU}}


def train(args):
    import torch

    config = configuration(args.config)
    manifest, train_records = load_manifest(args.manifest)
    val_records = [r for r in manifest["records"] if r["split"] == "val"]
    policy = load_policy(args.policy)
    policy_sha = file_hash(args.policy) if args.policy else None
    cpu = args.device == 'cpu'
    if cpu and args.command != 'preflight': raise ValueError('CPU is only allowed for bounded preflight')
    if args.command == 'preflight' and not 1 <= args.max_steps_this_run <= 4:
        raise ValueError('Preflight invocation is capped at four updates')
    if not cpu and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; refusing to silently run on CPU")
    if manifest["purpose"] != "reviewed_real_training" or not val_records:
        raise ValueError("CUDA training requires the real train and validation splits")
    if manifest["batch_size"] != config["batch_size"]:
        raise ValueError("Manifest and training config batch sizes differ")
    if args.max_seconds <= 0 or args.max_steps_this_run < 0:
        raise ValueError("Time and step bounds must be positive")
    if bool(args.init_checkpoint) != bool(args.init_sha256): raise ValueError('Initialization checkpoint and hash must be paired')
    if policy:
        if not args.init_checkpoint: raise ValueError('D05f requires a hashed D05d initialization')
        if any(r['label_origin'] != 'roboflow_published_annotation' for r in val_records):
            raise ValueError('D05f selects checkpoints on public validation only')
        if not any(r['label_origin']=='manual_review' for r in train_records): raise ValueError('No confirmed camera training samples')
    if (args.output/'last.pth').exists() and not args.resume: raise ValueError('Existing training output requires explicit resume')

    device = torch.device('cpu' if cpu else 'cuda:0')
    torch.set_num_threads(config["threads"])
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    if not cpu: torch.cuda.manual_seed_all(config["seed"])
    torch.use_deterministic_algorithms(True, warn_only=True)
    model, metadata = make_model(args.assets)
    if args.init_checkpoint:
        metadata['initialization'] = initialize(model, args.init_checkpoint, args.init_sha256)
    model = model.to(device)
    model.head.decode_in_inference = True
    optimizer = torch.optim.SGD(model.parameters(), lr=config["learning_rate"], momentum=0.9)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=config["max_steps"], eta_min=config["learning_rate"] * 0.1)
    dataset_sha, config_sha = file_hash(args.manifest), file_hash(args.config)
    total, epoch, cursor = 0, 0, 0
    best_rank, best_metrics = None, None
    val_history = []
    started_utc = utc_now()
    if args.resume:
        saved = torch.load(args.resume, map_location="cpu", weights_only=True)
        if saved["dataset_sha256"] != dataset_sha or saved["config_sha256"] != config_sha:
            raise ValueError("Resume dataset/config hash mismatch")
        if saved.get('policy_sha256') != policy_sha or saved.get('initialization', metadata['initialization']) != metadata['initialization']:
            raise ValueError('Resume policy/initialization mismatch')
        if "scheduler" not in saved:
            raise ValueError("Resume checkpoint has no scheduler state; use a D05d checkpoint")
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        scheduler.load_state_dict(saved["scheduler"])
        total, epoch, cursor = saved["steps"], saved["epoch"], saved["cursor"]
        torch.set_rng_state(saved["torch_rng"])
        if not cpu: torch.cuda.set_rng_state_all(saved["cuda_rng"])
        started_utc = saved["training_started_utc"]
        best_rank, best_metrics = saved["best_rank"], saved["best_validation"]
        val_history = saved["validation_history"]

    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = args.output / "metrics.jsonl"
    process_started = time.monotonic()
    process_cpu = time.process_time()
    peak_allocated = 0
    batch_times = []
    loss_window = []
    save_every = args.save_every
    epoch_samples = len(epoch_order(train_records, config['seed'], 0, policy))
    batches_per_epoch = math.ceil(epoch_samples / config["batch_size"])
    step_limit = config["max_steps"]
    if args.max_steps_this_run:
        step_limit = min(step_limit, total + args.max_steps_this_run)
    deadline = process_started + args.max_seconds
    stop_requested = False
    def request_stop(signum, _frame):
        nonlocal stop_requested
        stop_requested = True
    old_handlers = {s: signal.signal(s, request_stop) for s in (signal.SIGTERM, signal.SIGINT)}

    def save_checkpoint():
        state = checkpoint_state(torch, model, optimizer, scheduler, total=total, epoch=epoch,
            cursor=cursor, config=config, dataset_sha=dataset_sha, config_sha=config_sha,
            metadata=metadata, started_utc=started_utc, best_rank=best_rank,
            best_metrics=best_metrics, val_history=val_history, policy_sha=policy_sha)
        atomic_torch_save(torch, state, args.output / "last.pth")

    try:
        model.train()
        if not cpu: torch.cuda.reset_peak_memory_stats(device)
        while epoch < config["epochs"] and total < step_limit and time.monotonic() < deadline and not stop_requested:
            order = epoch_order(train_records, config['seed'], epoch, policy)
            while cursor < batches_per_epoch and total < step_limit and time.monotonic() < deadline and not stop_requested:
                selected = order[cursor * config["batch_size"]:(cursor + 1) * config["batch_size"]]
                chosen = [train_records[i] for i in selected]
                tick = time.perf_counter()
                images, targets, picture = batch(chosen, config["input_size"],
                    transform=transform(config['seed'] + epoch * batches_per_epoch + cursor) if policy else None)
                if total == 0 and cursor == 0 and not (args.output / "batch.png").exists():
                    if not cv2.imwrite(str(args.output / "batch.png"), picture):
                        raise ValueError("Failed to save real training batch visualization")
                    (args.output / "batch.png").chmod(0o600)
                images = images.to(device, non_blocking=True)
                targets = targets.to(device, non_blocking=True)
                optimizer.zero_grad(set_to_none=True)
                losses = model(images, targets)
                loss = losses["total_loss"]
                if not torch.isfinite(loss):
                    raise FloatingPointError("Nonfinite CUDA training loss")
                loss.backward()
                optimizer.step()
                scheduler.step()
                if not cpu: torch.cuda.synchronize(device)
                elapsed = time.perf_counter() - tick
                batch_times.append(elapsed)
                loss_window.append(float(loss.detach().cpu()))
                total += 1
                cursor += 1
                if not cpu: peak_allocated = max(peak_allocated, torch.cuda.max_memory_allocated(device))
                record = {"event": "step", "step": total, "epoch": epoch + 1,
                    "batch_in_epoch": cursor, "batches_per_epoch": batches_per_epoch,
                    "loss": loss_window[-1], "lr": scheduler.get_last_lr()[0],
                    "batch_seconds": elapsed, "gpu_memory_allocated_bytes": 0 if cpu else torch.cuda.memory_allocated(device),
                    "sample_ids": [r["sample_id"] for r in chosen]}
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                if total % save_every == 0:
                    save_checkpoint()
            if cursor == batches_per_epoch:
                epoch += 1
                cursor = 0
                metrics = validate(model, val_records, config["input_size"], device)
                recall = metrics["annotation_relative_recall_iou_050"] or 0.0
                extras = metrics["unmatched_predictions_per_image"] or 0.0
                rank = (recall, -extras)
                val_history.append({"epoch": epoch, "step": total, **metrics})
                improved = best_rank is None or rank > tuple(best_rank)
                if improved:
                    best_rank, best_metrics = rank, metrics
                    state = checkpoint_state(torch, model, optimizer, scheduler, total=total,
                        epoch=epoch, cursor=cursor, config=config, dataset_sha=dataset_sha,
                        config_sha=config_sha, metadata=metadata, started_utc=started_utc,
                        best_rank=best_rank, best_metrics=best_metrics, val_history=val_history, policy_sha=policy_sha)
                    atomic_torch_save(torch, state, args.output / "best.pth")
                save_checkpoint()
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"event": "validation", "epoch": epoch, "step": total,
                        "best": improved, **metrics}, ensure_ascii=False) + "\n")
                if args.validate_after:
                    break
        if args.validate_after and cursor:
            metrics = validate(model, val_records, config["input_size"], device)
            recall = metrics["annotation_relative_recall_iou_050"] or 0.0
            extras = metrics["unmatched_predictions_per_image"] or 0.0
            rank = (recall, -extras)
            if best_rank is None or rank > tuple(best_rank):
                best_rank, best_metrics = rank, metrics
                atomic_torch_save(torch, checkpoint_state(torch, model, optimizer, scheduler,
                    total=total, epoch=epoch, cursor=cursor, config=config,
                    dataset_sha=dataset_sha, config_sha=config_sha, metadata=metadata,
                    started_utc=started_utc, best_rank=best_rank, best_metrics=best_metrics,
                    val_history=val_history, policy_sha=policy_sha), args.output / "best.pth")
        save_checkpoint()
    except BaseException:
        if model is not None:
            try:
                save_checkpoint()
            except Exception:
                pass
        raise
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)

    elapsed = time.monotonic() - process_started
    result = {"status": "stopped_by_signal" if stop_requested else
              "time_limit" if time.monotonic() >= deadline else
              "step_limit" if total >= step_limit else
              "epoch_limit" if epoch >= config["epochs"] else "complete",
        "steps_this_run": total - (saved["steps"] if args.resume else 0) if args.resume else total,
        "total_steps": total, "epochs_completed": epoch, "cursor": cursor,
        "batches_per_epoch": batches_per_epoch, "train_images": len(train_records),
        "validation_images": len(val_records), "batch_size": config["batch_size"],
        "last_batch_size": epoch_samples % config["batch_size"] or config["batch_size"],
        "samples_per_epoch": epoch_samples, "policy_sha256": policy_sha, "policy": policy, "device": str(device),
        "drop_last": False, "wall_seconds": elapsed,
        "average_batch_seconds": float(np.mean(batch_times)) if batch_times else None,
        "p95_batch_seconds": float(np.percentile(batch_times, 95)) if batch_times else None,
        "cpu_seconds": time.process_time() - process_cpu,
        "peak_cuda_memory_allocated_bytes": 0 if cpu else max(peak_allocated, torch.cuda.max_memory_allocated(device)),
        "validation_history": val_history, "best_validation": best_metrics,
        "pretrained_initialization": metadata["initialization"],
        "dataset_sha256": dataset_sha, "config_sha256": config_sha,
        "started_utc": started_utc, "finished_utc": utc_now(),
        "resume_from": str(args.resume) if args.resume else None,
        "test_used": False}
    tmp = args.output / "run.json.tmp"
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, args.output / "run.json")
    return result


def evaluate_checkpoint(args):
    import torch

    if args.split == "test" and not args.frozen_checkpoint_and_thresholds:
        raise ValueError("Test requires selected checkpoint and thresholds frozen on validation")
    config = configuration(args.config)
    manifest, _ = load_manifest(args.manifest)
    records = [r for r in manifest["records"] if r["split"] == args.split]
    model, _ = make_model(args.assets, pretrained=False)
    saved = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    if saved["dataset_sha256"] != file_hash(args.manifest) or saved["config_sha256"] != file_hash(args.config):
        raise ValueError("Evaluation data/config hash differs from checkpoint")
    model.load_state_dict(saved["model"])
    model = model.cuda()
    result = {"split": args.split, "checkpoint_sha256": file_hash(args.checkpoint),
        "dataset_sha256": file_hash(args.manifest), "selected_by_validation": args.split == "test",
        "checkpoint_epoch": saved["epoch"], "checkpoint_step": saved["steps"],
        **validate(model, records, config["input_size"], torch.device("cuda:0"))}
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    os.chmod(args.output, 0o600)
    return result


def main():
    parser = argparse.ArgumentParser(description="Bounded CUDA fine-tuning for D05d")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "train"):
        p = sub.add_parser(name)
        for arg in ("manifest", "config", "assets", "output"):
            p.add_argument("--" + arg, type=Path, required=True)
        p.add_argument("--resume", type=Path)
        p.add_argument('--policy', type=Path)
        p.add_argument('--init-checkpoint', type=Path)
        p.add_argument('--init-sha256')
        p.add_argument('--device', choices=('cpu','cuda'), default='cuda')
        p.add_argument("--max-seconds", type=int, default=900 if name == "preflight" else 7200)
        p.add_argument("--max-steps-this-run", type=int, default=2 if name == "preflight" else 0)
        p.add_argument("--save-every", type=int, default=10 if name == "preflight" else 25)
        p.add_argument("--validate-after", action="store_true")
    p = sub.add_parser("evaluate")
    for arg in ("manifest", "config", "assets", "checkpoint", "output"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--split", choices=("val", "test"), required=True)
    p.add_argument("--frozen-checkpoint-and-thresholds", action="store_true")
    args = parser.parse_args()
    if args.command == "evaluate":
        result = evaluate_checkpoint(args)
    else:
        result = train(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
