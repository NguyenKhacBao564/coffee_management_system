import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import utcnow
from app.modules.accounts.models import AuthSession, User

password_hasher = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID)
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 1024:
        raise ValueError("Mật khẩu quá dài")
    return password_hasher.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        if len(password.encode("utf-8")) > 1024:
            return False
        return password_hasher.verify(encoded, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def dummy_password_check(password: str) -> None:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
    verify_password(_dummy_hash, password)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def csrf_for_session(session_token_hash: str) -> str:
    key = bytes.fromhex(session_token_hash)
    return hmac.new(key, b"nhu-tung-demo:csrf:v1", hashlib.sha256).hexdigest()


def create_session(db: Session, user: User | None, facility_id: int | None = None) -> tuple[AuthSession, str, str]:
    settings = get_settings()
    raw_token = secrets.token_urlsafe(32)
    session_token_hash = token_hash(raw_token)
    raw_csrf = csrf_for_session(session_token_hash)
    session = AuthSession(
        user_id=user.id if user else None,
        facility_id=facility_id,
        token_hash=session_token_hash,
        csrf_hash=token_hash(raw_csrf),
        expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session)
    db.flush()
    return session, raw_token, raw_csrf


def set_session_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        max_age=settings.session_ttl_seconds,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def require_csrf(request: Request, session: AuthSession) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(token_hash(supplied), session.csrf_hash):
        raise HTTPException(status_code=403, detail="Yêu cầu không hợp lệ. Hãy tải lại trang và thử lại.")


def session_from_request(request: Request, db: Session, allow_anonymous: bool = False) -> tuple[AuthSession, User | None]:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    session = db.query(AuthSession).filter(AuthSession.token_hash == token_hash(raw_token)).one_or_none()
    if session is None or session.revoked_at is not None or session.expires_at <= utcnow():
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    user = db.get(User, session.user_id) if session.user_id is not None else None
    if session.user_id is not None and (user is None or not user.is_active):
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    if user is None and not allow_anonymous:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    return session, user
