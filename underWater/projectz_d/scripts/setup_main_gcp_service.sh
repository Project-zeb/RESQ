#!/usr/bin/env bash
set -euo pipefail

# Google Cloud VM helper for main Django app systemd setup.
# Run as normal user. It uses sudo only for systemd actions.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_TEMPLATE="$PROJECT_ROOT/deploy/projectz-main-web.service"
SERVICE_NAME="projectz-main-web"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

SERVICE_USER="${SERVICE_USER:-$USER}"
SERVICE_GROUP="${SERVICE_GROUP:-$USER}"
APP_PORT="${APP_PORT:-8001}"

VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env}"

if [[ ! -f "$SERVICE_TEMPLATE" ]]; then
  echo "Missing service template: $SERVICE_TEMPLATE"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  echo "Create it first (example: cp .env.example .env if available, or create .env manually)."
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Python venv not found at $VENV_DIR"
  echo "Run:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

ensure_env_var() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf "\n%s=%s\n" "$key" "$value" >> "$ENV_FILE"
  fi
}

ensure_env_var "PORT" "$APP_PORT"
ensure_env_var "APP_URL_SCHEME" "https"

TMP_SERVICE="$(mktemp)"
cp "$SERVICE_TEMPLATE" "$TMP_SERVICE"

sed -i.bak "s|__SERVICE_USER__|$SERVICE_USER|g" "$TMP_SERVICE"
sed -i.bak "s|__SERVICE_GROUP__|$SERVICE_GROUP|g" "$TMP_SERVICE"
sed -i.bak "s|__WORKING_DIRECTORY__|$PROJECT_ROOT|g" "$TMP_SERVICE"
sed -i.bak "s|__ENV_FILE__|$ENV_FILE|g" "$TMP_SERVICE"
sed -i.bak "s|__VENV_PYTHON__|$VENV_DIR/bin/python|g" "$TMP_SERVICE"
sed -i.bak "s|0.0.0.0:8001|0.0.0.0:${APP_PORT}|g" "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo ""
echo "Service installed and started: $SERVICE_NAME"
echo "Check status: sudo systemctl status $SERVICE_NAME"
echo "Tail logs:    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Quick checks:"
echo "  curl -sS http://127.0.0.1:${APP_PORT}/"
