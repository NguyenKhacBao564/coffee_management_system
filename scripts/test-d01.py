#!/usr/bin/env python3
"""Run D01 API tests against a newly-created, isolated Compose database."""

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


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main() -> int:
    if not ENV_PATH.exists():
        print("Thiếu .env local. Chạy ./scripts/dev.sh up trước.", file=sys.stderr)
        return 2
    env_values = read_env(ENV_PATH)
    source = env_values.get("DATABASE_URL")
    user = env_values.get("POSTGRES_USER", "nhutung")
    if not source:
        print(".env chưa có DATABASE_URL.", file=sys.stderr)
        return 2
    parsed = urlsplit(source)
    database_name = f"nhutung_d01_test_{uuid4().hex[:10]}"
    username = unquote(parsed.username or user)
    password = unquote(parsed.password or "")
    host_port = int(env_values.get("POSTGRES_PORT", "5433"))
    test_url = urlunsplit((parsed.scheme, f"{quote(username, safe='')}:{quote(password, safe='')}@localhost:{host_port}", f"/{database_name}", "", ""))
    uv = shutil.which("uv") or "/tmp/nhutung-uv/bin/uv"
    created = False
    try:
        run([*COMPOSE, "exec", "-T", "db", "createdb", "-U", user, database_name], cwd=ROOT)
        created = True
        environment = {**os.environ, "DATABASE_URL": test_url, "APP_ENV": "test", "LOG_LEVEL": "WARNING"}
        run([uv, "sync", "--frozen", "--dev"], cwd=BACKEND, env=environment)
        run([uv, "run", "alembic", "upgrade", "head"], cwd=BACKEND, env=environment)
        run([uv, "run", "pytest", "-q", "tests/test_d01_auth.py"], cwd=BACKEND, env=environment)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"D01 checks failed with exit code {getattr(exc, 'returncode', 'unknown')}.", file=sys.stderr)
        return 1
    finally:
        if created:
            try:
                run([*COMPOSE, "exec", "-T", "db", "dropdb", "-U", user, "--if-exists", database_name], cwd=ROOT)
                print("Đã xóa database kiểm thử tạm; volume ứng dụng được giữ nguyên.")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"Không xóa được database kiểm thử tạm {database_name}; hãy xóa riêng database này.", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
