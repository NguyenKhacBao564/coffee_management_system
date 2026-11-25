"""Local management for fixed scale ingestion agents. Run with -m app.modules.scale_ingestion.cli."""

import argparse
import getpass
import hashlib
import os
import secrets
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import make_engine
from app.modules.accounts import models as _account_models  # Register Facility.user relationship targets for this standalone CLI.
from app.modules.facilities.models import Facility
from app.modules.scale_ingestion.models import ScaleAgent

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TOKEN_DIR = REPOSITORY_ROOT / "data" / "scale-agent-tokens"


def _database_url_for_cli() -> str:
    """Read the repository's Compose URL when the CLI runs from backend/."""
    url = os.environ.get("SCALE_ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL")
    env_values = {}
    env_path = REPOSITORY_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_values[key.strip()] = value.strip().strip("\"'")
    if not url:
        url = env_values.get("DATABASE_URL") or get_settings().database_url
    parsed = make_url(url)
    if parsed.host == "db":
        try:
            port = int(env_values.get("POSTGRES_PORT", "5433"))
        except ValueError:
            port = 5433
        url = parsed.set(host="127.0.0.1", port=port).render_as_string(hide_password=False)
    return url


def _local_session_scope():
    """Connect from this host to Compose's published PostgreSQL port by default."""
    url = _database_url_for_cli()
    engine = make_engine(url)
    local_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    @contextmanager
    def scope():
        try:
            with local_sessions.begin() as db:
                yield db
        finally:
            engine.dispose()
    return scope()


def _write_token(path: Path, value: str) -> bytes | None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    previous = path.read_bytes() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix=".agent-token-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(value + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return previous


def _restore_token_file(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    fd, temporary = tempfile.mkstemp(prefix=".agent-token-restore-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(previous)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quản trị scale agent local; token không truyền qua command line.")
    parser.add_argument("--token-dir", type=Path, default=DEFAULT_TOKEN_DIR, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Tạo agent gắn cố định với cơ sở và cân")
    create.add_argument("--facility-code", required=True)
    create.add_argument("--scale-code", required=True)
    create.add_argument("--display-name", required=True)
    disable = commands.add_parser("disable", help="Vô hiệu hóa agent")
    disable.add_argument("agent_id")
    rotate = commands.add_parser("rotate-token", help="Đổi token; token hiện tại mất hiệu lực")
    rotate.add_argument("agent_id")
    args = parser.parse_args(argv)

    if args.command == "create":
        facility_code = args.facility_code.strip()
        scale_code = args.scale_code.strip()
        display_name = args.display_name.strip()
        if not facility_code or not scale_code or len(scale_code) > 64 or not display_name or len(display_name) > 120:
            print("facility-code, scale-code hoặc display-name không hợp lệ.", file=sys.stderr)
            return 2
        token = secrets.token_urlsafe(32)
        agent_id = str(uuid4())
        token_path = args.token_dir / f"{agent_id}.token"
        previous = None
        token_written = False
        try:
            previous = _write_token(token_path, token)
            token_written = True
            with _local_session_scope() as db:
                facility = db.scalar(select(Facility).where(Facility.code == facility_code, Facility.is_active.is_(True)))
                if facility is None:
                    raise ValueError("Không tìm thấy cơ sở đang hoạt động.")
                db.add(ScaleAgent(agent_id=agent_id, display_name=display_name, facility_id=facility.id, scale_code=scale_code, is_active=True, token_hash=_token_hash(token)))
        except Exception as exc:
            if token_written:
                _restore_token_file(token_path, previous)
            message = str(exc) if isinstance(exc, ValueError) else "Không thể tạo agent (cơ sở/mã cân có thể đã tồn tại)."
            print(message, file=sys.stderr)
            return 2
        print(f"Đã tạo agent {agent_id}; token lưu tại {token_path} (quyền 0600).")
        return 0

    token_path = None
    previous = None
    token_written = False
    try:
        with _local_session_scope() as db:
            agent = db.scalar(select(ScaleAgent).where(ScaleAgent.agent_id == args.agent_id))
            if agent is None:
                raise ValueError("Không tìm thấy agent.")
            if args.command == "disable":
                if not agent.is_active:
                    print(f"Agent {agent.agent_id} đã bị vô hiệu hóa.")
                    return 0
                agent.is_active = False
            else:
                if not agent.is_active:
                    raise ValueError("Agent đã bị vô hiệu hóa; hãy tạo agent mới hoặc kích hoạt theo quy trình quản trị.")
                token = secrets.token_urlsafe(32)
                token_path = args.token_dir / f"{agent.agent_id}.token"
                previous = _write_token(token_path, token)
                token_written = True
                agent.token_hash = _token_hash(token)
                db.flush()
        if args.command == "disable":
            print(f"Đã vô hiệu hóa agent {args.agent_id}.")
        else:
            print(f"Đã đổi token cho agent {args.agent_id}; token cũ mất hiệu lực. File local: {token_path} (quyền 0600).")
        return 0
    except ValueError as exc:
        if token_written and token_path is not None:
            _restore_token_file(token_path, previous)
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        if token_written and token_path is not None:
            _restore_token_file(token_path, previous)
        print("Không thể hoàn tất thao tác agent.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
