#!/usr/bin/env bash
set -euo pipefail

# Google Cloud VM helper for Internal Disaster API systemd setup.
# Run as your normal user, and it will use sudo only where needed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_TEMPLATE="$PROJECT_ROOT/deploy/internal-disaster-api.service"
SERVICE_NAME="internal-disaster-api"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

SERVICE_USER="${SERVICE_USER:-$USER}"
SERVICE_GROUP="${SERVICE_GROUP:-$USER}"
INTERNAL_API_PORT="${INTERNAL_API_PORT:-5100}"

VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env}"

if [[ ! -f "$SERVICE_TEMPLATE" ]]; then
  echo "Missing service template: $SERVICE_TEMPLATE"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  echo "Create it first (example: cp .env.example .env)"
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

# Ensure required scheduler settings are present in .env
ensure_env_var() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf "\n%s=%s\n" "$key" "$value" >> "$ENV_FILE"
  fi
}

ensure_env_var "ENABLE_SCHEDULER" "true"
ensure_env_var "RUN_SYNC_ON_STARTUP" "true"
ensure_env_var "INTERNAL_API_DEBUG" "false"
ensure_env_var "INTERNAL_API_PORT" "$INTERNAL_API_PORT"

TMP_SERVICE="$(mktemp)"
cp "$SERVICE_TEMPLATE" "$TMP_SERVICE"

sed -i.bak "s|__SERVICE_USER__|$SERVICE_USER|g" "$TMP_SERVICE"
sed -i.bak "s|__SERVICE_GROUP__|$SERVICE_GROUP|g" "$TMP_SERVICE"
sed -i.bak "s|__WORKING_DIRECTORY__|$PROJECT_ROOT|g" "$TMP_SERVICE"
sed -i.bak "s|__ENV_FILE__|$ENV_FILE|g" "$TMP_SERVICE"
sed -i.bak "s|__VENV_PYTHON__|$VENV_DIR/bin/python|g" "$TMP_SERVICE"
sed -i.bak "s|127.0.0.1:5100|127.0.0.1:${INTERNAL_API_PORT}|g" "$TMP_SERVICE"

sudo cp "$TMP_SERVICE" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo ""
echo "Service installed and started: $SERVICE_NAME"
echo "Check status: sudo systemctl status $SERVICE_NAME"
echo "Tail logs:    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Quick API checks:"
echo "  curl -sS http://127.0.0.1:${INTERNAL_API_PORT}/health"
echo "  curl -sS -H \"X-Internal-API-Key: <your-key>\" http://127.0.0.1:${INTERNAL_API_PORT}/api/sources/status"
