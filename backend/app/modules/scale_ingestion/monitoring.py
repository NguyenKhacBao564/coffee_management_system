"""S03 session-authenticated, read-only monitoring. Independent of ingestion ACKs."""

from datetime import datetime, time, timezone, timedelta
from uuid import UUID
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Date, case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.accounts.security import session_from_request
from app.modules.facilities.models import Facility
from app.modules.scale_ingestion.models import ScaleAgent, ScaleSignal
from app.modules.scale_ingestion.provenance import is_acceptance_test

router = APIRouter(prefix="/api/scale-monitoring", tags=["scale-monitoring"])


def _scope(request: Request, db: Session, facility_id: int | None) -> list[int]:
    _, user = session_from_request(request, db, allow_anonymous=False)
    assert user is not None
    query = select(Facility.id).where(Facility.is_active.is_(True))
    if user.role != "admin":
        query = query.where(Facility.id.in_([f.id for f in user.facilities if f.is_active]))
    allowed = list(db.scalars(query))
    if facility_id is not None:
        if facility_id not in allowed:
            raise HTTPException(404, "Không tìm thấy cơ sở được phép xem.")
        return [facility_id]
    return allowed


def _agent(db: Session, agent_id: UUID, scope: list[int]) -> ScaleAgent:
    agent = db.scalar(select(ScaleAgent).where(ScaleAgent.agent_id == str(agent_id), ScaleAgent.facility_id.in_(scope)))
    if agent is None:
        raise HTTPException(404, "Không tìm thấy cân tại cơ sở được phép xem.")
    return agent


def _signal_out(signal: ScaleSignal | None):
    if signal is None:
        return None
    return {
        "event_id": str(signal.event_id), "agent_id": signal.agent_id,
        "sequence": str(signal.sequence), "weight_kg": format(signal.weight_kg, ".3f"),
        "source": signal.source,
        "observed_at_utc": signal.observed_at_utc.astimezone(timezone.utc),
        "received_at_utc": signal.received_at_utc.astimezone(timezone.utc),
        "is_acceptance_test": is_acceptance_test(signal.agent_id, str(signal.event_id)),
    }


def _latest(db: Session, agent_id: str):
    return db.scalar(select(ScaleSignal).where(ScaleSignal.agent_id == agent_id)
                     .order_by(ScaleSignal.observed_at_utc.desc(), ScaleSignal.id.desc()).limit(1))


@router.get("/agents")
def agents(request: Request, facility_id: int | None = Query(None, ge=1),
           page: int = Query(1, ge=1, le=10000), page_size: int = Query(50, ge=1, le=100),
           db: Session = Depends(get_db)):
    scope = _scope(request, db, facility_id)
    where = ScaleAgent.facility_id.in_(scope)
    total = db.scalar(select(func.count()).select_from(ScaleAgent).where(where))
    # Indexed correlated lookup, one latest row per agent; no per-agent request/query loop.
    latest_id = select(ScaleSignal.id).where(ScaleSignal.agent_id == ScaleAgent.agent_id).order_by(
        ScaleSignal.observed_at_utc.desc(), ScaleSignal.id.desc()).limit(1).correlate(ScaleAgent).scalar_subquery()
    rows = db.execute(select(ScaleAgent, Facility, ScaleSignal).join(Facility, Facility.id == ScaleAgent.facility_id)
                      .outerjoin(ScaleSignal, ScaleSignal.id == latest_id).where(where)
                      .order_by(Facility.code, ScaleAgent.scale_code, ScaleAgent.agent_id)
                      .offset((page - 1) * page_size).limit(page_size))
    return {"items": [{"agent_id": a.agent_id, "display_name": a.display_name, "scale_code": a.scale_code,
                       "is_active": a.is_active, "facility_id": f.id, "facility_code": f.code,
                       "facility_name": f.name, "latest": _signal_out(s)} for a, f, s in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/agents/{agent_id}/latest")
def latest(agent_id: UUID, request: Request, facility_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    agent = _agent(db, agent_id, _scope(request, db, facility_id))
    return {"agent_id": agent.agent_id, "latest": _signal_out(_latest(db, agent.agent_id))}


@router.get("/signals")
def signals(request: Request, facility_id: int | None = Query(None, ge=1), agent_id: UUID | None = None,
            observed_from: datetime | None = None, observed_to: datetime | None = None,
            page: int = Query(1, ge=1, le=10000), page_size: int = Query(30, ge=1, le=100),
            db: Session = Depends(get_db)):
    scope = _scope(request, db, facility_id)
    if agent_id is not None:
        _agent(db, agent_id, scope)  # Check direct IDs even for an empty result/time range.
    for value in (observed_from, observed_to):
        if value is not None and (value.tzinfo is None or value.utcoffset().total_seconds() != 0):
            raise HTTPException(422, "Khoảng thời gian phải có múi giờ UTC (Z hoặc +00:00).")
    if observed_from is not None and observed_to is not None and observed_from > observed_to:
        raise HTTPException(422, "Thời gian bắt đầu phải trước hoặc bằng thời gian kết thúc.")
    where = [ScaleAgent.facility_id.in_(scope)]
    if agent_id is not None:
        where.append(ScaleSignal.agent_id == str(agent_id))
    if observed_from is not None:
        where.append(ScaleSignal.observed_at_utc >= observed_from)
    if observed_to is not None:
        where.append(ScaleSignal.observed_at_utc <= observed_to)
    query = select(ScaleSignal).join(ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id).where(*where)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(ScaleSignal.observed_at_utc.desc(), ScaleSignal.id.desc())
                      .offset((page - 1) * page_size).limit(page_size))
    return {"items": [_signal_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def _signal_filters(scope: list[int], agent_id: UUID | None, observed_from: datetime | None,
                    observed_to: datetime | None, db: Session):
    if agent_id is not None:
        _agent(db, agent_id, scope)
    for value in (observed_from, observed_to):
        if value is not None and (value.tzinfo is None or value.utcoffset().total_seconds() != 0):
            raise HTTPException(422, "Khoảng thời gian phải có múi giờ UTC (Z hoặc +00:00).")
    if observed_from is not None and observed_to is not None and observed_from > observed_to:
        raise HTTPException(422, "Thời gian bắt đầu phải trước hoặc bằng thời gian kết thúc.")
    where = [ScaleAgent.facility_id.in_(scope)]
    if agent_id is not None:
        where.append(ScaleSignal.agent_id == str(agent_id))
    if observed_from is not None:
        where.append(ScaleSignal.observed_at_utc >= observed_from)
    if observed_to is not None:
        where.append(ScaleSignal.observed_at_utc <= observed_to)
    return where


@router.get("/signals/chart")
def signal_chart(request: Request, facility_id: int | None = Query(None, ge=1), agent_id: UUID | None = None,
                 observed_from: datetime | None = None, observed_to: datetime | None = None,
                 max_points: int = Query(1200, ge=100, le=2000),
                 view: Literal["raw", "overview", "auto"] = "raw", db: Session = Depends(get_db)):
    """Bounded chart series, ordered by observation time; never returns full history by default."""
    scope = _scope(request, db, facility_id)
    where = _signal_filters(scope, agent_id, observed_from, observed_to, db)
    # Find gaps in raw observations, before sampling. A long distance between
    # selected points is not evidence that the source stopped sending.
    ordered = select(
        ScaleSignal.id.label("signal_id"), ScaleSignal.agent_id,
        ScaleSignal.observed_at_utc, ScaleSignal.weight_kg,
        func.lag(ScaleSignal.observed_at_utc).over(
            partition_by=ScaleSignal.agent_id,
            order_by=(ScaleSignal.observed_at_utc, ScaleSignal.id),
        ).label("previous_observed_at"),
    ).join(ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id).where(*where).cte("ordered_raw_signals")
    total, first_at, last_at = db.execute(select(
        func.count(), func.min(ordered.c.observed_at_utc), func.max(ordered.c.observed_at_utc),
    ).select_from(ordered)).one()
    marked = select(ordered, case(
        (ordered.c.previous_observed_at.is_(None), 1),
        (func.extract("epoch", ordered.c.observed_at_utc - ordered.c.previous_observed_at) > 60, 1),
        else_=0,
    ).label("new_segment")).cte("marked_raw_signals")
    segmented = select(marked, func.sum(marked.c.new_segment).over(
        partition_by=marked.c.agent_id,
        order_by=(marked.c.observed_at_utc, marked.c.signal_id),
        rows=(None, 0),
    ).label("segment_number")).cte("segmented_raw_signals")
    start = observed_from or first_at
    end = observed_to or last_at
    span = (end - start).total_seconds() if start is not None and end is not None else 0
    chart_view = "overview" if view == "overview" or (view == "auto" and span > 10_800) else "raw"
    candidates = segmented
    candidate_count = total
    if chart_view == "overview":
        partition = (segmented.c.agent_id, segmented.c.segment_number)
        # One actual event per display segment, not a persisted/confirmed weighing.
        stats = select(segmented,
            func.count().over(partition_by=partition).label("segment_sample_count"),
            func.min(segmented.c.observed_at_utc).over(partition_by=partition).label("segment_started_at_utc"),
            func.max(segmented.c.observed_at_utc).over(partition_by=partition).label("segment_ended_at_utc"),
            func.count().over(partition_by=(*partition, segmented.c.weight_kg)).label("weight_frequency"),
        ).cte("overview_segment_stats")
        distance_to_middle = func.abs(func.extract("epoch", stats.c.observed_at_utc - stats.c.segment_started_at_utc)
            - func.extract("epoch", stats.c.segment_ended_at_utc - stats.c.segment_started_at_utc) / 2)
        representatives = select(stats, func.row_number().over(
            partition_by=(stats.c.agent_id, stats.c.segment_number),
            order_by=(stats.c.weight_frequency.desc(), distance_to_middle, stats.c.signal_id),
        ).label("representative_rank")).cte("overview_representatives")
        candidates = select(representatives).where(representatives.c.representative_rank == 1).cte("overview_candidates")
        candidate_count = db.scalar(select(func.count()).select_from(candidates)) or 0
    if candidate_count <= max_points:
        chosen = candidates
    else:
        # Four representatives per time bucket preserve endpoints and extrema.
        # Segment IDs survive sampling, including gaps inside a time bucket.
        buckets = max(1, max_points // 4)
        duration = max(1.0, (last_at - first_at).total_seconds())
        bucketed = select(candidates, func.least(buckets - 1, func.floor(
            func.extract("epoch", candidates.c.observed_at_utc - first_at) / duration * buckets,
        )).label("bucket")).cte("bucketed_signals")
        ranked = select(
            bucketed,
            func.row_number().over(partition_by=bucketed.c.bucket,
                                   order_by=(bucketed.c.observed_at_utc, bucketed.c.signal_id)).label("first_rank"),
            func.row_number().over(partition_by=bucketed.c.bucket,
                                   order_by=(bucketed.c.observed_at_utc.desc(), bucketed.c.signal_id.desc())).label("last_rank"),
            func.row_number().over(partition_by=bucketed.c.bucket,
                                   order_by=(bucketed.c.weight_kg, bucketed.c.observed_at_utc, bucketed.c.signal_id)).label("min_rank"),
            func.row_number().over(partition_by=bucketed.c.bucket,
                                   order_by=(bucketed.c.weight_kg.desc(), bucketed.c.observed_at_utc, bucketed.c.signal_id)).label("max_rank"),
        ).cte("ranked_signals")
        chosen = select(ranked).where(
            (ranked.c.first_rank == 1) | (ranked.c.last_rank == 1) |
            (ranked.c.min_rank == 1) | (ranked.c.max_rank == 1)).cte("chart_signal_ids")
    extra = [chosen.c.segment_started_at_utc, chosen.c.segment_ended_at_utc, chosen.c.segment_sample_count] if chart_view == "overview" else []
    rows = db.execute(select(ScaleSignal, chosen.c.segment_number, *extra).join(
        chosen, chosen.c.signal_id == ScaleSignal.id,
    ).order_by(ScaleSignal.observed_at_utc, ScaleSignal.id)).all()
    items = []
    for row in rows:
        item = {**_signal_out(row[0]), "series_key": f"{row[0].agent_id}:{row[1]}"}
        if chart_view == "overview":
            item.update(segment_started_at_utc=row[2], segment_ended_at_utc=row[3], segment_sample_count=row[4])
        items.append(item)
    for index, item in enumerate(items):
        item["gap_before"] = index > 0 and item["series_key"] != items[index - 1]["series_key"]
    return {"items": items, "total": total, "returned": len(items), "downsampled": candidate_count > len(items),
            "max_points": max_points, "gap_threshold_seconds": 60,
            "gap_basis": "raw_observations", "sampling_method": "time_bucket_first_min_max_last",
            "chart_view": chart_view, "total_segments": candidate_count if chart_view == "overview" else None,
            "representative_method": "most_frequent_weight_actual_sample_v1" if chart_view == "overview" else None,
            "overview_min_seconds": 10_800}


@router.get("/summary")
def monitoring_summary(request: Request, facility_id: int | None = Query(None, ge=1), agent_id: UUID | None = None,
                       observed_from: datetime | None = None, observed_to: datetime | None = None,
                       db: Session = Depends(get_db)):
    """Counts raw samples by observed time; deliberately does not add weights or infer weighings."""
    scope = _scope(request, db, facility_id)
    where = _signal_filters(scope, agent_id, observed_from, observed_to, db)
    scoped = select(ScaleSignal).join(ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id).where(*where).subquery()
    total = db.scalar(select(func.count()).select_from(scoped)) or 0
    delay = func.extract("epoch", scoped.c.received_at_utc - scoped.c.observed_at_utc)
    delayed_count = db.scalar(select(func.count()).select_from(scoped).where(delay > 60)) or 0
    max_delay = db.scalar(select(func.max(delay)).select_from(scoped))
    local_now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    day_start_local = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    month_start_local = day_start_local.replace(day=1)
    month_end_local = (month_start_local.replace(day=28) + timedelta(days=4)).replace(day=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = (day_start_local + timedelta(days=1)).astimezone(timezone.utc)
    month_start_utc = month_start_local.astimezone(timezone.utc)
    month_end_utc = month_end_local.astimezone(timezone.utc)
    scope_filters = [ScaleAgent.facility_id.in_(scope)]
    if agent_id is not None:
        scope_filters.append(ScaleSignal.agent_id == str(agent_id))
    today = db.scalar(select(func.count()).select_from(ScaleSignal).join(
        ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id).where(
            *scope_filters, ScaleSignal.observed_at_utc >= day_start_utc,
            ScaleSignal.observed_at_utc < day_end_utc)) or 0
    this_month = db.scalar(select(func.count()).select_from(ScaleSignal).join(
        ScaleAgent, ScaleAgent.agent_id == ScaleSignal.agent_id).where(
            *scope_filters, ScaleSignal.observed_at_utc >= month_start_utc,
            ScaleSignal.observed_at_utc < month_end_utc)) or 0
    days = db.execute(select(
        func.timezone("Asia/Ho_Chi_Minh", scoped.c.observed_at_utc).cast(Date).label("local_date"),
        func.count().label("sample_count"),
    ).select_from(scoped).group_by("local_date").order_by("local_date").limit(367)).all()
    return {"timezone": "Asia/Ho_Chi_Minh", "range_sample_count": total,
            "today_observed_sample_count": today, "month_observed_sample_count": this_month,
            "delayed_over_60s_sample_count": delayed_count,
            "max_receive_delay_seconds": float(max_delay) if max_delay is not None else None,
            "daily_counts_truncated": len(days) > 366,
            "daily_observed_sample_counts": [{"date": row.local_date.isoformat(), "sample_count": row.sample_count} for row in days[:366]],
            "observed_weighings": None, "confirmed_weighings": None, "needs_review_weighings": None,
            "weighing_status": "not_implemented", "weight_totals": None}
