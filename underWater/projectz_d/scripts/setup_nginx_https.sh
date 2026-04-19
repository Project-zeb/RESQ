#!/usr/bin/env bash
set -euo pipefail

# Setup Nginx reverse proxy + Let's Encrypt HTTPS for ProjectZ main app on GCP VM.
# Tested for Ubuntu/Debian style systems.

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "Run this script as a normal user with sudo privileges (not as root)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_FILE="$PROJECT_ROOT/deploy/nginx/projectz.conf.template"
SITE_NAME="projectz"
SITE_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
SITE_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
ENABLE_UFW="${ENABLE_UFW:-false}"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Usage: DOMAIN=yourdomain.com EMAIL=you@example.com ./scripts/setup_nginx_https.sh"
  echo "Example: DOMAIN=projectz.example.com EMAIL=admin@example.com ./scripts/setup_nginx_https.sh"
  exit 1
fi

if [[ ! -f "$TEMPLATE_FILE" ]]; then
  echo "Missing template: $TEMPLATE_FILE"
  exit 1
fi

command -v sudo >/dev/null || { echo "sudo is required"; exit 1; }

if ! command -v apt-get >/dev/null; then
  echo "This script currently supports apt-based systems (Ubuntu/Debian)."
  echo "Install nginx + certbot manually on your distro, then reuse template: $TEMPLATE_FILE"
  exit 1
fi

echo "Installing packages..."
sudo apt-get update -y
sudo apt-get install -y nginx certbot python3-certbot-nginx

echo "Creating nginx site config for $DOMAIN"
TMP_CONF="$(mktemp)"
cp "$TEMPLATE_FILE" "$TMP_CONF"
sed -i.bak "s|__DOMAIN__|$DOMAIN|g" "$TMP_CONF"

sudo cp "$TMP_CONF" "$SITE_AVAILABLE"
sudo ln -sfn "$SITE_AVAILABLE" "$SITE_ENABLED"

if [[ -e /etc/nginx/sites-enabled/default ]]; then
  sudo rm -f /etc/nginx/sites-enabled/default
fi

echo "Testing and reloading nginx"
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

if [[ "$ENABLE_UFW" == "true" ]] && command -v ufw >/dev/null; then
  echo "Opening HTTP/HTTPS in UFW"
  sudo ufw allow 'Nginx Full' || true
fi

echo "Requesting Let's Encrypt certificate for $DOMAIN"
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect

echo "Verifying certbot timer"
sudo systemctl enable --now certbot.timer >/dev/null 2>&1 || true
sudo systemctl status certbot.timer --no-pager || true

echo ""
echo "HTTPS setup complete."
echo "Check: https://$DOMAIN"
echo "Nginx status: sudo systemctl status nginx"
echo "Nginx logs:   sudo journalctl -u nginx -f"
