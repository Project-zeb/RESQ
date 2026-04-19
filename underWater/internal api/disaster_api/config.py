import os
from dataclasses import dataclass


def _to_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_float(value: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _sqlite_url_from_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    return f"sqlite:///{abs_path}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    ndma_cap_url: str
    ogd_dataset_url: str
    ogd_api_key: str
    mosdac_endpoint_url: str
    mosdac_api_token: str
    http_timeout_seconds: int
    poll_interval_seconds: int
    enable_scheduler: bool
    run_sync_on_startup: bool
    request_retries: int
    request_backoff_seconds: float
    source_stagger_seconds: float
    enable_collector_snapshot: bool
    collector_alert_json: str
    require_api_key: bool
    internal_api_key: str
    api_key_header: str
    admin_api_key: str
    admin_api_key_header: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expires_minutes: int
    jwt_max_expires_minutes: int
    jwt_issuer: str
    jwt_audience: str
    server_host: str
    server_port: int
    server_debug: bool


def load_settings() -> Settings:
    package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    default_db_path = os.path.join(package_root, "database.db")
    db_path = os.getenv("DB_PATH", default_db_path)
    database_url = os.getenv("DATABASE_URL", "").strip() or _sqlite_url_from_path(db_path)

    return Settings(
        database_url=database_url,
        ndma_cap_url=os.getenv("NDMA_CAP_URL", "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"),
        ogd_dataset_url=os.getenv("OGD_DATASET_URL", "").strip(),
        ogd_api_key=os.getenv("OGD_API_KEY", "").strip(),
        mosdac_endpoint_url=os.getenv("MOSDAC_ENDPOINT_URL", "").strip(),
        mosdac_api_token=os.getenv("MOSDAC_API_TOKEN", "").strip(),
        http_timeout_seconds=_to_int(os.getenv("HTTP_TIMEOUT_SECONDS"), 20),
        poll_interval_seconds=_to_int(os.getenv("POLL_INTERVAL_SECONDS"), 300),
        enable_scheduler=_to_bool(os.getenv("ENABLE_SCHEDULER"), True),
        run_sync_on_startup=_to_bool(os.getenv("RUN_SYNC_ON_STARTUP"), True),
        request_retries=_to_int(os.getenv("REQUEST_RETRIES"), 5),
        request_backoff_seconds=_to_float(os.getenv("REQUEST_BACKOFF_SECONDS"), 1.0),
        source_stagger_seconds=_to_float(os.getenv("SOURCE_STAGGER_SECONDS"), 2.0),
        enable_collector_snapshot=_to_bool(os.getenv("ENABLE_COLLECTOR_SNAPSHOT"), True),
        collector_alert_json=os.getenv("COLLECTOR_ALERT_JSON", "").strip(),
        require_api_key=_to_bool(os.getenv("REQUIRE_API_KEY"), True),
        internal_api_key=os.getenv("INTERNAL_API_KEY", "").strip(),
        api_key_header=os.getenv("API_KEY_HEADER", "X-Internal-API-Key").strip() or "X-Internal-API-Key",
        admin_api_key=os.getenv("ADMIN_API_KEY", "").strip(),
        admin_api_key_header=os.getenv("ADMIN_API_KEY_HEADER", "X-Admin-API-Key").strip() or "X-Admin-API-Key",
        jwt_secret=os.getenv("JWT_SECRET", "").strip(),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256",
        jwt_expires_minutes=_to_int(os.getenv("JWT_EXPIRES_MINUTES"), 30),
        jwt_max_expires_minutes=_to_int(os.getenv("JWT_MAX_EXPIRES_MINUTES"), 240),
        jwt_issuer=os.getenv("JWT_ISSUER", "internal-disaster-api").strip() or "internal-disaster-api",
        jwt_audience=os.getenv("JWT_AUDIENCE", "internal-clients").strip() or "internal-clients",
        server_host=os.getenv("INTERNAL_API_HOST", "0.0.0.0"),
        server_port=_to_int(os.getenv("INTERNAL_API_PORT"), 5100),
        server_debug=_to_bool(os.getenv("INTERNAL_API_DEBUG"), False),
    )
