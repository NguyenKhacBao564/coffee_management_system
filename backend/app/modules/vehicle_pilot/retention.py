"""Expire and purge evidence binaries after the configured retention window."""
import argparse
import logging
from pathlib import Path
import socket
import time

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.database import make_engine
from app.core.models import utcnow
from app.modules.scale_ingestion.cli import _database_url_for_cli
from app.modules.vehicle_pilot.models import CameraEvidence
from app.modules.vehicle_pilot.storage import EvidenceStorage

logger = logging.getLogger("nhu_tung.vehicle_pilot.retention")


def run_once(session_factory, storage: EvidenceStorage, *, now=None, limit: int = 100) -> dict:
    now = now or utcnow()
    due = []
    with session_factory.begin() as db:
        rows = db.scalars(
            select(CameraEvidence)
            .where(CameraEvidence.retention_until_utc <= now,
                   or_(CameraEvidence.storage_state != "expired", CameraEvidence.purged_at_utc.is_(None)))
            .order_by(CameraEvidence.retention_until_utc, CameraEvidence.id)
            .with_for_update(skip_locked=True)
            .limit(limit)
        ).all()
        for row in rows:
            row.storage_state = "expired"
            due.append((row.id, row.object_key))

    purged = 0
    errors = 0
    for evidence_id, object_key in due:
        try:
            storage.delete(object_key)
            with session_factory.begin() as db:
                row = db.scalar(select(CameraEvidence).where(CameraEvidence.id == evidence_id).with_for_update())
                if row and row.storage_state == "expired":
                    row.purged_at_utc = now
            purged += 1
        except Exception:
            errors += 1
            logger.exception("Evidence retention purge failed", extra={"evidence_id": str(evidence_id)})
    return {"due": len(due), "purged": purged, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Purge private pilot evidence after its configured retention period")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int, choices=[3600, 21600, 86400], default=3600)
    args = parser.parse_args(argv)
    if not args.once and not args.loop:
        parser.error("Choose --once or --loop")
    settings = get_settings()
    engine = make_engine(settings.database_url if Path("/.dockerenv").exists() else _database_url_for_cli())
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    storage = EvidenceStorage(settings.pilot_evidence_root)
    logger.info("Evidence retention worker started", extra={"retention_days": settings.pilot_evidence_retention_days,
        "host": socket.gethostname()})
    try:
        while True:
            result = run_once(session_factory, storage)
            if result["due"] or result["errors"]:
                logger.info("Evidence retention cycle completed", extra=result)
            if args.once:
                return 0 if not result["errors"] else 1
            time.sleep(args.interval_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
