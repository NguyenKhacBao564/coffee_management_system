#!/usr/bin/env python3
"""Run D01, D02, S01 and S03 checks on a disposable PostgreSQL database."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ENV_PATH = ROOT / ".env"
COMPOSE = ["docker", "compose", "--env-file", str(ENV_PATH), "-f", "compose.local.yml"]


def env_file(path):
    data = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def run(args, cwd, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main():
    if not ENV_PATH.exists():
        print("Thiếu .env local. Chạy ./scripts/dev.sh up trước.", file=sys.stderr); return 2
    config = env_file(ENV_PATH); source = config.get("DATABASE_URL")
    if not source:
        print(".env chưa có DATABASE_URL.", file=sys.stderr); return 2
    parsed = urlsplit(source); name = f"nhutung_d02_test_{uuid4().hex[:10]}"
    db_user = unquote(parsed.username or config.get("POSTGRES_USER", "nhutung")); password = unquote(parsed.password or "")
    test_url = urlunsplit((parsed.scheme, f"{quote(db_user, safe='')}:{quote(password, safe='')}@localhost:{config.get('POSTGRES_PORT', '5433')}", f"/{name}", "", ""))
    uv = shutil.which("uv") or ("/tmp/nhutung-uv/bin/uv" if Path("/tmp/nhutung-uv/bin/uv").exists() else None)
    python = BACKEND / ".venv" / "bin" / "python"
    created = False
    try:
        run([*COMPOSE, "exec", "-T", "db", "createdb", "-U", db_user, name], ROOT); created = True
        test_env = {**os.environ, "DATABASE_URL": test_url, "APP_ENV": "test", "LOG_LEVEL": "WARNING"}
        if python.exists():
            run([str(python), "-m", "alembic", "upgrade", "head"], BACKEND, test_env)
            run([str(python), "-m", "pytest", "-q", "tests/test_d01_auth.py", "tests/test_d02_operations.py", "tests/test_scale_ingestion.py", "tests/test_scale_monitoring.py", "tests/test_drum_processing.py"], BACKEND, test_env)
        elif uv:
            run([uv, "sync", "--frozen", "--dev"], BACKEND, test_env)
            run([uv, "run", "alembic", "upgrade", "head"], BACKEND, test_env)
            run([uv, "run", "pytest", "-q", "tests/test_d01_auth.py", "tests/test_d02_operations.py", "tests/test_scale_ingestion.py", "tests/test_scale_monitoring.py"], BACKEND, test_env)
        else:
            print("Cần backend/.venv/bin/python hoặc uv để chạy kiểm thử.", file=sys.stderr)
            return 2
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"D02 checks failed with exit code {getattr(exc, 'returncode', 'unknown')}.", file=sys.stderr); return 1
    finally:
        if created:
            try:
                run([*COMPOSE, "exec", "-T", "db", "dropdb", "-U", db_user, "--if-exists", name], ROOT)
                print("Đã xóa database kiểm thử tạm; volume và database ứng dụng được giữ nguyên.")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"Không xóa được database tạm {name}; hãy xóa riêng database này.", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
