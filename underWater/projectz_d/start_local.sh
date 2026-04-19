#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_DIR="$ROOT_DIR"
INTERNAL_DIR="$(cd "$ROOT_DIR/.." && pwd)/internal api"
INTERNAL_VENV="$INTERNAL_DIR/.venv"
MAIN_VENV=""
INTERNAL_PID=""
EMBED_INTERNAL_API="${EMBED_INTERNAL_API:-1}"
INTERNAL_DIR_EXISTS=0
if [[ -d "$INTERNAL_DIR" ]]; then
  INTERNAL_DIR_EXISTS=1
fi

if [[ "$EMBED_INTERNAL_API" != "1" && "$INTERNAL_DIR_EXISTS" != "1" ]]; then
  echo "Error: sibling folder 'internal api' not found."
  echo "Expected: $(cd "$ROOT_DIR/.." && pwd)/internal api"
  exit 1
fi

read_env_value() {
  local file="$1"
  local key="$2"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  grep -E "^${key}=" "$file" | tail -n 1 | cut -d'=' -f2- || true
}

upsert_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp_file
  tmp_file="$(mktemp)"

  if [[ -f "$file" ]]; then
    awk -v k="$key" -v v="$value" '
      BEGIN { replaced=0 }
      $0 ~ ("^" k "=") {
        print k "=" v
        replaced=1
        next
      }
      { print }
      END {
        if (!replaced) {
          print k "=" v
        }
      }
    ' "$file" > "$tmp_file"
  else
    printf "%s=%s\n" "$key" "$value" > "$tmp_file"
  fi

  mv "$tmp_file" "$file"
}

ensure_venv() {
  local app_dir="$1"
  local venv_dir="$2"
  local requirements_file="$3"
  local stamp_file="$venv_dir/.deps_installed"
  local created_venv=0
  local need_install=0

  if [[ ! -x "$venv_dir/bin/python" ]]; then
    echo "Creating virtualenv: $venv_dir"
    python3 -m venv "$venv_dir"
    created_venv=1
  fi

  if [[ ! -f "$requirements_file" ]]; then
    return 0
  fi

  if [[ "$created_venv" == "1" || "${FORCE_PIP_INSTALL:-0}" == "1" ]]; then
    need_install=1
  elif [[ -f "$stamp_file" && "$requirements_file" -nt "$stamp_file" ]]; then
    need_install=1
  elif [[ ! -f "$stamp_file" ]]; then
    if "$venv_dir/bin/python" -c "import django,requests" >/dev/null 2>&1; then
      date -u +"%Y-%m-%dT%H:%M:%SZ" > "$stamp_file"
      need_install=0
    else
      need_install=1
    fi
  fi

  if [[ "$need_install" == "1" ]]; then
    echo "Installing dependencies for: $app_dir"
    "$venv_dir/bin/python" -m pip install --upgrade pip
    "$venv_dir/bin/python" -m pip install -r "$requirements_file"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$stamp_file"
  fi
}

internal_api_is_healthy() {
  local port="$1"
  python3 - "$port" <<'PY'
import sys
import urllib.request

port = str(sys.argv[1] or "5100").strip() or "5100"
url = f"http://127.0.0.1:{port}/health"
try:
    with urllib.request.urlopen(url, timeout=1.5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

is_port_in_use() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1] or "2000")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
try:
    s.connect(("127.0.0.1", port))
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
finally:
    s.close()
PY
}

django_app_is_healthy() {
  local port="$1"
  python3 - "$port" <<'PY'
import sys
import urllib.request

port = str(sys.argv[1] or "2000").strip() or "2000"
url = f"http://127.0.0.1:{port}/health/db"
try:
    with urllib.request.urlopen(url, timeout=1.5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

start_internal_api_if_needed() {
  local port="$1"
  local log_file="$MAIN_DIR/.internal_api.log"

  if internal_api_is_healthy "$port"; then
    echo "Internal API already healthy at http://127.0.0.1:${port}"
    return 0
  fi

  echo "Starting internal API at http://127.0.0.1:${port}"
  (
    cd "$INTERNAL_DIR"
    "$INTERNAL_VENV/bin/python" run.py
  ) >> "$log_file" 2>&1 &
  INTERNAL_PID=$!

  local wait_seconds=20
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    if internal_api_is_healthy "$port"; then
      echo "Internal API is healthy."
      return 0
    fi

    if ! kill -0 "$INTERNAL_PID" >/dev/null 2>&1; then
      echo "Warning: internal API process exited early. Check $log_file"
      return 1
    fi

    local now_ts
    now_ts="$(date +%s)"
    if (( now_ts - start_ts >= wait_seconds )); then
      echo "Warning: internal API did not become healthy in ${wait_seconds}s. Check $log_file"
      return 1
    fi
    sleep 0.5
  done
}

cleanup() {
  if [[ -n "${INTERNAL_PID:-}" ]] && kill -0 "$INTERNAL_PID" >/dev/null 2>&1; then
    echo "Stopping internal API (pid ${INTERNAL_PID})"
    kill "$INTERNAL_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

choose_main_venv() {
  if [[ -x "$MAIN_DIR/.venv/bin/python" ]]; then
    MAIN_VENV="$MAIN_DIR/.venv"
    return
  fi
  if [[ -x "$MAIN_DIR/.venv_runtime/bin/python" ]]; then
    MAIN_VENV="$MAIN_DIR/.venv_runtime"
    return
  fi
  if [[ -x "$MAIN_DIR/.venv39/bin/python" ]]; then
    MAIN_VENV="$MAIN_DIR/.venv39"
    return
  fi
  MAIN_VENV="$MAIN_DIR/.venv"
}

INTERNAL_ALERTS_URL="http://127.0.0.1:2000/api/internal/alerts"
INTERNAL_AUTOSTART_FLAG="false"
if [[ "$EMBED_INTERNAL_API" != "1" ]]; then
  INTERNAL_ALERTS_URL="http://127.0.0.1:5100/api/alerts"
  INTERNAL_AUTOSTART_FLAG="true"
fi

PRIMARY_DB_VALUE="${PRIMARY_DB:-mongodb}"
EXISTING_MONGODB_URI="$(read_env_value "$MAIN_DIR/.env" "MONGODB_URI")"
EXISTING_MONGODB_LOCAL_URI="$(read_env_value "$MAIN_DIR/.env" "MONGODB_LOCAL_URI")"
EXISTING_SHARED_MONGODB_URI="$(read_env_value "$MAIN_DIR/.env" "SHARED_MONGODB_URI")"
EXISTING_MONGODB_DB_NAME="$(read_env_value "$MAIN_DIR/.env" "MONGODB_DB_NAME")"
EXISTING_MONGODB_PRIORITY="$(read_env_value "$MAIN_DIR/.env" "MONGODB_URI_PRIORITY")"
EXISTING_MONGODB_BACKEND="$(read_env_value "$MAIN_DIR/.env" "MONGODB_BACKEND")"
EXISTING_MONGODB_VERIFY="$(read_env_value "$MAIN_DIR/.env" "MONGODB_VERIFY_ON_STARTUP")"
EXISTING_MONGODB_TIMEOUT="$(read_env_value "$MAIN_DIR/.env" "MONGODB_CONNECT_TIMEOUT_MS")"
EXISTING_MONGODB_BRIDGE_SYNC="$(read_env_value "$MAIN_DIR/.env" "MONGODB_BRIDGE_SYNC")"
EXISTING_MONGODB_BRIDGE_INTERVAL="$(read_env_value "$MAIN_DIR/.env" "MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS")"
EXISTING_MONGODB_BRIDGE_SCOPE="$(read_env_value "$MAIN_DIR/.env" "MONGODB_BRIDGE_SCOPE")"

MONGODB_DB_NAME_VALUE="${MONGODB_DB_NAME:-${EXISTING_MONGODB_DB_NAME:-resqfy}}"
MONGODB_LOCAL_URI_DEFAULT="mongodb://127.0.0.1:27017/$MONGODB_DB_NAME_VALUE"
MONGODB_LOCAL_URI_VALUE="${MONGODB_LOCAL_URI:-${EXISTING_MONGODB_LOCAL_URI:-$MONGODB_LOCAL_URI_DEFAULT}}"
SHARED_MONGODB_URI_VALUE="${SHARED_MONGODB_URI:-${EXISTING_SHARED_MONGODB_URI:-}}"
MONGODB_URI_VALUE="${MONGODB_URI:-${EXISTING_MONGODB_URI:-$MONGODB_LOCAL_URI_VALUE}}"
MONGODB_URI_PRIORITY_VALUE="${MONGODB_URI_PRIORITY:-${EXISTING_MONGODB_PRIORITY:-local,shared}}"
MONGODB_BACKEND_VALUE="${MONGODB_BACKEND:-${EXISTING_MONGODB_BACKEND:-auto}}"
MONGODB_VERIFY_VALUE="${MONGODB_VERIFY_ON_STARTUP:-${EXISTING_MONGODB_VERIFY:-1}}"
MONGODB_TIMEOUT_VALUE="${MONGODB_CONNECT_TIMEOUT_MS:-${EXISTING_MONGODB_TIMEOUT:-2500}}"
MONGODB_BRIDGE_SYNC_VALUE="${MONGODB_BRIDGE_SYNC:-${EXISTING_MONGODB_BRIDGE_SYNC:-1}}"
MONGODB_BRIDGE_INTERVAL_VALUE="${MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS:-${EXISTING_MONGODB_BRIDGE_INTERVAL:-20}}"
MONGODB_BRIDGE_SCOPE_VALUE="${MONGODB_BRIDGE_SCOPE:-${EXISTING_MONGODB_BRIDGE_SCOPE:-users_only}}"
MONGODB_SQLITE_SYNC_VALUE="${MONGODB_SQLITE_FALLBACK_SYNC:-1}"
MONGODB_SQLITE_SYNC_INTERVAL_VALUE="${MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS:-15}"

echo "Preparing internal API environment..."
internal_api_key="$(read_env_value "$MAIN_DIR/.env" "INTERNAL_ALERTS_API_KEY")"
if [[ -z "${internal_api_key:-}" && "$INTERNAL_DIR_EXISTS" == "1" ]]; then
  if [[ ! -f "$INTERNAL_DIR/.env" ]]; then
    cp "$INTERNAL_DIR/.env.example" "$INTERNAL_DIR/.env"
  fi
  ensure_venv "$INTERNAL_DIR" "$INTERNAL_VENV" "$INTERNAL_DIR/requirements.txt"
  internal_api_key="$(read_env_value "$INTERNAL_DIR/.env" "INTERNAL_API_KEY")"
fi
if [[ -z "${internal_api_key:-}" ]]; then
  internal_api_key="$(openssl rand -hex 32)"
fi

if [[ "$INTERNAL_DIR_EXISTS" == "1" ]]; then
  admin_api_key="$(read_env_value "$INTERNAL_DIR/.env" "ADMIN_API_KEY")"
  if [[ -z "${admin_api_key:-}" ]]; then
    admin_api_key="$(openssl rand -hex 32)"
  fi

  upsert_env_value "$INTERNAL_DIR/.env" "INTERNAL_API_KEY" "$internal_api_key"
  upsert_env_value "$INTERNAL_DIR/.env" "ADMIN_API_KEY" "$admin_api_key"
  upsert_env_value "$INTERNAL_DIR/.env" "ENABLE_SCHEDULER" "true"
  upsert_env_value "$INTERNAL_DIR/.env" "RUN_SYNC_ON_STARTUP" "true"
  upsert_env_value "$INTERNAL_DIR/.env" "INTERNAL_API_PORT" "5100"
else
  echo "Internal API folder not found. Using embedded mode only."
fi

echo "Preparing main app environment..."
choose_main_venv
echo "Using main app virtualenv: $MAIN_VENV"
if [[ ! -f "$MAIN_DIR/.env" ]]; then
  cat > "$MAIN_DIR/.env" <<EOF
PRIMARY_DB=$PRIMARY_DB_VALUE
SQLITE_DB_PATH=app.db
MONGODB_URI=$MONGODB_URI_VALUE
MONGODB_LOCAL_URI=$MONGODB_LOCAL_URI_VALUE
SHARED_MONGODB_URI=$SHARED_MONGODB_URI_VALUE
MONGODB_URI_PRIORITY=$MONGODB_URI_PRIORITY_VALUE
MONGODB_DB_NAME=$MONGODB_DB_NAME_VALUE
MONGODB_BACKEND=$MONGODB_BACKEND_VALUE
MONGODB_VERIFY_ON_STARTUP=$MONGODB_VERIFY_VALUE
MONGODB_CONNECT_TIMEOUT_MS=$MONGODB_TIMEOUT_VALUE
MONGODB_BRIDGE_SYNC=$MONGODB_BRIDGE_SYNC_VALUE
MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS=$MONGODB_BRIDGE_INTERVAL_VALUE
MONGODB_BRIDGE_SCOPE=$MONGODB_BRIDGE_SCOPE_VALUE
MONGODB_SQLITE_FALLBACK_SYNC=$MONGODB_SQLITE_SYNC_VALUE
MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS=$MONGODB_SQLITE_SYNC_INTERVAL_VALUE
PORT=2000
SECRET_KEY=$(openssl rand -hex 24)
INTERNAL_ALERTS_API_URL=$INTERNAL_ALERTS_URL
INTERNAL_ALERTS_API_KEY=$internal_api_key
INTERNAL_ALERTS_API_KEY_HEADER=X-Internal-API-Key
INTERNAL_API_AUTOSTART=$INTERNAL_AUTOSTART_FLAG
INTERNAL_API_SYNC_ON_STARTUP=true
INTERNAL_API_SYNC_ON_ALERT_REQUEST=true
INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS=300
INTERNAL_API_POLL_INTERVAL_SECONDS=300
SQLITE_BOOTSTRAP_FROM_MYSQL=0
SQLITE_CONTINUOUS_SYNC_FROM_MYSQL=0
MYSQL_REVERSE_SYNC_FROM_SQLITE=0
MOBILE_ALERTS_SOURCE_POLICY=auto_fallback
DISABLE_GOOGLE_OAUTH=1
EOF
fi

upsert_env_value "$MAIN_DIR/.env" "PRIMARY_DB" "$PRIMARY_DB_VALUE"
upsert_env_value "$MAIN_DIR/.env" "SQLITE_BOOTSTRAP_FROM_MYSQL" "0"
upsert_env_value "$MAIN_DIR/.env" "SQLITE_CONTINUOUS_SYNC_FROM_MYSQL" "0"
upsert_env_value "$MAIN_DIR/.env" "MYSQL_REVERSE_SYNC_FROM_SQLITE" "0"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_URI" "$MONGODB_URI_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_LOCAL_URI" "$MONGODB_LOCAL_URI_VALUE"
upsert_env_value "$MAIN_DIR/.env" "SHARED_MONGODB_URI" "$SHARED_MONGODB_URI_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_URI_PRIORITY" "$MONGODB_URI_PRIORITY_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_DB_NAME" "$MONGODB_DB_NAME_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_BACKEND" "$MONGODB_BACKEND_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_VERIFY_ON_STARTUP" "$MONGODB_VERIFY_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_CONNECT_TIMEOUT_MS" "$MONGODB_TIMEOUT_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_BRIDGE_SYNC" "$MONGODB_BRIDGE_SYNC_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS" "$MONGODB_BRIDGE_INTERVAL_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_BRIDGE_SCOPE" "$MONGODB_BRIDGE_SCOPE_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_SQLITE_FALLBACK_SYNC" "$MONGODB_SQLITE_SYNC_VALUE"
upsert_env_value "$MAIN_DIR/.env" "MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS" "$MONGODB_SQLITE_SYNC_INTERVAL_VALUE"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_ALERTS_API_URL" "$INTERNAL_ALERTS_URL"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_ALERTS_API_KEY_HEADER" "X-Internal-API-Key"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_ALERTS_API_KEY" "$internal_api_key"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_API_AUTOSTART" "$INTERNAL_AUTOSTART_FLAG"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_API_SYNC_ON_STARTUP" "true"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_API_SYNC_ON_ALERT_REQUEST" "true"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS" "300"
upsert_env_value "$MAIN_DIR/.env" "INTERNAL_API_POLL_INTERVAL_SECONDS" "300"
upsert_env_value "$MAIN_DIR/.env" "MOBILE_ALERTS_SOURCE_POLICY" "auto_fallback"
upsert_env_value "$MAIN_DIR/.env" "DISABLE_GOOGLE_OAUTH" "1"

ensure_venv "$MAIN_DIR" "$MAIN_VENV" "$MAIN_DIR/requirements.txt"

PORT_VALUE="$(read_env_value "$MAIN_DIR/.env" "PORT")"
PORT_VALUE="${PORT_VALUE:-${PORT:-2000}}"
INTERNAL_PORT_VALUE="$(read_env_value "$INTERNAL_DIR/.env" "INTERNAL_API_PORT")"
INTERNAL_PORT_VALUE="${INTERNAL_PORT_VALUE:-5100}"

if [[ "$EMBED_INTERNAL_API" != "1" ]]; then
  start_internal_api_if_needed "$INTERNAL_PORT_VALUE" || true
else
  echo "Using embedded internal API endpoints via Django."
fi

if [[ "$PRIMARY_DB_VALUE" == "mongodb" ]]; then
  if [[ -n "${MONGODB_LOCAL_URI_VALUE:-}" || -n "${SHARED_MONGODB_URI_VALUE:-}" || -n "${MONGODB_URI_VALUE:-}" ]]; then
    echo "Primary DB requested: MongoDB (with SQLite fallback enabled)."
    echo "Mongo priority order: $MONGODB_URI_PRIORITY_VALUE"
    if [[ -n "${MONGODB_LOCAL_URI_VALUE:-}" ]]; then
      echo "✅ Local Mongo candidate set (preferred for speed when available)."
    fi
    if [[ -n "${SHARED_MONGODB_URI_VALUE:-}" ]]; then
      echo "✅ Shared Mongo candidate set (used when local Mongo is unavailable)."
    else
      echo "⚠️ Shared Mongo candidate is empty. Other machines will not share local-only data."
    fi
  else
    echo "Primary DB requested: MongoDB, but no Mongo URI candidates are set; SQLite fallback will be used."
  fi
fi

if is_port_in_use "$PORT_VALUE"; then
  if django_app_is_healthy "$PORT_VALUE"; then
    echo "Django app is already running at http://127.0.0.1:${PORT_VALUE}"
    echo "Reusing existing server process."
    exit 0
  fi
  echo "Error: http://127.0.0.1:${PORT_VALUE} is already in use by another process."
  echo "Set a different PORT in .env or stop the process using that port."
  exit 1
fi

echo "Starting Django app at http://127.0.0.1:${PORT_VALUE}"
cd "$MAIN_DIR"
if [[ "$PRIMARY_DB_VALUE" == "mongodb" ]]; then
  echo "Running SQLite fallback schema migrations..."
  "$MAIN_VENV/bin/python" manage.py migrate --database fallback_sqlite --noinput || true
  echo "Skipping default-database migrate for MongoDB runtime mode."
else
  "$MAIN_VENV/bin/python" manage.py migrate --noinput || true
fi
"$MAIN_VENV/bin/python" manage.py runserver "127.0.0.1:${PORT_VALUE}"
