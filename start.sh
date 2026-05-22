#!/usr/bin/env bash
# Запуск прокси через uvicorn внутри venv.
# Используется make-таргетами start/restart, но можно вызывать и вручную.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x "venv/bin/uvicorn" ]]; then
    echo "venv/bin/uvicorn not found. Run 'make install' first." >&2
    exit 1
fi

# Подхватываем PROXY_HOST / PROXY_PORT из .env (если есть)
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

HOST="${PROXY_HOST:-127.0.0.1}"
PORT="${PROXY_PORT:-11777}"

exec venv/bin/uvicorn main:app --host "$HOST" --port "$PORT" --log-level "${LOG_LEVEL:-info}"
