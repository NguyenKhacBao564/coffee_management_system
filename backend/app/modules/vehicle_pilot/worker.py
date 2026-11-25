"""Durable, single-claim mock AI worker. It deliberately never sends images to a provider."""
import argparse
from datetime import timedelta
import os
import socket
import time
from uuid import uuid4

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.database import make_engine
from app.core.models import utcnow
from app.modules.scale_ingestion.cli import _database_url_for_cli
from app.modules.vehicle_pilot.models import VehicleAIAttempt, VehicleAIJob


def _run_once(session_factory, owner: str) -> bool:
    now = utcnow()
    with session_factory.begin() as db:
        job = db.scalar(select(VehicleAIJob).where(
            or_(VehicleAIJob.status == "queued", (VehicleAIJob.status == "claimed") & (VehicleAIJob.lease_until < now)),
            VehicleAIJob.deadline_at > now,
        ).order_by(VehicleAIJob.queued_at, VehicleAIJob.id).with_for_update(skip_locked=True).limit(1))
        if job is None:
            db.query(VehicleAIJob).filter(VehicleAIJob.status.in_(["queued", "claimed"]), VehicleAIJob.deadline_at <= now).update(
                {VehicleAIJob.status: "expired", VehicleAIJob.finished_at: now, VehicleAIJob.error_code: "queue_deadline_exceeded"}, synchronize_session=False)
            return False
        if job.provider != "mock":
            job.status = "needs_review"
            job.finished_at = now
            job.error_code = "provider_not_enabled_in_worker"
            return True
        if job.attempts >= 3:
            job.status = "needs_review"
            job.finished_at = now
            job.error_code = "attempt_limit_reached"
            return True
        job.attempts += 1
        attempt = VehicleAIAttempt(id=uuid4(), job_id=job.id, attempt_number=job.attempts,
            status="claimed", started_at=now, reserved_usd=0, usage_json={}, result_json={})
        job.status = "claimed"
        job.lease_owner = owner
        job.lease_until = now + timedelta(seconds=30)
        db.add(attempt)
        job_id, attempt_id = job.id, attempt.id

    # The adapter exercises persistence/lease/recovery only. It does not read or upload evidence.
    completed_at = utcnow()
    mock_record = {"mode": "mock", "performed_inference": False, "billable": False,
                   "image_processing": "not_performed", "prediction_created": False}
    with session_factory.begin() as db:
        job = db.scalar(select(VehicleAIJob).where(VehicleAIJob.id == job_id).with_for_update())
        attempt = db.scalar(select(VehicleAIAttempt).where(VehicleAIAttempt.id == attempt_id).with_for_update())
        if job is None or attempt is None or job.status != "claimed" or job.lease_owner != owner:
            return True
        attempt.status = "mock_completed"
        attempt.finished_at = completed_at
        attempt.latency_ms = 0
        attempt.actual_usd = 0
        attempt.result_json = mock_record
        job.status = "mock_completed"
        job.finished_at = completed_at
        job.lease_until = None
        job.actual_usd = 0
        job.result_json = mock_record
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mock-only durable AI queue worker; never performs remote inference")
    parser.add_argument("--once", action="store_true", help="Claim at most one job and exit")
    parser.add_argument("--loop", action="store_true", help="Poll for mock jobs every bounded interval")
    parser.add_argument("--poll-seconds", type=float, default=2, choices=[1, 2, 3, 4, 5])
    args = parser.parse_args(argv)
    if not args.once and not args.loop:
        parser.error("Choose --once or --loop")
    if get_settings().pilot_ai_mode != "mock":
        parser.error("PILOT_AI_MODE must be 'mock'; real provider inference is not implemented/enabled here")
    engine = make_engine(_database_url_for_cli())
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    owner = f"{socket.gethostname()}:{os.getpid()}"
    try:
        while True:
            found = _run_once(session_factory, owner)
            if args.once:
                return 0
            if not found:
                time.sleep(args.poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
