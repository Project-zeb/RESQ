import json
from datetime import datetime, timezone
from typing import Any, Optional

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from disaster_api import db
from disaster_api.django_state import get_state


def _parse_int(value: Optional[Any], default: int, min_value: int, max_value: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _state():
    return get_state()


@require_http_methods(["GET"])
def health(request):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return JsonResponse({"status": "ok", "timestamp_utc": now}, status=200)


@require_http_methods(["GET"])
def get_alerts(request):
    state = _state()
    settings = state["settings"]

    limit = _parse_int(request.GET.get("limit"), default=500, min_value=1, max_value=5000)
    source = request.GET.get("source")
    severity = request.GET.get("severity")
    area = request.GET.get("area")
    since = request.GET.get("since")

    alerts = db.list_alerts(
        settings.database_url,
        limit=limit,
        source=source,
        severity=severity,
        area=area,
        since=since,
    )
    return JsonResponse({"count": len(alerts), "items": alerts}, status=200)


@require_http_methods(["GET"])
def get_alert(request, alert_id: int):
    state = _state()
    settings = state["settings"]

    alert = db.get_alert_by_id(settings.database_url, alert_id)
    if not alert:
        return JsonResponse({"error": "Alert not found"}, status=404)
    return JsonResponse(alert, status=200)


@require_http_methods(["GET"])
def get_source_status(request):
    state = _state()
    settings = state["settings"]

    runs = db.get_source_runs(settings.database_url)
    return JsonResponse({"count": len(runs), "items": runs}, status=200)


@require_http_methods(["POST"])
def run_sync(request):
    state = _state()
    summary = state["aggregator"].run_cycle()
    return JsonResponse(summary, status=200)


@require_http_methods(["POST"])
def create_access_token(request):
    state = _state()
    auth_service = state["auth_service"]

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        payload = {}

    requested_minutes = payload.get("expires_minutes")
    principal = getattr(request, "auth_principal", {"subject": "internal-client", "role": "api"})
    token_payload = auth_service.issue_jwt(principal, requested_minutes=requested_minutes)
    return JsonResponse(token_payload, status=200)


@require_http_methods(["GET"])
def get_api_keys(request):
    state = _state()
    auth_service = state["auth_service"]
    return JsonResponse(auth_service.list_api_keys(), status=200)


@require_http_methods(["POST"])
def rotate_api_keys(request):
    state = _state()
    auth_service = state["auth_service"]

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        payload = {}

    grace_seconds = payload.get("grace_seconds")
    label_raw = payload.get("label")
    label = str(label_raw).strip() if label_raw is not None else None
    rotation = auth_service.rotate_api_key(grace_seconds=grace_seconds, label=label)
    return JsonResponse(rotation, status=200)
