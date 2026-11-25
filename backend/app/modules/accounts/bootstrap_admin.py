"""Interactive, non-overwriting first-admin bootstrap command.

Run from backend: ``python -m app.modules.accounts.bootstrap_admin``.
"""

import getpass
import re
import sys
import unicodedata

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.accounts.models import User
from app.modules.audit.models import AccountAuditLog
from app.modules.facilities.models import Facility
from app.modules.accounts.schemas import normalize_username
from app.modules.accounts.security import hash_password


def create_first_admin(db: Session, username: str, display_name: str, password: str) -> bool:
    """Create the first admin only. Return False when an admin already exists."""
    db.execute(text("SELECT pg_advisory_xact_lock(81273301)"))
    if db.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
        return False
    username = normalize_username(username)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", username):
        raise ValueError("Tên đăng nhập không hợp lệ")
    display_name = unicodedata.normalize("NFKC", display_name).strip()
    if not display_name:
        raise ValueError("Tên hiển thị không được để trống")
    if len(password) < 12 or len(password) > 256 or len(password.encode("utf-8")) > 1024:
        raise ValueError("Mật khẩu cần dài từ 12 đến 256 ký tự")
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise ValueError("Tên đăng nhập đã được sử dụng")
    facility = db.scalar(select(Facility).where(Facility.code == "DEMO"))
    if facility is None:
        facility = Facility(code="DEMO", name="Cơ sở demo", is_active=True, is_demo=True)
        db.add(facility)
        db.flush()
    user = User(
        username=username,
        display_name=display_name,
        role="admin",
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(AccountAuditLog(actor_user_id=None, target_user_id=user.id, event="first_admin_bootstrapped", changes={"role": "admin"}))
    return True


def main() -> int:
    print("Tạo quản trị viên đầu tiên của Như Tùng.")
    username = input("Tên đăng nhập: ").strip()
    display_name = input("Tên hiển thị: ").strip()
    password = getpass.getpass("Mật khẩu (ít nhất 12 ký tự): ")
    confirmation = getpass.getpass("Nhập lại mật khẩu: ")
    if password != confirmation:
        print("Hai mật khẩu không khớp.", file=sys.stderr)
        return 2
    try:
        with SessionLocal.begin() as db:
            created = create_first_admin(db, username, display_name, password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if created:
        print("Đã tạo quản trị viên đầu tiên và cơ sở demo (nếu chưa có).")
    else:
        print("Đã có quản trị viên; không thay đổi dữ liệu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
