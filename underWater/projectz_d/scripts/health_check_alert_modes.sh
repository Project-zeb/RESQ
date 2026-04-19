#!/usr/bin/env bash
set -euo pipefail

APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:8001}"
ENDPOINT="${ENDPOINT:-/api/mobile/live-alerts}"
STATE="${STATE:-India}"
LIMIT="${LIMIT:-120}"
SCOPE="${SCOPE:-expanded}"

run_check() {
  local policy="$1"
  local tmp_json
  local http_code

  tmp_json="$(mktemp)"
  http_code="$(curl -sS -o "$tmp_json" -w '%{http_code}' "${APP_BASE_URL}${ENDPOINT}?state=${STATE}&limit=${LIMIT}&scope=${SCOPE}&source_policy=${policy}")"

  echo "\n=== policy=${policy} ==="
  echo "http_code=${http_code}"

  python3 - "$tmp_json" <<'PY'
import json
import sys
from collections import Counter

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

alerts = data.get("alerts") or []
print("success:", data.get("success"))
print("source_mode:", data.get("source_mode"))
print("source_policy:", data.get("source_policy"))
print("count:", data.get("count"))
print("message:", data.get("message"))
print("internal_error:", data.get("internal_error"))

types = Counter((a.get("type") or "").strip() for a in alerts)
print("top_types:", types.most_common(6))
print("has_gangtok:", any("gangtok" in (a.get("area") or "").lower() for a in alerts))
print("has_pathanamthitta:", any("pathanamthitta" in (a.get("area") or "").lower() for a in alerts))
PY

  rm -f "$tmp_json"
}

echo "Alert mode health check"
echo "APP_BASE_URL=${APP_BASE_URL}"
echo "STATE=${STATE} LIMIT=${LIMIT} SCOPE=${SCOPE}"

run_check "live_only"
run_check "auto_fallback"

echo "\nDone."
