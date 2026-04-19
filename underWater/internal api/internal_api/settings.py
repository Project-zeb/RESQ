import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "internal-api-local-dev-secret")


def _env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = _env_bool(os.getenv("DJANGO_DEBUG", os.getenv("DEBUG", "0")), default=False)

ALLOWED_HOSTS = ["*"]
APPEND_SLASH = False

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "disaster_api.middleware.ApiKeyMiddleware",
]

ROOT_URLCONF = "internal_api.urls"

TEMPLATES = []

WSGI_APPLICATION = "internal_api.wsgi.application"

sqlite_path = os.getenv("INTERNAL_DJANGO_DB_PATH", "database.db")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / sqlite_path),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TZ", "UTC")
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
