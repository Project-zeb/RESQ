#!/usr/bin/env bash
set -euo pipefail

INTERNAL_API_BASE_URL="${INTERNAL_API_BASE_URL:-http://127.0.0.1:5100}"
INTERNAL_API_ENV_FILE="${INTERNAL_API_ENV_FILE:-/Users/matrika/Desktop/sensor/internal api/.env}"

INTERNAL_API_KEY="${INTERNAL_API_KEY:-}"
INTERNAL_API_KEY_HEADER="${INTERNAL_API_KEY_HEADER:-X-Internal-API-Key}"

if [[ -z "$INTERNAL_API_KEY" && -f "$INTERNAL_API_ENV_FILE" ]]; then
  INTERNAL_API_KEY="$(grep -E '^INTERNAL_API_KEY=' "$INTERNAL_API_ENV_FILE" | head -n1 | sed 's/^INTERNAL_API_KEY=//')"
  INTERNAL_API_KEY_HEADER_FROM_ENV="$(grep -E '^API_KEY_HEADER=' "$INTERNAL_API_ENV_FILE" | head -n1 | sed 's/^API_KEY_HEADER=//')"
  if [[ -n "$INTERNAL_API_KEY_HEADER_FROM_ENV" ]]; then
    INTERNAL_API_KEY_HEADER="$INTERNAL_API_KEY_HEADER_FROM_ENV"
  fi
fi

if [[ -z "$INTERNAL_API_KEY" ]]; then
  echo "ERROR: INTERNAL_API_KEY not set and not found in $INTERNAL_API_ENV_FILE"
  echo "Set it as env var and retry: INTERNAL_API_KEY='...' ./scripts/check_internal_source_status.sh"
  exit 1
fi

echo "Internal API status check"
echo "BASE_URL=$INTERNAL_API_BASE_URL"
echo "KEY_HEADER=$INTERNAL_API_KEY_HEADER"

tmp_status="$(mktemp)"
tmp_alerts="$(mktemp)"

code_status="$(curl -sS -o "$tmp_status" -w '%{http_code}' -H "$INTERNAL_API_KEY_HEADER: $INTERNAL_API_KEY" "$INTERNAL_API_BASE_URL/api/sources/status")"
code_alerts="$(curl -sS -o "$tmp_alerts" -w '%{http_code}' -H "$INTERNAL_API_KEY_HEADER: $INTERNAL_API_KEY" "$INTERNAL_API_BASE_URL/api/alerts?limit=5")"

echo "\n/api/sources/status http_code=$code_status"
python3 - "$tmp_status" <<'PY'
import json
import sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)

items = data.get('items') or []
print('source_count:', data.get('count'))
for row in items:
    print('-', row.get('source'), '| status=', row.get('last_status'), '| records=', row.get('records_fetched'), '| last_error=', row.get('last_error'))
PY

echo "\n/api/alerts?limit=5 http_code=$code_alerts"
python3 - "$tmp_alerts" <<'PY'
import json
import sys
from collections import Counter

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)

items = data.get('items') or []
print('alerts_count:', data.get('count'))
print('top_sources:', Counter((x.get('source') or '') for x in items).most_common(5))
for item in items[:5]:
    print('-', (item.get('event_type') or 'Alert'), '|', (item.get('area') or 'N/A'))
PY

rm -f "$tmp_status" "$tmp_alerts"

echo "\nDone."
