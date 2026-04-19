#!/usr/bin/env bash
set -euo pipefail

# Configure a named Cloudflare Tunnel with fixed DNS hostname for local ProjectZ app.
# Works for macOS/Linux where cloudflared is installed.

TUNNEL_NAME="${TUNNEL_NAME:-projectz-main}"
DOMAIN_ROOT="${DOMAIN_ROOT:-matrikaregmi.com.np}"
SUBDOMAIN="${SUBDOMAIN:-app}"
APP_PORT="${APP_PORT:-8002}"

HOSTNAME="${SUBDOMAIN}.${DOMAIN_ROOT}"
CLOUDFLARED_DIR="${HOME}/.cloudflared"
CONFIG_FILE="${CLOUDFLARED_DIR}/config-${TUNNEL_NAME}.yml"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed."
  echo "macOS (Homebrew): brew install cloudflared"
  echo "Linux: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
fi

mkdir -p "$CLOUDFLARED_DIR"

if ! cloudflared tunnel list >/dev/null 2>&1; then
  echo "Cloudflare auth not found yet. Opening login flow..."
  cloudflared tunnel login
fi

if ! cloudflared tunnel info "$TUNNEL_NAME" >/dev/null 2>&1; then
  echo "Creating tunnel: $TUNNEL_NAME"
  cloudflared tunnel create "$TUNNEL_NAME"
fi

TUNNEL_ID="$(cloudflared tunnel list | awk -v t="$TUNNEL_NAME" '$2 == t {print $1; exit}')"

if [[ -z "$TUNNEL_ID" ]]; then
  echo "Could not resolve tunnel ID for tunnel name: $TUNNEL_NAME"
  echo "Run: cloudflared tunnel list"
  exit 1
fi

CREDENTIALS_FILE="${CLOUDFLARED_DIR}/${TUNNEL_ID}.json"
if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  echo "Missing credentials file: $CREDENTIALS_FILE"
  echo "Run: cloudflared tunnel create $TUNNEL_NAME"
  exit 1
fi

echo "Routing DNS hostname to tunnel: $HOSTNAME"
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME"

cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDENTIALS_FILE

ingress:
  - hostname: $HOSTNAME
    service: http://127.0.0.1:$APP_PORT
  - service: http_status:404
EOF

echo ""
echo "Cloudflare tunnel configured."
echo "Hostname: https://$HOSTNAME"
echo "Config:   $CONFIG_FILE"
echo ""
echo "Start tunnel in foreground:"
echo "  cloudflared --config $CONFIG_FILE tunnel run"
echo ""
echo "Keep your app running locally on port $APP_PORT, then open:"
echo "  https://$HOSTNAME"
