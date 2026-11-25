"""Inspect evidence DB/filesystem consistency; never deletes evidence automatically."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.modules.scale_ingestion.cli import _local_session_scope
from app.modules.vehicle_pilot.models import CameraEvidence
from app.modules.vehicle_pilot.storage import EvidenceStorage


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit/repair pilot evidence references without deleting files")
    parser.add_argument("--repair-states", action="store_true", help="Repair only DB state when an existing file has matching SHA-256")
    args = parser.parse_args(argv)
    storage = EvidenceStorage()
    with _local_session_scope() as db:
        rows = db.scalars(select(CameraEvidence).order_by(CameraEvidence.facility_id, CameraEvidence.object_key)).all()
        known = set()
        report = {"records": 0, "stored_ok": 0, "state_repaired": 0, "missing_or_mismatch": [], "orphans": []}
        for row in rows:
            report["records"] += 1
            path = storage.path(row.object_key)
            known.add(path)
            if row.storage_state == "expired":
                if path.is_file() and row.purged_at_utc is None:
                    report["missing_or_mismatch"].append({"evidence_id": str(row.id), "state": "expired_file_pending_purge"})
                continue
            if not path.is_file():
                if row.storage_state != "missing":
                    row.storage_state = "missing"
                report["missing_or_mismatch"].append({"evidence_id": str(row.id), "state": "file_missing"})
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != row.sha256:
                report["missing_or_mismatch"].append({"evidence_id": str(row.id), "state": "sha256_mismatch"})
                continue
            if row.storage_state != "stored":
                if args.repair_states:
                    row.storage_state = "stored"
                    report["state_repaired"] += 1
                else:
                    report["missing_or_mismatch"].append({"evidence_id": str(row.id), "state": f"file_present_db_{row.storage_state}"})
            else:
                report["stored_ok"] += 1
        if args.repair_states:
            db.commit()
        else:
            db.rollback()
    if storage.root.exists():
        for path in storage.root.rglob("*"):
            if not path.is_file() or path.name.endswith(".tmp") or path.name.startswith("."):
                continue
            if path not in known:
                report["orphans"].append(str(path.relative_to(storage.root)))
    os.umask(0o077)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["missing_or_mismatch"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
