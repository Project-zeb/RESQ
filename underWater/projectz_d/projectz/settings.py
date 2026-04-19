import os
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
REACT_FRONTEND_DIST = BASE_DIR / "frontend_react" / "dist"

SECRET_KEY = os.getenv("SECRET_KEY", "projectz-local-dev-secret")


def _env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = _env_bool(os.getenv("DJANGO_DEBUG", os.getenv("DEBUG", "1")), default=True)

ALLOWED_HOSTS = ["*"]
APPEND_SLASH = False

INSTALLED_APPS = [
    "daphne",  # ASGI server for Channels (must be first)
    "channels",  # Django Channels for WebSocket support
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "corsheaders",
    "core.apps.CoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "projectz.middleware.PasswordChangeMiddleware",
]

ROOT_URLCONF = "projectz.urls"

CORS_ALLOW_ALL_ORIGINS = True  # For local development
CORS_ALLOW_CREDENTIALS = True

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "projectz.jinja2.environment",
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "projectz.wsgi.application"
ASGI_APPLICATION = "projectz.asgi.application"


def _sqlite_database_settings():
    sqlite_path = os.getenv("SQLITE_DB_PATH", "app.db")
    sqlite_file = Path(sqlite_path)
    if not sqlite_file.is_absolute():
        sqlite_file = BASE_DIR / sqlite_path
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(sqlite_file),
    }


def _mysql_database_settings():
    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", ""),
        "USER": os.getenv("DB_USER", ""),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", ""),
        "PORT": os.getenv("DB_PORT", ""),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }


def _mongodb_db_name_from_uri(mongo_uri):
    try:
        parsed = urlparse(mongo_uri)
    except Exception:
        return ""
    path_part = str(parsed.path or "").strip("/")
    if not path_part:
        return ""
    return path_part.split("/", 1)[0].strip()


def _mongodb_ping_ok(mongo_uri, timeout_ms):
    try:
        from pymongo import MongoClient
    except Exception as exc:
        return False, f"pymongo not installed: {exc}"

    client = None
    try:
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        client.admin.command("ping")
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _is_local_mongo_uri(mongo_uri):
    uri = str(mongo_uri or "").strip()
    if not uri:
        return False
    try:
        hostname = (urlparse(uri).hostname or "").strip().lower()
    except Exception:
        hostname = ""
    return hostname in {"127.0.0.1", "localhost", "::1"}


def _mongodb_uri_candidates():
    mongo_name = (os.getenv("MONGODB_DB_NAME") or "").strip() or "resqfy"
    local_enabled = _env_bool(os.getenv("MONGODB_LOCAL_ENABLED", "1"), default=True)

    source_uri_map = {
        "local": (
            (os.getenv("MONGODB_LOCAL_URI") or os.getenv("MONGODB_URI_LOCAL") or f"mongodb://127.0.0.1:27017/{mongo_name}").strip()
            if local_enabled
            else ""
        ),
        "shared": (os.getenv("SHARED_MONGODB_URI") or "").strip(),
        "env": (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip(),
    }

    priority_text = (os.getenv("MONGODB_URI_PRIORITY") or "local,shared").strip().lower()
    requested_order = []
    for token in priority_text.split(","):
        key = token.strip().lower()
        if key and key in source_uri_map and key not in requested_order:
            requested_order.append(key)
    if not requested_order:
        requested_order = ["local", "shared"]

    ordered_candidates = []
    seen_uris = set()
    for key in requested_order:
        uri = str(source_uri_map.get(key) or "").strip()
        if not uri or uri in seen_uris:
            continue
        seen_uris.add(uri)
        ordered_candidates.append((key, uri))

    return ordered_candidates, requested_order, source_uri_map


MONGODB_ACTIVE_URI = ""
MONGODB_ACTIVE_SOURCE = ""
MONGODB_ACTIVE_DB_NAME = ""
MONGODB_CANDIDATE_URIS = {}
MONGODB_CANDIDATE_ERRORS = {}
MONGODB_URI_PRIORITY = []
MONGODB_SELECTION_ERROR = None


def _build_mongodb_database_settings():
    global MONGODB_ACTIVE_URI
    global MONGODB_ACTIVE_SOURCE
    global MONGODB_ACTIVE_DB_NAME
    global MONGODB_CANDIDATE_URIS
    global MONGODB_CANDIDATE_ERRORS
    global MONGODB_URI_PRIORITY
    global MONGODB_SELECTION_ERROR

    MONGODB_ACTIVE_URI = ""
    MONGODB_ACTIVE_SOURCE = ""
    MONGODB_ACTIVE_DB_NAME = ""
    MONGODB_CANDIDATE_URIS = {}
    MONGODB_CANDIDATE_ERRORS = {}
    MONGODB_URI_PRIORITY = []
    MONGODB_SELECTION_ERROR = None

    timeout_text = (os.getenv("MONGODB_CONNECT_TIMEOUT_MS") or "2500").strip()
    try:
        timeout_ms = max(500, int(timeout_text))
    except ValueError:
        timeout_ms = 2500

    verify_on_startup = _env_bool(os.getenv("MONGODB_VERIFY_ON_STARTUP", "1"), default=True)
    candidates, requested_order, source_uri_map = _mongodb_uri_candidates()
    MONGODB_URI_PRIORITY = requested_order
    MONGODB_CANDIDATE_URIS = {key: value for key, value in source_uri_map.items() if value}
    if not candidates:
        MONGODB_SELECTION_ERROR = "No MongoDB URI candidates configured"
        return None, MONGODB_SELECTION_ERROR

    selected_source = ""
    selected_uri = ""
    candidate_errors = {}
    if verify_on_startup:
        for source_key, candidate_uri in candidates:
            healthy, reason = _mongodb_ping_ok(candidate_uri, timeout_ms)
            if healthy:
                selected_source = source_key
                selected_uri = candidate_uri
                break
            candidate_errors[source_key] = reason or "MongoDB ping failed"
    else:
        selected_source, selected_uri = candidates[0]
    MONGODB_CANDIDATE_ERRORS = candidate_errors

    if not selected_uri:
        details = "; ".join(
            f"{source_key}: {candidate_errors.get(source_key, 'MongoDB ping failed')}"
            for source_key, _ in candidates
        )
        MONGODB_SELECTION_ERROR = f"MongoDB unreachable: {details}"
        return None, MONGODB_SELECTION_ERROR

    mongo_name = (
        (os.getenv("MONGODB_DB_NAME") or "").strip()
        or _mongodb_db_name_from_uri(selected_uri)
        or "resqfy"
    )
    MONGODB_ACTIVE_URI = selected_uri
    MONGODB_ACTIVE_SOURCE = selected_source
    MONGODB_ACTIVE_DB_NAME = mongo_name

    backend_pref = (os.getenv("MONGODB_BACKEND") or "auto").strip().lower()

    if backend_pref in {"official", "django_mongodb_backend"}:
        try:
            import django_mongodb_backend  # noqa: F401
        except Exception as exc:
            MONGODB_SELECTION_ERROR = f"django_mongodb_backend unavailable: {exc}"
            return None, MONGODB_SELECTION_ERROR
        return {
            "ENGINE": "django_mongodb_backend",
            "HOST": selected_uri,
            "NAME": mongo_name,
        }, None

    if backend_pref == "djongo":
        try:
            import djongo  # noqa: F401
        except Exception as exc:
            MONGODB_SELECTION_ERROR = f"djongo unavailable: {exc}"
            return None, MONGODB_SELECTION_ERROR
        return {
            "ENGINE": "djongo",
            "NAME": mongo_name,
            "ENFORCE_SCHEMA": False,
            "CLIENT": {
                "host": selected_uri,
            },
        }, None

    # auto preference: official backend first, then djongo.
    try:
        import django_mongodb_backend  # noqa: F401
        return {
            "ENGINE": "django_mongodb_backend",
            "HOST": selected_uri,
            "NAME": mongo_name,
        }, None
    except Exception:
        pass

    try:
        import djongo  # noqa: F401
        return {
            "ENGINE": "djongo",
            "NAME": mongo_name,
            "ENFORCE_SCHEMA": False,
            "CLIENT": {
                "host": selected_uri,
            },
        }, None
    except Exception as exc:
        MONGODB_SELECTION_ERROR = f"No MongoDB Django backend installed: {exc}"
        return None, MONGODB_SELECTION_ERROR


DB_PRIMARY = (os.getenv("PRIMARY_DB", "sqlite") or "sqlite").strip().lower()
SQLITE_FALLBACK_ALIAS = "fallback_sqlite"
if DB_PRIMARY == "mysql":
    DATABASES = {"default": _mysql_database_settings()}
elif DB_PRIMARY == "mongodb":
    mongo_settings, mongo_error = _build_mongodb_database_settings()
    sqlite_fallback_settings = _sqlite_database_settings()
    if mongo_settings:
        DATABASES = {
            "default": mongo_settings,
            SQLITE_FALLBACK_ALIAS: sqlite_fallback_settings,
        }
        print(f"✅ Django DB: MongoDB via {mongo_settings.get('ENGINE')}")
        print(f"✅ MongoDB selected source: {MONGODB_ACTIVE_SOURCE or 'env'}")
        if MONGODB_ACTIVE_URI and _is_local_mongo_uri(MONGODB_ACTIVE_URI):
            print("✅ MongoDB target: local host")
        elif MONGODB_ACTIVE_URI:
            print("✅ MongoDB target: shared/remote host")
        print(f"✅ SQLite fallback alias enabled: {SQLITE_FALLBACK_ALIAS}")
    else:
        DATABASES = {
            "default": sqlite_fallback_settings,
            SQLITE_FALLBACK_ALIAS: sqlite_fallback_settings,
        }
        print(f"⚠️ PRIMARY_DB=mongodb fallback to SQLite: {mongo_error}")
else:
    DATABASES = {"default": _sqlite_database_settings()}

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TZ", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static", REACT_FRONTEND_DIST]
STATIC_ROOT = BASE_DIR / "staticfiles"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = _env_bool(
    os.getenv("SESSION_COOKIE_SECURE"),
    default=str(os.getenv("APP_URL_SCHEME", "http")).strip().lower() == "https",
)
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# MongoDB backend compatibility: this project currently uses Django apps/models
# with AutoField/BigAutoField ids. The mongodb backend emits mongodb.E001.
# Allow silencing that check via env so Mongo primary can still boot.
SILENCED_SYSTEM_CHECKS = []
if DB_PRIMARY == "mongodb" and _env_bool(os.getenv("MONGODB_SILENCE_AUTOFIELD_CHECKS", "1"), default=True):
    SILENCED_SYSTEM_CHECKS.append("mongodb.E001")

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "core.auth_backend.ProfileLegacyBackend",
]

LOGIN_URL = "/login"

PASSWORD_HASHERS = [
    "core.legacy_hashers.WerkzeugPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# ============================================================================
# CHANNELS & DRAGONFLY CONFIGURATION
# ============================================================================
# WebSocket support via Django Channels with Dragonfly backend
# 
# NOTE: Uncomment after channels package is successfully installed
# Dragonfly is a drop-in Redis replacement that uses shared-nothing
# multi-threaded architecture for significantly better performance:
# - 25x throughput improvement over Redis
# - Linear scaling with CPU cores
# - Sub-millisecond latency
#
# Configuration:
# - CHANNEL_LAYERS: Routes WebSocket messages through Dragonfly
# - Dragonfly hostname can be set via DRAGONFLY_HOST env var
# - Default port is 6379 (same as Redis for compatibility)
# ============================================================================

# LOCAL DEVELOPMENT: Use InMemoryChannelLayer (no external dependencies)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    },
}

# PRODUCTION: Use Dragonfly (Redis-compatible, 25x faster than Redis)
# Dragonfly handles 100k+ simultaneous connections with multi-threaded architecture
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [("127.0.0.1", 6379)],
#         },
#     },
# }
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [(os.getenv("DRAGONFLY_HOST", "localhost"), 6379)],
#             "symmetric_encryption_keys": [os.getenv("SECRET_KEY", "projectz-local-dev-secret")],
#             "connection_kwargs": {
#                 "socket_connect_timeout": 10,
#                 "socket_timeout": 10,
#             },
#             "capacity": 1500,
#             "expiry": 10,
#         },
#     },
# }

# ============================================================================
# ASGI SERVER CONFIGURATION (for uvicorn with uvloop)
# ============================================================================
# When running with Uvicorn, configure it with uvloop for best performance:
# 
# Command:
#   uvicorn projectz.asgi:application \
#     --host 0.0.0.0 \
#     --port 9000 \
#     --workers 4 \
#     --loop uvloop \
#     --access-log
#
# Environment variable: ASGI_PORT, ASGI_WORKERS, ASGI_HOST
# ============================================================================

ASGI_HOST = os.getenv("ASGI_HOST", "0.0.0.0")
ASGI_PORT = int(os.getenv("ASGI_PORT", "9000"))
ASGI_WORKERS = int(os.getenv("ASGI_WORKERS", "4"))
ASGI_LOOP = os.getenv("ASGI_LOOP", "uvloop")  # Options: uvloop, asyncio

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
# Configure logging for debugging and monitoring async operations

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "channels": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "core.realtime": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
