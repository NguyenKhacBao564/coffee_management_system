from datetime import timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.models import utcnow
from app.modules.accounts.models import AuthSession, LoginAttempt, User
from app.modules.audit.models import AccountAuditLog
from app.modules.facilities.models import Facility
from app.modules.accounts.schemas import (
    AccountCreate,
    AccountListOut,
    AccountOut,
    AccountUpdate,
    ActiveFacilityRequest,
    FacilityCreate,
    FacilityDetailOut,
    FacilityDrumOut,
    FacilityEmployeeOut,
    FacilityModuleStatus,
    FacilityOut,
    FacilityOverviewItem,
    FacilityUpdate,
    LoginRequest,
    PasswordChange,
    PasswordReset,
    UserOut,
)
from app.modules.accounts.security import (
    clear_session_cookie,
    create_session,
    csrf_for_session,
    dummy_password_check,
    hash_password,
    password_hasher,
    require_csrf,
    session_from_request,
    set_session_cookie,
    token_hash,
    verify_password,
)

logger = logging.getLogger("nhu_tung.accounts")
router = APIRouter(prefix="/api")


def _current(request: Request, db: Session = Depends(get_db)) -> tuple[AuthSession, User | None]:
    return session_from_request(request, db, allow_anonymous=False)


def _csrf_context(request: Request, db: Session = Depends(get_db)) -> tuple[AuthSession, User | None]:
    session, user = session_from_request(request, db, allow_anonymous=True)
    require_csrf(request, session)
    return session, user


def _admin(context: tuple[AuthSession, User | None] = Depends(_current)) -> tuple[AuthSession, User]:
    session, user = context
    if user is None or user.role != "admin":
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này.")
    return session, user


def _admin_or_manager(context: tuple[AuthSession, User | None] = Depends(_current)) -> tuple[AuthSession, User]:
    session, user = context
    if user is None or user.role not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này.")
    return session, user


def _record_audit(db: Session, actor: User | None, target: User | None, event: str, changes: dict) -> None:
    db.add(
        AccountAuditLog(
            actor_user_id=actor.id if actor else None,
            target_user_id=target.id if target else None,
            event=event,
            changes=changes,
        )
    )


def _allowed_facilities(db: Session, user: User) -> list[Facility]:
    if user.role == "admin":
        return list(db.scalars(select(Facility).where(Facility.is_active.is_(True)).order_by(Facility.code)))
    return sorted((facility for facility in user.facilities if facility.is_active), key=lambda f: f.code)


def _profile(db: Session, session: AuthSession, user: User) -> UserOut:
    facilities = _allowed_facilities(db, user)
    active = next((facility for facility in facilities if facility.id == session.facility_id), None)
    if active is None and facilities:
        active = facilities[0]
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        facilities=[FacilityOut.model_validate(facility) for facility in facilities],
        active_facility=FacilityOut.model_validate(active) if active else None,
    )


def _account_out(user: User) -> AccountOut:
    return AccountOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        facilities=[FacilityOut.model_validate(f) for f in sorted(user.facilities, key=lambda item: item.code)],
    )


def _active_facilities_by_ids(db: Session, ids: list[int]) -> list[Facility]:
    if not ids:
        return []
    facilities = list(db.scalars(select(Facility).where(Facility.id.in_(ids), Facility.is_active.is_(True))))
    if len(facilities) != len(ids):
        raise HTTPException(status_code=422, detail="Chỉ có thể gán cơ sở đang hoạt động.")
    return sorted(facilities, key=lambda f: f.code)


def _validate_role_facilities(role: str, facilities: list[Facility]) -> None:
    if role in {"manager", "staff", "drum_operator"} and not facilities:
        raise HTTPException(status_code=422, detail="Quản lý, nhân viên và trông trống cần ít nhất một cơ sở đang hoạt động.")


def _raise_unavailable_login() -> None:
    raise HTTPException(status_code=429, detail="Không thể đăng nhập lúc này. Vui lòng thử lại sau.")


def _is_rate_limited(db: Session, username: str) -> bool:
    attempt = db.get(LoginAttempt, username)
    return bool(attempt and attempt.blocked_until and attempt.blocked_until > utcnow())


def _register_login_failure(db: Session, username: str) -> None:
    settings = get_settings()
    now = utcnow()
    try:
        attempt = db.scalar(select(LoginAttempt).where(LoginAttempt.username_key == username).with_for_update())
        if attempt is None:
            attempt = LoginAttempt(username_key=username, failure_count=1, window_started_at=now)
            db.add(attempt)
        elif now - attempt.window_started_at > timedelta(seconds=settings.login_failure_window_seconds):
            attempt.failure_count = 1
            attempt.window_started_at = now
            attempt.blocked_until = None
        else:
            attempt.failure_count += 1
        if attempt.failure_count >= settings.login_failure_limit:
            attempt.blocked_until = now + timedelta(seconds=settings.login_failure_window_seconds)
        db.commit()
    except IntegrityError:
        db.rollback()
        attempt = db.get(LoginAttempt, username)
        if attempt is not None:
            attempt.failure_count += 1
            if attempt.failure_count >= settings.login_failure_limit:
                attempt.blocked_until = now + timedelta(seconds=settings.login_failure_window_seconds)
            db.commit()


@router.get("/auth/csrf", tags=["auth"])
def csrf_token(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    """Return the session-bound synchronizer token in JSON, stable across tabs."""
    settings = get_settings()
    raw_cookie = request.cookies.get(settings.session_cookie_name)
    session = None
    if raw_cookie:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_cookie)))
        if session and (session.revoked_at is not None or session.expires_at <= utcnow()):
            session = None
    if session is None:
        session, raw_token, raw_csrf = create_session(db, None)
        set_session_cookie(response, raw_token)
        db.commit()
    else:
        raw_csrf = csrf_for_session(session.token_hash)
    return {"csrf_token": raw_csrf}


@router.post("/auth/login", tags=["auth"])
def login(payload: LoginRequest, response: Response, context=Depends(_csrf_context), db: Session = Depends(get_db)) -> dict:
    old_session, _ = context
    settings = get_settings()
    if settings.login_lockout_enabled and _is_rate_limited(db, payload.username):
        _raise_unavailable_login()
    user = db.scalar(select(User).where(User.username == payload.username))
    valid = verify_password(user.password_hash, payload.password) if user else False
    if not user:
        dummy_password_check(payload.password)
    if not valid or user is None or not user.is_active:
        if settings.login_lockout_enabled:
            _register_login_failure(db, payload.username)
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
    db.query(LoginAttempt).filter(LoginAttempt.username_key == payload.username).delete()
    old_session.revoked_at = utcnow()
    user.last_login_at = utcnow()
    allowed = _allowed_facilities(db, user)
    new_session, raw_token, raw_csrf = create_session(db, user, allowed[0].id if allowed else None)
    db.commit()
    set_session_cookie(response, raw_token)
    logger.info("Account sign-in completed", extra={"user_id": user.id})
    return {"user": _profile(db, new_session, user).model_dump(mode="json"), "csrf_token": raw_csrf}


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(context=Depends(_current), db: Session = Depends(get_db)) -> UserOut:
    session, user = context
    assert user is not None
    return _profile(db, session, user)


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(response: Response, context=Depends(_csrf_context), db: Session = Depends(get_db)) -> Response:
    session, user = context
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    session.revoked_at = utcnow()
    db.commit()
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/auth/change-password", tags=["auth"])
def change_password(payload: PasswordChange, response: Response, context=Depends(_csrf_context), db: Session = Depends(get_db)) -> dict:
    current_session, user = context
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=422, detail="Mật khẩu hiện tại không đúng.")
    user.password_hash = hash_password(payload.new_password)
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update({AuthSession.revoked_at: utcnow()})
    db.flush()
    new_session, raw_token, raw_csrf = create_session(db, user, current_session.facility_id)
    _record_audit(db, user, user, "password_changed", {})
    db.commit()
    set_session_cookie(response, raw_token)
    return {"user": _profile(db, new_session, user).model_dump(mode="json"), "csrf_token": raw_csrf}


@router.post("/auth/active-facility", tags=["facilities"])
def select_active_facility(payload: ActiveFacilityRequest, context=Depends(_csrf_context), db: Session = Depends(get_db)) -> dict:
    session, user = context
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    allowed_ids = {facility.id for facility in _allowed_facilities(db, user)}
    if payload.facility_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Không tìm thấy cơ sở.")
    session.facility_id = payload.facility_id
    db.commit()
    return {"user": _profile(db, session, user).model_dump(mode="json")}


@router.get("/facilities", response_model=list[FacilityOut], tags=["facilities"])
def facilities(context=Depends(_current), db: Session = Depends(get_db)) -> list[FacilityOut]:
    _, user = context
    assert user is not None
    return [FacilityOut.model_validate(facility) for facility in _allowed_facilities(db, user)]


@router.get("/facilities/{facility_id}", response_model=FacilityOut, tags=["facilities"])
def facility_detail(facility_id: int, context=Depends(_current), db: Session = Depends(get_db)) -> FacilityOut:
    _, user = context
    assert user is not None
    facility = next((f for f in _allowed_facilities(db, user) if f.id == facility_id), None)
    if facility is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cơ sở.")
    return FacilityOut.model_validate(facility)


@router.post("/admin/facilities", response_model=FacilityOut, status_code=201, tags=["admin"])
def create_facility(
    payload: FacilityCreate,
    context=Depends(_admin),
    _csrf=Depends(_csrf_context),
    db: Session = Depends(get_db),
) -> FacilityOut:
    _, actor = context
    code = payload.code.strip().upper()
    existing = db.scalar(select(Facility).where(Facility.code == code))
    if existing:
        raise HTTPException(status_code=409, detail=f"Mã chi nhánh '{code}' đã tồn tại.")
    facility = Facility(code=code, name=payload.name.strip(), is_active=True)
    db.add(facility)
    db.flush()
    _record_audit(db, actor, None, "facility_created", {"code": facility.code, "name": facility.name})
    db.commit()
    db.refresh(facility)
    return FacilityOut.model_validate(facility)


@router.patch("/admin/facilities/{facility_id}", response_model=FacilityOut, tags=["admin"])
def update_facility(
    facility_id: int,
    payload: FacilityUpdate,
    context=Depends(_admin),
    _csrf=Depends(_csrf_context),
    db: Session = Depends(get_db),
) -> FacilityOut:
    _, actor = context
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chi nhánh.")
    before = {"name": facility.name, "is_active": facility.is_active}
    facility.name = payload.name.strip()
    if payload.is_active is not None:
        facility.is_active = payload.is_active
    after = {"name": facility.name, "is_active": facility.is_active}
    _record_audit(db, actor, None, "facility_updated", {"code": facility.code, "before": before, "after": after})
    db.commit()
    db.refresh(facility)
    return FacilityOut.model_validate(facility)


@router.get("/admin/facilities/overview", response_model=list[FacilityOverviewItem], tags=["admin"])
def admin_facilities_overview(
    context=Depends(_admin),
    db: Session = Depends(get_db),
) -> list[FacilityOverviewItem]:
    facilities_db = db.query(Facility).order_by(Facility.code).all()
    from app.modules.drum_processing.models import Drum
    from app.modules.vehicle_pilot.models import CameraRuntime
    from app.modules.scale_ingestion.models import ScaleAgent

    items = []
    for f in facilities_db:
        drums = db.query(Drum).filter(Drum.facility_id == f.id).all()
        cams = db.query(CameraRuntime).filter(CameraRuntime.facility_id == f.id).all()
        scales = db.query(ScaleAgent).filter(ScaleAgent.facility_id == f.id).all()

        running_count = sum(1 for d in drums if d.status == "running")
        drum_status = "running" if running_count > 0 else ("ready" if len(drums) > 0 else "no_drums")
        cam_status = "active" if len(cams) > 0 else "unconfigured"
        scale_st = "active" if len(scales) > 0 else "unconfigured"

        items.append(
            FacilityOverviewItem(
                id=f.id,
                code=f.code,
                name=f.name,
                is_active=f.is_active,
                is_demo=f.is_demo,
                created_at=f.created_at,
                employees_count=len(f.users),
                drums_count=len(drums),
                running_drums_count=running_count,
                cameras_count=len(cams),
                scales_count=len(scales),
                drum_status=drum_status,
                camera_status=cam_status,
                scale_status=scale_st,
            )
        )
    return items


@router.get("/admin/facilities/{facility_id}/detail", response_model=FacilityDetailOut, tags=["admin"])
def admin_facility_detail(
    facility_id: int,
    context=Depends(_admin_or_manager),
    db: Session = Depends(get_db),
) -> FacilityDetailOut:
    _, user = context
    if user.role == "manager":
        mgr_fac_ids = {f.id for f in user.facilities}
        if facility_id not in mgr_fac_ids:
            raise HTTPException(status_code=403, detail="Không có quyền truy cập chi nhánh này.")

    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chi nhánh.")

    # Employees
    employees = [
        FacilityEmployeeOut(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
        )
        for u in sorted(facility.users, key=lambda item: (item.role != "manager", item.role != "drum_operator", item.username))
    ]

    # Drums
    from app.modules.drum_processing.models import Drum
    drums_db = db.query(Drum).filter(Drum.facility_id == facility_id).order_by(Drum.drum_code).all()
    drums = [
        FacilityDrumOut(
            id=d.id,
            drum_code=d.drum_code,
            drum_name=d.drum_name,
            capacity_kg=d.capacity_kg,
            measurement_mode=d.measurement_mode,
            has_moisture_imbalance=d.has_moisture_imbalance,
            has_blade_issue=d.has_blade_issue,
            status=d.status,
            is_active=d.is_active,
        )
        for d in drums_db
    ]

    # Drum processing status
    running_drums = sum(1 for d in drums if d.status == "running")
    operators_count = sum(1 for e in employees if e.role == "drum_operator" and e.is_active)
    if running_drums > 0:
        drum_status = FacilityModuleStatus(
            status="active",
            label="Đang hoạt động",
            details=f"{running_drums}/{len(drums)} trống đang sấy · {operators_count} thợ trông trống",
        )
    elif len(drums) > 0:
        drum_status = FacilityModuleStatus(
            status="ready",
            label="Sẵn sàng",
            details=f"{len(drums)} trống sấy rảnh · {operators_count} thợ trông trống",
        )
    else:
        drum_status = FacilityModuleStatus(
            status="unconfigured",
            label="Chưa kích hoạt",
            details="Chưa thiết lập trống sấy tại chi nhánh này",
        )

    # Camera status
    from app.modules.vehicle_pilot.models import CameraRuntime
    cams = db.query(CameraRuntime).filter(CameraRuntime.facility_id == facility_id).all()
    if cams:
        camera_status = FacilityModuleStatus(
            status="active",
            label="Đang hoạt động",
            details=f"{len(cams)} camera giám sát ({', '.join(c.camera_id for c in cams)})",
        )
    else:
        camera_status = FacilityModuleStatus(
            status="unconfigured",
            label="Chưa kết nối",
            details="Chưa phát hiện thiết bị camera gắn với chi nhánh này",
        )

    # Scale status
    from app.modules.scale_ingestion.models import ScaleAgent
    scales = db.query(ScaleAgent).filter(ScaleAgent.facility_id == facility_id).all()
    if scales:
        scale_status = FacilityModuleStatus(
            status="active",
            label="Đang hoạt động",
            details=f"{len(scales)} trạm cân đang kết nối",
        )
    else:
        scale_status = FacilityModuleStatus(
            status="unconfigured",
            label="Chưa kết nối",
            details="Chưa phát hiện đầu cân điện tử",
        )

    return FacilityDetailOut(
        id=facility.id,
        code=facility.code,
        name=facility.name,
        is_active=facility.is_active,
        is_demo=facility.is_demo,
        created_at=facility.created_at,
        employees=employees,
        drums=drums,
        drum_processing_status=drum_status,
        camera_status=camera_status,
        scale_status=scale_status,
    )


@router.get("/admin/accounts", response_model=AccountListOut, tags=["admin"])
def list_accounts(
    q: str | None = Query(default=None, max_length=80),
    role: str | None = Query(default=None, pattern="^(admin|manager|staff|drum_operator)$"),
    active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context=Depends(_admin_or_manager),
    db: Session = Depends(get_db),
) -> AccountListOut:
    _, actor = context
    stmt = select(User)
    if actor.role == "manager":
        mgr_fac_ids = [f.id for f in actor.facilities]
        stmt = stmt.join(User.facilities).where(
            User.role.in_(["staff", "drum_operator"]),
            Facility.id.in_(mgr_fac_ids),
        ).distinct()
    if q and q.strip():
        pattern = f"%{q.strip().casefold()}%"
        stmt = stmt.where(or_(User.username.ilike(pattern), User.display_name.ilike(pattern)))
    if role:
        if actor.role == "manager" and role not in ["staff", "drum_operator"]:
            return AccountListOut(items=[], page=page, page_size=page_size, total=0)
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = list(db.scalars(stmt.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    return AccountListOut(items=[_account_out(user) for user in users], page=page, page_size=page_size, total=total)


@router.post("/admin/accounts", response_model=AccountOut, status_code=201, tags=["admin"])
def create_account(payload: AccountCreate, context=Depends(_admin_or_manager), _csrf=Depends(_csrf_context), db: Session = Depends(get_db)) -> AccountOut:
    _, actor = context
    assert actor is not None
    if actor.role == "manager":
        if payload.role not in ["staff", "drum_operator"]:
            raise HTTPException(status_code=403, detail="Quản lý chỉ được tạo tài khoản nhân viên hoặc thợ trông trống.")
        mgr_fac_ids = {f.id for f in actor.facilities}
        if not payload.facility_ids or not set(payload.facility_ids).issubset(mgr_fac_ids):
            raise HTTPException(status_code=403, detail="Chỉ được gán tài khoản vào chi nhánh bạn quản lý.")
    if db.scalar(select(User.id).where(User.username == payload.username)) is not None:
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã được sử dụng.")
    assigned = _active_facilities_by_ids(db, payload.facility_ids)
    _validate_role_facilities(payload.role, assigned)
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=True,
        facilities=assigned,
    )
    db.add(user)
    db.flush()
    _record_audit(db, actor, user, "account_created", {"after": {"username": user.username, "role": user.role, "facility_ids": payload.facility_ids}})
    db.commit()
    db.refresh(user)
    return _account_out(user)


@router.patch("/admin/accounts/{user_id}", response_model=AccountOut, tags=["admin"])
def update_account(user_id: int, payload: AccountUpdate, context=Depends(_admin_or_manager), _csrf=Depends(_csrf_context), db: Session = Depends(get_db)) -> AccountOut:
    _, actor = context
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if actor.role == "manager":
        if target.role not in ["staff", "drum_operator"] or payload.role not in ["staff", "drum_operator"]:
            raise HTTPException(status_code=403, detail="Quản lý chỉ được chỉnh sửa tài khoản nhân viên hoặc thợ trông trống.")
        mgr_fac_ids = {f.id for f in actor.facilities}
        target_fac_ids = {f.id for f in target.facilities}
        if not target_fac_ids.intersection(mgr_fac_ids):
            raise HTTPException(status_code=403, detail="Tài khoản không thuộc chi nhánh của bạn.")
        if not payload.facility_ids or not set(payload.facility_ids).issubset(mgr_fac_ids):
            raise HTTPException(status_code=403, detail="Chỉ được gán tài khoản vào chi nhánh bạn quản lý.")
    assigned = _active_facilities_by_ids(db, payload.facility_ids)
    _validate_role_facilities(payload.role, assigned)
    if target.is_active and target.role == "admin" and (payload.role != "admin"):
        active_admins = list(db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True)).with_for_update()))
        if len(active_admins) <= 1:
            raise HTTPException(status_code=409, detail="Không thể hạ quyền quản trị viên cuối cùng đang hoạt động.")
    previous = {
        "display_name": target.display_name,
        "role": target.role,
        "facility_ids": sorted(facility.id for facility in target.facilities),
    }
    changes = {
        "before": previous,
        "after": {"display_name": payload.display_name, "role": payload.role, "facility_ids": payload.facility_ids},
    }
    target.display_name = payload.display_name
    target.role = payload.role
    target.facilities = assigned
    _record_audit(db, actor, target, "account_updated", changes)
    db.commit()
    db.refresh(target)
    return _account_out(target)


@router.patch("/admin/accounts/{user_id}/status", response_model=AccountOut, tags=["admin"])
def update_account_status(
    user_id: int,
    is_active: bool,
    context=Depends(_admin_or_manager),
    _csrf=Depends(_csrf_context),
    db: Session = Depends(get_db),
) -> AccountOut:
    _, actor = context
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if actor.role == "manager":
        if target.role not in ["staff", "drum_operator"]:
            raise HTTPException(status_code=403, detail="Quản lý chỉ được thay đổi trạng thái nhân viên hoặc thợ trông trống.")
        mgr_fac_ids = {f.id for f in actor.facilities}
        target_fac_ids = {f.id for f in target.facilities}
        if not target_fac_ids.intersection(mgr_fac_ids):
            raise HTTPException(status_code=403, detail="Tài khoản không thuộc chi nhánh của bạn.")
    if target.is_active and target.role == "admin" and not is_active:
        active_admins = list(db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True)).with_for_update()))
        if len(active_admins) <= 1:
            raise HTTPException(status_code=409, detail="Không thể vô hiệu hóa quản trị viên cuối cùng đang hoạt động.")
    if target.is_active != is_active:
        previous_active = target.is_active
        target.is_active = is_active
        if not is_active:
            db.query(AuthSession).filter(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None)).update({AuthSession.revoked_at: utcnow()})
        _record_audit(db, actor, target, "account_activated" if is_active else "account_deactivated", {"before": {"is_active": previous_active}, "after": {"is_active": is_active}})
    db.commit()
    db.refresh(target)
    return _account_out(target)


@router.post("/admin/accounts/{user_id}/reset-password", status_code=204, tags=["admin"])
def reset_account_password(user_id: int, payload: PasswordReset, context=Depends(_admin_or_manager), _csrf=Depends(_csrf_context), db: Session = Depends(get_db)) -> Response:
    _, actor = context
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    if actor.role == "manager":
        if target.role not in ["staff", "drum_operator"]:
            raise HTTPException(status_code=403, detail="Quản lý chỉ được đặt lại mật khẩu nhân viên hoặc thợ trông trống.")
        mgr_fac_ids = {f.id for f in actor.facilities}
        target_fac_ids = {f.id for f in target.facilities}
        if not target_fac_ids.intersection(mgr_fac_ids):
            raise HTTPException(status_code=403, detail="Tài khoản không thuộc chi nhánh của bạn.")
    target.password_hash = hash_password(payload.new_password)
    db.query(AuthSession).filter(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None)).update({AuthSession.revoked_at: utcnow()})
    _record_audit(db, actor, target, "password_reset", {})
    db.commit()
    return Response(status_code=204)


@router.get("/admin/audit", tags=["admin"])
def account_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    context=Depends(_admin),
    db: Session = Depends(get_db),
) -> dict:
    total = db.scalar(select(func.count()).select_from(AccountAuditLog)) or 0
    entries = list(db.scalars(select(AccountAuditLog).order_by(AccountAuditLog.created_at.desc(), AccountAuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    user_ids = {item.actor_user_id for item in entries if item.actor_user_id} | {item.target_user_id for item in entries if item.target_user_id}
    names = {user.id: user.username for user in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    return {
        "items": [
            {
                "id": item.id,
                "event": item.event,
                "actor_username": names.get(item.actor_user_id),
                "target_username": names.get(item.target_user_id),
                "changes": item.changes,
                "created_at": item.created_at,
            }
            for item in entries
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/admin/system/status", tags=["admin"])
def admin_system_status(context=Depends(_admin), db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    settings = get_settings()
    return {"api": "ok", "database": "connected", "environment": settings.app_env}


@router.get("/internal/health/ready", include_in_schema=False)
def internal_ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok"}
