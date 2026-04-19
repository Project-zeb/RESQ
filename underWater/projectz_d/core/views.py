from django.contrib.auth import (
    authenticate,
    get_user_model,
    login as django_login,
    logout as django_logout,
    update_session_auth_hash,
)
from django.db import connection
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import resolve
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import ensure_csrf_cookie

from core.models import AlertSnapshot, Disaster, UserProfile
from core.realtime.auth import generate_ws_token
from core.web import url
from dotenv import load_dotenv
import os
import json
import math
import re
import atexit
import secrets
import base64
import hashlib
import mimetypes
import gzip
import shutil
import subprocess
import zipfile
import requests # api will be called using this libraray
import sqlite3
import decimal
import threading
import time as time_module
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables from .env file before evaluating OAuth flags.
load_dotenv()

_disable_google_oauth = str(os.getenv("DISABLE_GOOGLE_OAUTH") or "").strip().lower() in [
    "1",
    "true",
    "yes",
    "on",
]
if _disable_google_oauth:
    OAuth = None
    AUTHLIB_IMPORT_ERROR = "disabled by DISABLE_GOOGLE_OAUTH"
else:
    try:
        from authlib.integrations.django_client import OAuth
        AUTHLIB_IMPORT_ERROR = None
    except Exception as authlib_import_exc:  # noqa: BLE001
        OAuth = None
        AUTHLIB_IMPORT_ERROR = authlib_import_exc
# import bcrypt


def json_response(payload, status=200):
    return JsonResponse(payload, safe=not isinstance(payload, list), status=status)


def _parse_json_body(request):
    if hasattr(request, "_cached_json_body"):
        return request._cached_json_body
    data = None
    try:
        if request.body:
            data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = None
    request._cached_json_body = data
    return data


_translate_text_cache = {}
_TRANSLATE_TEXT_CACHE_LIMIT = 4096


def _is_likely_english_text(value):
    text = str(value or "").strip()
    if not text:
        return True
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    ratio = ascii_chars / max(1, len(text))
    return ratio >= 0.98


def _translate_text_to_english_online(value, timeout_seconds=6.0, retries=1):
    text = str(value or "").strip()
    if not text:
        return ""
    if _is_likely_english_text(text):
        return text

    cached = _translate_text_cache.get(text)
    if cached is not None:
        return cached

    translated = ""
    max_attempts = max(1, int(retries or 0) + 1)
    for attempt in range(max_attempts):
        try:
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": "en",
                    "dt": "t",
                    "q": text[:1400],
                },
                timeout=max(2.5, float(timeout_seconds or 6.0)),
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and payload and isinstance(payload[0], list):
                parts = []
                for segment in payload[0]:
                    if isinstance(segment, list) and segment:
                        parts.append(str(segment[0] or ""))
                translated = "".join(parts).strip()
                if translated:
                    break
        except Exception:
            if attempt >= max_attempts - 1:
                translated = ""

    if len(_translate_text_cache) >= _TRANSLATE_TEXT_CACHE_LIMIT:
        try:
            _translate_text_cache.pop(next(iter(_translate_text_cache)))
        except Exception:
            _translate_text_cache.clear()
    _translate_text_cache[text] = translated
    return translated


def _get_query_param(request, key, default=None, cast=None, type=None):  # noqa: A002 - allow type kw for legacy usage
    if key not in request.GET:
        return default
    value = request.GET.get(key)
    caster = cast or type
    if caster is None:
        return value
    try:
        return caster(value)
    except Exception:
        return default


def _get_form_param(request, key, default=None, cast=None, type=None):  # noqa: A002 - allow type kw for legacy usage
    if key not in request.POST:
        return default
    value = request.POST.get(key)
    caster = cast or type
    if caster is None:
        return value
    try:
        return caster(value)
    except Exception:
        return default


def _get_request_endpoint(request):
    match = getattr(request, "resolver_match", None)
    if match and match.view_name:
        return match.view_name
    try:
        match = resolve(request.path_info)
        return match.view_name or ""
    except Exception:
        return ""


def _set_session_permanent(request, permanent=True):
    if permanent:
        request.session.set_expiry(60 * 60 * 24 * 30)
    else:
        request.session.set_expiry(0)


def _get_authenticated_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return user


def _get_or_create_profile(user):
    if not user:
        return None
    profile, _created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": "ADMIN" if (user.is_staff or user.is_superuser) else "USER",
        },
    )
    if profile.role == "ADMIN" and not (user.is_staff or user.is_superuser):
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    elif (user.is_staff or user.is_superuser) and profile.role != "ADMIN":
        profile.role = "ADMIN"
        profile.save(update_fields=["role"])
    return profile


def _profile_for_request(request):
    if hasattr(request, "_cached_profile"):
        return request._cached_profile
    user = _get_authenticated_user(request)
    if not user:
        request._cached_profile = None
        return None
    request._cached_profile = _get_or_create_profile(user)
    return request._cached_profile


def _sync_session_from_user(request, user, profile=None):
    if not user or not user.is_authenticated:
        return
    profile = profile or _profile_for_request(request)
    role = "ADMIN" if (user.is_staff or user.is_superuser) else "USER"
    if profile and profile.role:
        role = profile.role
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = role
    request.session["must_change_password"] = bool(profile.must_change_password) if profile else False
    request.session["is_blocked"] = bool(profile.is_blocked) if profile else False


def _session_context(request):
    user = _get_authenticated_user(request)
    profile = _profile_for_request(request) if user else None
    is_logged_in = bool(user)
    is_admin = bool(user and (user.is_staff or user.is_superuser or (profile and profile.role == "ADMIN")))
    username = user.username if user else None
    return {
        "is_logged_in": is_logged_in,
        "is_admin": is_admin,
        "username": username,
        "session": request.session,
    }


def _csrf_context(request):
    token = get_token(request)
    return {
        "csrf_token_value": token,
        "csrf_input": mark_safe(
            f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">'  # noqa: S308
        ),
    }


def render_page(request, template_name, **context):
    user = _get_authenticated_user(request)
    if user:
        _sync_session_from_user(request, user)
    base = _session_context(request)
    base.update(_csrf_context(request))
    base.update(context)
    return render(request, template_name, base)

def _user_payload(user, profile=None):
    if not user:
        return None
    role = None
    if profile and profile.role:
        role = profile.role
    else:
        role = "ADMIN" if (user.is_staff or user.is_superuser) else "USER"
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.get_full_name() or user.username,
        "role": role,
        "is_admin": bool(role == "ADMIN"),
    }


def _masked_user_identifier(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 2:
        return text[:1] + ("*" if len(text) == 2 else "")
    return text[0] + ("*" * (len(text) - 2)) + text[-1]


def _profile_payload(user, profile=None):
    if not user:
        return None
    profile = profile or UserProfile.objects.filter(user=user).first()
    account_type = (
        profile.role
        if (profile and profile.role)
        else ("ADMIN" if (user.is_staff or user.is_superuser) else "USER")
    )
    full_name = user.get_full_name() or user.username
    return {
        "id": user.id,
        "masked_id": _masked_user_identifier(user.username),
        "name": full_name,
        "username": user.username,
        "email": user.email or "",
        "phone": profile.phone if profile else "",
        "account_type": account_type,
        "password": "Hidden for security",
    }


def _react_frontend_dist_dir():
    dist_dir = getattr(settings, "REACT_FRONTEND_DIST", None) or os.path.join(
        APP_ROOT, "frontend_react", "dist"
    )
    if hasattr(dist_dir, "exists"):
        dist_dir = str(dist_dir)
    return dist_dir


def _safe_dist_path(root_dir, relative_path):
    normalized = os.path.normpath(os.path.join(root_dir, relative_path))
    root_abs = os.path.abspath(root_dir) + os.sep
    if not os.path.abspath(normalized).startswith(root_abs):
        raise Http404("Invalid asset path")
    return normalized


@ensure_csrf_cookie
def spa_index(request, path=None):
    dist_dir = _react_frontend_dist_dir()
    index_path = os.path.join(dist_dir, "index.html")
    if not os.path.exists(index_path):
        return HttpResponse(
            "React build not found. Run `npm install` and `npm run build` in frontend_react.",
            status=503,
            content_type="text/plain",
        )
    response = FileResponse(open(index_path, "rb"), content_type="text/html")
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def spa_asset(request, asset_path):
    """Serve SPA assets directly under /assets/* for cache compatibility."""
    dist_dir = _react_frontend_dist_dir()
    assets_dir = os.path.join(dist_dir, "assets")
    normalized = _safe_dist_path(assets_dir, asset_path)
    if not os.path.isfile(normalized):
        raise Http404("Asset not found")
    content_type = mimetypes.guess_type(normalized)[0] or "application/octet-stream"
    return FileResponse(open(normalized, "rb"), content_type=content_type)


def spa_public_asset(request, asset_path):
    """Serve root-level static files from the React dist folder (e.g. /logo.png)."""
    dist_dir = _react_frontend_dist_dir()
    normalized = _safe_dist_path(dist_dir, asset_path)
    if not os.path.isfile(normalized):
        raise Http404("Asset not found")
    content_type = mimetypes.guess_type(normalized)[0] or "application/octet-stream"
    return FileResponse(open(normalized, "rb"), content_type=content_type)


def spa_public_scoped_asset(request, scope, asset_path):
    """Serve static files from whitelisted subfolders in the React dist folder."""
    allowed_scopes = {"model_1_only", "model_2_only", "model_3_only"}
    if scope not in allowed_scopes:
        raise Http404("Asset scope not found")
    return spa_public_asset(request, f"{scope}/{asset_path}")


@ensure_csrf_cookie
def api_auth_csrf(request):
    return json_response({"csrfToken": get_token(request)})


def api_auth_session(request):
    user = _get_authenticated_user(request)
    if not user:
        return json_response({"authenticated": False})
    profile = _profile_for_request(request)
    return json_response({
        "authenticated": True,
        "user": _user_payload(user, profile),
    })


def api_auth_profile(request):
    user = _get_authenticated_user(request)
    if not user:
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    profile = _get_or_create_profile(user)

    if request.method == "GET":
        return json_response({
            "success": True,
            "profile": _profile_payload(user, profile),
        })

    if request.method not in {"POST", "PUT", "PATCH"}:
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    data = _parse_json_body(request) or {}

    username_provided = "username" in data
    email_provided = "email" in data
    name_provided = "name" in data
    phone_provided = "phone" in data

    next_name = (data.get("name") or "").strip() if name_provided else (user.get_full_name() or user.username)
    next_phone = (data.get("phone") or "").strip() if phone_provided else (profile.phone or "")
    current_username = str(user.username or "").strip()
    current_email = str(user.email or "").strip()
    requested_username = (data.get("username") or "").strip() if username_provided else current_username
    requested_email = (data.get("email") or "").strip() if email_provided else current_email

    if username_provided and requested_username.lower() != current_username.lower():
        return json_response({"success": False, "message": "Username cannot be changed."}, status=400)

    if email_provided and requested_email.lower() != current_email.lower():
        return json_response({"success": False, "message": "Email cannot be changed."}, status=400)

    if name_provided and not next_name:
        return json_response({"success": False, "message": "Name is required."}, status=400)

    user_updates = []

    if name_provided:
        name_parts = next_name.split(None, 1)
        next_first_name = name_parts[0] if name_parts else ""
        next_last_name = name_parts[1] if len(name_parts) > 1 else ""
        if user.first_name != next_first_name:
            user.first_name = next_first_name
            user_updates.append("first_name")
        if user.last_name != next_last_name:
            user.last_name = next_last_name
            user_updates.append("last_name")

    if user_updates:
        user.save(update_fields=user_updates)

    if phone_provided and (profile.phone or "") != next_phone:
        profile.phone = next_phone
        profile.save(update_fields=["phone"])

    _sync_session_from_user(request, user, profile=profile)

    return json_response({
        "success": True,
        "message": "Profile updated successfully.",
        "profile": _profile_payload(user, profile),
    })


def api_auth_login(request):
    if request.method != "POST":
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    data = _parse_json_body(request) or {}
    username_or_email = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""

    if not username_or_email or not password:
        return json_response({"success": False, "message": "Username or email and password are required."}, status=400)

    user = authenticate(request, username=username_or_email, password=password)
    if user is None and "@" in username_or_email:
        matched_user = (
            get_user_model()
            .objects.filter(email__iexact=username_or_email)
            .first()
        )
        if matched_user:
            user = authenticate(request, username=matched_user.username, password=password)
    if user is not None:
        profile = _get_or_create_profile(user)
        if profile and profile.is_blocked:
            user.is_active = False
            user.save(update_fields=["is_active"])

        if not user.is_active or (profile and profile.is_blocked):
            return json_response({"success": False, "message": "Your account is blocked. Contact support."}, status=403)

        django_login(request, user)
        _set_session_permanent(request, True)
        _sync_session_from_user(request, user, profile=profile)

        if STORE_PLAIN_PASSWORDS and profile and password:
            if profile.password_plain != password:
                profile.password_plain = password
                profile.save(update_fields=["password_plain"])

        require_password_change = bool(profile.must_change_password) if profile else False
        return json_response({
            "success": True,
            "require_password_change": require_password_change,
            "user": _user_payload(user, profile),
        })

    existing_user = (
        get_user_model()
        .objects.filter(Q(username__iexact=username_or_email) | Q(email__iexact=username_or_email))
        .first()
    )
    existing_profile = UserProfile.objects.filter(user=existing_user).first() if existing_user else None
    if existing_user and (not existing_user.is_active or (existing_profile and existing_profile.is_blocked)):
        msg = "Your account is blocked. Contact support."
    else:
        msg = f"Wrong credentials. Contact: {LOGIN_SUPPORT_EMAIL}"
    return json_response({"success": False, "message": msg}, status=401)


def api_auth_signup(request):
    if request.method != "POST":
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    data = _parse_json_body(request) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or data.get("fullName") or "").strip()
    phone = (data.get("phone") or "").strip()

    if not username:
        return json_response({"success": False, "message": "Username is required."}, status=400)
    if len(password) < 8:
        return json_response({"success": False, "message": "Password must be at least 8 characters."}, status=400)

    UserModel = get_user_model()
    existing = UserModel.objects.filter(Q(username__iexact=username) | Q(email__iexact=email)).first()
    if existing:
        profile = UserProfile.objects.filter(user=existing).first()
        if not existing.is_active or (profile and profile.is_blocked):
            msg = "Your account is blocked. Contact support."
        else:
            msg = "User already exists. Try again."
        return json_response({"success": False, "message": msg}, status=409)

    try:
        django_user = UserModel.objects.create_user(
            username=username,
            email=email or "",
            password=password,
            first_name=name or "",
        )
        profile, created = UserProfile.objects.get_or_create(
            user=django_user,
            defaults={
                "role": "USER",
                "phone": phone,
                "is_blocked": False,
                "must_change_password": False,
                "password_plain": (password if STORE_PLAIN_PASSWORDS else None),
            },
        )
        if not created:
            profile.role = "USER"
            profile.phone = phone
            profile.is_blocked = False
            profile.must_change_password = False
            profile.password_plain = password if STORE_PLAIN_PASSWORDS else None
            profile.save(
                update_fields=[
                    "role",
                    "phone",
                    "is_blocked",
                    "must_change_password",
                    "password_plain",
                ]
            )
        django_login(request, django_user, backend="django.contrib.auth.backends.ModelBackend")
        _set_session_permanent(request, True)
        _sync_session_from_user(request, django_user, profile=profile)
        return json_response({
            "success": True,
            "user": _user_payload(django_user, profile),
        })
    except Exception as err:
        return json_response({"success": False, "message": f"Signup failed: {err}"}, status=500)


def api_auth_change_password(request):
    if request.method != "POST":
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    user = _get_authenticated_user(request)
    if not user:
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    data = _parse_json_body(request) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""

    if not user.check_password(current_password):
        return json_response({"success": False, "message": "Current password is incorrect."}, status=400)
    if len(new_password) < 8:
        return json_response({"success": False, "message": "New password must be at least 8 characters."}, status=400)
    if new_password != confirm_password:
        return json_response({"success": False, "message": "New password and confirm password do not match."}, status=400)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)

    profile = _profile_for_request(request)
    if profile:
        profile.must_change_password = False
        profile.password_plain = new_password if STORE_PLAIN_PASSWORDS else None
        profile.save(update_fields=["must_change_password", "password_plain"])
    request.session["must_change_password"] = False
    _sync_session_from_user(request, user, profile=profile)

    return json_response({"success": True, "message": "Password updated successfully."})


def api_auth_logout(request):
    if request.method not in {"POST", "GET"}:
        return json_response({"success": False, "message": "Method not allowed"}, status=405)
    django_logout(request)
    return json_response({"success": True})


def _is_admin_request(request):
    user = _get_authenticated_user(request)
    if user and (user.is_staff or user.is_superuser):
        return True
    profile = _profile_for_request(request)
    return bool(profile and profile.role == "ADMIN")


def file_response(path, mimetype=None, as_attachment=False, download_name=None):
    response = FileResponse(open(path, "rb"), content_type=mimetype)
    if as_attachment:
        filename = download_name or os.path.basename(path)
        response["Content-Disposition"] = f'attachment; filename=\"{filename}\"'
    return response


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Database config
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
DB_PATH = os.getenv("SQLITE_DB_PATH", "app.db")
DB_PRIMARY = str(os.getenv("PRIMARY_DB", "sqlite") or "sqlite").strip().lower()
if DB_PRIMARY not in ["mysql", "sqlite", "mongodb"]:
    DB_PRIMARY = "sqlite"
MYSQL_USE_PURE = str(os.getenv("MYSQL_USE_PURE", "1") or "1").strip().lower() not in ["0", "false", "no", "off"]
SQLITE_BOOTSTRAP_FROM_MYSQL = str(os.getenv("SQLITE_BOOTSTRAP_FROM_MYSQL", "0") or "0").strip().lower() in ["1", "true", "yes", "on"]
SQLITE_CONTINUOUS_SYNC_FROM_MYSQL = str(os.getenv("SQLITE_CONTINUOUS_SYNC_FROM_MYSQL", "0") or "0").strip().lower() in ["1", "true", "yes", "on"]
MYSQL_REVERSE_SYNC_FROM_SQLITE = str(os.getenv("MYSQL_REVERSE_SYNC_FROM_SQLITE", "0") or "0").strip().lower() in ["1", "true", "yes", "on"]
SQLITE_SYNC_INTERVAL_SEC = max(5, int(os.getenv("SQLITE_SYNC_INTERVAL_SEC", "5")))
FIXED_ADMIN_EMAIL = str(os.getenv("FIXED_ADMIN_EMAIL", "matrik990@gmail.com") or "matrik990@gmail.com").strip().lower()
FIXED_ADMIN_USERNAME = str(os.getenv("FIXED_ADMIN_USERNAME", "matrik") or "matrik").strip()
FIXED_ADMIN_PASSWORD = str(os.getenv("FIXED_ADMIN_PASSWORD", "pine") or "pine").strip()
LOGIN_SUPPORT_EMAIL = str(os.getenv("LOGIN_SUPPORT_EMAIL", "contact@matrikaregmi.com.np") or "contact@matrikaregmi.com.np").strip()


def _to_bool_env(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ["1", "true", "yes", "on"]


LEGACY_SQL_ENABLED = _to_bool_env(os.getenv("LEGACY_SQL_ENABLED"), False)
MYSQL_CONNECTION_REQUIRED = (
    DB_PRIMARY == "mysql"
    or SQLITE_BOOTSTRAP_FROM_MYSQL
    or SQLITE_CONTINUOUS_SYNC_FROM_MYSQL
    or MYSQL_REVERSE_SYNC_FROM_SQLITE
)
MONGODB_SQLITE_FALLBACK_SYNC_ENABLED = _to_bool_env(
    os.getenv("MONGODB_SQLITE_FALLBACK_SYNC"),
    default=(DB_PRIMARY == "mongodb"),
)
MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS = max(
    5,
    int((os.getenv("MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS") or "15").strip() or "15"),
)
MONGODB_BRIDGE_SYNC_ENABLED = _to_bool_env(
    os.getenv("MONGODB_BRIDGE_SYNC"),
    default=(DB_PRIMARY == "mongodb"),
)
MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS = max(
    5,
    int((os.getenv("MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS") or "20").strip() or "20"),
)
MONGODB_BRIDGE_SCOPE = str(os.getenv("MONGODB_BRIDGE_SCOPE") or "users_only").strip().lower()
if MONGODB_BRIDGE_SCOPE not in {"users_only", "full"}:
    MONGODB_BRIDGE_SCOPE = "users_only"
MONGODB_SQLITE_FALLBACK_ALIAS = str(
    os.getenv("MONGODB_SQLITE_FALLBACK_ALIAS")
    or getattr(settings, "SQLITE_FALLBACK_ALIAS", "fallback_sqlite")
    or "fallback_sqlite"
).strip() or "fallback_sqlite"

USE_SQLITE = False
ACTIVE_DB_BACKEND = None
conn = None
cursor = None
mysql_conn = None
mysql_cursor = None
sqlite_conn = None
sqlite_cursor = None
sqlite_sync_lock = threading.Lock()
sqlite_sync_thread_started = False
mongo_sqlite_sync_lock = threading.Lock()
mongo_sqlite_sync_thread_started = False
mongo_sqlite_sync_last_attempt_utc = None
mongo_sqlite_sync_last_success_utc = None
mongo_sqlite_sync_last_error = None
mongo_sqlite_sync_last_warning = None
mongo_sqlite_sync_last_rows = {
    "users": 0,
    "profiles": 0,
    "disasters": 0,
    "snapshots": 0,
}
mongo_bridge_sync_lock = threading.Lock()
mongo_bridge_sync_thread_started = False
mongo_bridge_sync_last_attempt_utc = None
mongo_bridge_sync_last_success_utc = None
mongo_bridge_sync_last_error = None
mongo_bridge_sync_last_warning = None
mongo_bridge_sync_last_rows = {
    "local_to_shared": {},
    "shared_to_local": {},
}
ngo_cache_lock = threading.Lock()
ngo_cache_store = {}


SECURE_PASSWORD_MODE = _to_bool_env(os.getenv("SECURE_PASSWORD_MODE"), True)
STORE_PLAIN_PASSWORDS = _to_bool_env(os.getenv("STORE_PLAIN_PASSWORDS"), False)
EXPOSE_PLAIN_PASSWORDS = _to_bool_env(os.getenv("EXPOSE_PLAIN_PASSWORDS"), False)
if SECURE_PASSWORD_MODE:
    STORE_PLAIN_PASSWORDS = False
    EXPOSE_PLAIN_PASSWORDS = False


def _password_hash_looks_secure(value):
    text = str(value or "").strip()
    if not text:
        return False
    return text.startswith("pbkdf2:") or text.startswith("scrypt:")


def _hash_password(plain_password):
    return generate_password_hash(str(plain_password or ""))


def _verify_password(stored_password_hash, provided_password):
    stored_value = str(stored_password_hash or "")
    provided_value = str(provided_password or "")
    if not stored_value:
        return False
    if _password_hash_looks_secure(stored_value):
        try:
            return check_password_hash(stored_value, provided_value)
        except Exception:
            return False
    return secrets.compare_digest(stored_value, provided_value)


def _generate_temporary_password(length=12):
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    lower = "abcdefghijkmnopqrstuvwxyz"
    digits = "23456789"
    symbols = "!@#$%&*"

    chars = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]

    all_pool = upper + lower + digits + symbols
    while len(chars) < max(8, length):
        chars.append(secrets.choice(all_pool))

    for index in range(len(chars) - 1, 0, -1):
        swap_index = secrets.randbelow(index + 1)
        chars[index], chars[swap_index] = chars[swap_index], chars[index]

    return "".join(chars)


INTERNAL_API_AUTOSTART = _to_bool_env(os.getenv("INTERNAL_API_AUTOSTART"), True)
INTERNAL_API_SYNC_ON_ALERT_REQUEST = _to_bool_env(os.getenv("INTERNAL_API_SYNC_ON_ALERT_REQUEST"), True)
INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS = max(
    5, int((os.getenv("INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS") or "300").strip() or "300")
)
INTERNAL_API_START_TIMEOUT_SECONDS = max(
    5, int((os.getenv("INTERNAL_API_START_TIMEOUT_SECONDS") or "20").strip() or "20")
)
INTERNAL_API_AUTOSTART_LOG = os.getenv("INTERNAL_API_AUTOSTART_LOG", "/tmp/internal_api_autostart.log")
NGO_CACHE_TTL_SECONDS = max(30, int((os.getenv("NGO_CACHE_TTL_SECONDS") or "300").strip() or "300"))
NGO_REQUEST_TIMEOUT_SECONDS = max(
    1.0, float((os.getenv("NGO_REQUEST_TIMEOUT_SECONDS") or "2.0").strip() or "2.0")
)
NGO_RADIUS_METERS = max(1000, int((os.getenv("NGO_RADIUS_METERS") or "50000").strip() or "50000"))
NGO_MAX_RETURN_DISTANCE_KM = max(
    1.0, float((os.getenv("NGO_MAX_RETURN_DISTANCE_KM") or "120").strip() or "120")
)
NGO_OVERPASS_ENDPOINTS = [
    endpoint.strip()
    for endpoint in str(
        os.getenv(
            "NGO_OVERPASS_ENDPOINTS",
            "https://overpass-api.de/api/interpreter",
        )
        or ""
    ).split(",")
    if endpoint.strip()
]
if not NGO_OVERPASS_ENDPOINTS:
    NGO_OVERPASS_ENDPOINTS = ["https://overpass-api.de/api/interpreter"]

ANALYSIS_ASSET_CACHE_TTL_SECONDS = max(
    5, int((os.getenv("ANALYSIS_ASSET_CACHE_TTL_SECONDS") or "90").strip() or "90")
)
analysis_assets_cache_lock = threading.Lock()
analysis_assets_cache = {
    "generated_at_monotonic": 0.0,
    "payload": None,
}

INDIA_DEFAULT_COORDS = (22.9734, 78.6569)
NGO_CITY_COORDS = {
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "pune": (18.5204, 73.8567),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
}
NGO_STATE_COORDS = {
    "andhra pradesh": (15.9129, 79.7400),
    "arunachal pradesh": (28.2180, 94.7278),
    "chhattisgarh": (21.2787, 81.8661),
    "goa": (15.2993, 74.1240),
    "gujarat": (22.2587, 71.1924),
    "haryana": (29.0588, 76.0856),
}

_internal_api_process = None
_internal_api_started_by_main = False
_internal_api_log_handle = None
_internal_api_sync_lock = threading.Lock()
_internal_api_last_sync_monotonic = 0.0
_internal_api_last_sync_attempt_utc = None
_internal_api_last_sync_success_utc = None

CAP_FEED_TIMEOUT_SECONDS = max(
    5, int((os.getenv("SACHET_CAP_TIMEOUT_SECONDS") or "20").strip() or "20")
)
CAP_FEED_USE_ETAG = _to_bool_env(os.getenv("SACHET_CAP_USE_ETAG"), True)
CAP_FEED_STATE_PATH = os.path.abspath(
    str(os.getenv("SACHET_CAP_STATE_PATH") or os.path.join(APP_ROOT, "cap_feed_state.json")).strip()
)
CAP_FEED_LATEST_XML_PATH = os.path.abspath(
    str(os.getenv("SACHET_CAP_LATEST_XML_PATH") or os.path.join(APP_ROOT, "cap_feed_latest.xml")).strip()
)
CAP_FEED_ARCHIVE_ENABLED = _to_bool_env(os.getenv("SACHET_CAP_ARCHIVE_ENABLED"), True)
CAP_FEED_ARCHIVE_DIR = os.path.abspath(
    str(os.getenv("SACHET_CAP_ARCHIVE_DIR") or os.path.join(APP_ROOT, "cap_archive")).strip()
)
CAP_FEED_ARCHIVE_RETENTION_DAYS = max(
    0, int((os.getenv("SACHET_CAP_ARCHIVE_RETENTION_DAYS") or str(5 * 365)).strip() or str(5 * 365))
)
CAP_FEED_ARCHIVE_MAX_FILES = max(
    0, int((os.getenv("SACHET_CAP_ARCHIVE_MAX_FILES") or "0").strip() or "0")
)

cap_feed_cache_lock = threading.Lock()
cap_feed_state_cache = {}
cap_feed_state_loaded = False
cap_feed_archive_last_prune_monotonic = 0.0


def _internal_api_alerts_url():
    return (os.getenv("INTERNAL_ALERTS_API_URL") or "http://127.0.0.1:2000/api/internal/alerts").strip()


def _internal_api_base_url():
    alerts_url = _internal_api_alerts_url()
    parsed = urlparse(alerts_url)

    if not parsed.scheme or not parsed.netloc:
        return "http://127.0.0.1:5100"

    path = parsed.path or ""
    if "/api/" in path:
        prefix = path.split("/api/", 1)[0]
    else:
        prefix = path.rsplit("/", 1)[0] if "/" in path else ""

    prefix = prefix.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{prefix}"


def _internal_api_health_url():
    return f"{_internal_api_base_url()}/health"


def _internal_api_sync_url():
    return f"{_internal_api_base_url()}/api/sync"


def _internal_api_auth_headers():
    key = (os.getenv("INTERNAL_ALERTS_API_KEY") or "").strip()
    header = (os.getenv("INTERNAL_ALERTS_API_KEY_HEADER") or "X-Internal-API-Key").strip() or "X-Internal-API-Key"
    return {header: key} if key else {}


def _internal_api_is_embedded():
    alerts_url = _internal_api_alerts_url()
    parsed = urlparse(alerts_url)
    app_port_text = str(os.getenv("PORT") or "2000").strip() or "2000"
    try:
        app_port = int(app_port_text)
    except ValueError:
        app_port = 2000

    if parsed.scheme:
        host = (parsed.hostname or "").strip().lower()
        if host not in ["127.0.0.1", "localhost"]:
            return False
        if parsed.port and parsed.port != app_port:
            return False
        return (parsed.path or "").rstrip("/") == "/api/internal/alerts"

    return alerts_url.rstrip("/") == "/api/internal/alerts"


def _internal_api_auth_is_valid(request):
    expected = (
        os.getenv("INTERNAL_ALERTS_API_KEY")
        or os.getenv("INTERNAL_API_KEY")
        or ""
    ).strip()
    if not expected:
        return True

    header_name = (
        os.getenv("INTERNAL_ALERTS_API_KEY_HEADER")
        or os.getenv("API_KEY_HEADER")
        or "X-Internal-API-Key"
    ).strip() or "X-Internal-API-Key"

    provided = (request.headers.get(header_name) or "").strip()
    auth_header = (request.headers.get("Authorization") or "").strip()
    if not provided and auth_header.lower().startswith("bearer "):
        provided = auth_header.split(" ", 1)[1].strip()

    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def _normalize_alert_text_for_matching(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_embedded_severity(
    value,
    urgency=None,
    certainty=None,
    disaster_type=None,
    warning_message=None,
):
    severity_raw = str(value or "").strip().upper()
    urgency_raw = str(urgency or "").strip().upper()
    certainty_raw = str(certainty or "").strip().upper()

    if severity_raw in ["ALERT", "SEVERE", "EXTREME", "HIGH", "CRITICAL"]:
        return "ALERT"
    if severity_raw in ["WARNING", "MODERATE", "MEDIUM"]:
        return "WARNING"
    if severity_raw in ["WATCH", "ADVISORY", "MINOR", "LOW", "INFORMATION"]:
        return "WATCH"
    if severity_raw in ["UNKNOWN", "UNSPECIFIED", "NA", "N/A", "NONE", "NULL", ""]:
        severity_raw = ""

    if urgency_raw == "IMMEDIATE" and certainty_raw in ["OBSERVED", "LIKELY"]:
        return "ALERT"
    if urgency_raw in ["IMMEDIATE", "EXPECTED"] and certainty_raw in ["OBSERVED", "LIKELY"]:
        return "WARNING"
    if urgency_raw in ["IMMEDIATE", "EXPECTED"] or certainty_raw in ["OBSERVED", "LIKELY"]:
        return "WARNING"
    if urgency_raw in ["FUTURE", "PAST", "UNKNOWN"] and certainty_raw in ["POSSIBLE", "UNLIKELY", "UNKNOWN"]:
        return "WATCH"

    severity_blob = _normalize_alert_text_for_matching(
        f"{disaster_type or ''} {warning_message or ''} {severity_raw} {urgency_raw} {certainty_raw}"
    )
    if any(
        token in severity_blob
        for token in [
            "red alert",
            "extreme danger",
            "very severe",
            "take shelter immediately",
            "evacuate",
            "life threatening",
            "imminent",
            "flash flood emergency",
            "tsunami warning",
        ]
    ):
        return "ALERT"

    if any(
        token in severity_blob
        for token in [
            "low danger level",
            "low danger",
            "advisory",
            "monitor closely",
            "no immediate threat",
        ]
    ):
        return "WATCH"

    if any(
        token in severity_blob
        for token in [
            "warning",
            "high possibility",
            "be alert",
            "stay alert",
            "thunderstorm",
            "lightning",
            "cyclone",
            "flood",
            "heavy rain",
            "cloudburst",
            "landslide",
            "avalanche",
            "earthquake",
            "heat wave",
            "forest fire risk",
        ]
    ):
        return "WARNING"

    if any(
        token in severity_blob
        for token in [
            "watch",
            "advisory",
            "outlook",
            "monitor",
            "information",
            "awareness",
        ]
    ):
        return "WATCH"

    return "WATCH"


def _extract_cap_centroid(info_node):
    centroid = ""
    for area_node in info_node.findall("./{*}area"):
        circle = (area_node.findtext("./{*}circle") or "").strip()
        if circle and not centroid:
            first = circle.split()[0]
            if "," in first:
                parts = first.split(",")
                if len(parts) >= 2:
                    try:
                        lat_value = float(parts[0].strip())
                        lon_value = float(parts[1].strip())
                        centroid = f"{lon_value},{lat_value}"
                    except (TypeError, ValueError):
                        centroid = ""

        polygon = (area_node.findtext("./{*}polygon") or "").strip()
        if polygon and not centroid:
            first_pair = polygon.split()[0]
            if "," in first_pair:
                parts = first_pair.split(",")
                if len(parts) >= 2:
                    try:
                        lat_value = float(parts[0].strip())
                        lon_value = float(parts[1].strip())
                        centroid = f"{lon_value},{lat_value}"
                    except (TypeError, ValueError):
                        centroid = ""
    return centroid


def _parse_rss_pubdate_to_utc(pub_date_value):
    text = str(pub_date_value or "").strip()
    if not text:
        return ""
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return _to_utc_iso(text) or ""


def _extract_identifier_from_cap_link(link_value):
    link = str(link_value or "").strip()
    if not link:
        return ""
    try:
        parsed = urlparse(link)
        query = parse_qs(parsed.query or "")
        identifier_list = query.get("identifier") or query.get("id") or []
        if identifier_list:
            return str(identifier_list[0] or "").strip()
    except Exception:
        return ""
    return ""


def _normalize_rss_source(author_value):
    author_text = str(author_value or "").strip()
    if not author_text:
        return "NDMA SACHET"
    match = re.search(r"\(([^()]+)\)\s*$", author_text)
    if match:
        label = str(match.group(1) or "").strip()
        if label:
            return label
    if "@" in author_text:
        return "NDMA SACHET"
    return author_text


def _infer_rss_expiry_iso(start_iso, text_value):
    start_dt = _parse_utc_iso(start_iso)
    if start_dt is None:
        return ""

    text = _normalize_alert_text_for_matching(text_value)
    duration_minutes = None

    range_hour = re.search(r"next\s+(\d+)\s*-\s*(\d+)\s*hours?", text)
    if range_hour:
        duration_minutes = int(range_hour.group(2)) * 60

    if duration_minutes is None:
        single_hour = re.search(r"next\s+(\d+)\s*hours?", text)
        if single_hour:
            duration_minutes = int(single_hour.group(1)) * 60

    if duration_minutes is None:
        range_min = re.search(r"next\s+(\d+)\s*-\s*(\d+)\s*(?:mins?|minutes?)", text)
        if range_min:
            duration_minutes = int(range_min.group(2))

    if duration_minutes is None:
        min_to_hour = re.search(
            r"next\s+(\d+)\s*(?:mins?|minutes?)\s*(?:to|-)\s*(\d+)\s*hours?",
            text,
        )
        if min_to_hour:
            duration_minutes = int(min_to_hour.group(2)) * 60

    if duration_minutes is None:
        single_min = re.search(r"next\s+(\d+)\s*(?:mins?|minutes?)", text)
        if single_min:
            duration_minutes = int(single_min.group(1))

    if duration_minutes is None:
        range_day = re.search(r"next\s+(\d+)\s*-\s*(\d+)\s*days?", text)
        if range_day:
            duration_minutes = int(range_day.group(2)) * 24 * 60

    if duration_minutes is None:
        single_day = re.search(r"next\s+(\d+)\s*days?", text)
        if single_day:
            duration_minutes = int(single_day.group(1)) * 24 * 60

    if duration_minutes is None:
        # Most RSS weather alerts are short lived.
        duration_minutes = 180

    duration_minutes = max(15, min(duration_minutes, 72 * 60))
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return end_dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _infer_rss_area_description(text_value):
    text = str(text_value or "").strip()
    if not text:
        return "India"

    patterns = [
        r"\bover\s+(.+?)\s+in\s+next\b",
        r"\bover\s+(.+?)\s+during\s+next\b",
        r"\bover\s+(.+?)\s+from\s+\d",
        r"\bin\s+([A-Za-z0-9 ,&\-/]+?)\s+districts?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        area = str(match.group(1) or "").strip(" .,-;:")
        area = re.sub(r"\s+", " ", area)
        if area:
            return area[:260]

    return "India"


def _embedded_internal_alerts_from_feed_root(
    root,
    limit=200,
    area_query="",
    severity_query="",
    language_preference="",
):
    max_records = max(1, min(int(limit or 200), 5000))
    area_filter = str(area_query or "").strip().lower()
    severity_filter = str(severity_query or "").strip().upper()
    language_pref = str(language_preference or "").strip().lower()
    if severity_filter in ["ALL", "ANY"]:
        severity_filter = ""

    items = []
    fallback_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def append_item(
        index,
        identifier,
        event,
        severity,
        urgency,
        certainty,
        area_description,
        warning_message,
        source,
        start_time,
        end_time,
        centroid,
        event_en="",
        warning_message_en="",
        language_code="",
    ):
        if area_filter and area_filter not in str(area_description or "").lower():
            return
        if severity_filter and severity != severity_filter:
            return

        event_text = str(event or "Alert").strip() or "Alert"
        warning_text = str(warning_message or "").strip()
        event_en_text = str(event_en or "").strip()
        warning_en_text = str(warning_message_en or "").strip()
        if language_pref == "en":
            event_text = event_en_text or event_text
            warning_text = warning_en_text or warning_text

        updated_at = start_time or fallback_time
        item_id = f"embedded-{identifier or index}"
        payload_obj = {
            "identifier": identifier,
            "disaster_type": str(event or "Alert").strip() or "Alert",
            "severity": severity,
            "urgency": str(urgency or "").strip(),
            "certainty": str(certainty or "").strip(),
            "area_description": area_description,
            "warning_message": str(warning_message or "").strip(),
            "effective_start_time": start_time or None,
            "effective_end_time": end_time or None,
            "alert_source": source,
            "centroid": centroid,
        }
        if event_en_text:
            payload_obj["disaster_type_en"] = event_en_text
        if warning_en_text:
            payload_obj["warning_message_en"] = warning_en_text
        if str(language_code or "").strip():
            payload_obj["language"] = str(language_code).strip()

        items.append({
            "id": item_id,
            "external_id": identifier or None,
            "event_type": event_text,
            "event_type_en": event_en_text or None,
            "severity": severity,
            "urgency": str(urgency or "").strip() or None,
            "certainty": str(certainty or "").strip() or None,
            "area": area_description,
            "description": warning_text,
            "description_en": warning_en_text or None,
            "source": source,
            "source_name": source,
            "issued_at": start_time or None,
            "effective_at": start_time or None,
            "expires_at": end_time or None,
            "updated_at": updated_at,
            "payload": payload_obj,
        })

    if root is None:
        return items

    alert_nodes = root.findall(".//{*}alert")
    if alert_nodes:
        for index, alert_node in enumerate(alert_nodes, start=1):
            identifier = (alert_node.findtext("./{*}identifier") or "").strip()
            source = (
                alert_node.findtext("./{*}senderName")
                or alert_node.findtext("./{*}sender")
                or "NDMA SACHET"
            ).strip()

            info_nodes = alert_node.findall("./{*}info")
            if not info_nodes:
                continue

            def extract_info_fields(info_node):
                event = (info_node.findtext("./{*}event") or "Alert").strip()
                urgency = (info_node.findtext("./{*}urgency") or "").strip()
                certainty = (info_node.findtext("./{*}certainty") or "").strip()
                start_time = (
                    info_node.findtext("./{*}onset")
                    or info_node.findtext("./{*}effective")
                    or info_node.findtext("./{*}sent")
                    or ""
                ).strip()
                end_time = (info_node.findtext("./{*}expires") or "").strip()
                warning_message = (
                    info_node.findtext("./{*}description")
                    or info_node.findtext("./{*}headline")
                    or ""
                ).strip()
                severity = _normalize_embedded_severity(
                    info_node.findtext("./{*}severity"),
                    urgency=urgency,
                    certainty=certainty,
                    disaster_type=event,
                    warning_message=warning_message,
                )
                area_descriptions = []
                for area_node in info_node.findall("./{*}area"):
                    area_desc = (area_node.findtext("./{*}areaDesc") or "").strip()
                    if area_desc:
                        area_descriptions.append(area_desc)
                area_description = ", ".join(area_descriptions).strip()
                centroid = _extract_cap_centroid(info_node)
                language_code = (info_node.findtext("./{*}language") or "").strip()
                return {
                    "event": event,
                    "severity": severity,
                    "urgency": urgency,
                    "certainty": certainty,
                    "start_time": start_time,
                    "end_time": end_time,
                    "warning_message": warning_message,
                    "area_description": area_description,
                    "centroid": centroid,
                    "language_code": language_code,
                }

            selected_info = info_nodes[0]
            english_info = None
            for node in info_nodes:
                lang_code = (node.findtext("./{*}language") or "").strip().lower()
                if lang_code.startswith("en"):
                    english_info = node
                    break
            if language_pref == "en" and english_info is not None:
                selected_info = english_info

            selected_fields = extract_info_fields(selected_info)
            english_fields = extract_info_fields(english_info) if english_info is not None else {}

            append_item(
                index=index,
                identifier=identifier,
                event=selected_fields.get("event"),
                severity=selected_fields.get("severity"),
                urgency=selected_fields.get("urgency"),
                certainty=selected_fields.get("certainty"),
                area_description=selected_fields.get("area_description"),
                warning_message=selected_fields.get("warning_message"),
                source=source,
                start_time=selected_fields.get("start_time"),
                end_time=selected_fields.get("end_time"),
                centroid=selected_fields.get("centroid"),
                event_en=english_fields.get("event", ""),
                warning_message_en=english_fields.get("warning_message", ""),
                language_code=selected_fields.get("language_code", ""),
            )
            if len(items) >= max_records:
                break
    else:
        rss_items = root.findall(".//item")
        for index, item_node in enumerate(rss_items, start=1):
            title_text = str(item_node.findtext("./title") or "").strip()
            description_text = str(item_node.findtext("./description") or "").strip()
            warning_message = description_text or title_text
            event_text = title_text or "Alert"
            author_text = str(item_node.findtext("./author") or "").strip()
            source = _normalize_rss_source(author_text)
            guid_text = str(item_node.findtext("./guid") or "").strip()
            link_text = str(item_node.findtext("./link") or "").strip()
            identifier = guid_text or _extract_identifier_from_cap_link(link_text) or f"rss-{index}"

            start_iso = _parse_rss_pubdate_to_utc(item_node.findtext("./pubDate"))
            if not start_iso:
                start_iso = fallback_time
            end_iso = _infer_rss_expiry_iso(start_iso, f"{event_text} {warning_message}")

            severity = _normalize_embedded_severity(
                item_node.findtext("./category"),
                urgency="Expected",
                certainty="Likely",
                disaster_type=event_text,
                warning_message=warning_message,
            )
            rss_area_description = _infer_rss_area_description(f"{title_text} {description_text}")

            append_item(
                index=index,
                identifier=identifier,
                event=event_text,
                severity=severity,
                urgency="Expected",
                certainty="Likely",
                area_description=rss_area_description,
                warning_message=warning_message,
                source=source,
                start_time=start_iso,
                end_time=end_iso,
                centroid="",
                event_en="",
                warning_message_en="",
                language_code="",
            )
            if len(items) >= max_records:
                break

    return items[:max_records]


def _cap_archive_timestamp_from_name(file_path):
    name = os.path.basename(str(file_path or ""))
    match = re.search(r"cap_(\d{8})T(\d{6})Z_", name)
    if match:
        try:
            stamp = f"{match.group(1)}T{match.group(2)}Z"
            parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
            return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        stat = os.stat(file_path)
        return datetime.fromtimestamp(stat.st_mtime, timezone.utc)
    except Exception:
        return None


def _iter_cap_archive_files(date_from=None, date_to=None, max_files=120):
    if not CAP_FEED_ARCHIVE_ENABLED:
        return []
    if not os.path.isdir(CAP_FEED_ARCHIVE_DIR):
        return []

    max_allowed = max(1, min(int(max_files or 120), 2000))
    candidates = []
    for root_dir, _dirs, files in os.walk(CAP_FEED_ARCHIVE_DIR):
        for file_name in files:
            if not file_name.endswith(".xml.gz"):
                continue
            file_path = os.path.join(root_dir, file_name)
            ts = _cap_archive_timestamp_from_name(file_path)
            if ts is None:
                continue
            file_day = ts.date()
            if date_from and file_day < date_from:
                continue
            if date_to and file_day > date_to:
                continue
            candidates.append((ts, file_path))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _ts, path in candidates[:max_allowed]]


def _load_archived_internal_alert_items(
    limit=200,
    area_query="",
    severity_query="",
    language_preference="",
    date_from=None,
    date_to=None,
):
    max_records = max(1, min(int(limit or 200), 5000))
    max_files = max(20, min(int(os.getenv("CAP_ARCHIVE_HISTORY_MAX_FILES", "180") or "180"), 2000))
    file_paths = _iter_cap_archive_files(date_from=date_from, date_to=date_to, max_files=max_files)
    if not file_paths:
        return []

    collected = []
    seen_keys = set()
    for file_path in file_paths:
        if len(collected) >= max_records:
            break

        xml_bytes = b""
        try:
            with gzip.open(file_path, "rb") as gz_file:
                xml_bytes = gz_file.read()
        except Exception:
            continue
        if not xml_bytes:
            continue

        try:
            root = ET.fromstring(xml_bytes)
        except Exception:
            continue

        remaining = max_records - len(collected)
        items = _embedded_internal_alerts_from_feed_root(
            root,
            limit=remaining,
            area_query=area_query,
            severity_query=severity_query,
            language_preference=language_preference,
        )
        for item in items:
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            key = "|".join([
                str(item.get("external_id") or item.get("id") or "").strip().lower(),
                _normalize_alert_text_for_matching(item.get("event_type") or payload.get("disaster_type")),
                _normalize_alert_text_for_matching(item.get("description") or payload.get("warning_message")),
                str(item.get("effective_at") or payload.get("effective_start_time") or "").strip().lower(),
            ])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            collected.append(item)
            if len(collected) >= max_records:
                break

    return collected[:max_records]


def _embedded_internal_alerts_from_internal_sqlite(limit=200, area_query="", severity_query="", language_preference=""):
    sqlite_path = _resolve_internal_api_sqlite_path()
    if not sqlite_path or not os.path.isfile(sqlite_path):
        return []

    max_records = max(1, min(int(limit or 200), 5000))
    area_filter = str(area_query or "").strip().lower()
    severity_filter = str(severity_query or "").strip().upper()
    if severity_filter in ["ALL", "ANY"]:
        severity_filter = ""

    items = []
    try:
        with sqlite3.connect(sqlite_path) as db_conn:
            db_conn.row_factory = sqlite3.Row
            db_cur = db_conn.cursor()
            db_cur.execute("PRAGMA table_info(alerts)")
            columns = {
                str(row[1]).strip().lower()
                for row in (db_cur.fetchall() or [])
                if isinstance(row, (list, tuple)) and len(row) > 1
            }
            urgency_sql = "urgency" if "urgency" in columns else "'' AS urgency"
            certainty_sql = "certainty" if "certainty" in columns else "'' AS certainty"
            query = f"""
                SELECT
                    id,
                    source,
                    external_id,
                    event_type,
                    severity,
                    {urgency_sql},
                    {certainty_sql},
                    area,
                    description,
                    headline,
                    issued_at,
                    effective_at,
                    expires_at,
                    payload_json,
                    fetched_at,
                    updated_at
                FROM alerts
                ORDER BY
                    COALESCE(issued_at, effective_at, updated_at, fetched_at) DESC,
                    updated_at DESC,
                    id DESC
                LIMIT ?
            """
            db_cur.execute(query, (max_records,))
            rows = db_cur.fetchall()
    except Exception:
        return []

    for row in rows:
        row_dict = dict(row)
        payload_obj = {}
        payload_raw = row_dict.get("payload_json")
        if payload_raw:
            try:
                payload_obj = json.loads(payload_raw)
            except Exception:
                payload_obj = {}

        area_text = str(row_dict.get("area") or payload_obj.get("area_description") or "").strip()
        event_type_raw = str(row_dict.get("event_type") or payload_obj.get("disaster_type") or "Alert").strip() or "Alert"
        description_raw = str(
            row_dict.get("description")
            or row_dict.get("headline")
            or payload_obj.get("warning_message")
            or ""
        ).strip()
        urgency_text = str(row_dict.get("urgency") or payload_obj.get("urgency") or "").strip()
        certainty_text = str(row_dict.get("certainty") or payload_obj.get("certainty") or "").strip()
        severity_text = _normalize_embedded_severity(
            row_dict.get("severity") or payload_obj.get("severity"),
            urgency=urgency_text,
            certainty=certainty_text,
            disaster_type=event_type_raw,
            warning_message=description_raw,
        )
        if area_filter and area_filter not in area_text.lower():
            continue
        if severity_filter and severity_text != severity_filter:
            continue

        issued_at = (
            row_dict.get("issued_at")
            or row_dict.get("effective_at")
            or row_dict.get("updated_at")
            or row_dict.get("fetched_at")
        )
        source_name = str(
            row_dict.get("source")
            or payload_obj.get("alert_source")
            or payload_obj.get("source_name")
            or "internal_sqlite"
        ).strip() or "internal_sqlite"
        event_type_en = str(payload_obj.get("disaster_type_en") or "").strip()
        description_en = str(payload_obj.get("warning_message_en") or "").strip()
        event_type = event_type_en if language_preference == "en" and event_type_en else event_type_raw
        description_text = description_en if language_preference == "en" and description_en else description_raw
        centroid = str(payload_obj.get("centroid") or "").strip()

        if not payload_obj:
            payload_obj = {
                "identifier": row_dict.get("external_id"),
                "disaster_type": event_type_raw,
                "severity": severity_text,
                "urgency": urgency_text,
                "certainty": certainty_text,
                "area_description": area_text,
                "warning_message": description_raw,
                "effective_start_time": row_dict.get("effective_at") or row_dict.get("issued_at"),
                "effective_end_time": row_dict.get("expires_at"),
                "alert_source": source_name,
                "centroid": centroid,
            }
            if event_type_en:
                payload_obj["disaster_type_en"] = event_type_en
            if description_en:
                payload_obj["warning_message_en"] = description_en
        else:
            payload_obj.setdefault("alert_source", source_name)
            payload_obj.setdefault("area_description", area_text)
            payload_obj.setdefault("disaster_type", event_type_raw)
            payload_obj.setdefault("warning_message", description_raw)
            payload_obj.setdefault("severity", severity_text)
            if urgency_text:
                payload_obj.setdefault("urgency", urgency_text)
            if certainty_text:
                payload_obj.setdefault("certainty", certainty_text)
            if event_type_en:
                payload_obj.setdefault("disaster_type_en", event_type_en)
            if description_en:
                payload_obj.setdefault("warning_message_en", description_en)

        item_id = f"internal-sqlite-{row_dict.get('id')}"
        items.append({
            "id": item_id,
            "external_id": row_dict.get("external_id"),
            "event_type": event_type,
            "event_type_en": event_type_en or None,
            "severity": severity_text,
            "urgency": urgency_text or None,
            "certainty": certainty_text or None,
            "area": area_text,
            "description": description_text,
            "description_en": description_en or None,
            "source": source_name,
            "source_name": source_name,
            "issued_at": row_dict.get("issued_at"),
            "effective_at": row_dict.get("effective_at") or row_dict.get("issued_at"),
            "expires_at": row_dict.get("expires_at"),
            "updated_at": row_dict.get("updated_at") or issued_at,
            "payload": payload_obj,
        })

        if len(items) >= max_records:
            break

    return items


def _embedded_internal_alerts_items(limit=200, area_query="", severity_query="", language_preference=""):
    max_records = max(1, min(int(limit or 200), 5000))
    area_filter = str(area_query or "").strip().lower()
    severity_filter = str(severity_query or "").strip().upper()
    language_pref = str(language_preference or "").strip().lower()
    if severity_filter in ["ALL", "ANY"]:
        severity_filter = ""

    items = []
    fallback_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    def append_item(
        index,
        identifier,
        event,
        severity,
        urgency,
        certainty,
        area_description,
        warning_message,
        source,
        start_time,
        end_time,
        centroid,
        event_en="",
        warning_message_en="",
        language_code="",
    ):
        if area_filter and area_filter not in str(area_description or "").lower():
            return
        if severity_filter and severity != severity_filter:
            return

        event_text = str(event or "Alert").strip() or "Alert"
        warning_text = str(warning_message or "").strip()
        event_en_text = str(event_en or "").strip()
        warning_en_text = str(warning_message_en or "").strip()
        if language_pref == "en":
            event_text = event_en_text or event_text
            warning_text = warning_en_text or warning_text

        updated_at = start_time or fallback_time
        item_id = f"embedded-{identifier or index}"
        payload_obj = {
            "identifier": identifier,
            "disaster_type": str(event or "Alert").strip() or "Alert",
            "severity": severity,
            "urgency": str(urgency or "").strip(),
            "certainty": str(certainty or "").strip(),
            "area_description": area_description,
            "warning_message": str(warning_message or "").strip(),
            "effective_start_time": start_time or None,
            "effective_end_time": end_time or None,
            "alert_source": source,
            "centroid": centroid,
        }
        if event_en_text:
            payload_obj["disaster_type_en"] = event_en_text
        if warning_en_text:
            payload_obj["warning_message_en"] = warning_en_text
        if str(language_code or "").strip():
            payload_obj["language"] = str(language_code).strip()

        items.append({
            "id": item_id,
            "external_id": identifier or None,
            "event_type": event_text,
            "event_type_en": event_en_text or None,
            "severity": severity,
            "urgency": str(urgency or "").strip() or None,
            "certainty": str(certainty or "").strip() or None,
            "area": area_description,
            "description": warning_text,
            "description_en": warning_en_text or None,
            "source": source,
            "source_name": source,
            "issued_at": start_time or None,
            "effective_at": start_time or None,
            "expires_at": end_time or None,
            "updated_at": updated_at,
            "payload": payload_obj,
        })

    cap_error = None
    try:
        root = _load_cap_feed_root()
        alert_nodes = root.findall(".//{*}alert")

        if alert_nodes:
            for index, alert_node in enumerate(alert_nodes, start=1):
                identifier = (alert_node.findtext("./{*}identifier") or "").strip()
                source = (
                    alert_node.findtext("./{*}senderName")
                    or alert_node.findtext("./{*}sender")
                    or "NDMA SACHET"
                ).strip()

                info_nodes = alert_node.findall("./{*}info")
                if not info_nodes:
                    continue

                def extract_info_fields(info_node):
                    event = (info_node.findtext("./{*}event") or "Alert").strip()
                    urgency = (info_node.findtext("./{*}urgency") or "").strip()
                    certainty = (info_node.findtext("./{*}certainty") or "").strip()
                    start_time = (
                        info_node.findtext("./{*}onset")
                        or info_node.findtext("./{*}effective")
                        or info_node.findtext("./{*}sent")
                        or ""
                    ).strip()
                    end_time = (info_node.findtext("./{*}expires") or "").strip()
                    warning_message = (
                        info_node.findtext("./{*}description")
                        or info_node.findtext("./{*}headline")
                        or ""
                    ).strip()
                    severity = _normalize_embedded_severity(
                        info_node.findtext("./{*}severity"),
                        urgency=urgency,
                        certainty=certainty,
                        disaster_type=event,
                        warning_message=warning_message,
                    )
                    area_descriptions = []
                    for area_node in info_node.findall("./{*}area"):
                        area_desc = (area_node.findtext("./{*}areaDesc") or "").strip()
                        if area_desc:
                            area_descriptions.append(area_desc)
                    area_description = ", ".join(area_descriptions).strip()
                    centroid = _extract_cap_centroid(info_node)
                    language_code = (info_node.findtext("./{*}language") or "").strip()
                    return {
                        "event": event,
                        "severity": severity,
                        "urgency": urgency,
                        "certainty": certainty,
                        "start_time": start_time,
                        "end_time": end_time,
                        "warning_message": warning_message,
                        "area_description": area_description,
                        "centroid": centroid,
                        "language_code": language_code,
                    }

                selected_info = info_nodes[0]
                english_info = None
                for node in info_nodes:
                    lang_code = (node.findtext("./{*}language") or "").strip().lower()
                    if lang_code.startswith("en"):
                        english_info = node
                        break
                if language_pref == "en" and english_info is not None:
                    selected_info = english_info

                selected_fields = extract_info_fields(selected_info)
                english_fields = extract_info_fields(english_info) if english_info is not None else {}

                append_item(
                    index=index,
                    identifier=identifier,
                    event=selected_fields.get("event"),
                    severity=selected_fields.get("severity"),
                    urgency=selected_fields.get("urgency"),
                    certainty=selected_fields.get("certainty"),
                    area_description=selected_fields.get("area_description"),
                    warning_message=selected_fields.get("warning_message"),
                    source=source,
                    start_time=selected_fields.get("start_time"),
                    end_time=selected_fields.get("end_time"),
                    centroid=selected_fields.get("centroid"),
                    event_en=english_fields.get("event", ""),
                    warning_message_en=english_fields.get("warning_message", ""),
                    language_code=selected_fields.get("language_code", ""),
                )
                if len(items) >= max_records:
                    break
        else:
            rss_items = root.findall(".//item")
            for index, item_node in enumerate(rss_items, start=1):
                title_text = str(item_node.findtext("./title") or "").strip()
                description_text = str(item_node.findtext("./description") or "").strip()
                warning_message = description_text or title_text
                event_text = title_text or "Alert"
                author_text = str(item_node.findtext("./author") or "").strip()
                source = _normalize_rss_source(author_text)
                guid_text = str(item_node.findtext("./guid") or "").strip()
                link_text = str(item_node.findtext("./link") or "").strip()
                identifier = guid_text or _extract_identifier_from_cap_link(link_text) or f"rss-{index}"

                start_iso = _parse_rss_pubdate_to_utc(item_node.findtext("./pubDate"))
                if not start_iso:
                    start_iso = fallback_time
                end_iso = _infer_rss_expiry_iso(start_iso, f"{event_text} {warning_message}")

                severity = _normalize_embedded_severity(
                    item_node.findtext("./category"),
                    urgency="Expected",
                    certainty="Likely",
                    disaster_type=event_text,
                    warning_message=warning_message,
                )

                rss_area_description = _infer_rss_area_description(f"{title_text} {description_text}")

                append_item(
                    index=index,
                    identifier=identifier,
                    event=event_text,
                    severity=severity,
                    urgency="Expected",
                    certainty="Likely",
                    area_description=rss_area_description,
                    warning_message=warning_message,
                    source=source,
                    start_time=start_iso,
                    end_time=end_iso,
                    centroid="",
                    event_en="",
                    warning_message_en="",
                    language_code="",
                )
                if len(items) >= max_records:
                    break
    except Exception as exc:
        cap_error = exc

    if items:
        return items

    sqlite_items = _embedded_internal_alerts_from_internal_sqlite(
        limit=max_records,
        area_query=area_query,
        severity_query=severity_query,
        language_preference=language_pref,
    )
    if sqlite_items:
        return sqlite_items

    snapshot_payload = load_live_alerts_snapshot("india", "official", max_age_seconds=86400)
    snapshot_alerts = snapshot_payload.get("alerts") if isinstance(snapshot_payload, dict) else []
    if isinstance(snapshot_alerts, list):
        for index, alert in enumerate(snapshot_alerts, start=1):
            if not isinstance(alert, dict):
                continue
            lat = alert.get("lat")
            lon = alert.get("lon")
            centroid = ""
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                centroid = f"{float(lon)},{float(lat)}"

            append_item(
                index=index,
                identifier=str(alert.get("id") or ""),
                event=str(alert.get("type") or alert.get("title") or "Alert"),
                severity=_normalize_embedded_severity(
                    alert.get("severity"),
                    urgency=alert.get("urgency"),
                    certainty=alert.get("certainty"),
                    disaster_type=alert.get("type") or alert.get("title") or "Alert",
                    warning_message=alert.get("message") or "",
                ),
                urgency=alert.get("urgency"),
                certainty=alert.get("certainty"),
                area_description=str(alert.get("area") or ""),
                warning_message=str(alert.get("message") or ""),
                source=str(alert.get("source") or "Snapshot"),
                start_time=str(alert.get("start_time") or ""),
                end_time=str(alert.get("end_time") or ""),
                centroid=centroid,
                event_en=str(alert.get("type_en") or alert.get("disaster_type_en") or ""),
                warning_message_en=str(alert.get("message_en") or alert.get("warning_message_en") or ""),
            )
            if len(items) >= max_records:
                break

    if items:
        return items

    return items


def _embedded_internal_alerts_payload(limit=200, area_query="", severity_query="", language_preference=""):
    items = _embedded_internal_alerts_items(
        limit=limit,
        area_query=area_query,
        severity_query=severity_query,
        language_preference=language_preference,
    )
    return {
        "success": True,
        "count": len(items),
        "items": items,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_mode": "embedded_django",
    }


def _embedded_internal_sources_payload():
    attempted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        items = _embedded_internal_alerts_items(limit=5)
        return {
            "success": True,
            "items": [
                {
                    "source_name": "NDMA SACHET",
                    "last_status": "SUCCESS",
                    "last_attempt_at": attempted_at,
                    "last_success_at": attempted_at,
                    "records": len(items),
                    "error": None,
                }
            ],
        }
    except Exception as exc:
        return {
            "success": True,
            "items": [
                {
                    "source_name": "NDMA SACHET",
                    "last_status": "ERROR",
                    "last_attempt_at": attempted_at,
                    "last_success_at": None,
                    "records": 0,
                    "error": str(exc),
                }
            ],
        }


def _embedded_internal_sync_payload():
    attempted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    items = _embedded_internal_alerts_items(limit=30)
    return {
        "success": True,
        "attempted_at_utc": attempted_at,
        "summary": {
            "embedded_sachet": {
                "status": "SUCCESS",
                "records": len(items),
            }
        },
    }


def _internal_api_is_healthy(timeout_seconds=2):
    if _internal_api_is_embedded():
        return True
    try:
        response = requests.get(_internal_api_health_url(), timeout=timeout_seconds)
        return response.status_code == 200
    except Exception:
        return False


def _internal_api_workdir():
    configured = (os.getenv("INTERNAL_API_DIR") or "").strip()
    if configured and os.path.isdir(configured):
        return configured

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(base_dir, "..", "internal api")),
        os.path.abspath(os.path.join(base_dir, "..", "..", "internal api")),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def _internal_api_python_bin(workdir):
    venv_python = os.path.join(workdir, ".venv", "bin", "python")
    if os.path.isfile(venv_python):
        return venv_python
    return "python3"


def _stop_internal_api_started_by_main():
    global _internal_api_process, _internal_api_log_handle

    if _internal_api_started_by_main and _internal_api_process and _internal_api_process.poll() is None:
        try:
            _internal_api_process.terminate()
            _internal_api_process.wait(timeout=5)
        except Exception:
            try:
                _internal_api_process.kill()
            except Exception:
                pass

    if _internal_api_log_handle:
        try:
            _internal_api_log_handle.close()
        except Exception:
            pass
        _internal_api_log_handle = None


atexit.register(_stop_internal_api_started_by_main)


def ensure_internal_api_running():
    global _internal_api_process, _internal_api_started_by_main, _internal_api_log_handle

    if _internal_api_is_embedded():
        return True

    if _internal_api_is_healthy():
        return True

    if not INTERNAL_API_AUTOSTART:
        return False

    workdir = _internal_api_workdir()
    if not workdir:
        print("⚠️ INTERNAL_API_AUTOSTART is enabled, but internal api folder was not found.")
        return False

    python_bin = _internal_api_python_bin(workdir)
    env = os.environ.copy()
    env.setdefault("ENABLE_SCHEDULER", "true")
    env.setdefault("RUN_SYNC_ON_STARTUP", "true")
    env.setdefault("POLL_INTERVAL_SECONDS", (os.getenv("INTERNAL_API_POLL_INTERVAL_SECONDS") or "300").strip() or "300")

    if _internal_api_log_handle is None:
        _internal_api_log_handle = open(INTERNAL_API_AUTOSTART_LOG, "a", encoding="utf-8")

    try:
        _internal_api_process = subprocess.Popen(
            [python_bin, "run.py"],
            cwd=workdir,
            env=env,
            stdout=_internal_api_log_handle,
            stderr=_internal_api_log_handle,
        )
        _internal_api_started_by_main = True
    except Exception as exc:
        print(f"⚠️ Failed to auto-start internal API: {exc}")
        return False

    deadline = time_module.monotonic() + INTERNAL_API_START_TIMEOUT_SECONDS
    while time_module.monotonic() < deadline:
        if _internal_api_is_healthy(timeout_seconds=1):
            print("✅ Internal API auto-started and healthy")
            return True
        if _internal_api_process and _internal_api_process.poll() is not None:
            break
        time_module.sleep(0.4)

    return _internal_api_is_healthy(timeout_seconds=1)


def sync_internal_api_if_needed(force=False):
    global _internal_api_last_sync_monotonic, _internal_api_last_sync_attempt_utc, _internal_api_last_sync_success_utc

    if not INTERNAL_API_SYNC_ON_ALERT_REQUEST and not force:
        return

    if _internal_api_is_embedded():
        now = time_module.monotonic()
        if not force and (now - _internal_api_last_sync_monotonic) < INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS:
            return
        _internal_api_last_sync_attempt_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _internal_api_last_sync_monotonic = now
        try:
            _embedded_internal_alerts_items(limit=10)
            _internal_api_last_sync_success_utc = _internal_api_last_sync_attempt_utc
        except Exception:
            pass
        return

    now = time_module.monotonic()
    if not force and (now - _internal_api_last_sync_monotonic) < INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS:
        return

    if not _internal_api_sync_lock.acquire(blocking=False):
        return

    try:
        now = time_module.monotonic()
        if not force and (now - _internal_api_last_sync_monotonic) < INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS:
            return

        if not _internal_api_is_healthy(timeout_seconds=1):
            ensure_internal_api_running()
        if not _internal_api_is_healthy(timeout_seconds=2):
            return

        _internal_api_last_sync_attempt_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _internal_api_last_sync_monotonic = time_module.monotonic()
        try:
            response = requests.post(
                _internal_api_sync_url(),
                headers=_internal_api_auth_headers(),
                timeout=15,
            )
            if response.status_code < 400:
                _internal_api_last_sync_success_utc = _internal_api_last_sync_attempt_utc
        except Exception:
            pass
    finally:
        _internal_api_sync_lock.release()


class DatabaseCursorProxy:
    def __init__(self, target_cursor, backend):
        self._target_cursor = target_cursor
        self._backend = backend

    def _normalize_query(self, query):
        if self._backend == "sqlite":
            return query.replace('%s', '?')
        return query

    def execute(self, query, params=None):
        normalized_query = self._normalize_query(query)
        if params is None:
            return self._target_cursor.execute(normalized_query)
        return self._target_cursor.execute(normalized_query, params)

    def executemany(self, query, seq_of_params):
        normalized_query = self._normalize_query(query)
        return self._target_cursor.executemany(normalized_query, seq_of_params)

    def __getattr__(self, item):
        return getattr(self._target_cursor, item)


class DatabaseConnectionProxy:
    def __init__(self, target_conn, backend):
        self._target_conn = target_conn
        self._backend = backend

    def commit(self):
        return self._target_conn.commit()

    def rollback(self):
        return self._target_conn.rollback()

    def close(self):
        return self._target_conn.close()

    def cursor(self):
        return DatabaseCursorProxy(self._target_conn.cursor(), self._backend)

    def __getattr__(self, item):
        return getattr(self._target_conn, item)


def connect_mysql():
    global mysql_conn, mysql_cursor

    try:
        import mysql.connector
    except ImportError:
        print("⚠️ MySQL connector not available")
        return

    if not db_host or not db_user or not db_name:
        print("⚠️ MySQL config incomplete. Set DB_HOST, DB_USER and DB_NAME to enable MySQL.")
        return

    try:
        mysql_conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            use_pure=MYSQL_USE_PURE
        )
        mysql_cursor = mysql_conn.cursor()
        mode = "pure" if MYSQL_USE_PURE else "c-ext"
        print(f"✅ MySQL connected ({mode})")
    except Exception as err:
        mysql_conn = None
        mysql_cursor = None
        print(f"❌ MySQL connection failed: {err}")


def connect_sqlite():
    global sqlite_conn, sqlite_cursor

    try:
        sqlite_conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("PRAGMA journal_mode=WAL")
        sqlite_cursor.execute("PRAGMA synchronous=NORMAL")
        print(f"✅ SQLite connected ({DB_PATH})")
    except Exception as err:
        sqlite_conn = None
        sqlite_cursor = None
        print(f"❌ SQLite connection failed: {err}")


def select_active_database():
    global conn, cursor, USE_SQLITE, ACTIVE_DB_BACKEND

    selected_backend = None
    selected_conn = None
    selected_cursor = None

    if DB_PRIMARY == "mysql":
        if mysql_conn and mysql_cursor:
            selected_backend = "mysql"
            selected_conn = mysql_conn
            selected_cursor = mysql_cursor
        elif sqlite_conn and sqlite_cursor:
            selected_backend = "sqlite"
            selected_conn = sqlite_conn
            selected_cursor = sqlite_cursor
    else:
        if sqlite_conn and sqlite_cursor:
            selected_backend = "sqlite"
            selected_conn = sqlite_conn
            selected_cursor = sqlite_cursor
        elif mysql_conn and mysql_cursor:
            selected_backend = "mysql"
            selected_conn = mysql_conn
            selected_cursor = mysql_cursor

    if not selected_conn or not selected_cursor:
        conn = None
        cursor = None
        USE_SQLITE = False
        ACTIVE_DB_BACKEND = None
        print("❌ No database connection available")
        return

    conn = DatabaseConnectionProxy(selected_conn, selected_backend)
    cursor = DatabaseCursorProxy(selected_cursor, selected_backend)
    USE_SQLITE = selected_backend == "sqlite"
    ACTIVE_DB_BACKEND = selected_backend
    print(f"✅ Active database: {selected_backend.upper()} (PRIMARY_DB={DB_PRIMARY})")


if LEGACY_SQL_ENABLED:
    if MYSQL_CONNECTION_REQUIRED:
        connect_mysql()
    connect_sqlite()
    select_active_database()

# Initialize database tables
def _create_tables_for_backend(current_conn, current_cursor, backend):
    if backend == "sqlite":
        create_users_table = """
        CREATE TABLE IF NOT EXISTS Users (
            User_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name VARCHAR(100) NOT NULL,
            username VARCHAR(30) UNIQUE NOT NULL,
            email_id VARCHAR(100) UNIQUE NOT NULL,
            is_blocked BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            password_hash VARCHAR(255) NOT NULL,
            password_plain VARCHAR(255),
            role TEXT DEFAULT 'USER' CHECK(role IN ('ADMIN', 'USER')),
            must_change_password BOOLEAN DEFAULT 0,
            phone VARCHAR(10)
        );
        """

        create_disasters_table = """
        CREATE TABLE IF NOT EXISTS Disasters (
            Disaster_id INTEGER PRIMARY KEY AUTOINCREMENT,
            verify_status BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            media BLOB,
            media_type TEXT CHECK(media_type IN ('video','image')),
            reporter_id INTEGER NOT NULL,
            admin_id INTEGER,
            disaster_type VARCHAR(100) NOT NULL,
            description TEXT,
            latitude DECIMAL(10, 8) NOT NULL,
            longitude DECIMAL(11, 8) NOT NULL,
            address_text VARCHAR(255),
            FOREIGN KEY (reporter_id) REFERENCES Users(User_id) ON DELETE CASCADE,
            FOREIGN KEY (admin_id) REFERENCES Users(User_id) ON DELETE SET NULL
        );
        """

        create_alert_snapshots_table = """
        CREATE TABLE IF NOT EXISTS AlertSnapshots (
            snapshot_key TEXT PRIMARY KEY,
            saved_at_utc TEXT NOT NULL,
            scope TEXT,
            coverage_filter TEXT,
            source_mode TEXT,
            payload_json TEXT NOT NULL,
            alerts_count INTEGER NOT NULL DEFAULT 0
        );
        """
    else:
        create_users_table = """
        CREATE TABLE IF NOT EXISTS Users (
            User_id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(100) NOT NULL,
            username VARCHAR(30) UNIQUE NOT NULL,
            email_id VARCHAR(100) UNIQUE NOT NULL,
            is_blocked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            password_hash VARCHAR(255) NOT NULL,
            password_plain VARCHAR(255),
            role ENUM('ADMIN', 'USER') DEFAULT 'USER',
            must_change_password BOOLEAN DEFAULT FALSE,
            phone VARCHAR(10)
        );
        """

        create_disasters_table = """
        CREATE TABLE IF NOT EXISTS Disasters (
            Disaster_id INT AUTO_INCREMENT PRIMARY KEY,
            verify_status BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            media LONGBLOB,
            media_type ENUM('video','image'),
            reporter_id INT NOT NULL,
            admin_id INT NULL,
            disaster_type VARCHAR(100) NOT NULL,
            description TEXT,
            latitude DECIMAL(10, 8) NOT NULL,
            longitude DECIMAL(11, 8) NOT NULL,
            address_text VARCHAR(255),
            FOREIGN KEY (reporter_id) REFERENCES Users(User_id) ON DELETE CASCADE,
            FOREIGN KEY (admin_id) REFERENCES Users(User_id) ON DELETE SET NULL
        );
        """

    current_cursor.execute(create_users_table)
    current_cursor.execute(create_disasters_table)
    # Persist "last known good" live-alert responses for standby fallback.
    if backend == "sqlite":
        current_cursor.execute(create_alert_snapshots_table)
    else:
        current_cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS AlertSnapshots (
                snapshot_key VARCHAR(128) PRIMARY KEY,
                saved_at_utc VARCHAR(32) NOT NULL,
                scope VARCHAR(32),
                coverage_filter VARCHAR(32),
                source_mode VARCHAR(64),
                payload_json MEDIUMTEXT NOT NULL,
                alerts_count INT NOT NULL DEFAULT 0
            );
            """
        )
    current_conn.commit()


def init_database():
    """Create Users and Disasters tables for all connected backends"""
    backends = [
        ("mysql", mysql_conn, mysql_cursor),
        ("sqlite", sqlite_conn, sqlite_cursor),
    ]

    initialized_any = False
    for backend_name, backend_conn, backend_cursor in backends:
        if not backend_conn or not backend_cursor:
            continue
        try:
            _create_tables_for_backend(backend_conn, backend_cursor, backend_name)
            print(f"✅ Tables initialized ({backend_name.upper()})")
            initialized_any = True
        except Exception as err:
            print(f"❌ Error initializing {backend_name.upper()} tables: {err}")

    if not initialized_any:
        print("❌ Database connection not available")


def ensure_users_password_plain_column():
    backends = [
        ("mysql", mysql_conn, mysql_cursor),
        ("sqlite", sqlite_conn, sqlite_cursor),
    ]

    for backend_name, backend_conn, backend_cursor in backends:
        if not backend_conn or not backend_cursor:
            continue

        try:
            has_column = False
            if backend_name == "sqlite":
                backend_cursor.execute("PRAGMA table_info(Users)")
                columns = backend_cursor.fetchall()
                has_column = any(str(col[1]).lower() == "password_plain" for col in columns)
            else:
                backend_cursor.execute("SHOW COLUMNS FROM Users LIKE %s", ("password_plain",))
                has_column = backend_cursor.fetchone() is not None

            if not has_column:
                backend_cursor.execute("ALTER TABLE Users ADD COLUMN password_plain VARCHAR(255)")
                backend_conn.commit()
                print(f"✅ Added Users.password_plain ({backend_name.upper()})")
        except Exception as err:
            print(f"⚠️ Could not ensure password_plain column on {backend_name.upper()}: {err}")


def ensure_users_must_change_password_column():
    backends = [
        ("mysql", mysql_conn, mysql_cursor),
        ("sqlite", sqlite_conn, sqlite_cursor),
    ]

    for backend_name, backend_conn, backend_cursor in backends:
        if not backend_conn or not backend_cursor:
            continue

        try:
            has_column = False
            if backend_name == "sqlite":
                backend_cursor.execute("PRAGMA table_info(Users)")
                columns = backend_cursor.fetchall()
                has_column = any(str(col[1]).lower() == "must_change_password" for col in columns)
                if not has_column:
                    backend_cursor.execute("ALTER TABLE Users ADD COLUMN must_change_password BOOLEAN DEFAULT 0")
            else:
                backend_cursor.execute("SHOW COLUMNS FROM Users LIKE %s", ("must_change_password",))
                has_column = backend_cursor.fetchone() is not None
                if not has_column:
                    backend_cursor.execute("ALTER TABLE Users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE")

            if not has_column:
                backend_conn.commit()
                print(f"✅ Added Users.must_change_password ({backend_name.upper()})")
        except Exception as err:
            print(f"⚠️ Could not ensure must_change_password column on {backend_name.upper()}: {err}")


def backfill_plain_passwords():
    if not STORE_PLAIN_PASSWORDS:
        return
    if not cursor or not conn:
        return

    try:
        cursor.execute(
            "UPDATE Users SET password_plain = password_hash "
            "WHERE (password_plain IS NULL OR password_plain = '') AND password_hash IS NOT NULL"
        )
        conn.commit()
    except Exception as err:
        print(f"⚠️ Could not backfill plain passwords: {err}")


def enforce_single_fixed_admin():
    if not cursor or not conn:
        return

    try:
        admin_password_hash = _hash_password(FIXED_ADMIN_PASSWORD) if SECURE_PASSWORD_MODE else FIXED_ADMIN_PASSWORD
        admin_password_plain = FIXED_ADMIN_PASSWORD if STORE_PLAIN_PASSWORDS else None

        cursor.execute(
            """
            SELECT User_id
            FROM Users
            WHERE LOWER(email_id) = LOWER(%s) AND LOWER(username) = LOWER(%s)
            LIMIT 1
            """,
            (FIXED_ADMIN_EMAIL, FIXED_ADMIN_USERNAME),
        )
        fixed_user = cursor.fetchone()

        if fixed_user:
            cursor.execute(
                """
                    UPDATE Users
                    SET full_name = %s,
                        password_hash = %s,
                        password_plain = %s,
                        role = 'ADMIN',
                        must_change_password = 0,
                        is_blocked = 0
                    WHERE User_id = %s
                """,
                ("Matrik Admin", admin_password_hash, admin_password_plain, fixed_user[0]),
            )
        else:
            cursor.execute(
                """
                SELECT User_id
                FROM Users
                WHERE LOWER(email_id) = LOWER(%s) OR LOWER(username) = LOWER(%s)
                ORDER BY User_id ASC
                LIMIT 1
                """,
                (FIXED_ADMIN_EMAIL, FIXED_ADMIN_USERNAME),
            )
            candidate_user = cursor.fetchone()

            if candidate_user:
                cursor.execute(
                    """
                    UPDATE Users
                    SET full_name = %s,
                        username = %s,
                        email_id = %s,
                        password_hash = %s,
                        password_plain = %s,
                        role = 'ADMIN',
                        must_change_password = 0,
                        is_blocked = 0
                    WHERE User_id = %s
                    """,
                    (
                        "Matrik Admin",
                        FIXED_ADMIN_USERNAME,
                        FIXED_ADMIN_EMAIL,
                        admin_password_hash,
                        admin_password_plain,
                        candidate_user[0],
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO Users (full_name, username, email_id, password_hash, password_plain, role, must_change_password, phone)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "Matrik Admin",
                        FIXED_ADMIN_USERNAME,
                        FIXED_ADMIN_EMAIL,
                        admin_password_hash,
                        admin_password_plain,
                        "ADMIN",
                        0,
                        None,
                    ),
                )

        cursor.execute(
            """
            UPDATE Users
            SET role = 'USER'
            WHERE UPPER(role) = 'ADMIN'
              AND NOT (LOWER(email_id) = LOWER(%s) AND LOWER(username) = LOWER(%s))
            """,
            (FIXED_ADMIN_EMAIL, FIXED_ADMIN_USERNAME),
        )
        conn.commit()
        print("✅ Enforced single fixed admin account policy")
    except Exception as err:
        print(f"⚠️ Could not enforce single fixed admin policy: {err}")


def bootstrap_sqlite_from_mysql_if_empty():
    """Seed SQLite from MySQL one time when SQLite has no data."""
    if not mysql_conn or not mysql_cursor or not sqlite_conn or not sqlite_cursor:
        return

    try:
        sqlite_cursor.execute("SELECT COUNT(*) FROM Users")
        sqlite_users = sqlite_cursor.fetchone()[0]
        sqlite_cursor.execute("SELECT COUNT(*) FROM Disasters")
        sqlite_disasters = sqlite_cursor.fetchone()[0]

        if sqlite_users > 0 or sqlite_disasters > 0:
            return

        mysql_cursor.execute("SELECT COUNT(*) FROM Users")
        mysql_users = mysql_cursor.fetchone()[0]
        mysql_cursor.execute("SELECT COUNT(*) FROM Disasters")
        mysql_disasters = mysql_cursor.fetchone()[0]

        if mysql_users == 0 and mysql_disasters == 0:
            return

        mysql_cursor.execute(
            """
            SELECT User_id, full_name, username, email_id, is_blocked, created_at, password_hash, password_plain, role, must_change_password, phone
            FROM Users
            """
        )
        users_rows = mysql_cursor.fetchall()
        if users_rows:
            sqlite_cursor.executemany(
                """
                INSERT OR REPLACE INTO Users
                (User_id, full_name, username, email_id, is_blocked, created_at, password_hash, password_plain, role, must_change_password, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                users_rows
            )

        mysql_cursor.execute(
            """
            SELECT Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id,
                   disaster_type, description, latitude, longitude, address_text
            FROM Disasters
            """
        )
        disaster_rows = mysql_cursor.fetchall()
        if disaster_rows:
            sqlite_cursor.executemany(
                """
                INSERT OR REPLACE INTO Disasters
                (Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id,
                 disaster_type, description, latitude, longitude, address_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                disaster_rows
            )

        sqlite_conn.commit()
        print(f"✅ SQLite bootstrap complete (users={len(users_rows)}, disasters={len(disaster_rows)})")
    except Exception as err:
        print(f"⚠️ SQLite bootstrap skipped: {err}")


def _normalize_value_for_sqlite(value):
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    return value


def _normalize_value_for_mysql(value):
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def sync_mysql_to_sqlite(force=False):
    """Mirror users + disasters from MySQL into SQLite."""
    if not mysql_conn or not mysql_cursor or not sqlite_conn:
        return False

    acquired = sqlite_sync_lock.acquire(blocking=force)
    if not acquired:
        return False

    try:
        mysql_cur = mysql_conn.cursor()
        sqlite_cur = sqlite_conn.cursor()

        mysql_cur.execute(
            """
            SELECT User_id, full_name, username, email_id, is_blocked, created_at, password_hash, password_plain, role, must_change_password, phone
            FROM Users
            ORDER BY User_id
            """
        )
        users_rows = [tuple(_normalize_value_for_sqlite(v) for v in row) for row in mysql_cur.fetchall()]

        mysql_cur.execute(
            """
            SELECT Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id,
                   disaster_type, description, latitude, longitude, address_text
            FROM Disasters
            ORDER BY Disaster_id
            """
        )
        disaster_rows = [tuple(_normalize_value_for_sqlite(v) for v in row) for row in mysql_cur.fetchall()]

        sqlite_cur.execute("BEGIN IMMEDIATE")
        sqlite_cur.execute("DELETE FROM Disasters")
        sqlite_cur.execute("DELETE FROM Users")

        if users_rows:
            sqlite_cur.executemany(
                """
                INSERT OR REPLACE INTO Users
                (User_id, full_name, username, email_id, is_blocked, created_at, password_hash, password_plain, role, must_change_password, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                users_rows
            )

        if disaster_rows:
            sqlite_cur.executemany(
                """
                INSERT OR REPLACE INTO Disasters
                (Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id,
                 disaster_type, description, latitude, longitude, address_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                disaster_rows
            )

        sqlite_conn.commit()
        print(f"🔄 SQLite sync complete (users={len(users_rows)}, disasters={len(disaster_rows)})")
        return True
    except Exception as err:
        try:
            sqlite_conn.rollback()
        except Exception:
            pass
        print(f"⚠️ SQLite sync failed: {err}")
        return False
    finally:
        sqlite_sync_lock.release()


def sync_sqlite_to_mysql(force=False):
    """Mirror users + disasters from SQLite into MySQL."""
    global mysql_conn, mysql_cursor

    if not sqlite_conn:
        return False

    if not mysql_conn or not mysql_cursor:
        connect_mysql()

    if not mysql_conn or not mysql_cursor:
        return False

    acquired = sqlite_sync_lock.acquire(blocking=force)
    if not acquired:
        return False

    try:
        sqlite_cur = sqlite_conn.cursor()
        mysql_cur = mysql_conn.cursor()

        sqlite_cur.execute(
            """
            SELECT User_id, full_name, username, email_id, is_blocked, created_at, password_hash, password_plain, role, must_change_password, phone
            FROM Users
            ORDER BY User_id
            """
        )
        users_rows = [tuple(_normalize_value_for_mysql(v) for v in row) for row in sqlite_cur.fetchall()]

        sqlite_cur.execute(
            """
            SELECT Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id,
                   disaster_type, description, latitude, longitude, address_text
            FROM Disasters
            ORDER BY Disaster_id
            """
        )
        disaster_rows = [tuple(_normalize_value_for_mysql(v) for v in row) for row in sqlite_cur.fetchall()]

        mysql_cur.execute("SET FOREIGN_KEY_CHECKS=0")
        mysql_cur.execute("DELETE FROM Disasters")
        mysql_cur.execute("DELETE FROM Users")

        if users_rows:
            mysql_cur.executemany(
                """
                INSERT INTO Users
                (User_id, full_name, username, email_id, is_blocked, created_at, password_hash, password_plain, role, must_change_password, phone)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                users_rows
            )

        if disaster_rows:
            mysql_cur.executemany(
                """
                INSERT INTO Disasters
                (Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id,
                 disaster_type, description, latitude, longitude, address_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                disaster_rows
            )

        mysql_cur.execute("SET FOREIGN_KEY_CHECKS=1")
        mysql_conn.commit()
        print(f"🔄 MySQL reverse sync complete (users={len(users_rows)}, disasters={len(disaster_rows)})")
        return True
    except Exception as err:
        try:
            mysql_conn.rollback()
        except Exception:
            pass
        mysql_conn = None
        mysql_cursor = None
        print(f"⚠️ MySQL reverse sync failed: {err}")
        return False
    finally:
        sqlite_sync_lock.release()


def _sqlite_sync_loop():
    while True:
        try:
            if SQLITE_CONTINUOUS_SYNC_FROM_MYSQL and ACTIVE_DB_BACKEND == "mysql":
                sync_mysql_to_sqlite(force=False)
            elif MYSQL_REVERSE_SYNC_FROM_SQLITE and ACTIVE_DB_BACKEND == "sqlite":
                reverse_ok = sync_sqlite_to_mysql(force=False)
                if reverse_ok and DB_PRIMARY == "mysql":
                    select_active_database()
        except Exception as err:
            print(f"⚠️ SQLite sync loop error: {err}")
        time_module.sleep(SQLITE_SYNC_INTERVAL_SEC)


def start_sqlite_sync_worker():
    global sqlite_sync_thread_started
    if sqlite_sync_thread_started:
        return
    if not (SQLITE_CONTINUOUS_SYNC_FROM_MYSQL or MYSQL_REVERSE_SYNC_FROM_SQLITE):
        return
    sqlite_sync_thread_started = True
    threading.Thread(target=_sqlite_sync_loop, daemon=True, name='sqlite-sync-worker').start()
    print(f"✅ DB sync worker started (interval={SQLITE_SYNC_INTERVAL_SEC}s)")

# Initialize database on startup (legacy SQL mode only)
if LEGACY_SQL_ENABLED and cursor:
    init_database()
    ensure_users_password_plain_column()
    ensure_users_must_change_password_column()
    backfill_plain_passwords()
    if SQLITE_BOOTSTRAP_FROM_MYSQL:
        bootstrap_sqlite_from_mysql_if_empty()
    if SQLITE_CONTINUOUS_SYNC_FROM_MYSQL and ACTIVE_DB_BACKEND == "mysql":
        sync_mysql_to_sqlite(force=True)
    elif MYSQL_REVERSE_SYNC_FROM_SQLITE and ACTIVE_DB_BACKEND == "sqlite":
        sync_sqlite_to_mysql(force=True)
    if SQLITE_CONTINUOUS_SYNC_FROM_MYSQL or MYSQL_REVERSE_SYNC_FROM_SQLITE:
        start_sqlite_sync_worker()
    select_active_database()
    enforce_single_fixed_admin()


def _mongo_mode_active():
    engine = str(connection.settings_dict.get("ENGINE") or "").strip().lower()
    return "mongodb" in engine or "djongo" in engine


def _mongo_sqlite_fallback_path():
    configured = None
    try:
        configured = (settings.DATABASES.get(MONGODB_SQLITE_FALLBACK_ALIAS) or {}).get("NAME")
    except Exception:
        configured = None

    sqlite_path = str(configured or DB_PATH or "").strip()
    if not sqlite_path:
        return None
    if os.path.isabs(sqlite_path):
        return sqlite_path
    return os.path.abspath(os.path.join(APP_ROOT, sqlite_path))


def _to_sqlite_datetime_text(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt_value = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt_value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text

    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_sqlite_scalar(value):
    if value is None:
        return None
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime):
        return _to_sqlite_datetime_text(value)
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _stable_fallback_int_id(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except Exception:
        digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()
        return int(digest[:12], 16)


def _mapped_fallback_int_id(value, id_map):
    if value is None or value == "":
        return None
    key = str(value)
    if key in id_map:
        return id_map[key]
    return _stable_fallback_int_id(value)


def _ensure_mongo_sqlite_fallback_schema(sqlite_cur):
    sqlite_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_user (
            id INTEGER PRIMARY KEY,
            password TEXT NOT NULL,
            last_login TEXT NULL,
            is_superuser BOOLEAN NOT NULL DEFAULT 0,
            username TEXT NOT NULL UNIQUE,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            is_staff BOOLEAN NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            date_joined TEXT NOT NULL
        );
        """
    )
    sqlite_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS core_userprofile (
            id INTEGER PRIMARY KEY,
            legacy_user_id INTEGER UNIQUE,
            phone TEXT,
            role TEXT NOT NULL DEFAULT 'USER',
            is_blocked BOOLEAN NOT NULL DEFAULT 0,
            must_change_password BOOLEAN NOT NULL DEFAULT 0,
            password_plain TEXT,
            legacy_password_hash TEXT,
            user_id INTEGER NOT NULL UNIQUE
        );
        """
    )
    sqlite_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS Disasters (
            Disaster_id INTEGER PRIMARY KEY,
            verify_status BOOLEAN DEFAULT 0,
            created_at TEXT,
            media BLOB,
            media_type TEXT,
            reporter_id INTEGER NOT NULL,
            admin_id INTEGER,
            disaster_type TEXT NOT NULL,
            description TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            address_text TEXT
        );
        """
    )
    sqlite_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS AlertSnapshots (
            snapshot_key TEXT PRIMARY KEY,
            saved_at_utc TEXT NOT NULL,
            scope TEXT,
            coverage_filter TEXT,
            source_mode TEXT,
            payload_json TEXT NOT NULL,
            alerts_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def _mongo_uri_for_source(source_key):
    key = str(source_key or "").strip().lower()
    candidate_uris = getattr(settings, "MONGODB_CANDIDATE_URIS", {}) or {}
    if isinstance(candidate_uris, dict):
        uri_value = str(candidate_uris.get(key) or "").strip()
        if uri_value:
            return uri_value

    if key == "local":
        local_default_db = (os.getenv("MONGODB_DB_NAME") or "resqfy").strip() or "resqfy"
        return str(
            os.getenv("MONGODB_LOCAL_URI")
            or os.getenv("MONGODB_URI_LOCAL")
            or f"mongodb://127.0.0.1:27017/{local_default_db}"
        ).strip()
    if key == "shared":
        return str(os.getenv("SHARED_MONGODB_URI") or "").strip()
    if key == "env":
        return str(os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
    return ""


def _mongo_bridge_db_name(local_uri, shared_uri):
    return (
        str(os.getenv("MONGODB_DB_NAME") or "").strip()
        or _mongodb_db_name_from_uri(local_uri)
        or _mongodb_db_name_from_uri(shared_uri)
        or "resqfy"
    )


def _mongo_sync_filter(document, key_fields):
    criteria = {}
    for field_name in key_fields:
        if field_name in document and document.get(field_name) not in (None, ""):
            criteria[field_name] = document.get(field_name)
            break
    if criteria:
        return criteria
    fallback_id = document.get("id")
    if fallback_id not in (None, ""):
        return {"id": fallback_id}
    return None


def _sync_mongo_collection(source_db, target_db, source_candidates, target_candidates, key_fields):
    source_collection_name = _find_collection_name(source_db.list_collection_names(), source_candidates)
    if not source_collection_name:
        return {
            "source_collection": None,
            "target_collection": target_candidates[0],
            "copied": 0,
            "skipped": 0,
        }

    target_collection_name = (
        _find_collection_name(target_db.list_collection_names(), target_candidates)
        or target_candidates[0]
    )
    source_collection = source_db[source_collection_name]
    target_collection = target_db[target_collection_name]

    copied = 0
    skipped = 0
    for item in source_collection.find({}, {"_id": 0}):
        document = dict(item or {})
        sync_filter = _mongo_sync_filter(document, key_fields)
        if not sync_filter:
            skipped += 1
            continue
        target_collection.replace_one(sync_filter, document, upsert=True)
        copied += 1

    return {
        "source_collection": source_collection_name,
        "target_collection": target_collection_name,
        "copied": copied,
        "skipped": skipped,
    }


def _sync_mongo_uri_to_uri(source_uri, target_uri, db_name, timeout_ms, bridge_scope="users_only"):
    source = str(source_uri or "").strip()
    target = str(target_uri or "").strip()
    if not source or not target:
        return False, "Missing source/target Mongo URI", {}
    if source == target:
        return True, "same_uri", {
            "rows": {
                "users": 0,
                "profiles": 0,
                "disasters": 0,
                "snapshots": 0,
            },
            "collections": {},
        }

    source_client = None
    target_client = None
    try:
        from pymongo import MongoClient

        source_client = MongoClient(
            source,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        target_client = MongoClient(
            target,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        source_client.admin.command("ping")
        target_client.admin.command("ping")

        source_db = source_client[db_name]
        target_db = target_client[db_name]
        normalized_scope = str(bridge_scope or "users_only").strip().lower()
        if normalized_scope not in {"users_only", "full"}:
            normalized_scope = "users_only"

        if normalized_scope == "full":
            sync_plan = [
                ("users", ["auth_user", "users"], ["auth_user", "users"], ["id", "username"]),
                ("profiles", ["core_userprofile", "userprofile"], ["core_userprofile", "userprofile"], ["user_id", "id"]),
                ("disasters", ["Disasters", "core_disaster", "disasters"], ["Disasters", "core_disaster", "disasters"], ["Disaster_id", "disaster_id"]),
                ("snapshots", ["AlertSnapshots", "alertsnapshots"], ["AlertSnapshots", "alertsnapshots"], ["snapshot_key"]),
            ]
        else:
            sync_plan = [
                ("users", ["auth_user", "users"], ["auth_user", "users"], ["id", "username"]),
                ("profiles", ["core_userprofile", "userprofile"], ["core_userprofile", "userprofile"], ["user_id", "id"]),
            ]
        rows = {"users": 0, "profiles": 0, "disasters": 0, "snapshots": 0}
        collection_details = {}
        for metric_name, source_candidates, target_candidates, key_fields in sync_plan:
            result = _sync_mongo_collection(
                source_db=source_db,
                target_db=target_db,
                source_candidates=source_candidates,
                target_candidates=target_candidates,
                key_fields=key_fields,
            )
            rows[metric_name] = int(result.get("copied") or 0)
            collection_details[metric_name] = result

        return True, None, {
            "scope": normalized_scope,
            "rows": rows,
            "collections": collection_details,
        }
    except Exception as exc:
        return False, str(exc), {}
    finally:
        if source_client is not None:
            try:
                source_client.close()
            except Exception:
                pass
        if target_client is not None:
            try:
                target_client.close()
            except Exception:
                pass


def sync_mongodb_local_shared_bridge(force=False):
    global mongo_bridge_sync_last_attempt_utc, mongo_bridge_sync_last_success_utc
    global mongo_bridge_sync_last_error, mongo_bridge_sync_last_warning, mongo_bridge_sync_last_rows

    if not MONGODB_BRIDGE_SYNC_ENABLED or DB_PRIMARY != "mongodb":
        return False
    if not _mongo_mode_active():
        return False
    try:
        import pymongo  # noqa: F401
    except Exception:
        mongo_bridge_sync_last_error = "pymongo is not installed"
        return False

    acquired = mongo_bridge_sync_lock.acquire(blocking=force)
    if not acquired:
        return False

    try:
        attempt_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        mongo_bridge_sync_last_attempt_utc = attempt_time

        local_uri = _mongo_uri_for_source("local")
        shared_uri = _mongo_uri_for_source("shared")
        if not local_uri or not shared_uri:
            mongo_bridge_sync_last_warning = "Local/Shared Mongo URI missing. Bridge sync skipped."
            mongo_bridge_sync_last_error = None
            return True
        if local_uri == shared_uri:
            mongo_bridge_sync_last_warning = "Local and shared Mongo URIs are identical. Bridge sync skipped."
            mongo_bridge_sync_last_error = None
            return True

        timeout_text = (os.getenv("MONGODB_CONNECT_TIMEOUT_MS") or "2500").strip()
        try:
            timeout_ms = max(500, int(timeout_text))
        except ValueError:
            timeout_ms = 2500

        active_source = str(getattr(settings, "MONGODB_ACTIVE_SOURCE", "") or "").strip().lower()
        preferred_source = active_source if active_source in {"local", "shared"} else "local"
        db_name = _mongo_bridge_db_name(local_uri=local_uri, shared_uri=shared_uri)

        local_to_shared_ok, local_to_shared_err, local_to_shared_stats = _sync_mongo_uri_to_uri(
            source_uri=local_uri,
            target_uri=shared_uri,
            db_name=db_name,
            timeout_ms=timeout_ms,
            bridge_scope=MONGODB_BRIDGE_SCOPE,
        )
        shared_to_local_ok, shared_to_local_err, shared_to_local_stats = _sync_mongo_uri_to_uri(
            source_uri=shared_uri,
            target_uri=local_uri,
            db_name=db_name,
            timeout_ms=timeout_ms,
            bridge_scope=MONGODB_BRIDGE_SCOPE,
        )

        warning_parts = []
        if not local_to_shared_ok:
            warning_parts.append(f"local->shared failed: {local_to_shared_err}")
        if not shared_to_local_ok:
            warning_parts.append(f"shared->local failed: {shared_to_local_err}")

        if preferred_source == "local" and not local_to_shared_ok:
            raise RuntimeError(local_to_shared_err or "local->shared bridge sync failed")

        mongo_bridge_sync_last_rows = {
            "local_to_shared": (local_to_shared_stats or {}).get("rows", {}),
            "shared_to_local": (shared_to_local_stats or {}).get("rows", {}),
        }
        mongo_bridge_sync_last_success_utc = attempt_time
        mongo_bridge_sync_last_warning = "; ".join(warning_parts) if warning_parts else None
        mongo_bridge_sync_last_error = None
        return True
    except Exception as err:
        mongo_bridge_sync_last_error = str(err)
        return False
    finally:
        mongo_bridge_sync_lock.release()


def sync_mongodb_to_sqlite_fallback(force=False):
    global mongo_sqlite_sync_last_attempt_utc, mongo_sqlite_sync_last_success_utc
    global mongo_sqlite_sync_last_error, mongo_sqlite_sync_last_warning, mongo_sqlite_sync_last_rows

    if not MONGODB_SQLITE_FALLBACK_SYNC_ENABLED or DB_PRIMARY != "mongodb":
        return False
    if not _mongo_mode_active():
        return False

    acquired = mongo_sqlite_sync_lock.acquire(blocking=force)
    if not acquired:
        return False

    attempt_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    mongo_sqlite_sync_last_attempt_utc = attempt_time

    try:
        sqlite_path = _mongo_sqlite_fallback_path()
        if not sqlite_path:
            raise RuntimeError("SQLite fallback path is not configured.")
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)

        user_model = get_user_model()
        user_payload = list(
            user_model.objects.all().values(
                "id",
                "password",
                "last_login",
                "is_superuser",
                "username",
                "first_name",
                "last_name",
                "email",
                "is_staff",
                "is_active",
                "date_joined",
            )
        )
        profile_payload = list(
            UserProfile.objects.all().values(
                "id",
                "user_id",
                "legacy_user_id",
                "phone",
                "role",
                "is_blocked",
                "must_change_password",
                "password_plain",
                "legacy_password_hash",
            )
        )

        warning_parts = []
        try:
            disaster_payload = list(
                Disaster.objects.all().values(
                    "disaster_id",
                    "verify_status",
                    "created_at",
                    "media",
                    "media_type",
                    "reporter_id",
                    "admin_id",
                    "disaster_type",
                    "description",
                    "latitude",
                    "longitude",
                    "address_text",
                )
            )
        except Exception as exc:
            disaster_payload = []
            warning_parts.append(f"Disaster sync skipped: {exc}")

        try:
            snapshot_payload = list(
                AlertSnapshot.objects.all().values(
                    "snapshot_key",
                    "saved_at_utc",
                    "scope",
                    "coverage_filter",
                    "source_mode",
                    "payload_json",
                    "alerts_count",
                )
            )
        except Exception as exc:
            snapshot_payload = []
            warning_parts.append(f"Snapshot sync skipped: {exc}")

        user_id_map = {}
        user_rows = []
        for item in user_payload:
            source_id = item.get("id")
            mapped_id = _stable_fallback_int_id(source_id)
            if mapped_id is None:
                continue
            user_id_map[str(source_id)] = mapped_id
            user_rows.append(
                (
                    mapped_id,
                    str(item.get("password") or ""),
                    _to_sqlite_datetime_text(item.get("last_login")),
                    1 if item.get("is_superuser") else 0,
                    str(item.get("username") or ""),
                    str(item.get("first_name") or ""),
                    str(item.get("last_name") or ""),
                    str(item.get("email") or ""),
                    1 if item.get("is_staff") else 0,
                    1 if item.get("is_active", True) else 0,
                    _to_sqlite_datetime_text(item.get("date_joined")) or attempt_time,
                )
            )

        profile_rows = []
        for item in profile_payload:
            mapped_user_id = _mapped_fallback_int_id(item.get("user_id"), user_id_map)
            if mapped_user_id is None:
                continue
            profile_rows.append(
                (
                    _stable_fallback_int_id(item.get("id")),
                    item.get("legacy_user_id"),
                    str(item.get("phone") or ""),
                    str(item.get("role") or "USER").upper(),
                    1 if item.get("is_blocked") else 0,
                    1 if item.get("must_change_password") else 0,
                    item.get("password_plain"),
                    item.get("legacy_password_hash"),
                    mapped_user_id,
                )
            )

        disaster_rows = []
        for item in disaster_payload:
            reporter_id = _mapped_fallback_int_id(item.get("reporter_id"), user_id_map)
            if reporter_id is None:
                continue
            disaster_rows.append(
                (
                    _stable_fallback_int_id(item.get("disaster_id")),
                    1 if item.get("verify_status") else 0,
                    _to_sqlite_datetime_text(item.get("created_at")),
                    _to_sqlite_scalar(item.get("media")),
                    item.get("media_type"),
                    reporter_id,
                    _mapped_fallback_int_id(item.get("admin_id"), user_id_map),
                    str(item.get("disaster_type") or ""),
                    item.get("description"),
                    _to_sqlite_scalar(item.get("latitude")),
                    _to_sqlite_scalar(item.get("longitude")),
                    item.get("address_text"),
                )
            )

        snapshot_rows = [
            (
                str(item.get("snapshot_key") or ""),
                str(item.get("saved_at_utc") or ""),
                item.get("scope"),
                item.get("coverage_filter"),
                item.get("source_mode"),
                str(item.get("payload_json") or ""),
                int(item.get("alerts_count") or 0),
            )
            for item in snapshot_payload
            if str(item.get("snapshot_key") or "").strip()
        ]

        source_total_rows = len(user_rows) + len(profile_rows) + len(disaster_rows) + len(snapshot_rows)
        existing_rows = {
            "users": _sqlite_table_count(sqlite_path, "auth_user") or 0,
            "profiles": _sqlite_table_count(sqlite_path, "core_userprofile") or 0,
            "disasters": _sqlite_first_available_count(sqlite_path, ["Disasters", "core_disaster"]) or 0,
            "snapshots": _sqlite_table_count(sqlite_path, "AlertSnapshots") or 0,
        }
        existing_total_rows = (
            existing_rows["users"]
            + existing_rows["profiles"]
            + existing_rows["disasters"]
            + existing_rows["snapshots"]
        )

        # Guardrail: when MongoDB is empty but fallback already has data,
        # do not wipe the fallback snapshot.
        if source_total_rows == 0 and existing_total_rows > 0:
            warning_parts.append("MongoDB source is empty; existing SQLite fallback data was preserved.")
            mongo_sqlite_sync_last_success_utc = attempt_time
            mongo_sqlite_sync_last_rows = existing_rows
            mongo_sqlite_sync_last_warning = "; ".join(warning_parts)
            mongo_sqlite_sync_last_error = None
            return True

        sqlite_connection = sqlite3.connect(sqlite_path, check_same_thread=False, timeout=30)
        try:
            sqlite_cur = sqlite_connection.cursor()
            sqlite_cur.execute("PRAGMA journal_mode=WAL")
            sqlite_cur.execute("PRAGMA synchronous=NORMAL")
            _ensure_mongo_sqlite_fallback_schema(sqlite_cur)

            sqlite_cur.execute("BEGIN IMMEDIATE")
            sqlite_cur.execute("DELETE FROM core_userprofile")
            sqlite_cur.execute("DELETE FROM Disasters")
            sqlite_cur.execute("DELETE FROM AlertSnapshots")
            sqlite_cur.execute("DELETE FROM auth_user")

            if user_rows:
                sqlite_cur.executemany(
                    """
                    INSERT OR REPLACE INTO auth_user
                    (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    user_rows,
                )
            if profile_rows:
                sqlite_cur.executemany(
                    """
                    INSERT OR REPLACE INTO core_userprofile
                    (id, legacy_user_id, phone, role, is_blocked, must_change_password, password_plain, legacy_password_hash, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    profile_rows,
                )
            if disaster_rows:
                sqlite_cur.executemany(
                    """
                    INSERT OR REPLACE INTO Disasters
                    (Disaster_id, verify_status, created_at, media, media_type, reporter_id, admin_id, disaster_type, description, latitude, longitude, address_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    disaster_rows,
                )
            if snapshot_rows:
                sqlite_cur.executemany(
                    """
                    INSERT OR REPLACE INTO AlertSnapshots
                    (snapshot_key, saved_at_utc, scope, coverage_filter, source_mode, payload_json, alerts_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    snapshot_rows,
                )

            sqlite_connection.commit()
        except Exception:
            sqlite_connection.rollback()
            raise
        finally:
            sqlite_connection.close()

        mongo_sqlite_sync_last_success_utc = attempt_time
        mongo_sqlite_sync_last_rows = {
            "users": len(user_rows),
            "profiles": len(profile_rows),
            "disasters": len(disaster_rows),
            "snapshots": len(snapshot_rows),
        }
        mongo_sqlite_sync_last_warning = "; ".join(warning_parts) if warning_parts else None
        mongo_sqlite_sync_last_error = None
        return True
    except Exception as err:
        mongo_sqlite_sync_last_error = str(err)
        return False
    finally:
        mongo_sqlite_sync_lock.release()


def _mongodb_sqlite_sync_loop():
    while True:
        try:
            sync_mongodb_to_sqlite_fallback(force=False)
        except Exception as err:
            print(f"⚠️ MongoDB->SQLite fallback sync loop error: {err}")
        time_module.sleep(MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS)


def _mongodb_bridge_sync_loop():
    while True:
        try:
            sync_mongodb_local_shared_bridge(force=False)
        except Exception as err:
            print(f"⚠️ MongoDB local/shared bridge sync loop error: {err}")
        time_module.sleep(MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS)


def start_mongodb_sqlite_fallback_sync_worker():
    global mongo_sqlite_sync_thread_started
    if mongo_sqlite_sync_thread_started:
        return
    if not MONGODB_SQLITE_FALLBACK_SYNC_ENABLED or DB_PRIMARY != "mongodb":
        return
    if not _mongo_mode_active():
        return

    mongo_sqlite_sync_thread_started = True
    threading.Thread(
        target=_mongodb_sqlite_sync_loop,
        daemon=True,
        name="mongodb-sqlite-fallback-sync",
    ).start()
    threading.Thread(
        target=sync_mongodb_to_sqlite_fallback,
        kwargs={"force": True},
        daemon=True,
        name="mongodb-sqlite-fallback-initial-sync",
    ).start()
    print(
        f"✅ MongoDB->SQLite fallback sync worker started "
        f"(interval={MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS}s)"
    )


def start_mongodb_bridge_sync_worker():
    global mongo_bridge_sync_thread_started
    if mongo_bridge_sync_thread_started:
        return
    if not MONGODB_BRIDGE_SYNC_ENABLED or DB_PRIMARY != "mongodb":
        return
    if not _mongo_mode_active():
        return

    local_uri = _mongo_uri_for_source("local")
    shared_uri = _mongo_uri_for_source("shared")
    if not local_uri or not shared_uri or local_uri == shared_uri:
        return

    mongo_bridge_sync_thread_started = True
    threading.Thread(
        target=_mongodb_bridge_sync_loop,
        daemon=True,
        name="mongodb-local-shared-bridge-sync",
    ).start()
    threading.Thread(
        target=sync_mongodb_local_shared_bridge,
        kwargs={"force": True},
        daemon=True,
        name="mongodb-local-shared-bridge-initial-sync",
    ).start()
    print(
        f"✅ MongoDB local/shared bridge sync worker started "
        f"(interval={MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS}s)"
    )


if DB_PRIMARY == "mongodb":
    start_mongodb_sqlite_fallback_sync_worker()
    start_mongodb_bridge_sync_worker()

app_secret_key = os.getenv('SECRET_KEY') or 'projectz-local-dev-secret'
if SECURE_PASSWORD_MODE and app_secret_key == 'projectz-local-dev-secret':
    raise RuntimeError("SECRET_KEY must be set when SECURE_PASSWORD_MODE=true")


def _is_password_change_required(user):
    if not user or not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    if profile is None:
        profile = UserProfile.objects.filter(user=user).first()
    return bool(profile and profile.must_change_password)


def enforce_password_change(request):
    user = _get_authenticated_user(request)
    if not user:
        return None

    endpoint = _get_request_endpoint(request)
    allowed_endpoints = {
        "static",
        "logout",
        "login",
        "login_google",
        "authorize",
        "change_password",
        "signup",
        "db_health",
        "mobile_sos_payload",
        "mobile_sos_app_download_apk",
        "mobile_sos_app_download_page",
        "mobile_sos_app_download_version",
        "mobile_sos_service_worker",
        "mobile_sos_manifest",
        "mobile_sos_basic",
        "mobile_sos",
        "mobile_live_alerts",
        "mobile_live_alerts_check",
        "mobile_live_alerts_check_legacy",
        "mobile_hill90_diagnostics",
        "mobile_hill90_force_sync",
        "mobile_analysis_module_one_assets",
        "mobile_analysis_asset",
        "mobile_analysis",
        "mobile_organization",
        "mobile_satellite",
        "mobile_details",
        "mobile_alerts",
        "mobile_landing",
        "mobile_home",
        "get_weather_grid",
        "get_nearby_ngos",
        "live_ngos",
        "contact_request",
    }

    if endpoint in allowed_endpoints:
        return None

    requires_change = _is_password_change_required(user)
    request.session["must_change_password"] = requires_change
    if requires_change:
        return redirect(url("change_password"))
    return None


def _check_mysql_health(reconnect=False):
    if not mysql_conn:
        return False, "not_connected"
    try:
        mysql_conn.ping(reconnect=reconnect, attempts=1, delay=0)
        return True, "ok"
    except Exception as err:
        return False, str(err)


def _check_sqlite_health():
    if not sqlite_conn:
        return False, "not_connected"
    try:
        sqlite_conn.execute("SELECT 1")
        return True, "ok"
    except Exception as err:
        return False, str(err)


def db_health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return json_response(
            {
                "success": True,
                "database": connection.settings_dict.get("ENGINE", "unknown"),
                "name": connection.settings_dict.get("NAME", ""),
            }
        )
    except Exception as err:
        return json_response({"success": False, "error": str(err)}, status=500)


# this will be used in forecasting open meteor api

def _is_mysql_connection_error(err):
    text = str(err or '').lower()
    return any(token in text for token in [
        '2013',
        '2006',
        '2055',
        'lost connection',
        'server has gone away',
        'connection not available',
        'closed',
        'ssl connection error',
        'wrong version number'
    ])


def _ensure_read_backend_ready():
    global mysql_conn, mysql_cursor

    if not cursor:
        select_active_database()

    if ACTIVE_DB_BACKEND != "mysql":
        return

    mysql_ok, _ = _check_mysql_health(reconnect=False)
    if mysql_ok:
        return

    if sqlite_conn and sqlite_cursor:
        print("⚠️ MySQL unavailable for reads. Switching active backend to SQLITE.")
        mysql_conn = None
        mysql_cursor = None
        select_active_database()


def _recover_after_mysql_failure():
    global mysql_conn, mysql_cursor

    recovered = False

    try:
        if mysql_conn:
            mysql_conn.ping(reconnect=True, attempts=1, delay=0)
            mysql_cursor = mysql_conn.cursor()
            recovered = True
    except Exception:
        recovered = False

    if not recovered:
        connect_mysql()
        recovered = bool(mysql_conn and mysql_cursor)

    if not recovered:
        mysql_conn = None
        mysql_cursor = None

    select_active_database()
    return bool(cursor)

def execute_query(query, params=None):
    """Execute query using the active backend"""
    global cursor
    if not LEGACY_SQL_ENABLED:
        return None
    _ensure_read_backend_ready()
    if not cursor:
        return None

    def _run_query_once():
        if params is not None:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor

    try:
        return _run_query_once()
    except Exception as e:
        if ACTIVE_DB_BACKEND == "mysql" and _is_mysql_connection_error(e):
            print(f"⚠️ MySQL query failed, attempting recovery: {e}")
            if _recover_after_mysql_failure():
                try:
                    return _run_query_once()
                except Exception as retry_err:
                    print(f"Query retry error: {retry_err}")
                    return None
        print(f"Query error: {e}")
        return None

def fetch_one(query, params=None):
    """Fetch one result"""
    if not LEGACY_SQL_ENABLED:
        return None
    result_cursor = execute_query(query, params)
    if result_cursor:
        return result_cursor.fetchone()
    return None

def fetch_all(query, params=None):
    """Fetch all results"""
    if not LEGACY_SQL_ENABLED:
        return []
    result_cursor = execute_query(query, params)
    if result_cursor:
        return result_cursor.fetchall()
    return []

def execute_update(query, params=None):
    """Execute update/insert/delete"""
    if not LEGACY_SQL_ENABLED:
        return False
    result_cursor = execute_query(query, params)
    if result_cursor and conn:
        conn.commit()
        if SQLITE_CONTINUOUS_SYNC_FROM_MYSQL and ACTIVE_DB_BACKEND == "mysql":
            sync_mysql_to_sqlite(force=False)
        elif MYSQL_REVERSE_SYNC_FROM_SQLITE and ACTIVE_DB_BACKEND == "sqlite":
            sync_sqlite_to_mysql(force=False)
        return True
    return False


ALERT_SNAPSHOT_MAX_ITEMS = max(
    50,
    int((os.getenv("ALERT_SNAPSHOT_MAX_ITEMS") or "500").strip() or "500"),
)
ALERT_SNAPSHOT_MAX_AGE_SECONDS = max(
    60,
    int((os.getenv("ALERT_SNAPSHOT_MAX_AGE_SECONDS") or str(7 * 24 * 60 * 60)).strip() or str(7 * 24 * 60 * 60)),
)


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _alerts_snapshot_key(coverage_filter, scope):
    cov = str(coverage_filter or "india").strip().lower() or "india"
    if cov not in ["india", "international", "all"]:
        cov = "india"
    # We never write an "all" snapshot currently; map to India for a useful standby.
    if cov == "all":
        cov = "india"

    sc = str(scope or "official").strip().lower() or "official"
    if sc not in ["official", "expanded"]:
        sc = "official"
    return f"live_alerts:{cov}:{sc}"


def save_live_alerts_snapshot(coverage_filter, scope, source_mode, generated_at, alerts):
    if not isinstance(alerts, list) or len(alerts) == 0:
        return False

    safe_alerts = alerts[:ALERT_SNAPSHOT_MAX_ITEMS]
    cov = str(coverage_filter or "india").strip().lower() or "india"
    if cov not in ["india", "international", "all"]:
        cov = "india"
    if cov == "all":
        cov = "india"

    sc = str(scope or "official").strip().lower() or "official"
    if sc not in ["official", "expanded"]:
        sc = "official"

    snapshot_key = _alerts_snapshot_key(cov, sc)
    saved_at = _utc_now_iso()
    payload = {
        "success": True,
        "generated_at": generated_at,
        "source_mode": str(source_mode or "live") or "live",
        "data_scope": sc,
        "coverage_filter": cov,
        "saved_at_utc": saved_at,
        "count": len(safe_alerts),
        "alerts": safe_alerts,
    }

    try:
        payload_json = json.dumps(payload, ensure_ascii=False)
        AlertSnapshot.objects.update_or_create(
            snapshot_key=snapshot_key,
            defaults={
                "saved_at_utc": saved_at,
                "scope": sc,
                "coverage_filter": cov,
                "source_mode": str(source_mode or ""),
                "payload_json": payload_json,
                "alerts_count": len(safe_alerts),
            },
        )
        return True
    except Exception as err:
        print(f"⚠️ Failed to save alerts snapshot: {err}")
        return False


def load_live_alerts_snapshot(coverage_filter, scope, max_age_seconds=None):
    cov = str(coverage_filter or "india").strip().lower() or "india"
    if cov not in ["india", "international", "all"]:
        cov = "india"
    if cov == "all":
        cov = "india"

    sc = str(scope or "official").strip().lower() or "official"
    if sc not in ["official", "expanded"]:
        sc = "official"

    snapshot_key = _alerts_snapshot_key(cov, sc)
    row = (
        AlertSnapshot.objects.filter(snapshot_key=snapshot_key)
        .values_list("payload_json", "saved_at_utc")
        .first()
    )
    if not row:
        return None

    try:
        payload_json = row[0]
        saved_at_utc = row[1]
        payload = json.loads(payload_json) if payload_json else None
        if not isinstance(payload, dict):
            return None

        max_age = ALERT_SNAPSHOT_MAX_AGE_SECONDS if max_age_seconds is None else max(0, int(max_age_seconds))
        saved_dt = _parse_utc_iso(saved_at_utc)
        if saved_dt and max_age > 0:
            age = (datetime.now(timezone.utc) - saved_dt).total_seconds()
            if age < 0 or age > max_age:
                return None
            payload["snapshot_age_seconds"] = int(age)

        payload["snapshot_saved_at_utc"] = str(saved_at_utc or "").strip() or payload.get("saved_at_utc")
        return payload
    except Exception:
        return None


def _internal_alerts_json_fallback_path():
    configured = str(os.getenv("SENSOR_ALERT_JSON") or "").strip()
    if configured:
        return configured

    container_default = "/app/fallback_alerts.json"
    container_dir = os.path.dirname(container_default)
    if os.path.isdir(container_dir) and os.access(container_dir, os.W_OK):
        return container_default

    return os.path.join(APP_ROOT, "fallback_alerts.json")


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _write_json_atomic(path, payload):
    try:
        target_dir = os.path.dirname(os.path.abspath(path))
        os.makedirs(target_dir, exist_ok=True)
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
        return True
    except Exception:
        return False


def _load_cap_feed_state():
    global cap_feed_state_cache, cap_feed_state_loaded
    with cap_feed_cache_lock:
        if cap_feed_state_loaded:
            return dict(cap_feed_state_cache)

        payload = _read_json_file(CAP_FEED_STATE_PATH)
        if not isinstance(payload, dict):
            payload = {}
        cap_feed_state_cache = payload
        cap_feed_state_loaded = True
        return dict(cap_feed_state_cache)


def _save_cap_feed_state(next_state):
    global cap_feed_state_cache, cap_feed_state_loaded
    safe_state = dict(next_state or {})
    with cap_feed_cache_lock:
        cap_feed_state_cache = safe_state
        cap_feed_state_loaded = True
    _write_json_atomic(CAP_FEED_STATE_PATH, safe_state)


def _load_cap_latest_xml_bytes():
    try:
        with open(CAP_FEED_LATEST_XML_PATH, "rb") as file_obj:
            payload = file_obj.read()
        if isinstance(payload, bytes) and len(payload) > 0:
            return payload
    except Exception:
        return None
    return None


def _save_cap_latest_xml_bytes(xml_bytes):
    if not isinstance(xml_bytes, (bytes, bytearray)) or len(xml_bytes) == 0:
        return False
    try:
        target_dir = os.path.dirname(os.path.abspath(CAP_FEED_LATEST_XML_PATH))
        os.makedirs(target_dir, exist_ok=True)
        temp_path = f"{CAP_FEED_LATEST_XML_PATH}.tmp"
        with open(temp_path, "wb") as file_obj:
            file_obj.write(bytes(xml_bytes))
        os.replace(temp_path, CAP_FEED_LATEST_XML_PATH)
        return True
    except Exception:
        return False


def _prune_cap_archive_if_needed():
    global cap_feed_archive_last_prune_monotonic
    if not CAP_FEED_ARCHIVE_ENABLED:
        return

    now_mono = time_module.monotonic()
    if (now_mono - cap_feed_archive_last_prune_monotonic) < 3600:
        return
    cap_feed_archive_last_prune_monotonic = now_mono

    try:
        if not os.path.isdir(CAP_FEED_ARCHIVE_DIR):
            return

        xml_files = []
        for root_dir, _dirs, files in os.walk(CAP_FEED_ARCHIVE_DIR):
            for name in files:
                if name.endswith(".xml.gz"):
                    xml_files.append(os.path.join(root_dir, name))

        if CAP_FEED_ARCHIVE_RETENTION_DAYS > 0:
            cutoff_ts = time_module.time() - (CAP_FEED_ARCHIVE_RETENTION_DAYS * 86400)
            for path in xml_files:
                try:
                    if os.path.getmtime(path) < cutoff_ts:
                        os.remove(path)
                except Exception:
                    continue

        if CAP_FEED_ARCHIVE_MAX_FILES > 0:
            xml_files = []
            for root_dir, _dirs, files in os.walk(CAP_FEED_ARCHIVE_DIR):
                for name in files:
                    if name.endswith(".xml.gz"):
                        xml_files.append(os.path.join(root_dir, name))
            xml_files.sort(
                key=lambda path: os.path.getmtime(path) if os.path.exists(path) else 0.0,
                reverse=True,
            )
            stale_files = xml_files[CAP_FEED_ARCHIVE_MAX_FILES:]
            for path in stale_files:
                try:
                    os.remove(path)
                except Exception:
                    continue
    except Exception:
        return


def _archive_cap_xml_payload(xml_bytes, cap_url, etag_value, last_modified_value, status_code, fetch_utc, payload_sha256):
    if not CAP_FEED_ARCHIVE_ENABLED:
        return None
    if not isinstance(xml_bytes, (bytes, bytearray)) or len(xml_bytes) == 0:
        return None

    _prune_cap_archive_if_needed()

    fetch_dt = _parse_utc_iso(fetch_utc) or datetime.now(timezone.utc)
    archive_rel_dir = os.path.join(fetch_dt.strftime("%Y"), fetch_dt.strftime("%m"), fetch_dt.strftime("%d"))
    archive_dir = os.path.join(CAP_FEED_ARCHIVE_DIR, archive_rel_dir)
    os.makedirs(archive_dir, exist_ok=True)

    safe_sha = str(payload_sha256 or "").strip().lower()[:12] or "unknown"
    filename = f"cap_{fetch_dt.strftime('%Y%m%dT%H%M%SZ')}_{safe_sha}.xml.gz"
    abs_path = os.path.join(archive_dir, filename)

    with gzip.open(abs_path, "wb") as gz_file:
        gz_file.write(bytes(xml_bytes))

    rel_path = os.path.relpath(abs_path, CAP_FEED_ARCHIVE_DIR)
    entry = {
        "saved_at_utc": fetch_utc,
        "url": str(cap_url or ""),
        "etag": str(etag_value or ""),
        "last_modified": str(last_modified_value or ""),
        "status_code": int(status_code or 0),
        "sha256": str(payload_sha256 or ""),
        "bytes": len(xml_bytes),
        "file": rel_path.replace("\\", "/"),
    }

    manifest_path = os.path.join(CAP_FEED_ARCHIVE_DIR, "manifest.ndjson")
    try:
        with open(manifest_path, "a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(entry, ensure_ascii=False))
            manifest.write("\n")
    except Exception:
        pass

    return entry


def _cap_feed_storage_status():
    state = _load_cap_feed_state()
    latest_file_stats = _file_stats(CAP_FEED_LATEST_XML_PATH)
    archive_count = 0
    if os.path.isdir(CAP_FEED_ARCHIVE_DIR):
        try:
            for root_dir, _dirs, files in os.walk(CAP_FEED_ARCHIVE_DIR):
                archive_count += len([name for name in files if name.endswith(".xml.gz")])
        except Exception:
            archive_count = 0
    return {
        "etag_enabled": CAP_FEED_USE_ETAG,
        "state_file": CAP_FEED_STATE_PATH,
        "latest_xml_file": latest_file_stats,
        "archive_enabled": CAP_FEED_ARCHIVE_ENABLED,
        "archive_dir": CAP_FEED_ARCHIVE_DIR,
        "archive_count": archive_count,
        "archive_retention_days": CAP_FEED_ARCHIVE_RETENTION_DAYS,
        "archive_max_files": CAP_FEED_ARCHIVE_MAX_FILES,
        "last_url": str(state.get("url") or ""),
        "last_etag": str(state.get("etag") or ""),
        "last_modified": str(state.get("last_modified") or ""),
        "last_status_code": state.get("last_status_code"),
        "last_fetch_utc": str(state.get("last_fetch_utc") or ""),
        "last_payload_sha256": str(state.get("payload_sha256") or ""),
        "last_archive_file": str(state.get("last_archive_file") or ""),
    }


def _load_cap_feed_root():
    default_rss_url = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
    cap_url = (os.getenv("SACHET_CAP_URL") or default_rss_url).strip() or default_rss_url
    if cap_url.rstrip("/").endswith("/CapFeed"):
        cap_url = default_rss_url

    state = _load_cap_feed_state()
    same_url_state = isinstance(state, dict) and str(state.get("url") or "") == cap_url
    state_etag = str(state.get("etag") or "").strip() if same_url_state else ""
    state_last_modified = str(state.get("last_modified") or "").strip() if same_url_state else ""
    state_payload_sha = str(state.get("payload_sha256") or "").strip().lower() if same_url_state else ""

    request_headers = {
        "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    }
    if CAP_FEED_USE_ETAG and state_etag:
        request_headers["If-None-Match"] = state_etag
    if CAP_FEED_USE_ETAG and state_last_modified:
        request_headers["If-Modified-Since"] = state_last_modified

    fetch_utc = _utc_now_iso()
    response = requests.get(cap_url, headers=request_headers, timeout=CAP_FEED_TIMEOUT_SECONDS)
    status_code = int(response.status_code)

    if status_code == 304:
        cached_xml = _load_cap_latest_xml_bytes()
        if cached_xml:
            root = ET.fromstring(cached_xml)
            _save_cap_feed_state({
                "url": cap_url,
                "etag": state_etag,
                "last_modified": state_last_modified,
                "last_status_code": 304,
                "last_fetch_utc": fetch_utc,
                "payload_sha256": state_payload_sha,
                "last_archive_file": str(state.get("last_archive_file") or ""),
            })
            return root

        # If conditional request returns 304 but no local cache is available,
        # issue one full request so downstream processing remains reliable.
        response = requests.get(cap_url, timeout=CAP_FEED_TIMEOUT_SECONDS)
        status_code = int(response.status_code)

    response.raise_for_status()
    xml_bytes = response.content or b""
    preview = bytes(xml_bytes[:300]).decode("utf-8", errors="ignore").lower()
    if "<!doctype html" in preview or "<html" in preview:
        # Safety fallback: some URLs return the website shell instead of RSS XML.
        cap_url = default_rss_url
        response = requests.get(cap_url, headers=request_headers, timeout=CAP_FEED_TIMEOUT_SECONDS)
        response.raise_for_status()
        xml_bytes = response.content or b""
        preview = bytes(xml_bytes[:300]).decode("utf-8", errors="ignore").lower()
        if "<!doctype html" in preview or "<html" in preview:
            raise ValueError("CAP feed returned HTML instead of XML")

    if not xml_bytes:
        raise ValueError("CAP feed response was empty")

    root = ET.fromstring(xml_bytes)
    etag_value = str(response.headers.get("ETag") or state_etag or "").strip()
    last_modified_value = str(response.headers.get("Last-Modified") or state_last_modified or "").strip()
    payload_sha = hashlib.sha256(xml_bytes).hexdigest()

    _save_cap_latest_xml_bytes(xml_bytes)

    archive_entry = None
    if status_code == 200 and payload_sha != state_payload_sha:
        try:
            archive_entry = _archive_cap_xml_payload(
                xml_bytes=xml_bytes,
                cap_url=cap_url,
                etag_value=etag_value,
                last_modified_value=last_modified_value,
                status_code=status_code,
                fetch_utc=fetch_utc,
                payload_sha256=payload_sha,
            )
        except Exception:
            archive_entry = None

    _save_cap_feed_state({
        "url": cap_url,
        "etag": etag_value,
        "last_modified": last_modified_value,
        "last_status_code": status_code,
        "last_fetch_utc": fetch_utc,
        "payload_sha256": payload_sha,
        "last_archive_file": (
            str((archive_entry or {}).get("file") or "")
            or str(state.get("last_archive_file") or "")
        ),
    })

    return root


def _raw_alert_from_formatted_entry(item):
    if not isinstance(item, dict):
        return None

    alert_id = item.get("id")
    disaster_type = item.get("type") or "Alert"
    severity = item.get("severity") or "WATCH"
    urgency = item.get("urgency") or ""
    certainty = item.get("certainty") or ""
    area_description = item.get("area") or ""
    warning_message = item.get("message") or ""
    start_time = item.get("start_time")
    end_time = item.get("end_time")
    alert_source = item.get("source") or "Resqfy"
    severity_color = item.get("severity_color") or "yellow"
    disaster_type_en = item.get("type_en") or ""
    warning_message_en = item.get("message_en") or ""
    lat = item.get("lat")
    lon = item.get("lon")

    centroid = ""
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        centroid = f"{float(lon)},{float(lat)}"

    payload = {
        "identifier": str(alert_id or ""),
        "disaster_type": str(disaster_type),
        "severity": str(severity),
        "urgency": str(urgency),
        "certainty": str(certainty),
        "area_description": str(area_description),
        "warning_message": str(warning_message),
        "effective_start_time": start_time,
        "effective_end_time": end_time,
        "alert_source": str(alert_source),
        "severity_color": str(severity_color),
        "centroid": centroid,
        "source_section": str(item.get("source_section") or ""),
    }
    if str(disaster_type_en).strip():
        payload["disaster_type_en"] = str(disaster_type_en).strip()
    if str(warning_message_en).strip():
        payload["warning_message_en"] = str(warning_message_en).strip()
    return payload


def _save_internal_alerts_json_fallback(generated_at, source_mode, alerts):
    if not isinstance(alerts, list):
        return False

    fallback_path = _internal_alerts_json_fallback_path()
    if not fallback_path:
        return False

    raw_alerts = []
    for item in alerts:
        raw_item = _raw_alert_from_formatted_entry(item)
        if raw_item:
            raw_alerts.append(raw_item)

    payload = {
        "metadata": {
            "generated_at_utc": _to_utc_iso(generated_at) or _utc_now_iso(),
            "source_mode": str(source_mode or "unknown"),
            "count": len(raw_alerts),
        },
        "raw": {
            "alerts": raw_alerts,
            "nowcast": {"nowcastDetails": []},
            "earthquakes": {"alerts": []},
            "location_alerts": {"alerts": []},
            "address_alerts": {"alerts": []},
        },
    }

    candidate_paths = [fallback_path]
    local_default = os.path.join(APP_ROOT, "fallback_alerts.json")
    if os.path.abspath(local_default) not in [os.path.abspath(path) for path in candidate_paths]:
        candidate_paths.append(local_default)

    for target_path in candidate_paths:
        try:
            target_dir = os.path.dirname(os.path.abspath(target_path))
            os.makedirs(target_dir, exist_ok=True)
            temp_path = f"{target_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)
            os.replace(temp_path, target_path)
            return True
        except Exception:
            continue

    print("⚠️ Failed to save internal JSON fallback: no writable target path")
    return False


def _ensure_internal_sqlite_alert_schema(sqlite_cur):
    sqlite_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            event_type TEXT,
            severity TEXT,
            urgency TEXT,
            certainty TEXT,
            area TEXT,
            status TEXT,
            issued_at TEXT,
            effective_at TEXT,
            expires_at TEXT,
            headline TEXT,
            description TEXT,
            instruction TEXT,
            payload_json TEXT,
            fetched_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source, external_id)
        )
        """
    )
    # Backward-compatible migration: older local DBs may miss these columns.
    try:
        sqlite_cur.execute("PRAGMA table_info(alerts)")
        existing_columns = {
            str(row[1]).strip().lower()
            for row in (sqlite_cur.fetchall() or [])
            if isinstance(row, (list, tuple)) and len(row) > 1
        }
        if "urgency" not in existing_columns:
            sqlite_cur.execute("ALTER TABLE alerts ADD COLUMN urgency TEXT")
        if "certainty" not in existing_columns:
            sqlite_cur.execute("ALTER TABLE alerts ADD COLUMN certainty TEXT")
    except Exception:
        pass

    sqlite_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS source_runs (
            source TEXT PRIMARY KEY,
            last_status TEXT NOT NULL,
            last_attempt_at TEXT NOT NULL,
            last_success_at TEXT,
            last_error TEXT,
            records_fetched INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )


def _sync_formatted_alerts_to_internal_sqlite(alerts, source_name="django_live_sync"):
    if not isinstance(alerts, list) or len(alerts) == 0:
        return {"ok": False, "reason": "empty_alerts", "rows": 0}

    sqlite_path = _resolve_internal_api_sqlite_path()
    if not sqlite_path:
        return {"ok": False, "reason": "internal_sqlite_path_missing", "rows": 0}

    now_utc = _utc_now_iso()
    rows = []
    for item in alerts:
        if not isinstance(item, dict):
            continue
        external_id = str(item.get("id") or "").strip()
        if not external_id:
            continue
        payload_obj = _raw_alert_from_formatted_entry(item) or {}
        rows.append(
            {
                "source": str(source_name or "django_live_sync"),
                "external_id": external_id,
                "event_type": str(item.get("type") or "Alert"),
                "severity": str(item.get("severity") or "WATCH"),
                "urgency": str(item.get("urgency") or payload_obj.get("urgency") or ""),
                "certainty": str(item.get("certainty") or payload_obj.get("certainty") or ""),
                "area": str(item.get("area") or ""),
                "description": str(item.get("message") or ""),
                "headline": str(item.get("type") or "Alert"),
                "issued_at": item.get("start_time"),
                "effective_at": item.get("start_time"),
                "expires_at": item.get("end_time"),
                "payload_json": json.dumps(payload_obj, ensure_ascii=False),
                "fetched_at": now_utc,
                "updated_at": now_utc,
            }
        )

    if len(rows) == 0:
        return {"ok": False, "reason": "no_rows", "rows": 0}

    try:
        target_dir = os.path.dirname(os.path.abspath(sqlite_path))
        os.makedirs(target_dir, exist_ok=True)
        with sqlite3.connect(sqlite_path) as db_conn:
            db_cur = db_conn.cursor()
            _ensure_internal_sqlite_alert_schema(db_cur)

            db_cur.executemany(
                """
                INSERT INTO alerts (
                    source, external_id, event_type, severity, urgency, certainty, area,
                    description, headline, issued_at, effective_at, expires_at,
                    payload_json, fetched_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, external_id) DO UPDATE SET
                    event_type=excluded.event_type,
                    severity=excluded.severity,
                    urgency=excluded.urgency,
                    certainty=excluded.certainty,
                    area=excluded.area,
                    description=excluded.description,
                    headline=excluded.headline,
                    issued_at=excluded.issued_at,
                    effective_at=excluded.effective_at,
                    expires_at=excluded.expires_at,
                    payload_json=excluded.payload_json,
                    fetched_at=excluded.fetched_at,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        row["source"],
                        row["external_id"],
                        row["event_type"],
                        row["severity"],
                        row["urgency"],
                        row["certainty"],
                        row["area"],
                        row["description"],
                        row["headline"],
                        row["issued_at"],
                        row["effective_at"],
                        row["expires_at"],
                        row["payload_json"],
                        row["fetched_at"],
                        row["updated_at"],
                    )
                    for row in rows
                ],
            )

            db_cur.execute(
                """
                INSERT INTO source_runs (
                    source, last_status, last_attempt_at, last_success_at,
                    last_error, records_fetched, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_status=excluded.last_status,
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=excluded.last_success_at,
                    last_error=excluded.last_error,
                    records_fetched=excluded.records_fetched,
                    updated_at=excluded.updated_at
                """,
                (str(source_name or "django_live_sync"), "SUCCESS", now_utc, now_utc, None, len(rows), now_utc),
            )
            db_conn.commit()
        return {"ok": True, "reason": None, "rows": len(rows)}
    except Exception as err:
        return {"ok": False, "reason": str(err), "rows": 0}

def fetch_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    response = requests.get(url)
    return response.json()

def generate_radius_points(lat, lon, radius_km=100):
    # Degrees of latitude per km (approx 111)
    delta_lat = radius_km / 111
    # Degrees of longitude per km varies based on latitude
    delta_lon = radius_km / (111 * math.cos(math.radians(lat)))

    return [
        (lat, lon),
        (lat + delta_lat, lon),
        (lat - delta_lat, lon),
        (lat, lon + delta_lon),
        (lat, lon - delta_lon)
    ]


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def haversine_distance_km(lat1, lon1, lat2, lon2):
    lat1 = _safe_float(lat1)
    lon1 = _safe_float(lon1)
    lat2 = _safe_float(lat2)
    lon2 = _safe_float(lon2)
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float("inf")

    radius_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_earth_km * c


def estimate_duration_text(distance_km, avg_speed_kmph=30):
    if not isinstance(distance_km, (int, float)) or not math.isfinite(distance_km):
        return None, "N/A"
    if distance_km <= 0:
        return 2, "2 min"

    minutes = max(2, int(round((distance_km / avg_speed_kmph) * 60)))
    if minutes >= 60:
        hours = minutes // 60
        rem_minutes = minutes % 60
        if rem_minutes == 0:
            return minutes, f"{hours} hr"
        return minutes, f"{hours} hr {rem_minutes} min"
    return minutes, f"{minutes} min"

# this will be used to get location of the user from the ip address using ip api

def get_location_by_ip():
    # In local development, '127.0.0.1' won't work. 
    # We use an external service to get the public IP or a test IP.
    try:
        # This API returns JSON with lat, lon, city, etc.
        response = requests.get('http://ip-api.com/json/')
        data = response.json()
        
        if data['status'] == 'success':
            return data['lat'], data['lon']
    except Exception as e:
        print(f"Error getting location: {e}")
    
    return None, None



# Load NGO contact database
ngo_contacts_cache_lock = threading.Lock()
ngo_contacts_cache = {}


def _resolve_existing_path(*candidates):
    for candidate in candidates:
        path_text = str(candidate or "").strip()
        if not path_text:
            continue
        absolute = os.path.abspath(path_text)
        if os.path.isfile(absolute):
            return absolute
    return ""


def _extract_docx_paragraphs(docx_path):
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            xml_payload = archive.read("word/document.xml")
    except Exception:
        return []

    try:
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(xml_payload)
    except Exception:
        return []

    paragraphs = []
    for node in root.findall(".//w:p", namespace):
        chunks = [str(item.text or "") for item in node.findall(".//w:t", namespace)]
        text = "".join(chunks).replace("\xa0", " ").strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _parse_docx_state_name(raw_text):
    original = str(raw_text or "").strip()
    text = original.replace("■", " ").replace("•", " ").strip()
    if not text:
        return ""

    # Keep state switching strict: accept only true heading-like lines.
    # This avoids false positives from notes that mention other states.
    upper = re.sub(r"\s+", " ", text).upper()
    if len(upper) > 48:
        return ""
    if ":" in upper or "/" in upper:
        return ""

    for state_name in NGO_STATE_COORDS:
        state_upper = state_name.upper()
        if upper == state_upper:
            return state_name
        if original.startswith("■") and upper.endswith(state_upper):
            return state_name
    return ""


def _parse_ngo_docx_contacts(docx_path):
    paragraphs = _extract_docx_paragraphs(docx_path)
    if not paragraphs:
        return {}

    contacts = {}
    current_state = "india"
    seen_names = set()
    field_labels = {
        "HELPLINE",
        "ALT. CONTACT",
        "EMAIL",
        "WEBSITE",
        "VOLUNTEERS",
        "MED KIT",
        "SHELTER",
        "FOOD",
        "TENTS",
        "WATER",
        "NOTE",
    }

    i = 0
    total = len(paragraphs)
    while i < total:
        line = str(paragraphs[i] or "").strip()
        state_name = _parse_docx_state_name(line)
        if state_name:
            current_state = state_name
            i += 1
            continue

        next_line = str(paragraphs[i + 1] or "").strip() if i + 1 < total else ""
        if "Type:" not in next_line:
            i += 1
            continue

        name = line
        normalized_name = normalize_org_name(name)
        if (
            not name
            or len(name) > 160
            or normalized_name in seen_names
            or normalized_name.startswith("national emergency helplines")
        ):
            i += 1
            continue

        type_match = re.search(r"Type:\s*([^|]+)", next_line, flags=re.IGNORECASE)
        type_value = str(type_match.group(1)).strip() if type_match else "NGO"

        phone_value = "Not available"
        email_value = "Not available"
        website_value = "Not available"
        note_value = ""

        j = i + 2
        while j < total:
            probe_line = str(paragraphs[j] or "").strip()
            if not probe_line:
                j += 1
                continue
            if _parse_docx_state_name(probe_line):
                break
            if j + 1 < total and "Type:" in str(paragraphs[j + 1] or "") and probe_line.upper() not in field_labels:
                break

            probe_upper = probe_line.upper()
            if probe_upper in field_labels:
                value = str(paragraphs[j + 1] or "").strip() if j + 1 < total else ""
                value = value or "Not available"

                if probe_upper == "HELPLINE":
                    phone_value = value
                elif probe_upper == "ALT. CONTACT":
                    if phone_value == "Not available":
                        phone_value = value
                    elif value.lower() not in phone_value.lower():
                        phone_value = f"{phone_value} / {value}"
                elif probe_upper == "EMAIL":
                    email_value = value
                elif probe_upper == "WEBSITE":
                    website_value = value
                elif probe_upper == "NOTE":
                    note_value = value
                j += 2
                continue

            j += 1

        state_label = current_state.title() if current_state and current_state != "india" else "India"
        lat, lon = NGO_STATE_COORDS.get(current_state, INDIA_DEFAULT_COORDS)
        contacts[name] = {
            "name": name,
            "type": type_value,
            "phone": phone_value,
            "email": email_value,
            "website": website_value,
            "areas": [state_label],
            "address": f"{state_label} relief coverage",
            "note": note_value,
            "lat": lat,
            "lon": lon,
        }
        seen_names.add(normalized_name)
        i = max(i + 1, j)

    return contacts


def _load_ngo_contacts_json(json_path):
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

    contacts = {}
    for ngo in data.get("ngo_contacts", []):
        if not isinstance(ngo, dict):
            continue
        name = str(ngo.get("name") or "").strip()
        if not name:
            continue
        contacts[name] = ngo
    return contacts


def load_ngo_contacts():
    json_path = _resolve_existing_path(os.path.join(APP_ROOT, "ngos_contacts.json"), "ngos_contacts.json")
    docx_path = _resolve_existing_path(
        os.getenv("NGO_DIRECTORY_DOCX"),
        os.path.join(APP_ROOT, "India_NGO_Directory_6States.docx"),
        os.path.join(APP_ROOT, "..", "India_NGO_Directory_6States.docx"),
    )
    source_path = docx_path or json_path
    if not source_path:
        return {}

    try:
        source_mtime = os.path.getmtime(source_path)
    except Exception:
        source_mtime = 0.0

    with ngo_contacts_cache_lock:
        cached = ngo_contacts_cache.get(source_path)
        if cached and float(cached.get("mtime") or 0.0) == float(source_mtime):
            payload = cached.get("data")
            if isinstance(payload, dict):
                return payload

    contacts = _parse_ngo_docx_contacts(source_path) if docx_path and source_path == docx_path else {}
    if not contacts and json_path:
        contacts = _load_ngo_contacts_json(json_path)

    with ngo_contacts_cache_lock:
        ngo_contacts_cache[source_path] = {
            "mtime": source_mtime,
            "data": contacts if isinstance(contacts, dict) else {},
        }

    return contacts if isinstance(contacts, dict) else {}


def normalize_org_name(name):
    value = str(name or '').strip().lower()
    cleaned = ''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in value)
    return ' '.join(cleaned.split())


def pick_first_value(*values, fallback='Not available'):
    for item in values:
        text = str(item or '').strip()
        if text and text.lower() not in ['not available', 'na', 'n/a', 'none', '-']:
            return text
    return fallback


def _ngo_cache_key(lat, lon, radius):
    return (round(float(lat), 2), round(float(lon), 2), int(radius))


def _ngo_cache_get(cache_key):
    with ngo_cache_lock:
        cached = ngo_cache_store.get(cache_key)
        if not cached:
            return None
        age_seconds = time_module.time() - float(cached.get("ts", 0))
        if age_seconds > NGO_CACHE_TTL_SECONDS:
            ngo_cache_store.pop(cache_key, None)
            return None
        data = cached.get("data")
        if isinstance(data, list):
            return data
    return None


def _ngo_cache_set(cache_key, data):
    if not isinstance(data, list):
        return
    with ngo_cache_lock:
        ngo_cache_store[cache_key] = {
            "ts": time_module.time(),
            "data": data
        }


def _ngo_contact_fallback(ngo_contacts_db, lat, lon, max_distance_km=None):
    def guess_coords(areas):
        area_texts = []
        if isinstance(areas, list):
            area_texts = [str(item or '').strip().lower() for item in areas if str(item or '').strip()]

        joined = " ".join(area_texts)
        if "pan india" in joined or "all cities" in joined:
            return INDIA_DEFAULT_COORDS

        for text in area_texts:
            for city_name, coords in NGO_CITY_COORDS.items():
                if city_name in text:
                    return coords
        return INDIA_DEFAULT_COORDS

    fallback = []
    for name, ngo_info in ngo_contacts_db.items():
        areas = ngo_info.get('areas', []) if isinstance(ngo_info.get('areas'), list) else []
        fallback_lat = _safe_float(ngo_info.get('lat'))
        fallback_lon = _safe_float(ngo_info.get('lon'))
        if fallback_lat is None or fallback_lon is None:
            fallback_lat, fallback_lon = guess_coords(areas)
        distance_km = haversine_distance_km(lat, lon, fallback_lat, fallback_lon)
        if isinstance(max_distance_km, (int, float)) and math.isfinite(distance_km):
            if distance_km > float(max_distance_km):
                continue
        eta_minutes, eta_text = estimate_duration_text(distance_km)

        fallback.append({
            "name": name,
            "type": ngo_info.get('type', 'NGO'),
            "lat": fallback_lat,
            "lon": fallback_lon,
            "phone": ngo_info.get('phone', 'Not available'),
            "email": ngo_info.get('email', 'Not available'),
            "website": ngo_info.get('website', 'Not available'),
            "address": areas[0] if areas else 'Nearby support',
            "areas": areas,
            "distance_km": round(distance_km, 2),
            "estimated_duration_min": eta_minutes,
            "estimated_duration": eta_text,
            "source": "contacts_fallback"
        })
    return fallback


def _fetch_overpass_payload(query_text):
    for endpoint in NGO_OVERPASS_ENDPOINTS:
        try:
            response = requests.post(
                endpoint,
                data={'data': query_text},
                timeout=NGO_REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code >= 400:
                continue
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get('elements'), list):
                return payload
        except Exception:
            continue
    return None

  
oauth = OAuth() if OAuth is not None else None
google = None
if oauth is not None:
    google = oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID', ''),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET', ''),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile' # This tells Google WHAT info to give us
        }
    )
else:
    print(f"⚠️ Google OAuth disabled: {AUTHLIB_IMPORT_ERROR}")


def get_google_redirect_uri(request=None):
    explicit_uri = str(os.getenv('GOOGLE_REDIRECT_URI', '') or '').strip()
    if explicit_uri:
        return explicit_uri
    if request is not None:
        absolute = url('authorize', request=request, _external=True)
    else:
        absolute = url('authorize', _external=True)
    return absolute.replace('/oauth2callback', '/auth/callback').replace('/oauth2/callback', '/auth/callback')

def index(request):
    return spa_index(request)




 #route for the port 5000/login
# there are two http methods-> get and post 
# here we need to take the input in the login form from user so the method is POST 
# by default if not mentioned route takes GET method 
# GET method is used to fetch and show data to user


def login(request):
    # this method checks user credentials and redirects them appropriately
    msg = _get_query_param(request, 'msg','')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            msg = "Username and password are required."
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                profile = _get_or_create_profile(user)
                if profile and profile.is_blocked:
                    user.is_active = False
                    user.save(update_fields=["is_active"])

                if not user.is_active or (profile and profile.is_blocked):
                    msg = 'Your account is blocked. Contact support.'
                else:
                    django_login(request, user)
                    _set_session_permanent(request, True)
                    _sync_session_from_user(request, user, profile=profile)

                    if STORE_PLAIN_PASSWORDS and profile and password:
                        if profile.password_plain != password:
                            profile.password_plain = password
                            profile.save(update_fields=["password_plain"])

                    if profile and profile.must_change_password:
                        return redirect(url('change_password'))

                    return redirect(url('home'))

            existing_user = (
                get_user_model()
                .objects.filter(Q(username__iexact=username) | Q(email__iexact=username))
                .first()
            )
            existing_profile = UserProfile.objects.filter(user=existing_user).first() if existing_user else None
            if existing_user and (not existing_user.is_active or (existing_profile and existing_profile.is_blocked)):
                msg = 'Your account is blocked. Contact support.'
            else:
                msg = f'Wrong credentials. Contact: {LOGIN_SUPPORT_EMAIL}'

    return render_page(request, "login.html", msg=msg)


def change_password(request):
    user = _get_authenticated_user(request)
    if not user:
        return redirect(url('login'))

    profile = _get_or_create_profile(user)
    username = user.username
    must_change_password = bool(profile.must_change_password) if profile else False
    msg = ''
    msg_type = 'info'

    if request.method == 'POST':
        current_password = _get_form_param(request, 'current_password', '')
        new_password = _get_form_param(request, 'new_password', '')
        confirm_password = _get_form_param(request, 'confirm_password', '')

        if not user.check_password(current_password):
            msg = 'Current password is incorrect.'
            msg_type = 'error'
        elif len(new_password) < 8:
            msg = 'New password must be at least 8 characters.'
            msg_type = 'error'
        elif new_password != confirm_password:
            msg = 'New password and confirm password do not match.'
            msg_type = 'error'
        else:
            user.set_password(new_password)
            user.save(update_fields=["password"])
            update_session_auth_hash(request, user)
            if profile:
                profile.must_change_password = False
                if STORE_PLAIN_PASSWORDS:
                    profile.password_plain = new_password
                else:
                    profile.password_plain = None
                profile.save(update_fields=["must_change_password", "password_plain"])
            request.session['must_change_password'] = False
            _sync_session_from_user(request, user, profile=profile)
            return redirect(url(
                'mobile_home',
                open_profile='1',
                profile_msg='Password updated successfully.',
                profile_msg_type='success',
            ))

    if must_change_password and not msg:
        msg = 'Your password was reset by admin. Please set a new password to continue.'
        msg_type = 'info'

    return render_page(request, 
        'change_password.html',
        username=username,
        must_change_password=must_change_password,
        msg=msg,
        msg_type=msg_type,
    )

# @app.route('/auth/callback')
# def authorize(request):
#     # 1. Get user info from Google
#     token = google.authorize_access_token()
#     user_info = token.get('userinfo')
    
#     email = user_info['email']
#     name = user_info['name']
    
#     # 2. Check if this email already exists in our database
#     # Note: Using %s because your helper function handles the conversion
#     query = "SELECT username, password_hash FROM users WHERE email_id = %s"
#     result = fetch_one(query, (email,))

#     if result:
#         # Scenario 1: Existing User
#         # result[0] is username, result[1] is password_hash
#         request.session['user'] = {
#             'email': email,
#             'name': name,
#             'username': result[0]
#         }
#     else:
#         # Scenario 2: New User (Signup)
#         # We fetch details from Google and insert them into our DB
#         insert_query = "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)"
#         # Since it's a Google login, we might leave password_hash as 'GOOGLE_AUTH'
#         execute_update(insert_query, (name, email, 'GOOGLE_AUTH'))
        
#         request.session['user'] = {
#             'email': email,
#             'name': name,
#             'username': name
#         }

#     return render_page(request, "admin.html", user_info=request.session.get('user')) # Or wherever you want them to go



def authorize(request):
    if google is None:
        return redirect(url('login', msg='Google login is temporarily unavailable. Please use username/password.'))

    # 1. Get user info from Google
    token = google.authorize_access_token(request)
    user_info = token.get('userinfo') or {}

    email = str(user_info.get('email') or '').strip()
    name = str(user_info.get('name') or '').strip()

    if not email:
        return redirect(url('login', msg='Google login failed. Please use username/password.'))

    UserModel = get_user_model()
    django_user = UserModel.objects.filter(email__iexact=email).first()

    if not django_user:
        # Scenario 2: New User (Signup)
        return redirect(url('signup', name=name, email=email))

    if name and django_user.first_name != name:
        django_user.first_name = name
        django_user.save(update_fields=["first_name"])

    profile = _get_or_create_profile(django_user)
    is_fixed_admin = (
        str(email or '').strip().lower() == FIXED_ADMIN_EMAIL
        and str(django_user.username or '').strip().lower() == FIXED_ADMIN_USERNAME.lower()
    )
    if is_fixed_admin:
        django_user.is_staff = True
        django_user.is_superuser = True
        django_user.save(update_fields=["is_staff", "is_superuser"])
        if profile and profile.role != "ADMIN":
            profile.role = "ADMIN"
            profile.save(update_fields=["role"])

    if not django_user.is_active or (profile and profile.is_blocked):
        msg = 'Your account is blocked. Contact support.'
        return redirect(url('login', msg=msg))

    django_login(request, django_user)
    _set_session_permanent(request, True)
    _sync_session_from_user(request, django_user, profile=profile)

    if profile and profile.must_change_password:
        return redirect(url('change_password'))

    # always go to /home; that route will dispatch based on role
    return redirect(url('home'))

def login_google(request):
    if google is None:
        return redirect(url('login', msg='Google login is temporarily unavailable. Please use username/password.'))

      
    # This creates the URL for our 'authorize' callback function
    redirect_uri = get_google_redirect_uri(request)
    # This sends the user to Google
    return google.authorize_redirect(request, redirect_uri)
    # return redirect(url('login', msg='Google login is not configured yet. Please login using username and password.'))


def home(request):
    user = _get_authenticated_user(request)
    if not user:
        return redirect(url('login'))
    _sync_session_from_user(request, user)
    if _is_admin_request(request):
        return render_page(request, "admin.html", username=user.username)
    return redirect(url('mobile_home'))


def admin_panel(request):
    if not _is_admin_request(request):
        return redirect(url('login'))
    user = _get_authenticated_user(request)
    return render_page(request, "admin.html", username=user.username if user else None)


def admin_user_view(request):
    if not _is_admin_request(request):
        return redirect(url('login'))
    user = _get_authenticated_user(request)
    return render_page(request, "admin.html", username=user.username if user else None)


def mobile_landing(request):
    return redirect(url('mobile_home'))


def mobile_home(request):
    user = _get_authenticated_user(request)
    profile = _profile_for_request(request) if user else None
    is_logged_in = bool(user)
    is_admin = _is_admin_request(request)
    profile_msg = (_get_query_param(request, 'profile_msg') or '').strip()
    profile_msg_type = (_get_query_param(request, 'profile_msg_type') or '').strip().lower()
    open_profile = (_get_query_param(request, 'open_profile') or '').strip() == '1'

    if is_logged_in:
        username_value = str(user.username or '')
        if len(username_value) <= 2:
            masked_username = username_value[:1] + ('*' if len(username_value) == 2 else '')
        else:
            masked_username = username_value[0] + ('*' * (len(username_value) - 2)) + username_value[-1]
        full_name = user.get_full_name() or user.username
        password_value = (
            profile.password_plain
            if (profile and EXPOSE_PLAIN_PASSWORDS and profile.password_plain)
            else 'Hidden for security'
        )
        profile = {
            'full_name': full_name,
            'name': full_name,
            'username': user.username,
            'email': user.email,
            'phone': profile.phone if profile else '',
            'account_type': profile.role if profile else ('ADMIN' if user.is_staff else 'USER'),
            'password': password_value,
            'masked_username': masked_username
        }

    return render_page(request, 
        'home_mobile.html',
        username=user.username if user else None,
        is_logged_in=is_logged_in,
        is_admin=is_admin,
        profile=profile,
        profile_msg=profile_msg,
        profile_msg_type=profile_msg_type,
        open_profile=open_profile
    )


def mobile_profile_update(request):
    user = _get_authenticated_user(request)
    if not user:
        return redirect(url('login'))

    profile = _get_or_create_profile(user)
    username = (_get_form_param(request, 'username') or '').strip()
    phone = (_get_form_param(request, 'phone') or '').strip()

    if not username:
        return redirect(url(
            'mobile_home',
            open_profile='1',
            profile_msg='Username is required.',
            profile_msg_type='error'
        ))

    existing = (
        get_user_model()
        .objects.filter(username__iexact=username)
        .exclude(id=user.id)
        .exists()
    )
    if existing:
        return redirect(url(
            'mobile_home',
            open_profile='1',
            profile_msg='Username already in use.',
            profile_msg_type='error'
        ))

    try:
        if user.username != username:
            user.username = username
            user.save(update_fields=["username"])
        if profile and profile.phone != phone:
            profile.phone = phone
            profile.save(update_fields=["phone"])
        _sync_session_from_user(request, user, profile=profile)

        return redirect(url(
            'mobile_home',
            open_profile='1',
            profile_msg='Profile updated successfully.',
            profile_msg_type='success'
        ))
    except Exception:
        return redirect(url(
            'mobile_home',
            open_profile='1',
            profile_msg='Unable to update profile right now.',
            profile_msg_type='error'
        ))


def mobile_details(request):
    return render_page(request, 'details_mobile.html', username=request.session.get('username'))


def mobile_alerts(request):
    return render_page(request, 'alerts_mobile.html', username=request.session.get('username'))


def mobile_sos(request):
    return render_page(request, 'sos_mobile.html', username=request.session.get('username'))


def mobile_sos_basic(request):
    return render_page(request, 'sos_basic.html', username=request.session.get('username'))


def _mobile_sos_apk_path():
    return os.path.join(
        APP_ROOT,
        'native-sos-wrapper',
        'android',
        'app',
        'build',
        'outputs',
        'apk',
        'debug',
        'app-debug.apk'
    )


def _mobile_sos_apk_archive_dir():
    return os.path.join(APP_ROOT, 'apk_history')


def _mobile_sos_apk_checksum(apk_path):
    hasher = hashlib.sha256()
    with open(apk_path, 'rb') as apk_file:
        for chunk in iter(lambda: apk_file.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def _mobile_sos_archive_current_apk(apk_path):
    if not os.path.isfile(apk_path):
        return None

    try:
        current_checksum = _mobile_sos_apk_checksum(apk_path)
    except OSError:
        return None

    archive_dir = _mobile_sos_apk_archive_dir()
    try:
        os.makedirs(archive_dir, exist_ok=True)
    except OSError:
        return None

    try:
        for entry in os.listdir(archive_dir):
            if not entry.lower().endswith('.apk'):
                continue
            existing_path = os.path.join(archive_dir, entry)
            if not os.path.isfile(existing_path):
                continue
            try:
                if _mobile_sos_apk_checksum(existing_path) == current_checksum:
                    return current_checksum
            except OSError:
                continue
    except OSError:
        return current_checksum

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_name = f'projectz-sos-{stamp}-{current_checksum[:8]}.apk'
    archive_path = os.path.join(archive_dir, archive_name)
    try:
        shutil.copy2(apk_path, archive_path)
    except OSError:
        return current_checksum

    return current_checksum


def _mobile_sos_list_archived_apks(exclude_checksum=None):
    archive_dir = _mobile_sos_apk_archive_dir()
    if not os.path.isdir(archive_dir):
        return []

    versions = []
    try:
        apk_files = [name for name in os.listdir(archive_dir) if name.lower().endswith('.apk')]
    except OSError:
        return []

    for file_name in apk_files:
        file_path = os.path.join(archive_dir, file_name)
        if not os.path.isfile(file_path):
            continue

        try:
            checksum = _mobile_sos_apk_checksum(file_path)
        except OSError:
            checksum = None

        if exclude_checksum and checksum == exclude_checksum:
            continue

        try:
            size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        except OSError:
            size_mb = None

        try:
            updated_at = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
            updated_sort = os.path.getmtime(file_path)
        except OSError:
            updated_at = None
            updated_sort = 0

        versions.append({
            'file_name': file_name,
            'size_mb': size_mb,
            'updated_at': updated_at,
            'updated_sort': updated_sort,
            'download_url': url('mobile_sos_app_download_version', apk_filename=file_name)
        })

    versions.sort(key=lambda item: item['updated_sort'], reverse=True)
    return versions


def _mobile_sos_external_apk_url():
    value = (os.getenv('SOS_APP_EXTERNAL_APK_URL') or '').strip()
    return value or None


def mobile_sos_app_download_page(request):
    apk_path = _mobile_sos_apk_path()
    external_apk_url = _mobile_sos_external_apk_url()
    apk_exists = os.path.isfile(apk_path)
    latest_apk = None
    history_versions = []
    current_checksum = None
    if external_apk_url:
        apk_exists = True

    if apk_exists:
        if external_apk_url:
            latest_apk = {
                'title': 'Latest APK (External Host)',
                'size_mb': None,
                'updated_at': None,
                'download_url': external_apk_url,
                'source': 'external'
            }
        else:
            try:
                apk_size_mb = round(os.path.getsize(apk_path) / (1024 * 1024), 2)
            except OSError:
                apk_size_mb = None

            try:
                apk_updated_at = datetime.fromtimestamp(os.path.getmtime(apk_path)).strftime('%Y-%m-%d %H:%M')
            except OSError:
                apk_updated_at = None

            current_checksum = _mobile_sos_archive_current_apk(apk_path)
            latest_apk = {
                'title': 'Latest APK',
                'size_mb': apk_size_mb,
                'updated_at': apk_updated_at,
                'download_url': url('mobile_sos_app_download_apk'),
                'source': 'local'
            }

    history_versions = _mobile_sos_list_archived_apks(exclude_checksum=current_checksum)

    return render_page(request, 
        'sos_app_download.html',
        username=request.session.get('username'),
        apk_exists=apk_exists,
        latest_apk=latest_apk,
        history_versions=history_versions,
        external_apk_url=external_apk_url,
        download_url=(external_apk_url or url('mobile_sos_app_download_apk'))
    )


def mobile_sos_app_download_apk(request):
    external_apk_url = _mobile_sos_external_apk_url()
    if external_apk_url:
        return redirect(external_apk_url)

    apk_path = _mobile_sos_apk_path()
    if not os.path.isfile(apk_path):
        raise Http404

    response = file_response(
        apk_path,
        mimetype='application/vnd.android.package-archive',
        as_attachment=True,
        download_name='projectz-sos.apk'
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


def mobile_sos_app_download_version(request, apk_filename):
    safe_name = os.path.basename((apk_filename or '').strip())
    if not safe_name or safe_name != apk_filename or not safe_name.lower().endswith('.apk'):
        raise Http404

    file_path = os.path.join(_mobile_sos_apk_archive_dir(), safe_name)
    if not os.path.isfile(file_path):
        raise Http404

    response = file_response(
        file_path,
        mimetype='application/vnd.android.package-archive',
        as_attachment=True,
        download_name=safe_name
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


def mobile_sos_service_worker(request):
    sw_path = os.path.join(APP_ROOT, 'static', 'mobile-sos-sw.js')
    if not os.path.isfile(sw_path):
        raise Http404

    response = file_response(sw_path, mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/mobile/'
    return response


def mobile_sos_manifest(request):
    manifest_path = os.path.join(APP_ROOT, 'static', 'manifest-mobile-sos.json')
    if not os.path.isfile(manifest_path):
        raise Http404

    response = file_response(manifest_path, mimetype='application/manifest+json')
    response.headers['Cache-Control'] = 'no-cache'
    return response


def _ensure_sos_reporter_user_id():
    UserModel = get_user_model()
    existing = UserModel.objects.filter(username="offline_sos_bot").first()
    if existing:
        _get_or_create_profile(existing)
        return existing.id

    user = UserModel.objects.create(
        username="offline_sos_bot",
        email="offline_sos_bot@local.invalid",
        is_active=True,
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"role": "USER", "is_blocked": False, "must_change_password": False},
    )
    return user.id


def mobile_sos_payload(request):
    payload = _parse_json_body(request) or {}

    disaster_type = str(payload.get('disaster_type') or 'Emergency').strip()[:100] or 'Emergency'
    description = str(payload.get('description') or '').strip()
    address_text = str(payload.get('address_text') or '').strip()
    latitude = payload.get('latitude')
    longitude = payload.get('longitude')

    if latitude is None or longitude is None:
        return json_response({"success": False, "message": "latitude and longitude are required"}, status=400)

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "invalid coordinates"}, status=400)

    reporter = _get_authenticated_user(request)
    reporter_id = reporter.id if reporter else None
    if not reporter_id:
        reporter_id = _ensure_sos_reporter_user_id()
    if not reporter_id:
        return json_response({"success": False, "message": "unable to allocate reporter"}, status=500)

    if not description:
        description = f"SOS request received via mobile app ({'offline-sync' if payload.get('queued_offline') else 'live'})"

    try:
        Disaster.objects.create(
            reporter_id=reporter_id,
            disaster_type=disaster_type,
            description=description,
            address_text=address_text,
            latitude=latitude,
            longitude=longitude,
            media_type=None,
            media=None,
            verify_status=False,
            admin_id=None,
        )
        return json_response({"success": True, "message": "SOS payload accepted"})
    except Exception as err:
        return json_response({"success": False, "message": str(err)}, status=500)


def _analysis_candidate_directories():
    section_dirs = ['DATA&GRAPHS', 'DATA&GRAPHS1', 'module2', 'finalAI']
    configured_roots_raw = str(os.getenv('ANALYSIS_MODULE_ROOTS', '') or '').strip()
    configured_roots = [item.strip() for item in configured_roots_raw.split(',') if item.strip()]

    default_roots = [
        os.path.join(APP_ROOT, 'ANALYSIS_MODULE'),
        '/Users/matrika/Downloads/ANALYSIS_MODULE',  # legacy local path fallback
    ]

    root_candidates = configured_roots + default_roots
    candidate_dirs = []

    for root_dir in root_candidates:
        if not root_dir:
            continue
        candidate_dirs.append(root_dir)
        for section in section_dirs:
            candidate_dirs.append(os.path.join(root_dir, section))

    normalized = []
    seen = set()
    for directory in candidate_dirs:
        real_dir = os.path.realpath(directory)
        if os.path.isdir(real_dir) and real_dir not in seen:
            seen.add(real_dir)
            normalized.append(real_dir)
    return normalized


def _analysis_encode_asset_id(file_path):
    encoded = base64.urlsafe_b64encode(file_path.encode('utf-8')).decode('ascii')
    return encoded.rstrip('=')


def _analysis_decode_asset_id(asset_id):
    try:
        padded = asset_id + ('=' * (-len(asset_id) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8')
        return decoded
    except Exception:
        return None


def _analysis_asset_title(filename):
    name = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
    return ' '.join(word.capitalize() for word in name.split()) or filename


def mobile_analysis_module_one_assets(request):
    now_monotonic = time_module.monotonic()
    with analysis_assets_cache_lock:
        cached_payload = analysis_assets_cache.get("payload")
        cached_age = now_monotonic - float(analysis_assets_cache.get("generated_at_monotonic") or 0.0)
        if isinstance(cached_payload, dict) and cached_age <= ANALYSIS_ASSET_CACHE_TTL_SECONDS:
            return json_response(cached_payload)

    allowed_extensions = {'.html', '.htm', '.png', '.jpg', '.jpeg', '.webp', '.svg'}
    excluded_filenames = {'emergency_priority_dashboard.html'}
    assets = []
    html_count = 0
    image_count = 0

    for directory in _analysis_candidate_directories():
        folder_name = os.path.basename(directory)
        for entry in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, entry)
            if not os.path.isfile(full_path):
                continue

            if entry.strip().lower() in excluded_filenames:
                continue

            extension = os.path.splitext(entry)[1].lower()
            if extension not in allowed_extensions:
                continue

            asset_type = 'iframe' if extension in {'.html', '.htm'} else 'image'
            if asset_type == 'iframe':
                html_count += 1
            else:
                image_count += 1

            asset_id = _analysis_encode_asset_id(os.path.realpath(full_path))
            assets.append({
                'id': asset_id,
                'title': _analysis_asset_title(entry),
                'filename': entry,
                'type': asset_type,
                'folder': folder_name,
                'url': url('mobile_analysis_asset', asset_id=asset_id)
            })

    assets.sort(key=lambda item: (item['type'] != 'iframe', item['title'].lower()))
    message = 'Module One visualizations loaded.' if assets else 'No Module One visualizations found yet.'

    payload = {
        'count': len(assets),
        'html_count': html_count,
        'image_count': image_count,
        'directories': [os.path.basename(path) for path in _analysis_candidate_directories()],
        'assets': assets,
        'message': message
    }

    with analysis_assets_cache_lock:
        analysis_assets_cache["generated_at_monotonic"] = now_monotonic
        analysis_assets_cache["payload"] = payload

    return json_response(payload)


def mobile_analysis_asset(request, asset_id):
    decoded_path = _analysis_decode_asset_id(asset_id)
    if not decoded_path:
        raise Http404

    real_file_path = os.path.realpath(decoded_path)
    allowed_dirs = _analysis_candidate_directories()

    if not os.path.isfile(real_file_path):
        raise Http404

    if not any(os.path.commonpath([real_file_path, allowed_dir]) == allowed_dir for allowed_dir in allowed_dirs):
        raise PermissionDenied

    mime_type, _ = mimetypes.guess_type(real_file_path)
    return file_response(real_file_path, mimetype=mime_type)


def mobile_analysis(request):
    return render_page(request, 'analysis_mobile.html', username=request.session.get('username'))


def mobile_organization(request):
    return render_page(request, 'organization_mobile.html', username=request.session.get('username'))


def mobile_satellite(request):
    return render_page(request, 'satellite_mobile.html', username=request.session.get('username'))


def mobile_admin_panel(request):
    if not _is_admin_request(request):
        return redirect(url('login'))
    return render_page(request, 'admin_mobile.html', username=request.session.get('username'))


def mobile_live_alerts_check(request):
    return render_page(request, 'live_alerts_check.html', username=request.session.get('username'))


def mobile_live_alerts_check_legacy(request):
    return redirect(url('mobile_live_alerts_check'))


def _format_bytes(size_bytes):
    try:
        size = float(size_bytes)
    except (TypeError, ValueError):
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return "0 B"


def _parse_datetime_any(value):
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass

    for fmt in ['%a %b %d %H:%M:%S IST %Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _to_utc_iso(value):
    parsed = _parse_datetime_any(value)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_key_value_env(env_path):
    values = {}
    if not env_path or not os.path.isfile(env_path):
        return values

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return values
    return values


def _resolve_main_sqlite_path():
    if os.path.isabs(DB_PATH):
        return DB_PATH
    return os.path.abspath(os.path.join(APP_ROOT, DB_PATH))


def _resolve_internal_api_sqlite_path():
    workdir = _internal_api_workdir()
    if not workdir:
        return None

    env_path = os.path.join(workdir, ".env")
    env_values = _read_key_value_env(env_path)

    database_url = str(env_values.get("DATABASE_URL", "")).strip()
    if database_url.startswith("sqlite:///"):
        sqlite_path = database_url.replace("sqlite:///", "", 1).strip()
        if sqlite_path:
            if not os.path.isabs(sqlite_path):
                sqlite_path = os.path.abspath(os.path.join(workdir, sqlite_path))
            return sqlite_path

    db_path = str(env_values.get("DB_PATH", "database.db")).strip() or "database.db"
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(os.path.join(workdir, db_path))
    return db_path


def _file_stats(path):
    if not path:
        return {
            "path": None,
            "exists": False,
            "size_bytes": 0,
            "size_human": "0 B",
            "modified_at_utc": None
        }

    exists = os.path.isfile(path)
    size_bytes = os.path.getsize(path) if exists else 0
    modified_at = None
    if exists:
        modified_at = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return {
        "path": path,
        "exists": exists,
        "size_bytes": size_bytes,
        "size_human": _format_bytes(size_bytes),
        "modified_at_utc": modified_at
    }


def _sqlite_table_count(sqlite_path, table_name):
    if not sqlite_path or not os.path.isfile(sqlite_path):
        return None
    try:
        with sqlite3.connect(sqlite_path) as connection:
            cursor_obj = connection.cursor()
            cursor_obj.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cursor_obj.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return None


def _sqlite_first_available_count(sqlite_path, table_names):
    if not sqlite_path or not os.path.isfile(sqlite_path):
        return None
    for table_name in table_names:
        count = _sqlite_table_count(sqlite_path, table_name)
        if count is not None:
            return count
    return 0


def _engine_mode_from_django_engine(engine_text):
    engine = str(engine_text or "").strip().lower()
    if engine.endswith("sqlite3"):
        return "sqlite"
    if engine.endswith("mysql"):
        return "mysql"
    if "djongo" in engine or "mongodb" in engine:
        return "mongodb"
    return "unknown"


def _mask_mongodb_uri(mongo_uri):
    text = str(mongo_uri or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        db_name = str(parsed.path or "").lstrip("/") or "default"
        auth = "****@" if (parsed.username or parsed.password) else ""
        scheme = parsed.scheme or "mongodb"
        return f"{scheme}://{auth}{host}{port}/{db_name}"
    except Exception:
        return "mongodb://****"


def _mongodb_db_name_from_uri(mongo_uri):
    text = str(mongo_uri or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    db_name = str(parsed.path or "").strip("/")
    if not db_name:
        return ""
    return db_name.split("/", 1)[0].strip()


def _find_collection_name(collection_names, candidates):
    lowered = {str(name).lower(): str(name) for name in (collection_names or [])}
    for candidate in candidates:
        name = lowered.get(str(candidate).lower())
        if name:
            return name
    return None


def _mongodb_storage_status(mongo_uri, explicit_db_name, timeout_ms):
    uri = str(mongo_uri or "").strip()
    if not uri:
        return {
            "available": False,
            "error": "MONGODB_URI is missing",
        }
    if not _module_available("pymongo"):
        return {
            "available": False,
            "error": "pymongo is not installed",
        }

    mongo_db_name = str(explicit_db_name or "").strip() or _mongodb_db_name_from_uri(uri) or "resqfy"
    client = None
    try:
        from pymongo import MongoClient

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        database_obj = client[mongo_db_name]
        stats = database_obj.command("dbStats")
        collection_names = database_obj.list_collection_names()

        users_collection = _find_collection_name(collection_names, ["auth_user", "users"])
        profiles_collection = _find_collection_name(collection_names, ["core_userprofile", "userprofile"])
        disasters_collection = _find_collection_name(collection_names, ["Disasters", "core_disaster", "disasters"])
        snapshots_collection = _find_collection_name(collection_names, ["AlertSnapshots", "alertsnapshots"])

        def _count_collection(collection_name):
            if not collection_name:
                return 0
            try:
                return int(database_obj[collection_name].estimated_document_count())
            except Exception:
                return 0

        users_count = _count_collection(users_collection)
        profiles_count = _count_collection(profiles_collection)
        disasters_count = _count_collection(disasters_collection)
        snapshots_count = _count_collection(snapshots_collection)

        data_size = int(stats.get("dataSize") or 0)
        storage_size = int(stats.get("storageSize") or 0)
        index_size = int(stats.get("indexSize") or 0)
        objects_count = int(stats.get("objects") or 0)

        return {
            "available": True,
            "db_name": mongo_db_name,
            "collections_count": int(stats.get("collections") or len(collection_names)),
            "objects_count": objects_count,
            "data_size_bytes": data_size,
            "data_size_human": _format_bytes(data_size),
            "storage_size_bytes": storage_size,
            "storage_size_human": _format_bytes(storage_size),
            "index_size_bytes": index_size,
            "index_size_human": _format_bytes(index_size),
            "rows": {
                "users": users_count,
                "profiles": profiles_count,
                "disasters": disasters_count,
                "snapshots": snapshots_count,
            },
        }
    except Exception as exc:
        return {
            "available": False,
            "db_name": mongo_db_name,
            "error": str(exc),
        }
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _module_available(module_name):
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _mongodb_ping_status(mongo_uri, timeout_ms):
    uri = str(mongo_uri or "").strip()
    if not uri:
        return False, "MONGODB_URI is missing"

    if not _module_available("pymongo"):
        return False, "pymongo is not installed"

    try:
        from pymongo import MongoClient
    except Exception as exc:
        return False, str(exc)

    client = None
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        client.admin.command("ping")
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _database_runtime_status():
    requested_primary = DB_PRIMARY
    django_engine = str(connection.settings_dict.get("ENGINE") or "")
    active_mode = _engine_mode_from_django_engine(django_engine)
    active_name = str(connection.settings_dict.get("NAME") or "")

    mongo_active_uri = str(getattr(settings, "MONGODB_ACTIVE_URI", "") or "").strip()
    mongo_active_source = str(getattr(settings, "MONGODB_ACTIVE_SOURCE", "") or "").strip().lower()
    mongo_active_db_name = str(getattr(settings, "MONGODB_ACTIVE_DB_NAME", "") or "").strip()
    mongo_candidate_uris = getattr(settings, "MONGODB_CANDIDATE_URIS", {}) or {}
    mongo_candidate_errors = getattr(settings, "MONGODB_CANDIDATE_ERRORS", {}) or {}
    mongo_priority_order = getattr(settings, "MONGODB_URI_PRIORITY", []) or []
    mongo_selection_error = str(getattr(settings, "MONGODB_SELECTION_ERROR", "") or "").strip() or None

    mongo_uri = mongo_active_uri or (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
    mongo_backend_pref = (os.getenv("MONGODB_BACKEND") or "auto").strip().lower()
    mongo_db_name = mongo_active_db_name or (os.getenv("MONGODB_DB_NAME") or "").strip()
    timeout_text = (os.getenv("MONGODB_CONNECT_TIMEOUT_MS") or "2500").strip()
    verify_on_startup = _to_bool_env(os.getenv("MONGODB_VERIFY_ON_STARTUP"), True)
    try:
        timeout_ms = max(500, int(timeout_text))
    except Exception:
        timeout_ms = 2500

    mongo_requested = requested_primary == "mongodb"
    mongo_configured = bool(mongo_uri or any(str(value or "").strip() for value in mongo_candidate_uris.values()))
    mongo_host = ""
    if mongo_configured:
        try:
            mongo_host = (urlparse(mongo_uri).hostname or "").strip().lower()
        except Exception:
            mongo_host = ""
    mongo_is_local = mongo_host in {"", "127.0.0.1", "localhost", "::1"}
    if not mongo_active_source:
        if mongo_is_local:
            mongo_active_source = "local"
        elif mongo_uri:
            mongo_active_source = "env"
    mongo_scope = "local" if mongo_is_local else "shared_remote"
    mongo_active = active_mode == "mongodb"
    fallback_active = mongo_requested and not mongo_active
    mongo_connect_ok = None
    mongo_connect_error = None

    django_mongo_backend_available = _module_available("django_mongodb_backend")
    djongo_available = _module_available("djongo")
    shared_candidate_uri = _mongo_uri_for_source("shared")
    shared_candidate_configured = bool(shared_candidate_uri)
    candidate_uri_masked = {
        key: _mask_mongodb_uri(value)
        for key, value in mongo_candidate_uris.items()
        if str(value or "").strip()
    }
    remote_candidate_configured = any(
        key in candidate_uri_masked
        for key in ["shared", "env"]
    )
    bridge_sync_healthy = bool(
        not MONGODB_BRIDGE_SYNC_ENABLED
        or not shared_candidate_configured
        or mongo_active_source == "shared"
        or bool(mongo_bridge_sync_last_success_utc)
    )
    clone_sharing_ready = bool(
        remote_candidate_configured
        or mongo_active_source == "shared"
        or (bool(mongo_uri) and not mongo_is_local)
    )

    fallback_reason = None
    if mongo_requested:
        if not mongo_configured:
            fallback_reason = "MONGODB_URI is missing"
        elif mongo_selection_error and fallback_active:
            fallback_reason = mongo_selection_error
        elif not (django_mongo_backend_available or djongo_available):
            fallback_reason = "No MongoDB Django backend package installed"
        elif verify_on_startup:
            mongo_connect_ok, mongo_connect_error = _mongodb_ping_status(mongo_uri, timeout_ms)
            if not mongo_connect_ok:
                fallback_reason = f"MongoDB ping failed: {mongo_connect_error}"

    if mongo_active and mongo_connect_ok is None and mongo_configured and verify_on_startup:
        mongo_connect_ok, mongo_connect_error = _mongodb_ping_status(mongo_uri, timeout_ms)

    if mongo_requested and mongo_active:
        start_mongodb_sqlite_fallback_sync_worker()
        start_mongodb_bridge_sync_worker()

    mongo_storage = _mongodb_storage_status(mongo_uri, mongo_db_name, timeout_ms)

    fallback_sqlite_path = _mongo_sqlite_fallback_path()
    fallback_rows = {
        "users": _sqlite_table_count(fallback_sqlite_path, "auth_user"),
        "profiles": _sqlite_table_count(fallback_sqlite_path, "core_userprofile"),
        "disasters": _sqlite_first_available_count(fallback_sqlite_path, ["Disasters", "core_disaster"]),
        "snapshots": _sqlite_table_count(fallback_sqlite_path, "AlertSnapshots"),
    }
    fallback_file = _file_stats(fallback_sqlite_path)
    fallback_schema_ready = all(value is not None for value in fallback_rows.values())
    fallback_ready = bool(
        fallback_file.get("exists")
        and fallback_schema_ready
        and MONGODB_SQLITE_FALLBACK_SYNC_ENABLED
        and not mongo_sqlite_sync_last_error
    )
    fallback_not_ready_reason = None
    if not fallback_file.get("exists"):
        fallback_not_ready_reason = "SQLite fallback file is missing."
    elif not fallback_schema_ready:
        fallback_not_ready_reason = "SQLite fallback schema is incomplete."
    elif mongo_sqlite_sync_last_error:
        fallback_not_ready_reason = mongo_sqlite_sync_last_error

    return {
        "requested_primary": requested_primary,
        "active_mode": active_mode,
        "django_engine": django_engine,
        "active_name": active_name,
        "mongodb": {
            "requested": mongo_requested,
            "configured": mongo_configured,
            "uri_masked": _mask_mongodb_uri(mongo_uri),
            "shared_uri_masked": _mask_mongodb_uri(shared_candidate_uri),
            "candidate_uris_masked": candidate_uri_masked,
            "db_name": mongo_db_name or None,
            "backend_preference": mongo_backend_pref,
            "verify_on_startup": verify_on_startup,
            "connect_timeout_ms": timeout_ms,
            "selected_source": mongo_active_source or None,
            "priority_order": list(mongo_priority_order) if isinstance(mongo_priority_order, (list, tuple)) else [],
            "candidate_errors": mongo_candidate_errors,
            "selection_error": mongo_selection_error,
            "active": mongo_active,
            "host": mongo_host or None,
            "scope": mongo_scope if mongo_configured else "not_configured",
            "shared_configured": shared_candidate_configured,
            "shared_ready": clone_sharing_ready,
            "clone_sharing_ready": clone_sharing_ready,
            "bridge_sync_enabled": bool(MONGODB_BRIDGE_SYNC_ENABLED),
            "bridge_sync_healthy": bridge_sync_healthy,
            "fallback_active": fallback_active,
            "fallback_reason": fallback_reason,
            "connect_ok": mongo_connect_ok,
            "connect_error": mongo_connect_error,
            "storage": mongo_storage,
            "backend_packages": {
                "django_mongodb_backend": django_mongo_backend_available,
                "djongo": djongo_available,
            },
        },
        "sqlite_fallback_sync": {
            "enabled": bool(MONGODB_SQLITE_FALLBACK_SYNC_ENABLED and mongo_requested),
            "alias": MONGODB_SQLITE_FALLBACK_ALIAS,
            "interval_seconds": MONGODB_SQLITE_FALLBACK_SYNC_INTERVAL_SECONDS,
            "thread_running": mongo_sqlite_sync_thread_started,
            "last_attempt_utc": mongo_sqlite_sync_last_attempt_utc,
            "last_success_utc": mongo_sqlite_sync_last_success_utc,
            "last_error": mongo_sqlite_sync_last_error,
            "last_warning": mongo_sqlite_sync_last_warning,
            "ready": fallback_ready,
            "ready_reason": fallback_not_ready_reason,
            "last_rows": mongo_sqlite_sync_last_rows,
            "file": fallback_file,
            "rows": fallback_rows,
        },
        "mongo_bridge_sync": {
            "enabled": bool(MONGODB_BRIDGE_SYNC_ENABLED and mongo_requested),
            "scope": MONGODB_BRIDGE_SCOPE,
            "interval_seconds": MONGODB_BRIDGE_SYNC_INTERVAL_SECONDS,
            "thread_running": mongo_bridge_sync_thread_started,
            "last_attempt_utc": mongo_bridge_sync_last_attempt_utc,
            "last_success_utc": mongo_bridge_sync_last_success_utc,
            "last_error": mongo_bridge_sync_last_error,
            "last_warning": mongo_bridge_sync_last_warning,
            "last_rows": mongo_bridge_sync_last_rows,
        },
    }


def _latest_utc_from_values(values):
    latest_dt = None
    for value in values:
        parsed = _parse_datetime_any(value)
        if not parsed:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        if latest_dt is None or parsed > latest_dt:
            latest_dt = parsed
    if latest_dt is None:
        return None
    return latest_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mobile_hill90_diagnostics(request):
    internal_headers = _internal_api_auth_headers()
    internal_base_url = _internal_api_base_url()
    embedded_internal = _internal_api_is_embedded()
    internal_healthy = _internal_api_is_healthy(timeout_seconds=2)
    if not internal_healthy:
        ensure_internal_api_running()
        internal_healthy = _internal_api_is_healthy(timeout_seconds=2)

    source_runs = []
    source_runs_error = None
    latest_alert_item = None
    latest_alert_error = None

    if internal_healthy:
        if embedded_internal:
            try:
                payload = _embedded_internal_sources_payload()
                source_runs = payload.get("items", []) if isinstance(payload, dict) else []
            except Exception as exc:
                source_runs_error = str(exc)

            try:
                payload = _embedded_internal_alerts_payload(limit=1)
                latest_items = payload.get("items", []) if isinstance(payload, dict) else []
                latest_alert_item = latest_items[0] if latest_items else None
            except Exception as exc:
                latest_alert_error = str(exc)
        else:
            try:
                response = requests.get(f"{internal_base_url}/api/sources/status", headers=internal_headers, timeout=8)
                response.raise_for_status()
                payload = response.json() if response.content else {}
                source_runs = payload.get("items", []) if isinstance(payload, dict) else []
            except Exception as exc:
                source_runs_error = str(exc)

            try:
                response = requests.get(_internal_api_alerts_url(), params={"limit": 1}, headers=internal_headers, timeout=8)
                response.raise_for_status()
                payload = response.json() if response.content else {}
                latest_items = payload.get("items", []) if isinstance(payload, dict) else []
                latest_alert_item = latest_items[0] if latest_items else None
            except Exception as exc:
                latest_alert_error = str(exc)
    else:
        source_runs_error = "internal_api_health_down"
        latest_alert_error = "internal_api_health_down"

    source_success_count = len([item for item in source_runs if str(item.get("last_status", "")).upper() == "SUCCESS"])
    source_last_success = _latest_utc_from_values([item.get("last_success_at") for item in source_runs])
    source_last_attempt = _latest_utc_from_values([item.get("last_attempt_at") for item in source_runs])

    if internal_healthy and _internal_api_last_sync_attempt_utc is None:
        try:
            sync_internal_api_if_needed(force=True)
        except Exception:
            pass

    pipeline_last_attempt = _internal_api_last_sync_attempt_utc or source_last_attempt
    pipeline_last_success = _internal_api_last_sync_success_utc or source_last_success

    latest_alert_updated = None
    latest_alert_source = None
    latest_alert_id = None
    if isinstance(latest_alert_item, dict):
        latest_alert_updated = _to_utc_iso(
            latest_alert_item.get("updated_at")
            or latest_alert_item.get("fetched_at")
            or latest_alert_item.get("effective_at")
            or latest_alert_item.get("issued_at")
        )
        latest_alert_payload = latest_alert_item.get("payload") if isinstance(latest_alert_item.get("payload"), dict) else {}
        latest_alert_source = (
            latest_alert_payload.get("alert_source")
            or latest_alert_payload.get("source_name")
            or latest_alert_item.get("source")
            or "N/A"
        )
        latest_alert_id = latest_alert_item.get("external_id") or latest_alert_item.get("id")

    main_sqlite_path = _resolve_main_sqlite_path()
    internal_sqlite_path = _resolve_internal_api_sqlite_path()
    fallback_file_path = _internal_alerts_json_fallback_path()

    main_sqlite = _file_stats(main_sqlite_path)
    internal_sqlite = _file_stats(internal_sqlite_path)
    fallback_file = _file_stats(fallback_file_path)

    main_sqlite["rows"] = {
        "users": _sqlite_table_count(main_sqlite_path, "auth_user"),
        "profiles": _sqlite_table_count(main_sqlite_path, "core_userprofile"),
        "disasters": _sqlite_first_available_count(main_sqlite_path, ["Disasters", "core_disaster"]),
    }
    internal_sqlite["rows"] = {
        "alerts": _sqlite_table_count(internal_sqlite_path, "alerts"),
        "source_runs": _sqlite_table_count(internal_sqlite_path, "source_runs"),
    }

    total_sqlite_bytes = int(main_sqlite.get("size_bytes", 0)) + int(internal_sqlite.get("size_bytes", 0))

    fallback_generated_at = None
    fallback_alerts_count = 0
    if fallback_file.get("exists"):
        try:
            with open(fallback_file_path, "r", encoding="utf-8") as fallback_handle:
                fallback_payload = json.load(fallback_handle)
            fallback_generated_at = _to_utc_iso((fallback_payload.get("metadata") or {}).get("generated_at_utc"))
            fallback_raw = fallback_payload.get("raw") if isinstance(fallback_payload.get("raw"), dict) else {}
            fallback_alerts = fallback_raw.get("alerts") if isinstance(fallback_raw.get("alerts"), list) else []
            fallback_alerts_count = len(fallback_alerts)
        except Exception:
            fallback_generated_at = None
            fallback_alerts_count = 0

    mongo_snapshot_payload = load_live_alerts_snapshot("india", "official")
    mongo_snapshot_alerts = (
        mongo_snapshot_payload.get("alerts")
        if isinstance(mongo_snapshot_payload, dict) and isinstance(mongo_snapshot_payload.get("alerts"), list)
        else []
    )
    mongo_snapshot_count = len(mongo_snapshot_alerts)
    mongo_snapshot_saved_at = None
    mongo_snapshot_age_seconds = None
    if isinstance(mongo_snapshot_payload, dict):
        mongo_snapshot_saved_at = (
            mongo_snapshot_payload.get("snapshot_saved_at_utc")
            or mongo_snapshot_payload.get("saved_at_utc")
            or mongo_snapshot_payload.get("generated_at")
        )
        mongo_snapshot_age_seconds = mongo_snapshot_payload.get("snapshot_age_seconds")

    mongo_primary_ready = mongo_snapshot_count > 0
    sqlite_fallback_ready = bool(
        internal_sqlite.get("exists")
        and isinstance(internal_sqlite["rows"].get("alerts"), int)
        and int(internal_sqlite["rows"].get("alerts")) > 0
    )
    json_fallback_ready = bool(fallback_file.get("exists") and fallback_alerts_count > 0)

    generated_hint_utc = latest_alert_updated or source_last_success or mongo_snapshot_saved_at or fallback_generated_at
    if mongo_primary_ready:
        recommended_mode = "mongo_primary"
    elif sqlite_fallback_ready:
        recommended_mode = "sqlite_fallback"
    elif json_fallback_ready:
        recommended_mode = "file_fallback"
    else:
        recommended_mode = "degraded"

    database_status = _database_runtime_status()
    mongo_storage = ((database_status.get("mongodb") or {}).get("storage") or {})
    sqlite_fallback_sync = database_status.get("sqlite_fallback_sync") or {}
    main_db_mode = str(database_status.get("active_mode") or "unknown").lower()
    main_db_rows = {
        "users": main_sqlite["rows"].get("users"),
        "profiles": main_sqlite["rows"].get("profiles"),
        "disasters": main_sqlite["rows"].get("disasters"),
    }
    if main_db_mode == "mongodb":
        mongo_rows = mongo_storage.get("rows") if isinstance(mongo_storage, dict) else {}
        main_db_rows = {
            "users": (mongo_rows or {}).get("users"),
            "profiles": (mongo_rows or {}).get("profiles"),
            "disasters": (mongo_rows or {}).get("disasters"),
        }

    return json_response({
        "success": True,
        "server_time_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pipeline": {
            "internal_api_healthy": internal_healthy,
            "recommended_mode": recommended_mode,
            "priority_chain": "local_mongodb -> internal_sqlite -> file_fallback -> degraded",
            "last_sync_attempt_utc": pipeline_last_attempt,
            "last_sync_success_utc": pipeline_last_success,
            "sync_interval_seconds": INTERNAL_API_SYNC_MIN_INTERVAL_SECONDS,
        },
        "updates": {
            "source_last_success_utc": source_last_success,
            "source_last_attempt_utc": source_last_attempt,
            "latest_alert_updated_utc": latest_alert_updated,
            "latest_alert_source": latest_alert_source,
            "latest_alert_id": latest_alert_id,
            "generated_hint_utc": generated_hint_utc,
        },
        "sources": {
            "count": len(source_runs),
            "healthy_count": source_success_count,
            "failing_count": max(0, len(source_runs) - source_success_count),
            "items": source_runs,
            "status_error": source_runs_error,
            "latest_alert_error": latest_alert_error,
        },
        "storage": {
            "main_db_mode": main_db_mode,
            "main_db_rows": main_db_rows,
            "main_mongodb": mongo_storage,
            "main_sqlite": main_sqlite,
            "internal_sqlite": internal_sqlite,
            "sqlite_fallback_sync": sqlite_fallback_sync,
            "fallback_file": fallback_file,
            "internal_mongo_snapshot": {
                "ready": mongo_primary_ready,
                "count": mongo_snapshot_count,
                "saved_at_utc": mongo_snapshot_saved_at,
                "age_seconds": mongo_snapshot_age_seconds,
            },
            "internal_json_fallback": {
                "ready": json_fallback_ready,
                "alerts_count": fallback_alerts_count,
                "generated_at_utc": fallback_generated_at,
            },
            "internal_failover_ready": {
                "mongo_primary": mongo_primary_ready,
                "sqlite_fallback": sqlite_fallback_ready,
                "file_fallback": json_fallback_ready,
            },
            "cap_feed": _cap_feed_storage_status(),
            "total_sqlite_bytes": total_sqlite_bytes,
            "total_sqlite_human": _format_bytes(total_sqlite_bytes),
        },
        "internal_api": {
            "base_url": internal_base_url,
            "alerts_url": _internal_api_alerts_url(),
            "health_url": _internal_api_health_url(),
            "priority_chain": "local_mongodb -> internal_sqlite -> file_fallback -> degraded",
            "ready": {
                "mongo_primary": mongo_primary_ready,
                "sqlite_fallback": sqlite_fallback_ready,
                "file_fallback": json_fallback_ready,
            },
        },
        "database": database_status,
    })


def mobile_hill90_force_sync(request):
    global _internal_api_last_sync_attempt_utc, _internal_api_last_sync_success_utc, _internal_api_last_sync_monotonic

    embedded_internal = _internal_api_is_embedded()
    ensure_internal_api_running()
    if not _internal_api_is_healthy(timeout_seconds=3):
        return json_response({
            "success": False,
            "message": "Internal API is not healthy"
        }, status=502)

    attempted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _internal_api_last_sync_attempt_utc = attempted_at

    if embedded_internal:
        try:
            sync_payload = _embedded_internal_sync_payload()
            _internal_api_last_sync_success_utc = attempted_at
            _internal_api_last_sync_monotonic = time_module.monotonic()
            return json_response({
                "success": True,
                "attempted_at_utc": attempted_at,
                "sync_response": sync_payload
            }, status=200)
        except Exception as exc:
            return json_response({
                "success": False,
                "attempted_at_utc": attempted_at,
                "message": str(exc)
            }, status=502)

    try:
        response = requests.post(_internal_api_sync_url(), headers=_internal_api_auth_headers(), timeout=25)
        payload = response.json() if response.content else {}
        if response.status_code < 400:
            _internal_api_last_sync_success_utc = attempted_at
            _internal_api_last_sync_monotonic = time_module.monotonic()
            return json_response({
                "success": True,
                "attempted_at_utc": attempted_at,
                "sync_response": payload
            }, status=200)

        return json_response({
            "success": False,
            "attempted_at_utc": attempted_at,
            "message": f"Sync endpoint returned HTTP {response.status_code}",
            "sync_response": payload
        }, status=502)
    except Exception as exc:
        return json_response({
            "success": False,
            "attempted_at_utc": attempted_at,
            "message": str(exc)
        }, status=502)


def mobile_live_alerts(request):
    state_filter = (_get_query_param(request, 'state') or '').strip().lower()
    section = (_get_query_param(request, 'section') or 'live').strip().lower()
    if section not in ['live', 'history']:
        section = 'live'
    coverage_param = _get_query_param(request, 'coverage')
    coverage_filter = (coverage_param or '').strip().lower()
    if coverage_filter:
        if coverage_filter not in ['all', 'india', 'international']:
            coverage_filter = 'all'
    else:
        if state_filter in ['international', 'global', 'outside india']:
            coverage_filter = 'international'
        elif state_filter in ['', 'india', 'all']:
            coverage_filter = 'india'
        else:
            coverage_filter = 'all'

    state_query = state_filter
    if state_query in ['', 'india', 'all', 'international', 'global', 'outside india']:
        state_query = ''

    severity_filter = (_get_query_param(request, 'severity') or '').strip().lower()
    type_filter = (_get_query_param(request, 'disaster_type') or '').strip().lower()
    date_filter = (_get_query_param(request, 'date') or '').strip()
    date_from_filter = (_get_query_param(request, 'date_from') or '').strip()
    date_to_filter = (_get_query_param(request, 'date_to') or '').strip()
    if date_filter:
        if not date_from_filter:
            date_from_filter = date_filter
        if not date_to_filter:
            date_to_filter = date_filter
    language_param = (_get_query_param(request, 'lang') or '').strip().lower()
    language_pref = 'en' if language_param in ['en', 'english'] else 'original'
    scope = (_get_query_param(request, 'scope') or 'official').strip().lower()
    if scope not in ['official', 'expanded']:
        scope = 'official'
    source_policy = (_get_query_param(request, 'source_policy') or os.getenv('MOBILE_ALERTS_SOURCE_POLICY', 'auto_fallback')).strip().lower()
    if source_policy not in ['live_only', 'auto_fallback']:
        source_policy = 'auto_fallback'
    max_items = _get_query_param(request, 'limit', default=200, type=int)
    max_items = max(10, min(max_items, 2000))
    active_only_raw = _get_query_param(request, "active_only")
    if active_only_raw is None:
        active_only = False if section == 'history' else True
    else:
        active_only = str(active_only_raw).strip().lower() not in ["0", "false", "no", "off"]
    active_recent_hours = max(
        1,
        int((os.getenv("MOBILE_ALERTS_ACTIVE_RECENT_HOURS") or "6").strip() or "6"),
    )

    def parse_date_filter_value(value):
        text = str(value or '').strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, '%Y-%m-%d').date()
        except ValueError:
            return None

    parsed_date_from = parse_date_filter_value(date_from_filter)
    parsed_date_to = parse_date_filter_value(date_to_filter)
    if parsed_date_from and parsed_date_to and parsed_date_from > parsed_date_to:
        parsed_date_from, parsed_date_to = parsed_date_to, parsed_date_from

    def category_from_text(disaster_type_value, warning_message_value):
        type_text = str(disaster_type_value or "").strip()
        warning_text = str(warning_message_value or "").strip()

        warning_category = classify_alert_category_with_translation(warning_text)
        if warning_category != "Other":
            return warning_category

        type_category = classify_alert_category_with_translation(type_text)
        if type_category != "Other":
            return type_category

        blob = f"{type_text} {warning_text}".strip()
        return classify_alert_category_with_translation(blob)

    def parse_alert_date(value):
        if not value:
            return None
        as_text = str(value).strip()
        if not as_text:
            return None

        try:
            return datetime.fromisoformat(as_text.replace('Z', '+00:00')).date()
        except ValueError:
            pass

        for fmt in ['%a %b %d %H:%M:%S IST %Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
            try:
                return datetime.strptime(as_text, fmt).date()
            except ValueError:
                continue
        return None

    def parse_alert_datetime(value):
        if not value:
            return None
        as_text = str(value).strip()
        if not as_text:
            return None

        iso_value = _to_utc_iso(as_text)
        parsed = _parse_utc_iso(iso_value) if iso_value else None
        if parsed:
            return parsed

        for fmt in ['%a %b %d %H:%M:%S IST %Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
            try:
                dt = datetime.strptime(as_text, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def dedupe_text(value):
        return _normalize_alert_text_for_matching(value)

    def alert_time_rank(value):
        iso_value = _to_utc_iso(value)
        parsed = _parse_utc_iso(iso_value) if iso_value else None
        if parsed is None:
            return 0
        return int(parsed.timestamp())

    def alert_day_bucket(value):
        parsed = parse_alert_date(value)
        if parsed is None:
            return ""
        return parsed.isoformat()

    translation_cache = {}
    category_cache = {}
    auto_translate_enabled = str(os.getenv("ALERTS_EN_AUTO_TRANSLATE", "true") or "").strip().lower() in [
        "1",
        "true",
        "yes",
        "on",
    ]

    def is_likely_english_text(value):
        return _is_likely_english_text(value)

    def translate_text_to_english(value):
        text = str(value or "").strip()
        if not text:
            return ""
        if is_likely_english_text(text):
            return text
        if not auto_translate_enabled:
            return ""

        cached = translation_cache.get(text)
        if cached is not None:
            return cached

        translated = _translate_text_to_english_online(
            text,
            timeout_seconds=6.0,
            retries=2,
        )

        translation_cache[text] = translated
        return translated

    def extract_alert_category_tags_basic(text_value):
        blob = str(text_value or "").strip().lower()
        if not blob:
            return ['Other']

        def has_whole_word(keyword):
            token = str(keyword or "").strip().lower()
            if not token:
                return False
            pattern = rf"(?<![\w\u0900-\u097f]){re.escape(token)}(?![\w\u0900-\u097f])"
            return re.search(pattern, blob) is not None

        tags = []
        def add_tag(name):
            if name not in tags:
                tags.append(name)

        if any(k in blob for k in ['cyclone', 'cyclonic', 'hurricane', 'storm surge', 'typhoon', 'चक्रवात', 'चक्रीवादळ', 'ଘୁର୍ଣ୍ଣିଝଡ଼', 'ಚಂಡಮಾರುತ']):
            add_tag('Cyclone')
        if any(k in blob for k in ['landslide', 'mudslide', 'rockfall', 'भूस्खलन', 'दरड', 'ಭೂಕುಸಿತ', 'ଭୂସ୍ଖଳନ']):
            add_tag('Landslide')
        if any(k in blob for k in ['avalanche', 'snow avalanche', 'snow slide', 'ice slide', 'हिमस्खलन', 'ಹಿಮಪಾತ']):
            add_tag('Avalanche')
        if any(k in blob for k in ['heat wave', 'heatwave', 'extreme heat', 'high temperature', 'उष्णलहर', 'लू', 'ಬಿಸಿಗಾಳಿ', 'ତାପ ତରଙ୍ଗ']):
            add_tag('Heat Wave')
        if any(k in blob for k in ['lightning', 'lighting', 'thunderbolt', 'विज', 'बिजली', 'पिडुग', 'మెరుపు', 'ಮಿಂಚು', 'ಪಿಡುಗು', 'ବଜ୍ରପାତ']):
            add_tag('Lightning')
        if any(k in blob for k in ['thunderstorm', 'thunderstrom', 'thunder', 'मेघगर्ज', 'storm', 'ఉరుము', 'ಗುಡುಗು', 'ಗಾಳಿಯೊಂದಿಗೆ']):
            add_tag('Thunderstorm')
        if (
            any(k in blob for k in ['flood', 'inundation', 'waterlogging', 'dam release', 'flash flood', 'badh', 'बाढ़', 'बाढ़', 'ನೆರೆ', 'ବନ୍ୟା'])
            or has_whole_word('पूर')
        ):
            add_tag('Flood')
        if any(k in blob for k in ['rain', 'rainfall', 'downpour', 'cloudburst', 'अतिवृष्ट', 'पाऊस', 'बारिश', 'వర్ష', 'ಮಳೆ', 'ବର୍ଷା']):
            add_tag('Rain')
        if any(k in blob for k in ['earthquake', 'seismic', 'aftershock', 'tremor', 'भूकंप', 'ಭೂಕಂಪ', 'ଭୂମିକମ୍ପ']):
            add_tag('Earthquake')
        if any(k in blob for k in ['fire', 'wildfire', 'forest fire', 'blaze', 'आग', 'ಬೆಂಕಿ', 'ଅଗ୍ନି']):
            add_tag('Fire')

        if not tags:
            return ['Other']
        return tags

    def classify_alert_category_basic(text_value):
        tags = extract_alert_category_tags_basic(text_value)
        priority_order = [
            'Cyclone',
            'Landslide',
            'Avalanche',
            'Heat Wave',
            'Lightning',
            'Thunderstorm',
            'Flood',
            'Rain',
            'Earthquake',
            'Fire',
        ]
        for name in priority_order:
            if name in tags:
                return name
        return 'Other'

    def classify_alert_category_with_translation(text_value):
        raw_text = str(text_value or "").strip()
        if not raw_text:
            return 'Other'

        cached = category_cache.get(raw_text)
        if cached:
            return cached

        category = classify_alert_category_basic(raw_text)
        if category == 'Other' and not is_likely_english_text(raw_text):
            translated = translate_text_to_english(raw_text)
            if translated:
                category = classify_alert_category_basic(translated)

        category_cache[raw_text] = category
        return category

    def category_tags_from_text(disaster_type_value, warning_message_value):
        raw_text = f"{disaster_type_value or ''} {warning_message_value or ''}".strip()
        tags = extract_alert_category_tags_basic(raw_text)
        if tags == ['Other'] and not is_likely_english_text(raw_text):
            translated = translate_text_to_english(raw_text)
            if translated:
                tags = extract_alert_category_tags_basic(translated)
        return tags

    def normalize_alert_area(value):
        area_text = str(value or '').strip()
        return area_text if area_text else 'Area not specified'

    def normalize_alert_severity(
        raw_severity,
        raw_color=None,
        urgency_value=None,
        certainty_value=None,
        disaster_type_value=None,
        warning_message_value=None,
        category_value=None,
    ):
        mapped = _normalize_embedded_severity(
            raw_severity,
            urgency=urgency_value,
            certainty=certainty_value,
            disaster_type=disaster_type_value,
            warning_message=warning_message_value,
        )

        color_value = str(raw_color or '').strip().lower()
        if color_value in ['amber']:
            color_value = 'orange'
        elif color_value in ['critical', 'danger']:
            color_value = 'red'
        elif color_value in ['advisory', 'minor', 'info', 'information']:
            color_value = 'yellow'

        severity_raw_text = str(raw_severity or "").strip().upper()
        urgency_text = str(urgency_value or "").strip().upper()
        certainty_text = str(certainty_value or "").strip().upper()
        severity_blob = _normalize_alert_text_for_matching(
            f"{disaster_type_value or ''} {warning_message_value or ''} {severity_raw_text} {urgency_text} {certainty_text}"
        )

        has_critical_phrase = any(
            token in severity_blob
            for token in [
                "red alert",
                "extreme danger",
                "very severe",
                "take shelter immediately",
                "evacuate",
                "life threatening",
                "imminent",
                "flash flood emergency",
                "tsunami warning",
            ]
        )

        # Some upstream feeds send ALERT by default for Expected/Likely advisories.
        # Downshift these to avoid painting every card as red unless we have explicit critical cues.
        if (
            mapped == 'ALERT'
            and severity_raw_text == 'ALERT'
            and urgency_text == 'EXPECTED'
            and certainty_text == 'LIKELY'
            and not has_critical_phrase
        ):
            mapped = 'WARNING'

        if (
            mapped in ['ALERT', 'WARNING']
            and not has_critical_phrase
            and any(
                token in severity_blob
                for token in [
                    "low danger level",
                    "low danger",
                    "advisory",
                    "monitor closely",
                    "no immediate threat",
                ]
            )
        ):
            mapped = 'WATCH'

        default_color = 'yellow'
        if mapped == 'WARNING':
            default_color = 'orange'
        elif mapped == 'ALERT':
            default_color = 'red'

        if mapped != 'ALERT' and color_value == 'red' and not has_critical_phrase:
            color_value = default_color

        if color_value not in ['red', 'orange', 'yellow', 'green']:
            color_value = default_color
        return mapped, color_value

    india_area_tokens = [
        'india',
        'andaman and nicobar',
        'andhra pradesh',
        'arunachal pradesh',
        'assam',
        'bihar',
        'chandigarh',
        'chhattisgarh',
        'dadra and nagar haveli',
        'daman and diu',
        'goa',
        'gujarat',
        'haryana',
        'himachal pradesh',
        'jammu and kashmir',
        'jharkhand',
        'karnataka',
        'kerala',
        'ladakh',
        'lakshadweep',
        'madhya pradesh',
        'maharashtra',
        'manipur',
        'meghalaya',
        'mizoram',
        'nagaland',
        'odisha',
        'orissa',
        'punjab',
        'rajasthan',
        'sikkim',
        'tamil nadu',
        'telangana',
        'tripura',
        'uttar pradesh',
        'uttarakhand',
        'west bengal',
        'delhi',
        'new delhi',
        'puducherry',
        'pondicherry',
    ]
    international_area_tokens = [
        'afghanistan',
        'bangladesh',
        'bhutan',
        'china',
        'indonesia',
        'iran',
        'maldives',
        'myanmar',
        'nepal',
        'pakistan',
        'sri lanka',
        'tajikistan',
        'thailand',
        'tibet',
        'uzbekistan',
    ]

    def classify_alert_coverage(area_description, lat_value, lon_value):
        if isinstance(lat_value, (int, float)) and isinstance(lon_value, (int, float)):
            in_india_box = 6.0 <= float(lat_value) <= 38.5 and 68.0 <= float(lon_value) <= 98.8
            return 'india' if in_india_box else 'international'

        area_text = str(area_description or '').strip().lower()
        if area_text:
            if any(token in area_text for token in india_area_tokens):
                return 'india'
            if any(token in area_text for token in international_area_tokens):
                return 'international'

        return 'unknown'

    def passes_coverage_filter(area_description, lat_value, lon_value):
        if coverage_filter == 'all':
            return True
        coverage = classify_alert_coverage(area_description, lat_value, lon_value)
        if coverage_filter == 'international':
            return coverage == 'international'
        # For India mode, include unknown coverage rather than dropping potentially local alerts
        return coverage in ['india', 'unknown']

    def extract_lat_lon_from_centroid(centroid_value):
        if centroid_value is None:
            return None, None

        if isinstance(centroid_value, (list, tuple)) and len(centroid_value) >= 2:
            try:
                return float(centroid_value[1]), float(centroid_value[0])
            except (TypeError, ValueError):
                return None, None

        centroid_text = str(centroid_value).strip()
        if ',' not in centroid_text:
            return None, None
        parts = centroid_text.split(',')
        if len(parts) != 2:
            return None, None
        try:
            return float(parts[1].strip()), float(parts[0].strip())
        except (TypeError, ValueError):
            return None, None

    def fetch_direct_sachet_cap_alerts(max_records=3000):
        root = _load_cap_feed_root()

        cap_alerts = []
        for alert_node in root.findall('.//{*}alert'):
            identifier = (alert_node.findtext('./{*}identifier') or '').strip()
            source = (alert_node.findtext('./{*}senderName') or alert_node.findtext('./{*}sender') or 'NDMA SACHET').strip()

            info = alert_node.find('./{*}info')
            if info is None:
                continue

            event = (info.findtext('./{*}event') or 'Alert').strip()
            urgency = (info.findtext('./{*}urgency') or '').strip()
            certainty = (info.findtext('./{*}certainty') or '').strip()
            start_time = (info.findtext('./{*}onset') or info.findtext('./{*}effective') or info.findtext('./{*}sent') or '').strip()
            end_time = (info.findtext('./{*}expires') or '').strip()
            warning_message = (info.findtext('./{*}description') or info.findtext('./{*}headline') or '').strip()
            severity = _normalize_embedded_severity(
                info.findtext('./{*}severity'),
                urgency=urgency,
                certainty=certainty,
                disaster_type=event,
                warning_message=warning_message,
            )

            area_descriptions = []
            centroid = ''

            for area_node in info.findall('./{*}area'):
                area_desc = (area_node.findtext('./{*}areaDesc') or '').strip()
                if area_desc:
                    area_descriptions.append(area_desc)

                circle = (area_node.findtext('./{*}circle') or '').strip()
                if not centroid and circle:
                    first = circle.split()[0]
                    if ',' in first:
                        circle_parts = first.split(',')
                        if len(circle_parts) >= 2:
                            try:
                                lat_value = float(circle_parts[0].strip())
                                lon_value = float(circle_parts[1].strip())
                                centroid = f"{lon_value},{lat_value}"
                            except (TypeError, ValueError):
                                centroid = ''

                polygon = (area_node.findtext('./{*}polygon') or '').strip()
                if not centroid and polygon:
                    first_pair = polygon.split()[0]
                    if ',' in first_pair:
                        poly_parts = first_pair.split(',')
                        if len(poly_parts) >= 2:
                            try:
                                lat_value = float(poly_parts[0].strip())
                                lon_value = float(poly_parts[1].strip())
                                centroid = f"{lon_value},{lat_value}"
                            except (TypeError, ValueError):
                                centroid = ''

            area_description = ', '.join(area_descriptions).strip()

            cap_alerts.append({
                'identifier': identifier,
                'disaster_type': event,
                'severity': severity,
                'urgency': urgency,
                'certainty': certainty,
                'area_description': area_description,
                'warning_message': warning_message,
                'effective_start_time': start_time,
                'effective_end_time': end_time,
                'alert_source': source,
                'centroid': centroid,
            })

            if len(cap_alerts) >= max_records:
                break

        return cap_alerts

    def append_formatted_entry(
        target,
        *,
        alert_id,
        disaster_type,
        disaster_type_en=None,
        severity_value,
        urgency_value=None,
        certainty_value=None,
        severity_color_value,
        area_description,
        warning_message,
        warning_message_en=None,
        source_value,
        source_section,
        start_time_value,
        end_time_value,
        lat,
        lon,
        language_view=True,
    ):
        area_text = normalize_alert_area(area_description)
        disaster_text_raw = str(disaster_type or 'Alert').strip() or 'Alert'
        warning_text_raw = str(warning_message or '').strip()
        disaster_text_en = str(disaster_type_en or '').strip()
        warning_text_en = str(warning_message_en or '').strip()

        if language_view and language_pref == 'en':
            if not disaster_text_en:
                disaster_text_en = translate_text_to_english(disaster_text_raw)
            if not warning_text_en:
                warning_text_en = translate_text_to_english(warning_text_raw)
            disaster_text = disaster_text_en or disaster_text_raw
            warning_text = warning_text_en or warning_text_raw
        else:
            disaster_text = disaster_text_raw
            warning_text = warning_text_raw

        category_tags = category_tags_from_text(
            f"{disaster_text_raw} {disaster_text_en}",
            f"{warning_text_raw} {warning_text_en}",
        )
        normalized_category_tags = []
        for tag in category_tags:
            tag_text = str(tag or "").strip()
            if tag_text and tag_text not in normalized_category_tags:
                normalized_category_tags.append(tag_text)
        if not normalized_category_tags:
            normalized_category_tags = ["Other"]

        derived_category = category_from_text(
            f"{disaster_text_raw} {disaster_text_en}",
            f"{warning_text_raw} {warning_text_en}",
        )
        if derived_category not in normalized_category_tags:
            normalized_category_tags.insert(0, derived_category)

        severity_text, severity_color_text = normalize_alert_severity(
            severity_value,
            severity_color_value,
            urgency_value=urgency_value,
            certainty_value=certainty_value,
            disaster_type_value=disaster_text_raw,
            warning_message_value=warning_text_raw,
            category_value=derived_category,
        )

        # Keep the response aligned with "live active" semantics rather than full feed history.
        now_utc_dt = datetime.now(timezone.utc)
        start_dt = parse_alert_datetime(start_time_value)
        end_dt = parse_alert_datetime(end_time_value)
        if active_only:
            if end_dt is not None and end_dt <= now_utc_dt:
                return False

        if not passes_coverage_filter(area_text, lat, lon):
            return False
        if state_query:
            state_search_blob = " ".join([
                str(area_text or ""),
                str(source_value or ""),
                str(disaster_text_raw or ""),
                str(disaster_text_en or ""),
                str(warning_text_raw or ""),
                str(warning_text_en or ""),
            ]).lower()
            if state_query not in state_search_blob:
                return False
        if severity_filter and severity_filter != 'all' and severity_filter != severity_text.lower():
            return False
        if type_filter and type_filter != 'all':
            normalized = type_filter.lower()
            if normalized == 'cyclonic':
                normalized = 'cyclone'
            if normalized == 'heatwave':
                normalized = 'heat wave'
            searchable = f"{disaster_text_raw} {warning_text_raw} {disaster_text_en} {warning_text_en}".lower()
            category_keys = {
                str(tag or "").strip().lower()
                for tag in normalized_category_tags
                if str(tag or "").strip()
            }
            if 'cyclonic' in category_keys:
                category_keys.add('cyclone')
            if 'heatwave' in category_keys:
                category_keys.add('heat wave')
            if normalized in ['cyclonic', 'cyclone', 'landslide', 'avalanche', 'flood', 'rain', 'lightning', 'thunderstorm', 'fire', 'earthquake', 'heat wave', 'other']:
                if normalized not in category_keys:
                    return False
            elif normalized not in searchable:
                return False
        if parsed_date_from is not None or parsed_date_to is not None:
            start_date = parse_alert_date(start_time_value)
            if start_date is None:
                return False
            if parsed_date_from is not None and start_date < parsed_date_from:
                return False
            if parsed_date_to is not None and start_date > parsed_date_to:
                return False

        target_key = id(target)
        dedupe_state = dedupe_by_target.setdefault(
            target_key,
            {"ids": set(), "signatures": set(), "canonical_positions": {}},
        )

        alert_id_key = str(alert_id or "").strip().lower()
        if alert_id_key and alert_id_key not in ["none", "null", "n/a", "na"]:
            if alert_id_key in dedupe_state["ids"]:
                return False

        signature_parts = [
            str(disaster_text_raw or "").strip().lower(),
            str(warning_text_raw or "").strip().lower(),
            str(area_text or "").strip().lower(),
            str(start_time_value or "").strip().lower(),
            str(end_time_value or "").strip().lower(),
            str(source_value or "").strip().lower(),
        ]
        signature_key = "|".join(signature_parts)
        if signature_key in dedupe_state["signatures"]:
            return False

        canonical_parts = [
            dedupe_text(derived_category),
            dedupe_text(disaster_text_raw),
            dedupe_text(warning_text_raw),
            dedupe_text(area_text),
            dedupe_text(source_value),
            alert_day_bucket(start_time_value),
        ]
        canonical_key = "|".join(canonical_parts)

        entry_payload = {
            'id': alert_id,
            'type': disaster_text,
            'type_original': disaster_text_raw,
            'type_en': disaster_text_en or None,
            'category': derived_category,
            'category_tags': normalized_category_tags,
            'severity': severity_text,
            'severity_color': severity_color_text,
            'urgency': str(urgency_value or '').strip() or None,
            'certainty': str(certainty_value or '').strip() or None,
            'area': area_text,
            'message': warning_text,
            'message_original': warning_text_raw,
            'message_en': warning_text_en or None,
            'source': str(source_value or 'Unknown source'),
            'source_section': str(source_section or 'unknown'),
            'start_time': start_time_value,
            'end_time': end_time_value,
            'lat': lat,
            'lon': lon,
            'location_available': isinstance(lat, (int, float)) and isinstance(lon, (int, float)),
        }

        existing_index = dedupe_state["canonical_positions"].get(canonical_key)
        if isinstance(existing_index, int) and 0 <= existing_index < len(target):
            existing_item = target[existing_index]
            existing_rank = alert_time_rank(existing_item.get('start_time'))
            incoming_rank = alert_time_rank(start_time_value)
            if incoming_rank <= existing_rank:
                return False
            target[existing_index] = entry_payload
            if alert_id_key and alert_id_key not in ["none", "null", "n/a", "na"]:
                dedupe_state["ids"].add(alert_id_key)
            dedupe_state["signatures"].add(signature_key)
            return True

        if alert_id_key and alert_id_key not in ["none", "null", "n/a", "na"]:
            dedupe_state["ids"].add(alert_id_key)
        dedupe_state["signatures"].add(signature_key)
        target.append(entry_payload)
        dedupe_state["canonical_positions"][canonical_key] = len(target) - 1
        return True

    formatted = []
    dedupe_by_target = {}
    generated_at = None
    source_mode = 'degraded'
    internal_error = None

    internal_api_url = os.getenv('INTERNAL_ALERTS_API_URL', 'http://127.0.0.1:2000/api/internal/alerts').strip()
    internal_api_key = os.getenv('INTERNAL_ALERTS_API_KEY', '').strip()
    internal_api_key_header = os.getenv('INTERNAL_ALERTS_API_KEY_HEADER', 'X-Internal-API-Key').strip() or 'X-Internal-API-Key'
    embedded_internal = _internal_api_is_embedded()
    internal_limit = min(5000, max(500, max_items * 4))

    live_sync_status = {
        'internal_fetch_ok': False,
        'internal_items': 0,
        'mongo_snapshot_saved': False,
        'sqlite_synced': False,
        'sqlite_sync_rows': 0,
        'sqlite_sync_error': None,
        'json_saved': False,
    }

    if section == 'history':
        history_items = _load_archived_internal_alert_items(
            limit=internal_limit,
            area_query=state_query,
            severity_query=severity_filter.upper() if (severity_filter and severity_filter != 'all') else "",
            language_preference=language_pref,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
        )
        history_formatted = []
        for item in history_items:
            if not isinstance(item, dict):
                continue
            payload_item = item.get('payload') if isinstance(item.get('payload'), dict) else {}
            lat, lon = extract_lat_lon_from_centroid(payload_item.get('centroid'))
            if lat is None or lon is None:
                try:
                    lat = float(payload_item.get('lat')) if payload_item.get('lat') is not None else None
                    lon = float(payload_item.get('lon')) if payload_item.get('lon') is not None else None
                except (TypeError, ValueError):
                    lat, lon = None, None

            append_formatted_entry(
                history_formatted,
                alert_id=item.get('external_id') or item.get('id'),
                disaster_type=item.get('event_type') or payload_item.get('disaster_type') or 'Alert',
                disaster_type_en=item.get('event_type_en') or payload_item.get('disaster_type_en'),
                severity_value=item.get('severity') or payload_item.get('severity') or 'WATCH',
                urgency_value=item.get('urgency') or payload_item.get('urgency'),
                certainty_value=item.get('certainty') or payload_item.get('certainty'),
                severity_color_value=payload_item.get('severity_color'),
                area_description=item.get('area') or payload_item.get('area_description'),
                warning_message=item.get('description') or item.get('headline') or payload_item.get('warning_message') or '',
                warning_message_en=item.get('description_en') or payload_item.get('warning_message_en'),
                source_value=(
                    payload_item.get('alert_source')
                    or payload_item.get('source_name')
                    or payload_item.get('source')
                    or item.get('source_name')
                    or item.get('source')
                    or 'Archive'
                ),
                source_section='archive_history',
                start_time_value=payload_item.get('effective_start_time') or item.get('effective_at') or item.get('issued_at'),
                end_time_value=payload_item.get('effective_end_time') or item.get('expires_at'),
                lat=lat,
                lon=lon,
                language_view=False,
            )
            if len(history_formatted) >= max_items:
                break

        generated_at = _utc_now_iso()
        mappable_count = len([a for a in history_formatted if a.get('location_available')])
        return json_response({
            'success': True,
            'count': len(history_formatted),
            'mappable_count': mappable_count,
            'source_mode': 'archive_history',
            'section': section,
            'language_mode': language_pref,
            'source_policy': source_policy,
            'data_scope': scope,
            'state_filter': state_filter or 'india',
            'coverage_filter': coverage_filter,
            'severity_filter': severity_filter or 'all',
            'type_filter': type_filter or 'all',
            'date_filter': date_filter or '',
            'date_from': date_from_filter or '',
            'date_to': date_to_filter or '',
            'active_only': active_only,
            'active_recent_hours': active_recent_hours,
            'generated_at': generated_at,
            'internal_error': None if history_formatted else 'archive_history_empty',
            'sync_status': live_sync_status,
            'alerts': history_formatted,
        })

    # Step 1: Fetch live internal alerts and sync all backup stores.
    internal_items = []
    try:
        sync_internal_api_if_needed()
        params = {'limit': internal_limit}
        if state_query:
            params['area'] = state_query
        if severity_filter and severity_filter != 'all':
            params['severity'] = severity_filter.upper()

        if embedded_internal:
            internal_payload = _embedded_internal_alerts_payload(
                limit=params.get('limit'),
                area_query=params.get('area', ''),
                severity_query=params.get('severity', ''),
            )
            generated_at = internal_payload.get('generated_at_utc')
        else:
            headers = {}
            if internal_api_key:
                headers[internal_api_key_header] = internal_api_key
            response = requests.get(internal_api_url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            internal_payload = response.json() if response.content else {}
            generated_at = response.headers.get('Date')

        internal_items = internal_payload.get('items', []) if isinstance(internal_payload, dict) else []
        live_sync_status['internal_fetch_ok'] = True
        live_sync_status['internal_items'] = len(internal_items)
    except Exception as exc:
        internal_error = str(exc)

    live_formatted = []
    if internal_items:
        for item in internal_items:
            if not isinstance(item, dict):
                continue
            payload_item = item.get('payload') if isinstance(item.get('payload'), dict) else {}
            lat, lon = extract_lat_lon_from_centroid(payload_item.get('centroid'))
            if lat is None or lon is None:
                try:
                    lat = float(payload_item.get('lat')) if payload_item.get('lat') is not None else None
                    lon = float(payload_item.get('lon')) if payload_item.get('lon') is not None else None
                except (TypeError, ValueError):
                    lat, lon = None, None

            append_formatted_entry(
                live_formatted,
                alert_id=item.get('external_id') or item.get('id'),
                disaster_type=item.get('event_type') or payload_item.get('disaster_type') or 'Alert',
                disaster_type_en=item.get('event_type_en') or payload_item.get('disaster_type_en'),
                severity_value=item.get('severity') or payload_item.get('severity') or 'WATCH',
                urgency_value=item.get('urgency') or payload_item.get('urgency'),
                certainty_value=item.get('certainty') or payload_item.get('certainty'),
                severity_color_value=payload_item.get('severity_color'),
                area_description=item.get('area') or payload_item.get('area_description'),
                warning_message=item.get('description') or item.get('headline') or payload_item.get('warning_message') or '',
                warning_message_en=item.get('description_en') or payload_item.get('warning_message_en'),
                source_value=(
                    payload_item.get('alert_source')
                    or payload_item.get('source_name')
                    or payload_item.get('source')
                    or item.get('source_name')
                    or item.get('source')
                    or 'Internal API'
                ),
                source_section='internal_api_live',
                start_time_value=payload_item.get('effective_start_time') or item.get('effective_at') or item.get('issued_at'),
                end_time_value=payload_item.get('effective_end_time') or item.get('expires_at'),
                lat=lat,
                lon=lon,
                language_view=False,
            )
            if len(live_formatted) >= max_items:
                break

    if live_sync_status['internal_fetch_ok'] and not live_formatted:
        generated_at = generated_at or _utc_now_iso()
        return json_response({
            'success': True,
            'count': 0,
            'mappable_count': 0,
            'source_mode': 'internal_api_live',
            'section': section,
            'language_mode': language_pref,
            'source_policy': source_policy,
            'data_scope': scope,
            'state_filter': state_filter or 'india',
            'coverage_filter': coverage_filter,
            'severity_filter': severity_filter or 'all',
            'type_filter': type_filter or 'all',
            'date_filter': date_filter or '',
            'date_from': date_from_filter or '',
            'date_to': date_to_filter or '',
            'active_only': active_only,
            'active_recent_hours': active_recent_hours,
            'generated_at': generated_at,
            'internal_error': internal_error,
            'sync_status': live_sync_status,
            'alerts': [],
        })

    if live_formatted:
        generated_at = generated_at or _utc_now_iso()
        live_sync_status['mongo_snapshot_saved'] = bool(
            save_live_alerts_snapshot(coverage_filter, scope, 'internal_api_live', generated_at, live_formatted)
        )
        sqlite_sync_result = _sync_formatted_alerts_to_internal_sqlite(
            live_formatted,
            source_name='django_live_sync',
        )
        live_sync_status['sqlite_synced'] = bool(sqlite_sync_result.get('ok'))
        live_sync_status['sqlite_sync_rows'] = int(sqlite_sync_result.get('rows') or 0)
        live_sync_status['sqlite_sync_error'] = sqlite_sync_result.get('reason')
        live_sync_status['json_saved'] = bool(
            _save_internal_alerts_json_fallback(generated_at, 'internal_api_live', live_formatted)
        )

        # Prefer freshly synced live data for response.
        # Snapshot/fallback chain is for continuity when live sync is unavailable.
        mappable_count = len([a for a in live_formatted if a.get('location_available')])
        return json_response({
            'success': True,
            'count': len(live_formatted),
            'mappable_count': mappable_count,
            'source_mode': 'internal_api_live',
            'section': section,
            'language_mode': language_pref,
            'source_policy': source_policy,
            'data_scope': scope,
            'state_filter': state_filter or 'india',
            'coverage_filter': coverage_filter,
            'severity_filter': severity_filter or 'all',
            'type_filter': type_filter or 'all',
            'date_filter': date_filter or '',
            'date_from': date_from_filter or '',
            'date_to': date_to_filter or '',
            'active_only': active_only,
            'active_recent_hours': active_recent_hours,
            'generated_at': generated_at,
            'internal_error': internal_error,
            'sync_status': live_sync_status,
            'alerts': live_formatted,
        })

    # Step 2: Serve from failover chain:
    # local Mongo snapshot -> internal SQLite -> JSON fallback -> degraded
    snapshot_payload = load_live_alerts_snapshot(coverage_filter, scope)
    if isinstance(snapshot_payload, dict):
        cached_alerts = snapshot_payload.get('alerts') if isinstance(snapshot_payload.get('alerts'), list) else []
        for cached in cached_alerts:
            if not isinstance(cached, dict):
                continue
            lat = cached.get('lat')
            lon = cached.get('lon')
            try:
                lat = float(lat) if lat is not None else None
                lon = float(lon) if lon is not None else None
            except (TypeError, ValueError):
                lat, lon = None, None

            append_formatted_entry(
                formatted,
                alert_id=cached.get('id') or cached.get('external_id') or cached.get('identifier'),
                disaster_type=cached.get('type') or cached.get('disaster_type') or 'Alert',
                disaster_type_en=cached.get('type_en') or cached.get('disaster_type_en'),
                severity_value=cached.get('severity') or 'WATCH',
                urgency_value=cached.get('urgency'),
                certainty_value=cached.get('certainty'),
                severity_color_value=cached.get('severity_color') or cached.get('severity_colour'),
                area_description=cached.get('area') or cached.get('area_description'),
                warning_message=cached.get('message') or cached.get('warning_message') or '',
                warning_message_en=cached.get('message_en') or cached.get('warning_message_en'),
                source_value=cached.get('source') or cached.get('alert_source') or 'Mongo snapshot',
                source_section='mongo_primary',
                start_time_value=cached.get('start_time') or cached.get('effective_start_time'),
                end_time_value=cached.get('end_time') or cached.get('effective_end_time'),
                lat=lat,
                lon=lon,
            )
            if len(formatted) >= max_items:
                break

        if formatted:
            source_mode = 'mongo_primary'
            generated_at = generated_at or snapshot_payload.get('generated_at') or snapshot_payload.get('snapshot_saved_at_utc')

    if not formatted:
        sqlite_items = _embedded_internal_alerts_from_internal_sqlite(
            limit=internal_limit,
            area_query=state_query,
            severity_query=severity_filter.upper() if (severity_filter and severity_filter != 'all') else "",
        )
        sqlite_generated = []
        for item in sqlite_items:
            if not isinstance(item, dict):
                continue
            payload_item = item.get('payload') if isinstance(item.get('payload'), dict) else {}
            lat, lon = extract_lat_lon_from_centroid(payload_item.get('centroid'))
            if lat is None or lon is None:
                try:
                    lat = float(payload_item.get('lat')) if payload_item.get('lat') is not None else None
                    lon = float(payload_item.get('lon')) if payload_item.get('lon') is not None else None
                except (TypeError, ValueError):
                    lat, lon = None, None

            if append_formatted_entry(
                formatted,
                alert_id=item.get('external_id') or item.get('id'),
                disaster_type=item.get('event_type') or payload_item.get('disaster_type') or 'Alert',
                disaster_type_en=item.get('event_type_en') or payload_item.get('disaster_type_en'),
                severity_value=item.get('severity') or payload_item.get('severity') or 'WATCH',
                urgency_value=item.get('urgency') or payload_item.get('urgency'),
                certainty_value=item.get('certainty') or payload_item.get('certainty'),
                severity_color_value=payload_item.get('severity_color'),
                area_description=item.get('area') or payload_item.get('area_description'),
                warning_message=item.get('description') or item.get('headline') or payload_item.get('warning_message') or '',
                warning_message_en=item.get('description_en') or payload_item.get('warning_message_en'),
                source_value=item.get('source') or item.get('source_name') or payload_item.get('alert_source') or 'internal_sqlite',
                source_section='sqlite_fallback',
                start_time_value=payload_item.get('effective_start_time') or item.get('effective_at') or item.get('issued_at'),
                end_time_value=payload_item.get('effective_end_time') or item.get('expires_at'),
                lat=lat,
                lon=lon,
            ):
                sqlite_generated.append(
                    item.get('updated_at') or item.get('effective_at') or item.get('issued_at') or item.get('fetched_at')
                )
            if len(formatted) >= max_items:
                break

        if formatted:
            source_mode = 'sqlite_fallback'
            generated_at = generated_at or _latest_utc_from_values(sqlite_generated) or _utc_now_iso()

    if not formatted:
        source_mode = 'file_fallback'
        data_file = _internal_alerts_json_fallback_path()
        payload = None
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r', encoding='utf-8') as file_obj:
                    payload = json.load(file_obj)
            except Exception:
                payload = None

        if isinstance(payload, dict):
            generated_at = payload.get('metadata', {}).get('generated_at_utc') or generated_at
            raw_block = payload.get('raw', {}) if isinstance(payload.get('raw'), dict) else {}
            raw_alerts = raw_block.get('alerts', []) if isinstance(raw_block.get('alerts'), list) else []
            for alert in raw_alerts:
                if not isinstance(alert, dict):
                    continue
                lat, lon = extract_lat_lon_from_centroid(alert.get('centroid'))
                append_formatted_entry(
                    formatted,
                    alert_id=alert.get('identifier'),
                    disaster_type=alert.get('disaster_type') or 'Alert',
                    disaster_type_en=alert.get('disaster_type_en'),
                    severity_value=alert.get('severity') or 'WATCH',
                    urgency_value=alert.get('urgency'),
                    certainty_value=alert.get('certainty'),
                    severity_color_value=alert.get('severity_color') or 'yellow',
                    area_description=alert.get('area_description'),
                    warning_message=alert.get('warning_message') or '',
                    warning_message_en=alert.get('warning_message_en'),
                    source_value=alert.get('alert_source') or 'JSON fallback',
                    source_section=alert.get('source_section') or alert.get('_source_section') or 'file_fallback',
                    start_time_value=alert.get('effective_start_time'),
                    end_time_value=alert.get('effective_end_time'),
                    lat=lat,
                    lon=lon,
                )
                if len(formatted) >= max_items:
                    break

    if not formatted:
        return json_response({
            'success': True,
            'message': 'Live alerts temporarily unavailable',
            'internal_error': internal_error,
            'source_mode': 'degraded',
            'section': section,
            'language_mode': language_pref,
            'source_policy': source_policy,
            'scope': scope,
            'date_from': date_from_filter or '',
            'date_to': date_to_filter or '',
            'active_only': active_only,
            'active_recent_hours': active_recent_hours,
            'count': 0,
            'alerts': [],
            'sync_status': live_sync_status,
        })

    mappable_count = len([a for a in formatted if a.get('location_available')])
    return json_response({
        'success': True,
        'count': len(formatted),
        'mappable_count': mappable_count,
        'source_mode': source_mode,
        'section': section,
        'language_mode': language_pref,
        'source_policy': source_policy,
        'data_scope': scope,
        'state_filter': state_filter or 'india',
        'coverage_filter': coverage_filter,
        'severity_filter': severity_filter or 'all',
        'type_filter': type_filter or 'all',
        'date_filter': date_filter or '',
        'date_from': date_from_filter or '',
        'date_to': date_to_filter or '',
        'active_only': active_only,
        'active_recent_hours': active_recent_hours,
        'generated_at': generated_at,
        'internal_error': internal_error,
        'sync_status': live_sync_status,
        'alerts': formatted
    })


def api_mobile_translate_alert(request):
    if request.method != "POST":
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    data = _parse_json_body(request) or {}
    type_text = str(data.get("type") or "").strip()
    message_text = str(data.get("message") or "").strip()

    if not type_text and not message_text:
        return json_response({"success": False, "message": "Alert text is required."}, status=400)

    translated_type = type_text
    translated_message = message_text

    try:
        if type_text and not _is_likely_english_text(type_text):
            translated_type = _translate_text_to_english_online(
                type_text,
                timeout_seconds=6.0,
                retries=2,
            ) or type_text

        if message_text and not _is_likely_english_text(message_text):
            translated_message = _translate_text_to_english_online(
                message_text,
                timeout_seconds=6.0,
                retries=2,
            ) or message_text
    except Exception:
        translated_type = type_text
        translated_message = message_text

    available = (
        (bool(type_text) and str(translated_type).strip() != type_text)
        or (bool(message_text) and str(translated_message).strip() != message_text)
    )

    return json_response({
        "success": True,
        "available": bool(available),
        "translated_type": translated_type or type_text,
        "translated_message": translated_message or message_text,
    })


def api_internal_health(request):
    return json_response({
        "success": True,
        "status": "ok",
        "service": "embedded_internal_api",
        "time_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })


def api_internal_alerts(request):
    if not _internal_api_auth_is_valid(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    limit = _get_query_param(request, "limit", default=200, type=int)
    area_query = (_get_query_param(request, "area") or "").strip()
    severity_query = (_get_query_param(request, "severity") or "").strip()
    language_query = (_get_query_param(request, "lang") or "").strip().lower()

    try:
        payload = _embedded_internal_alerts_payload(
            limit=limit,
            area_query=area_query,
            severity_query=severity_query,
            language_preference=language_query,
        )
        return json_response(payload)
    except Exception as exc:
        return json_response({"success": False, "message": str(exc)}, status=502)


def api_internal_sources_status(request):
    if not _internal_api_auth_is_valid(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    payload = _embedded_internal_sources_payload()
    return json_response(payload)


def api_internal_sync(request):
    if request.method not in {"POST", "GET"}:
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    if not _internal_api_auth_is_valid(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    global _internal_api_last_sync_monotonic, _internal_api_last_sync_attempt_utc, _internal_api_last_sync_success_utc

    try:
        payload = _embedded_internal_sync_payload()
        _internal_api_last_sync_attempt_utc = payload.get("attempted_at_utc")
        _internal_api_last_sync_success_utc = payload.get("attempted_at_utc")
        _internal_api_last_sync_monotonic = time_module.monotonic()
        return json_response(payload)
    except Exception as exc:
        return json_response({"success": False, "message": str(exc)}, status=502)


def api_ws_token(request):
    """Return a JWT token for WebSocket auth for the current user."""
    user = _get_authenticated_user(request)
    if not user:
        return json_response({"success": False, "message": "Unauthorized"}, status=401)
    try:
        token = generate_ws_token(user)
        return json_response({"success": True, "token": token})
    except Exception as exc:
        return json_response({"success": False, "message": str(exc)}, status=500)


def api_weather_grid(request):
    """Return weather grid data as JSON for the React app."""
    lat = _get_query_param(request, 'lat', type=float)
    lon = _get_query_param(request, 'lon', type=float)

    if lat is None or lon is None:
        lat, lon = get_location_by_ip()

    if lat is None or lon is None:
        return json_response({"success": False, "message": "Could not detect location."}, status=400)

    points = generate_radius_points(lat, lon)
    msg = []
    results = []
    for p_lat, p_lon in points:
        weather_data = fetch_weather(p_lat, p_lon)
        current = weather_data.get('current_weather', {})
        results.append({
            "coords": [p_lat, p_lon],
            "temperature": current.get('temperature'),
            "windspeed": current.get('windspeed'),
            "precipitation": current.get('precipitation', 0)
        })

    if results:
        if (results[0].get('temperature') or 0) > 40:
            msg.append("Heat wave alert.")
        if (results[0].get('windspeed') or 0) > 20:
            msg.append("Storm alert.")
        if (results[0].get('precipitation') or 0) > 10:
            msg.append("Flood alert.")

    summary = results[0] if results else {}
    return json_response({
        "success": True,
        "summary": summary,
        "grid": results,
        "messages": msg
    })


def api_report_disaster(request):
    """JSON API for reporting a disaster incident (React)."""
    if request.method != 'POST':
        return json_response({"success": False, "message": "Method not allowed"}, status=405)

    user = _get_authenticated_user(request)
    if not user:
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    data = _parse_json_body(request) or {}

    disaster_type = data.get('disaster_type') or _get_form_param(request, 'disaster_type')
    description = data.get('description') or _get_form_param(request, 'description')
    address_text = data.get('address_text') or _get_form_param(request, 'address_text')
    latitude = data.get('latitude') or _get_form_param(request, 'latitude', type=float)
    longitude = data.get('longitude') or _get_form_param(request, 'longitude', type=float)

    try:
        latitude = float(latitude) if latitude is not None else None
        longitude = float(longitude) if longitude is not None else None
    except Exception:
        return json_response({"success": False, "message": "Invalid coordinates"}, status=400)

    media_type = (data.get('media_type') or _get_form_param(request, 'media_type') or '').strip().lower()
    if media_type not in ('image', 'video'):
        media_type = None

    media_file = request.FILES.get('media')
    media_blob = None

    if media_file:
        media_blob = media_file.read()
        if not media_type:
            guessed = (getattr(media_file, 'content_type', '') or '').strip().lower()
            if guessed.startswith('image/'):
                media_type = 'image'
            elif guessed.startswith('video/'):
                media_type = 'video'
    else:
        media_base64 = data.get('media_base64')
        if media_base64:
            try:
                if ',' in media_base64:
                    media_base64 = media_base64.split(',', 1)[1]
                media_blob = base64.b64decode(media_base64)
            except Exception:
                return json_response({"success": False, "message": "Invalid media_base64 payload"}, status=400)

    is_admin = _is_admin_request(request)
    verify_status = True if is_admin else False
    admin_id = user.id if (is_admin and user) else None

    try:
        incident = Disaster.objects.create(
            reporter_id=user.id,
            disaster_type=disaster_type,
            description=description,
            address_text=address_text,
            latitude=latitude,
            longitude=longitude,
            media_type=media_type,
            media=media_blob,
            verify_status=verify_status,
            admin_id=admin_id,
        )
    except Exception as exc:
        return json_response({"success": False, "message": str(exc)}, status=500)

    msg = (
        "Disaster report verified automatically." if is_admin
        else "Disaster reported successfully. It will be verified by an admin."
    )
    return json_response({
        "success": True,
        "message": msg,
        "incident_id": getattr(incident, 'disaster_id', None)
    })


def logout(request):
    django_logout(request)
    return redirect(url('login'))



def signup(request):
    msg = ''
    user_info = None
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        name = _get_form_param(request, 'name')
        role = 'USER'
        phone = _get_form_param(request, 'phone')
        user_info = {
            'name': name,
            'username': username,
            'email_id': email,
            'phone': phone,
            'password': password,
            'role': role,
        }
        
        if len(password) < 8:
            msg = "Password must be at least 8 characters."
            return render_page(request, "signup.html", msg=msg, user_info=user_info)

        UserModel = get_user_model()
        existing = UserModel.objects.filter(Q(username__iexact=username) | Q(email__iexact=email)).first()

        if existing:
            profile = UserProfile.objects.filter(user=existing).first()
            if not existing.is_active or (profile and profile.is_blocked):
                msg = "Your account is blocked. Contact support."
            else:
                msg = "User already exists. Try again."
        else:
            try:
                django_user = UserModel.objects.create_user(
                    username=username,
                    email=email or "",
                    password=password,
                    first_name=name or "",
                )
                profile, _created = UserProfile.objects.get_or_create(
                    user=django_user,
                    defaults={
                        "role": role,
                        "phone": phone,
                        "is_blocked": False,
                        "must_change_password": False,
                        "password_plain": (password if STORE_PLAIN_PASSWORDS else None),
                    },
                )
                if not _created:
                    profile.role = role
                    profile.phone = phone
                    profile.is_blocked = False
                    profile.must_change_password = False
                    profile.password_plain = password if STORE_PLAIN_PASSWORDS else None
                    profile.save(
                        update_fields=[
                            "role",
                            "phone",
                            "is_blocked",
                            "must_change_password",
                            "password_plain",
                        ]
                    )
                return redirect(url('login'))
            except Exception as err:
                msg = f"Signup failed: {err}"

    return render_page(request, "signup.html", msg=msg, user_info=user_info)


def get_weather_grid(request):
    return redirect(url('mobile_satellite'))

    
   
    lat, lon = get_location_by_ip()
    
    if lat and lon:
       
        points = generate_radius_points(lat, lon)
        msg=[]
        results = []
        for p_lat, p_lon in points:
            weather_data = fetch_weather(p_lat, p_lon)
            # Extract only temperature, windspeed, and precipitation from Open-Meteo API
            current = weather_data.get('current_weather', {})
            results.append({
                "coords": [p_lat, p_lon],                
                "temperature": current.get('temperature'),
                "windspeed": current.get('windspeed'),
                "precipitation": current.get('precipitation', 0)
            })
        # results[0]['temperature']=80 test case for heat wave alert
        if results[0]['temperature']>40:
            msg.append("Heat wave alert.")
        if results[0]['windspeed']>20:
            msg.append("Storm alert.")
        if results[0]['precipitation']>10:
            msg.append("Flood alert.") 
            
        
        return render_page(request, "weather.html", temperature=results[0]['temperature'], windspeed=results[0]['windspeed'], precipitation=results[0]['precipitation'], grid_data=results,msg=msg)
    else:
        return render_page(request, "weather.html", msg="Could not detect location.")

def get_nearby_ngos(request): 
    return redirect(url('mobile_organization'))

def live_ngos(request):
    ngo_contacts_db = load_ngo_contacts()
    normalized_contacts = {
        normalize_org_name(name): details for name, details in ngo_contacts_db.items()
    }

    lat = _get_query_param(request, 'lat', type=float)
    lon = _get_query_param(request, 'lon', type=float)
    radius = _get_query_param(request, 'radius', type=int) or NGO_RADIUS_METERS
    radius = max(1000, min(int(radius), 200000))
    max_distance_km = max(1.0, radius / 1000.0)
    strict_nearby_only = str(_get_query_param(request, 'nearby_only') or '').strip().lower() in ['1', 'true', 'yes', 'on']

    if lat is None or lon is None:
        return json_response({"error": "Missing coordinates"}, status=400)

    cache_key = _ngo_cache_key(lat, lon, radius)
    cached_ngos = _ngo_cache_get(cache_key)
    if cached_ngos is not None:
        return json_response(cached_ngos)

    query = (
        f"[out:json][timeout:25];"
        f"("
        f"node[\"office\"=\"ngo\"](around:{radius},{lat},{lon});"
        f"node[\"office\"=\"charity\"](around:{radius},{lat},{lon});"
        f"node[\"office\"=\"non_profit\"](around:{radius},{lat},{lon});"
        f"node[\"office\"=\"foundation\"](around:{radius},{lat},{lon});"
        f"node[\"amenity\"=\"ngo\"](around:{radius},{lat},{lon});"
        f"node[\"amenity\"=\"social_facility\"](around:{radius},{lat},{lon});"
        f"node[\"social_facility\"=\"shelter\"](around:{radius},{lat},{lon});"
        f"node[\"amenity\"=\"shelter\"](around:{radius},{lat},{lon});"
        f"node[\"amenity\"=\"hospital\"](around:{radius},{lat},{lon});"
        f"node[\"amenity\"=\"clinic\"](around:{radius},{lat},{lon});"
        f"node[\"emergency\"=\"ambulance_station\"](around:{radius},{lat},{lon});"
        f"node[\"emergency\"=\"fire_station\"](around:{radius},{lat},{lon});"
        f"node[\"amenity\"=\"police\"](around:{radius},{lat},{lon});"
        f"way[\"office\"=\"ngo\"](around:{radius},{lat},{lon});"
        f"way[\"office\"=\"charity\"](around:{radius},{lat},{lon});"
        f"way[\"office\"=\"non_profit\"](around:{radius},{lat},{lon});"
        f"way[\"office\"=\"foundation\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"ngo\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"social_facility\"](around:{radius},{lat},{lon});"
        f"way[\"social_facility\"=\"shelter\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"shelter\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"hospital\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"clinic\"](around:{radius},{lat},{lon});"
        f"way[\"emergency\"=\"ambulance_station\"](around:{radius},{lat},{lon});"
        f"way[\"emergency\"=\"fire_station\"](around:{radius},{lat},{lon});"
        f"way[\"amenity\"=\"police\"](around:{radius},{lat},{lon});"
        f"relation[\"office\"=\"ngo\"](around:{radius},{lat},{lon});"
        f"relation[\"office\"=\"charity\"](around:{radius},{lat},{lon});"
        f"relation[\"office\"=\"non_profit\"](around:{radius},{lat},{lon});"
        f"relation[\"office\"=\"foundation\"](around:{radius},{lat},{lon});"
        f"relation[\"amenity\"=\"ngo\"](around:{radius},{lat},{lon});"
        f"relation[\"amenity\"=\"social_facility\"](around:{radius},{lat},{lon});"
        f"relation[\"social_facility\"=\"shelter\"](around:{radius},{lat},{lon});"
        f"relation[\"amenity\"=\"shelter\"](around:{radius},{lat},{lon});"
        f"relation[\"amenity\"=\"hospital\"](around:{radius},{lat},{lon});"
        f"relation[\"amenity\"=\"clinic\"](around:{radius},{lat},{lon});"
        f"relation[\"emergency\"=\"ambulance_station\"](around:{radius},{lat},{lon});"
        f"relation[\"emergency\"=\"fire_station\"](around:{radius},{lat},{lon});"
        f"relation[\"amenity\"=\"police\"](around:{radius},{lat},{lon});"
        f");"
        f"out tags center;"
    )

    data = _fetch_overpass_payload(query) or {"elements": []}

    try:
        ngos = []
        seen = set()
        for element in data.get('elements', []):
            tags = element.get('tags', {})
            ngo_name = tags.get('name', 'Unnamed Relief Facility')
            element_lat = _safe_float(element.get('lat'))
            element_lon = _safe_float(element.get('lon'))

            if element_lat is None or element_lon is None:
                center = element.get('center') or {}
                element_lat = _safe_float(center.get('lat'))
                element_lon = _safe_float(center.get('lon'))

            if element_lat is None or element_lon is None:
                continue

            normalized_name = normalize_org_name(ngo_name)

            contact_info = ngo_contacts_db.get(ngo_name)
            if not contact_info:
                contact_info = normalized_contacts.get(normalized_name)
            if not contact_info and normalized_name:
                for known_name, known_contact in normalized_contacts.items():
                    if normalized_name in known_name or known_name in normalized_name:
                        contact_info = known_contact
                        break
            contact_info = contact_info or {}

            phone_value = pick_first_value(
                tags.get('phone'),
                tags.get('contact:phone'),
                contact_info.get('phone')
            )
            email_value = pick_first_value(
                tags.get('email'),
                tags.get('contact:email'),
                contact_info.get('email')
            )
            website_value = pick_first_value(
                tags.get('website'),
                tags.get('contact:website'),
                tags.get('url'),
                contact_info.get('website')
            )

            address_value = pick_first_value(
                tags.get('addr:full'),
                tags.get('addr:street'),
                tags.get('addr:city'),
                tags.get('is_in:city'),
                tags.get('addr:state')
            )

            area_coverage = contact_info.get('areas') if isinstance(contact_info.get('areas'), list) else []

            dedupe_key = (
                normalized_name,
                round(element_lat, 4),
                round(element_lon, 4)
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            ngo_entry = {
                "name": ngo_name,
                "type": tags.get('office', tags.get('amenity', 'NGO')),
                "lat": element_lat,
                "lon": element_lon,
                "phone": phone_value,
                "email": email_value,
                "website": website_value,
                "address": address_value,
                "areas": area_coverage,
                "source": "osm"
            }

            distance_km = haversine_distance_km(lat, lon, ngo_entry['lat'], ngo_entry['lon'])
            if not math.isfinite(distance_km):
                continue
            if strict_nearby_only and distance_km > max_distance_km:
                continue
            eta_minutes, eta_text = estimate_duration_text(distance_km)
            ngo_entry['distance_km'] = round(distance_km, 2)
            ngo_entry['estimated_duration_min'] = eta_minutes
            ngo_entry['estimated_duration'] = eta_text
            ngos.append(ngo_entry)

        if not ngos:
            # Return the full fallback directory when live data is unavailable,
            # unless the client asked for strict nearby-only results.
            fallback_max = max_distance_km if strict_nearby_only else None
            ngos = _ngo_contact_fallback(ngo_contacts_db, lat, lon, max_distance_km=fallback_max)
            ngos.sort(key=lambda item: item.get('distance_km', 999999))
            return json_response(ngos[:100])

        ngos.sort(key=lambda item: item.get('distance_km', 999999))
        ngos = ngos[:100]
        _ngo_cache_set(cache_key, ngos)
        return json_response(ngos)
    except Exception as err:
        fallback_max = max_distance_km if strict_nearby_only else None
        fallback = _ngo_contact_fallback(ngo_contacts_db, lat, lon, max_distance_km=fallback_max)
        fallback.sort(key=lambda item: item.get('distance_km', 999999))
        return json_response(fallback[:100])

def contact_request(request):
    """Handle NGO contact inquiries"""
    try:
        inquiry_data = _parse_json_body(request)
        
        # Save inquiry to a file
        inquiries_file = 'ngo_inquiries.json'
        
        # Load existing inquiries or create new list
        try:
            with open(inquiries_file, 'r') as f:
                inquiries = json.load(f)
        except FileNotFoundError:
            inquiries = []
        
        # Add new inquiry
        inquiries.append(inquiry_data)
        
        # Save back to file
        with open(inquiries_file, 'w') as f:
            json.dump(inquiries, f, indent=2)
        
        # You could also send email here or integrate with WhatsApp API
        # For now, just save it
        
        return json_response({
            "success": True,
            "message": "Your inquiry has been recorded. The NGO will contact you soon."
        }, status=200)
        
    except Exception as e:
        return json_response({"error": f"Failed to process request: {str(e)}"}, status=500)

def get_all_users(request):
    """Get all users for admin dashboard"""
    if not _is_admin_request(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
    try:
        scope = (_get_query_param(request, "scope") or "all").strip().lower()
        include_admin = str(_get_query_param(request, "include_admin") or "1").strip().lower() not in ["0", "false", "no", "off"]
        UserModel = get_user_model()
        users = UserModel.objects.order_by("id")
        user_list = []
        for user in users:
            profile = UserProfile.objects.filter(user=user).first()
            role = profile.role if profile else ("ADMIN" if user.is_staff else "USER")
            if not include_admin and role == "ADMIN":
                continue
            is_blocked = bool(profile.is_blocked) if profile else (not user.is_active)
            is_active = bool(user.is_active) and not is_blocked
            if scope == "active" and not is_active:
                continue
            if scope == "blocked" and not is_blocked:
                continue
            full_name = user.get_full_name() or user.username
            user_list.append({
                "user_id": user.id,
                "name": full_name,
                "username": user.username,
                "email": user.email,
                "phone": profile.phone if profile else "",
                "password": profile.password_plain if (profile and EXPOSE_PLAIN_PASSWORDS) else "",
                "role": role,
                "is_blocked": is_blocked,
                "is_active": is_active,
                "created_at": str(user.date_joined) if hasattr(user, "date_joined") else "",
                "last_login": str(user.last_login) if getattr(user, "last_login", None) else ""
            })
        
        return json_response({"success": True, "users": user_list})
    except Exception as e:
        return json_response({"success": False, "message": str(e)}, status=500)


def admin_reset_user_password(request):
    if not _is_admin_request(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)

    payload = _parse_json_body(request) or {}
    user_id = payload.get('user_id')
    provided_password = str(payload.get('new_password') or '').strip()

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return json_response({"success": False, "message": "Invalid user id"}, status=400)

    if provided_password and len(provided_password) < 8:
        return json_response({"success": False, "message": "Temporary password must be at least 8 characters"}, status=400)

    UserModel = get_user_model()
    user_obj = UserModel.objects.filter(id=user_id).first()
    if not user_obj:
        return json_response({"success": False, "message": "User not found"}, status=404)

    temp_password = provided_password or _generate_temporary_password(12)
    try:
        user_obj.set_password(temp_password)
        user_obj.is_active = True
        user_obj.save(update_fields=["password", "is_active"])
        profile = _get_or_create_profile(user_obj)
        if profile:
            profile.must_change_password = True
            profile.is_blocked = False
            profile.password_plain = temp_password if STORE_PLAIN_PASSWORDS else None
            profile.save(update_fields=["must_change_password", "is_blocked", "password_plain"])
    except Exception:
        return json_response({"success": False, "message": "Could not reset password"}, status=500)

    if request.user and request.user.is_authenticated and request.user.id == user_id:
        request.session['must_change_password'] = True

    return json_response({
        "success": True,
        "message": f"Temporary password generated for {user_obj.username}",
        "temp_password": temp_password,
        "must_change_password": True,
    })


# @app.route('/block-user', methods=['POST'])
# def block_user(request):
#     """Block or unblock a user"""
#     if 'user_id' not in request.session or request.session.get('role') != 'ADMIN':
#         return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
#     try:
#         data = request.json
#         user_id = data.get('user_id')
        
#         # Get current status
#         result = fetch_one("SELECT is_blocked FROM users WHERE user_id = %s", (user_id,))
        
#         if not result:
#             return json_response({"success": False, "message": "User not found"}, status=404)
        
#         # Toggle the blocked status
#         new_status = not result[0]
#         execute_update("UPDATE users SET is_blocked = %s WHERE user_id = %s", (new_status, user_id))
        
#         return json_response({"success": True, "message": "User status updated successfully"})
#     except Exception as e:
#         return json_response({"success": False, "message": str(e)}, status=500)

# @app.route('/get-all-incidents', methods=['GET'])
# def get_all_incidents(request):
#     """Get all reported disaster incidents for admin"""
#     if 'user_id' not in request.session or request.session.get('role') != 'ADMIN':
#         return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
#     try:
#         incidents = fetch_all("""
#             SELECT d.Disaster_id, d.reporter_id, u.username, d.disaster_type, d.description,
#                    d.address_text, d.latitude, d.longitude, d.verify_status, d.media_type, 
#                    d.created_at
#             FROM Disasters d
#             JOIN Users u ON d.reporter_id = u.user_id
#             ORDER BY d.created_at DESC
#         """)
        
#         incident_list = []
#         for incident in incidents:
#             incident_list.append({
#                 "incident_id": incident[0],
#                 "user_id": incident[1],
#                 "username": incident[2],
#                 "incident_type": incident[3],
#                 "description": incident[4],
#                 "location": incident[5],
#                 "latitude": float(incident[6]) if incident[6] else None,
#                 "longitude": float(incident[7]) if incident[7] else None,
#                 "is_verified": bool(incident[8]),
#                 "media_type": incident[9],
#                 "created_at": str(incident[10])
#             })
        
#         return json_response({"success": True, "incidents": incident_list})
#     except Exception as e:
#         return json_response({"success": False, "message": str(e)}, status=500)

# @app.route('/verify-incident', methods=['POST'])
# def verify_incident(request):
#     """Verify a disaster incident"""
#     if 'user_id' not in request.session or request.session.get('role') != 'ADMIN':
#         return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
#     try:
#         data = request.json
#         incident_id = data.get('incident_id')
        
#         result = fetch_one("SELECT verify_status FROM Disasters WHERE Disaster_id = %s", (incident_id,))
        
#         if not result:
#             return json_response({"success": False, "message": "Incident not found"}, status=404)
        
#         # Toggle the verified status and set admin_id
#         new_status = not result[0]
#         execute_update("UPDATE Disasters SET verify_status = %s, admin_id = %s WHERE Disaster_id = %s", 
#                       (new_status, request.session.get('user_id'), incident_id))
        
#         return json_response({"success": True, "message": "Incident status updated successfully"})
#     except Exception as e:
#         return json_response({"success": False, "message": str(e)}, status=500)

# @app.route('/delete-incident', methods=['POST'])
# def delete_incident(request):
#     """Delete a disaster incident"""
#     if 'user_id' not in request.session or request.session.get('role') != 'ADMIN':
#         return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
#     try:
#         data = request.json
#         incident_id = data.get('incident_id')
        
#         execute_update("DELETE FROM Disasters WHERE Disaster_id = %s", (incident_id,))
        
#         return json_response({"success": True, "message": "Incident deleted successfully"})
#     except Exception as e:
#         return json_response({"success": False, "message": str(e)}, status=500)

# @app.route('/report-disaster', methods=['GET', 'POST'])
# def report_disaster(request):
#     """Report a new disaster incident"""
#     user_info = request.session.get('user_info')
#     user_id = _get_query_param(request, 'user_id')
#     if request.method == 'GET':
#         return render_page(request, 'report_disaster.html', username=request.session.get('username') if 'user_id' in request.session else None, user_info=user_info)
    
#     # POST request - handle disaster reporting (requires authentication)
#     if 'user_id' not in request.session:
#         return render_page(request, 'report_disaster.html', msg='You must be logged in to submit a disaster report.', msg_type='error')
    
#     try:
#         disaster_type = _get_form_param(request, 'disaster_type')
#         description = _get_form_param(request, 'description')
#         address_text = _get_form_param(request, 'address_text')
#         latitude = _get_form_param(request, 'latitude', type=float)
#         longitude = _get_form_param(request, 'longitude', type=float)
#         media_type = _get_form_param(request, 'media_type')  # 'image' or 'video'
        
#         media_file = request.FILES.get('media')
#         media_blob = None
        
#         if media_file:
#             media_blob = media_file.read()
        
#         # If admin, auto-verify. If regular user, unverified by default
#         is_admin = request.session.get('role') == 'ADMIN'
#         verify_status = True if is_admin else False
#         admin_id = request.session.get('user_id') if is_admin else None
        
#         execute_update("""
#             INSERT INTO Disasters 
#             (reporter_id, disaster_type, description, address_text, latitude, longitude, media_type, media, verify_status, admin_id)
#             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#         """, (request.session.get('user_id'), disaster_type, description, address_text, latitude, longitude, media_type, media_blob, verify_status, admin_id))
        
#         msg = "Your disaster report has been verified automatically!" if is_admin else "Disaster reported successfully. Thank you for your report! It will be verified by an admin soon."
#         return render_page(request, 'report_disaster.html', username=request.session.get('username'), msg=msg, msg_type='success')
#     except Exception as e:
#         return render_page(request, 'report_disaster.html', username=request.session.get('username'), msg=str(e), msg_type='error')


# @app.route('/get-all-users', methods=['GET'])
# def get_all_users(request):
#     """Get all users for admin dashboard"""
#     if 'user_id' not in request.session or request.session.get('role') != 'ADMIN':
#         return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
#     try:
#         cursor.execute("SELECT user_id, full_name, username, email_id, phone, role, is_blocked, created_at FROM users where role='USER'")
#         users = cursor.fetchall()
        
#         user_list = []
#         for user in users:
#             user_list.append({
#                 "user_id": user[0],
#                 "name": user[1],
#                 "username": user[2],
#                 "email": user[3],
#                 "phone": user[4],
#                 "role": user[5],
#                 "is_blocked": bool(user[6]),
#                 "created_at": str(user[7])
#             })
        
#         return json_response({"success": True, "users": user_list})
#     except Exception as e:
#         return json_response({"success": False, "message": str(e)}, status=500)

def block_user(request):
    """Block or unblock a user"""
    if not _is_admin_request(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
    try:
        data = _parse_json_body(request) or {}
        user_id = data.get('user_id')
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return json_response({"success": False, "message": "Invalid user id"}, status=400)

        UserModel = get_user_model()
        user_obj = UserModel.objects.filter(id=user_id).first()
        if not user_obj:
            return json_response({"success": False, "message": "User not found"}, status=404)

        profile = _get_or_create_profile(user_obj)
        current_blocked = bool(profile.is_blocked) if profile else (not user_obj.is_active)
        new_status = not current_blocked
        if profile:
            profile.is_blocked = new_status
            profile.save(update_fields=["is_blocked"])
        user_obj.is_active = not new_status
        user_obj.save(update_fields=["is_active"])
        
        return json_response({"success": True, "message": "User status updated successfully"})
    except Exception as e:
        return json_response({"success": False, "message": str(e)}, status=500)

def get_all_incidents(request):
    """Get all reported disaster incidents for admin"""
    if not _is_admin_request(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
    try:
        incidents = Disaster.objects.select_related("reporter").order_by("-created_at")
        incident_list = []
        for incident in incidents:
            reporter_username = incident.reporter.username if incident.reporter_id else "Unknown"
            incident_list.append({
                "incident_id": incident.disaster_id,
                "user_id": incident.reporter_id,
                "username": reporter_username,
                "incident_type": incident.disaster_type,
                "description": incident.description,
                "location": incident.address_text,
                "latitude": float(incident.latitude) if incident.latitude is not None else None,
                "longitude": float(incident.longitude) if incident.longitude is not None else None,
                "is_verified": bool(incident.verify_status),
                "media_type": incident.media_type,
                "created_at": str(incident.created_at)
            })
        
        return json_response({"success": True, "incidents": incident_list})
    except Exception as e:
        return json_response({"success": False, "message": str(e)}, status=500)

def verify_incident(request):
    """Verify a disaster incident"""
    if not _is_admin_request(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
    try:
        data = _parse_json_body(request)
        incident_id = data.get('incident_id')
        
        incident = Disaster.objects.filter(disaster_id=incident_id).first()
        if not incident:
            return json_response({"success": False, "message": "Incident not found"}, status=404)
        
        # Toggle the verified status and set admin_id
        new_status = not bool(incident.verify_status)
        incident.verify_status = new_status
        admin_user = _get_authenticated_user(request)
        incident.admin_id = admin_user.id if admin_user else None
        incident.save(update_fields=["verify_status", "admin_id"])
        
        return json_response({"success": True, "message": "Incident status updated successfully"})
    except Exception as e:
        return json_response({"success": False, "message": str(e)}, status=500)

def delete_incident(request):
    """Delete a disaster incident"""
    if not _is_admin_request(request):
        return json_response({"success": False, "message": "Unauthorized"}, status=401)
    
    try:
        data = _parse_json_body(request)
        incident_id = data.get('incident_id')
        
        Disaster.objects.filter(disaster_id=incident_id).delete()
        
        return json_response({"success": True, "message": "Incident deleted successfully"})
    except Exception as e:
        return json_response({"success": False, "message": str(e)}, status=500)

def report_disaster(request):
    """Report a new disaster incident"""
    
    if request.method == 'GET':
        return render_page(request, 
            'report_disaster.html',
            username=request.user.username if getattr(request, "user", None) is not None and request.user.is_authenticated else None
        )
    
    # POST request - handle disaster reporting (requires authentication)
    user = _get_authenticated_user(request)
    if not user:
        return render_page(request, 'report_disaster.html', msg='You must be logged in to submit a disaster report.', msg_type='error')
    
    try:
        disaster_type = _get_form_param(request, 'disaster_type')
        description = _get_form_param(request, 'description')
        address_text = _get_form_param(request, 'address_text')
        latitude = _get_form_param(request, 'latitude', type=float)
        longitude = _get_form_param(request, 'longitude', type=float)
        media_type = (_get_form_param(request, 'media_type') or '').strip().lower()  # 'image' or 'video'
        if media_type not in ('image', 'video'):
            media_type = None
        
        media_file = request.FILES.get('media')
        media_blob = None
        
        if media_file:
            media_blob = media_file.read()
            if not media_type:
                guessed_type = (media_file.mimetype or '').strip().lower()
                if guessed_type.startswith('image/'):
                    media_type = 'image'
                elif guessed_type.startswith('video/'):
                    media_type = 'video'
            if not media_type:
                return render_page(request, 
                    'report_disaster.html',
                    username=request.session.get('username'),
                    msg='Please select a valid media type (image/video) when uploading a file.',
                    msg_type='error'
                )
        
        # If admin, auto-verify. If regular user, unverified by default
        is_admin = _is_admin_request(request)
        verify_status = True if is_admin else False
        admin_id = user.id if (is_admin and user) else None

        try:
            Disaster.objects.create(
                reporter_id=user.id,
                disaster_type=disaster_type,
                description=description,
                address_text=address_text,
                latitude=latitude,
                longitude=longitude,
                media_type=media_type,
                media=media_blob,
                verify_status=verify_status,
                admin_id=admin_id,
            )
        except Exception:
            # Legacy DB might still enforce FK against Users_legacy. Fallback to legacy id.
            profile = _profile_for_request(request)
            legacy_id = getattr(profile, "legacy_user_id", None) if profile else None
            if not legacy_id:
                raise
            Disaster.objects.create(
                reporter_id=legacy_id,
                disaster_type=disaster_type,
                description=description,
                address_text=address_text,
                latitude=latitude,
                longitude=longitude,
                media_type=media_type,
                media=media_blob,
                verify_status=verify_status,
                admin_id=legacy_id if is_admin else None,
            )
        
        msg = "Your disaster report has been verified automatically!" if is_admin else "Disaster reported successfully. Thank you for your report! It will be verified by an admin soon."
        return render_page(request, 'report_disaster.html', username=user.username, msg=msg, msg_type='success')
    except Exception as e:
        return render_page(request, 'report_disaster.html', username=user.username if user else None, msg=str(e), msg_type='error')
    
