# version_1

## One-Command Local Start (SQLite, beginner friendly)

From a fresh clone, run:

```bash
cd projectz_v.2
./start_local.sh
```

What this does automatically:

- creates virtualenvs for main app and internal API (if missing)
- installs dependencies
- enforces SQLite-first mode (no MySQL requirement)
- aligns internal API key between both apps
- starts Django on `http://127.0.0.1:2000`
- auto-starts internal API on `:5100` and syncs latest alerts

step 1-> make an .env file for environment variables

db_host = localhost
db_user = root
db_password = ayaan
db_name=Save_India
secret_key=secret

copy paste for user ayaan local machine change for yourself accordingly

## Live Disaster Alert Integration

This project now supports backend ingestion of external alert feeds and serves them as JSON for mobile UI.

### Environment variables

Add these optional variables in `.env`:

- `ALERT_SYNC_INTERVAL_SECONDS=120` (poll window; default is 120 seconds)
- `NDMA_CAP_FEED_URL=https://sachet.ndma.gov.in/cap_public_website.xml`
- `IMD_RSS_FEED_URL=https://mausam.imd.gov.in/`
- `CWC_FEED_URL=https://ffs.india-water.gov.in/`

### Backend endpoints

- `GET /api/mobile-alerts` → returns stored alerts and performs sync if cache is stale.
- `POST /api/mobile-alerts/sync` → manual sync trigger.
- `POST /api/mobile-alerts/sync?force=true` → force sync immediately.

### Notes

- NDMA SACHET can return `403` for some environments unless access is whitelisted or routed through an approved channel.
- IMD/CWC endpoints can also change structure or availability; keep feed URLs configurable in `.env`.

## Google Cloud Always Free - Main App Auto Start

You can run this as a single app. The internal API service is optional.

1) Prepare environment and dependencies:

```bash
cd projectz_v.2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Create `.env` (or update it) with at least:

```env
PORT=8001
APP_URL_SCHEME=https
MOBILE_ALERTS_SOURCE_POLICY=live_only
PRIMARY_DB=sqlite
SQLITE_DB_PATH=app.db
secret_key=<your-random-secret>
```

Optional (only if you still use the separate internal API):

```env
INTERNAL_ALERTS_API_URL=http://127.0.0.1:5100/api/alerts
INTERNAL_ALERTS_API_KEY=<same key used by internal API>
INTERNAL_ALERTS_API_KEY_HEADER=X-Internal-API-Key
```

3) Install and start `systemd` service:

```bash
./scripts/setup_main_gcp_service.sh
```

4) Verify:

```bash
sudo systemctl status projectz-main-web
sudo journalctl -u projectz-main-web -f
curl -sS http://127.0.0.1:8001/
```

5) Restart after code changes:

```bash
sudo systemctl restart projectz-main-web
```

Tip:

- Open GCP firewall for your app port (`8001`) if you access it directly from browser.

## Cloudflare Tunnel with Fixed Domain (matrikaregmi.com.np)

Use this if you want a stable URL instead of temporary quick tunnel links.

1) Install `cloudflared` (macOS):

```bash
brew install cloudflared
```

2) Ensure your app runs locally on port `8002`:

```bash
cd projectz_v.2
PORT=8002 ./.venv39/bin/python manage.py runserver 0.0.0.0:8002
```

3) In another terminal, configure named tunnel + fixed DNS:

```bash
cd projectz_v.2
DOMAIN_ROOT=matrikaregmi.com.np SUBDOMAIN=app APP_PORT=8002 ./scripts/setup_cloudflare_tunnel.sh
```

4) Start tunnel with generated config:

```bash
cloudflared --config ~/.cloudflared/config-projectz-main.yml tunnel run
```

Result:

- Your fixed URL will be `https://app.matrikaregmi.com.np`
- You can open it from your phone immediately (mobile network or Wi-Fi).

Notes:

- First run will open Cloudflare login in browser (`cloudflared tunnel login`).
- Make sure your domain is active in your Cloudflare account.
- If `app` is already used, change `SUBDOMAIN` (for example: `projectz`).

## Google Cloud Always Free - Nginx + HTTPS (Domain)

After `projectz-main-web` service is running, use Nginx as reverse proxy and enable HTTPS with Let's Encrypt.

1) Point your domain DNS `A` record to your VM external IP.

2) Ensure GCP firewall allows inbound `80` and `443`.

3) On VM, run:

```bash
cd projectz_v.2
DOMAIN=yourdomain.com EMAIL=you@example.com ./scripts/setup_nginx_https.sh
```

4) Verify:

```bash
curl -I http://yourdomain.com
curl -I https://yourdomain.com
sudo systemctl status nginx
```

Notes:

- Script installs `nginx`, `certbot`, and `python3-certbot-nginx`.
- It creates Nginx site config from `deploy/nginx/projectz.conf.template`.
- It enables HTTP→HTTPS redirect automatically.

## Google Cloud Firewall (One Command)

Use this to open inbound `80/443` and (optionally) tag your VM.

```bash
cd projectz_v.2
PROJECT_ID=<your-project-id> ./scripts/setup_gcp_firewall.sh
```

Apply the network tag to your VM in the same run:

```bash
PROJECT_ID=<your-project-id> INSTANCE_NAME=<vm-name> INSTANCE_ZONE=<zone> ./scripts/setup_gcp_firewall.sh
```

Notes:

- Script path: `scripts/setup_gcp_firewall.sh`
- Default firewall rule name: `projectz-allow-web`
- Default target tag: `projectz-web`

## Beginner One-Command Setup (VM)

If you are starting from zero, run everything with one script:

```bash
cd projectz_v.2
./scripts/full_gcp_setup.sh
```

With firewall + VM tag + HTTPS in same run:

```bash
PROJECT_ID=<your-project-id> INSTANCE_NAME=<vm-name> INSTANCE_ZONE=<zone> DOMAIN=yourdomain.com EMAIL=you@example.com ./scripts/full_gcp_setup.sh
```

Requirements for this script:

- Folder layout on VM must be sibling directories:
	- `projectz_v.2`
	- `internal api`
- VM user must have `sudo` access.
- DNS A record must point to VM IP if using HTTPS.
