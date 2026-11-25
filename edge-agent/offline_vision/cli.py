import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cv2

from .config import load_config
from .detectors import MODELS, PlateDetector, VehicleDetector
from .evaluate import evaluate
from .export import write_json
from .fixtures import FixtureOCR, FixturePlateDetector, FixtureVehicleDetector, create_fixture
from .ocr import FastPlateOCR, PlateOCR
from .pipeline import run_pipeline
from .profiling import Profiler


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("Video start must have an explicit timezone")
    return parsed.astimezone(timezone.utc)


def fetch_models(folder: Path):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = {}
    for kind, info in MODELS.items():
        path = folder / info["filename"]
        if not path.exists():
            temporary = path.with_suffix(".download")
            if temporary.exists(): raise ValueError("Previous partial download exists; inspect/remove it before retry")
            url = f"https://huggingface.co/{info['repository']}/resolve/{info['revision']}/{info['filename']}"
            try:
                subprocess.run(["curl","--fail","--silent","--show-error","--location","--max-time","180","--max-filesize","40000000",url,"-o",str(temporary)],check=True)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != info["sha256"]:
                    raise ValueError("Downloaded weights do not match pinned SHA-256")
                temporary.rename(path)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError("Existing model differs from pinned checksum; refusing to overwrite")
        path.chmod(0o600)
        license_path = folder / f"{kind}-LICENSE.txt"
        if not license_path.exists():
            subprocess.run(["curl","--fail","--silent","--show-error","--location","--max-time","30",
                            f"https://huggingface.co/{info['repository']}/resolve/{info['revision']}/LICENSE","-o",str(license_path)],check=True)
        license_path.chmod(0o600)
        manifest[kind] = {**info, "bytes":path.stat().st_size,
                          "source_url":f"https://huggingface.co/{info['repository']}/resolve/{info['revision']}/{info['filename']}"}
    write_json(folder / "manifest.json", manifest)
    print(f"Verified three pinned models ({sum(item['bytes'] for item in manifest.values()) / 1e6:.1f} MB); inference stays offline.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="D05 offline vehicle/plate pipeline and manual-label OCR diagnostics; no application DB or network inference")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch-models", help="Explicit small model download, pinned revision/SHA; no dataset")
    fetch.add_argument("--model-dir",type=Path,default=Path("data/offline-vision/models"))
    fixture = sub.add_parser("fixture",help="Create synthetic video + scripted control-test scenario")
    fixture.add_argument("--case",choices=["no-vehicle","outside-roi","enter-exit","short-dropout","no-plate","conflicting-ocr"],required=True)
    fixture.add_argument("--output",type=Path,required=True)
    run = sub.add_parser("run")
    run.add_argument("--video",type=Path,required=True); run.add_argument("--config",type=Path,required=True)
    run.add_argument("--output",type=Path,required=True); run.add_argument("--model-dir",type=Path,default=Path("data/offline-vision/models"))
    run.add_argument("--start-seconds",type=float,default=0); run.add_argument("--end-seconds",type=float)
    run.add_argument("--video-start-utc",type=utc,help="Explicit absolute clock at media timestamp zero; never inferred from filename/overlay")
    run.add_argument("--fixture-scenario",type=Path,help="Scripted test adapters only; result is labeled fixture, never model performance")
    run.add_argument("--plate-model-manifest",type=Path,help="Optional exported one-class YOLOX-Nano; baseline unchanged when omitted")
    run.add_argument("--plate-model-threshold",type=float,help="Explicit threshold selected for the replacement detector; independent of YuNet score")
    run.add_argument("--fastplate-dir", type=Path, help="Use pinned FastPlate CCT-S v2 on the whole original plate crop")
    assessment = sub.add_parser("evaluate",help="Score only explicitly completed manual labels")
    assessment.add_argument("--result",type=Path,required=True); assessment.add_argument("--labels",type=Path,required=True)
    assessment.add_argument("--output",type=Path,required=True)
    prepare = sub.add_parser("prepare-labels", help="Select 30–50 native-pixel PNGs; no OCR ground truth")
    prepare.add_argument("--video", type=Path, action="append", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--count", type=int, default=40)
    prepare.add_argument("--candidate-interval", type=float, default=3)
    prepare.add_argument("--model-dir", type=Path, default=Path("data/offline-vision/models"))
    fetch_rec = sub.add_parser("fetch-benchmark-model", help="Explicit 4.5 MB official pinned CPU recognizer download")
    fetch_rec.add_argument("--output", type=Path, default=Path("data/offline-vision/benchmark-models/paddle-tiny"))
    label_import = sub.add_parser("import-labels", help="Import manually filled CSV into separate labels JSON")
    label_import.add_argument("--dataset", type=Path, required=True); label_import.add_argument("--csv", type=Path, required=True)
    label_import.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("audit-labels", help="Validate manual labels, groups and duplicate split leakage")
    audit.add_argument("--dataset", type=Path, required=True); audit.add_argument("--labels", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    bench = sub.add_parser("benchmark-ocr", help="Paired OCR benchmark, exact whole plate only with manual ground truth")
    bench.add_argument("--dataset", type=Path, required=True); bench.add_argument("--labels", type=Path, required=True)
    bench.add_argument("--output", type=Path, required=True)
    bench.add_argument("--model-dir", type=Path, default=Path("data/offline-vision/models"))
    bench.add_argument("--recognizer-dir", type=Path, default=Path("data/offline-vision/benchmark-models/paddle-tiny"))
    bench.add_argument("--detector-match-iou", type=float, default=.5,
        help="One-to-one manual bbox / fine-tuned detector proposal match threshold; default 0.5")
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch-models": fetch_models(args.model_dir)
        elif args.command == "fetch-benchmark-model":
            from .recognizer import fetch_recognizer
            fetch_recognizer(args.output); print("Verified pinned recognizer weights/config; inference remains local CPU")
        elif args.command == "prepare-labels":
            from .dataset import prepare_dataset
            cv2.setNumThreads(2)
            manifest = prepare_dataset(args.video, args.output, VehicleDetector(args.model_dir,.35), count=args.count, candidate_interval=args.candidate_interval)
            print(json.dumps({"dataset": str(args.output), "frames": len(manifest["frames"]), "status": "awaiting_manual_review"}))
        elif args.command == "import-labels":
            from .dataset import import_csv
            if args.output.exists(): raise ValueError("Labels output exists; refusing overwrite")
            write_json(args.output, import_csv(args.dataset,args.csv)); print(args.output)
        elif args.command == "audit-labels":
            from .dataset import validate_labels, duplicate_audit
            if args.output.exists(): raise ValueError("Audit output exists; refusing overwrite")
            labels = json.loads(args.labels.read_text())
            result = {"manual_counts": validate_labels(labels,args.dataset), **duplicate_audit(labels)}
            write_json(args.output, result); print(json.dumps({k:result[k] for k in ["manual_counts", "training_ready"]}))
        elif args.command == "benchmark-ocr":
            from .benchmark import run_benchmark
            cv2.setNumThreads(2)
            result = run_benchmark(args.dataset,args.labels,args.output,args.model_dir,args.recognizer_dir,
                detector_match_iou=args.detector_match_iou)
            print(json.dumps({"status": result["status"], "manual_counts": result["manual_counts"],
                "detector_assessment": result.get("detector_assessment"), "metrics": result["metrics"]}))
        elif args.command == "fixture": print(create_fixture(args.output,args.case))
        elif args.command == "evaluate":
            if args.output.exists(): raise ValueError("Evaluation output exists; refusing overwrite")
            write_json(args.output,evaluate(json.loads(args.result.read_text()),json.loads(args.labels.read_text())))
            print(args.output)
        else:
            import math
            if not math.isfinite(args.start_seconds) or args.start_seconds < 0 or (args.end_seconds is not None and (not math.isfinite(args.end_seconds) or args.end_seconds <= args.start_seconds)):
                raise ValueError("Invalid media range")
            config = load_config(args.config)
            cv2.setNumThreads(config.cpu_threads)
            profile = Profiler()
            try:
                if args.fixture_scenario:
                    scenario = json.loads(args.fixture_scenario.read_text())
                    detectors = FixtureVehicleDetector(scenario), FixturePlateDetector(scenario), FixtureOCR(scenario)
                else:
                    ocr = FastPlateOCR(args.fastplate_dir) if args.fastplate_dir else PlateOCR(args.model_dir,config.ocr_layout)
                    detectors = VehicleDetector(args.model_dir,config.vehicle_threshold), PlateDetector(args.model_dir,config.plate_threshold), ocr
                    if args.plate_model_manifest:
                        from .fine_tune.detector import YoloXPlateDetector
                        if args.plate_model_threshold is None:raise ValueError('Replacement detector requires its own explicit --plate-model-threshold')
                        replacement=YoloXPlateDetector(args.plate_model_manifest,threshold=args.plate_model_threshold)
                        if replacement.metadata['purpose']=='synthetic_preflight_fixture':raise ValueError('Preflight fixture checkpoint is not a camera model')
                        detectors=detectors[0],replacement,detectors[2]
                report = run_pipeline(args.video,args.output,config,*detectors,start=args.start_seconds,end=args.end_seconds,
                                      video_start_utc=args.video_start_utc,profile=profile,fixture=bool(args.fixture_scenario))
                print(json.dumps({"result":str(args.output / "result.json"),"review":str(args.output / "review.html"),"statistics":report["statistics"]},ensure_ascii=False,indent=2))
            finally:
                if not profile.stopped.is_set(): profile.finish()
    except (ValueError, TypeError, KeyError, OSError, ImportError, subprocess.CalledProcessError, cv2.error) as exc:
        print(f"Offline pipeline failed: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
