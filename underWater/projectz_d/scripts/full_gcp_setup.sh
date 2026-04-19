#!/usr/bin/env bash
set -euo pipefail

# One-command bootstrap for ProjectZ on a GCP VM.
# Run on VM from project root: ./scripts/full_gcp_setup.sh
# Optional env vars:
#   DOMAIN, EMAIL, PROJECT_ID, INSTANCE_NAME, INSTANCE_ZONE

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERNAL_DIR="$(cd "$ROOT_DIR/../internal api" 2>/dev/null && pwd || true)"
MAIN_DIR="$ROOT_DIR"

if [[ -z "$INTERNAL_DIR" || ! -d "$INTERNAL_DIR" ]]; then
  echo "Could not find sibling folder: ../internal api"
  echo "Expected structure on VM:"
  echo "  /home/<user>/projectz_v.2"
  echo "  /home/<user>/internal api"
  exit 1
fi

ensure_env_var() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -qE "^${key}=" "$file"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf "\n%s=%s\n" "$key" "$value" >> "$file"
  fi
}

gen_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

echo "[1/7] Installing system packages"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
else
  echo "Non-apt system detected. Install python3, venv, pip, nginx, certbot manually first."
fi

echo "[2/7] Setting up internal API Python environment"
cd "$INTERNAL_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

INTERNAL_KEY="$(grep -E '^INTERNAL_API_KEY=' .env | head -n1 | cut -d= -f2- || true)"
ADMIN_KEY="$(grep -E '^ADMIN_API_KEY=' .env | head -n1 | cut -d= -f2- || true)"
[[ -n "$INTERNAL_KEY" ]] || INTERNAL_KEY="$(gen_secret)"
[[ -n "$ADMIN_KEY" ]] || ADMIN_KEY="$(gen_secret)"

ensure_env_var .env INTERNAL_API_KEY "$INTERNAL_KEY"
ensure_env_var .env ADMIN_API_KEY "$ADMIN_KEY"
ensure_env_var .env ENABLE_SCHEDULER true
ensure_env_var .env RUN_SYNC_ON_STARTUP true
ensure_env_var .env INTERNAL_API_DEBUG false
ensure_env_var .env INTERNAL_API_PORT 5100

if [[ -x ./scripts/setup_gcp_service.sh ]]; then
  echo "[3/7] Installing internal API systemd service"
  ./scripts/setup_gcp_service.sh
else
  echo "Missing executable script: $INTERNAL_DIR/scripts/setup_gcp_service.sh"
  exit 1
fi

deactivate || true

echo "[4/7] Setting up main app Python environment"
cd "$MAIN_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  touch .env
fi

SECRET_KEY_CURRENT="$(grep -E '^secret_key=' .env | head -n1 | cut -d= -f2- || true)"
[[ -n "$SECRET_KEY_CURRENT" ]] || SECRET_KEY_CURRENT="$(gen_secret)"

ensure_env_var .env PORT 8001
ensure_env_var .env APP_URL_SCHEME https
ensure_env_var .env PRIMARY_DB sqlite
ensure_env_var .env SQLITE_DB_PATH app.db
ensure_env_var .env INTERNAL_ALERTS_API_URL http://127.0.0.1:5100/api/alerts
ensure_env_var .env INTERNAL_ALERTS_API_KEY "$INTERNAL_KEY"
ensure_env_var .env INTERNAL_ALERTS_API_KEY_HEADER X-Internal-API-Key
ensure_env_var .env MOBILE_ALERTS_SOURCE_POLICY live_only
ensure_env_var .env secret_key "$SECRET_KEY_CURRENT"

if [[ -x ./scripts/setup_main_gcp_service.sh ]]; then
  echo "[5/7] Installing main app systemd service"
  ./scripts/setup_main_gcp_service.sh
else
  echo "Missing executable script: $MAIN_DIR/scripts/setup_main_gcp_service.sh"
  exit 1
fi

deactivate || true

echo "[6/7] Optional: opening GCP firewall (if PROJECT_ID provided)"
if [[ -n "${PROJECT_ID:-}" ]]; then
  if [[ -n "${INSTANCE_NAME:-}" && -n "${INSTANCE_ZONE:-}" ]]; then
    PROJECT_ID="$PROJECT_ID" INSTANCE_NAME="$INSTANCE_NAME" INSTANCE_ZONE="$INSTANCE_ZONE" ./scripts/setup_gcp_firewall.sh || true
  else
    PROJECT_ID="$PROJECT_ID" ./scripts/setup_gcp_firewall.sh || true
  fi
else
  echo "Skipping firewall script (set PROJECT_ID to enable)."
fi

echo "[7/7] Optional: enabling HTTPS (if DOMAIN + EMAIL provided)"
if [[ -n "${DOMAIN:-}" && -n "${EMAIL:-}" ]]; then
  DOMAIN="$DOMAIN" EMAIL="$EMAIL" ./scripts/setup_nginx_https.sh
else
  echo "Skipping HTTPS setup (set DOMAIN and EMAIL to enable)."
fi

echo ""
echo "Bootstrap finished."
echo "Check services:"
echo "  sudo systemctl status internal-disaster-api"
echo "  sudo systemctl status projectz-main-web"
echo "Open app:"
echo "  http://<vm-external-ip>:8001  (without domain/https)"
echo "  https://<your-domain>         (if DOMAIN/EMAIL were provided)"
