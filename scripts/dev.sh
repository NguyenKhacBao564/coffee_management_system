#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
COMPOSE=(docker compose --env-file .env -f compose.local.yml)

if [[ ! -f .env ]]; then
  echo "Chưa có .env. Hãy chạy: cp .env.example .env và đặt mật khẩu local."
  exit 2
fi

wait_for_db() {
  for attempt in {1..30}; do
    if "${COMPOSE[@]}" exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
      return 0
    fi
    if [[ "$attempt" == 30 ]]; then echo "PostgreSQL chưa sẵn sàng sau 30 giây." >&2; return 1; fi
    sleep 1
  done
}

case "${1:-}" in
  up)
    "${COMPOSE[@]}" build api web
    "${COMPOSE[@]}" up -d db
    wait_for_db
    "${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head
    "${COMPOSE[@]}" up -d api web
    "${COMPOSE[@]}" ps
    ;;
  status)
    "${COMPOSE[@]}" ps
    ;;
  logs)
    if [[ -n "${2:-}" ]]; then
      "${COMPOSE[@]}" logs --tail=100 -f "$2"
    else
      "${COMPOSE[@]}" logs --tail=100 -f
    fi
    ;;
  migrate)
    "${COMPOSE[@]}" build api
    "${COMPOSE[@]}" up -d db
    wait_for_db
    "${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  *)
    echo "Dùng: $0 {up|status|logs [service]|migrate|down}"
    echo "down chỉ dừng và gỡ container/network; không xóa volume PostgreSQL."
    exit 2
    ;;
esac
