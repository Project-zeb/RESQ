import os

_LOCK_PATH = "/tmp/projectz_internal_api_autostart.lock"
_LOCK_HANDLE = None
_AUTOSTARTED_PID = None


def _env_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_falsey(value: str) -> bool:
    return str(value or "").strip().lower() in {"0", "false", "no", "off"}


def _acquire_lock():
    global _LOCK_HANDLE
    if _LOCK_HANDLE is not None:
        return _LOCK_HANDLE
    try:
        import fcntl
    except Exception:
        return None

    lock_file = open(_LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        lock_file.close()
        return None
    _LOCK_HANDLE = lock_file
    return lock_file


def start_internal_api_if_needed():
    global _AUTOSTARTED_PID

    should_autostart = not _env_falsey(os.getenv("INTERNAL_API_AUTOSTART"))
    should_sync_on_startup = not _env_falsey(os.getenv("INTERNAL_API_SYNC_ON_STARTUP", "true"))

    if not should_autostart and not should_sync_on_startup:
        return
    if _env_truthy(os.getenv("PROJECTZ_DISABLE_INTERNAL_AUTOSTART")) and not should_sync_on_startup:
        return

    current_pid = os.getpid()
    if _AUTOSTARTED_PID == current_pid:
        return

    _AUTOSTARTED_PID = current_pid

    lock = _acquire_lock()
    # Sync-on-startup should still run even if another process holds the lock.
    # The lock mainly protects process auto-start races.
    allow_autostart = lock is not None

    try:
        from core import views

        if should_autostart and allow_autostart:
            views.ensure_internal_api_running()
        if should_sync_on_startup:
            views.sync_internal_api_if_needed(force=True)
    except Exception:
        # Avoid crashing startup if internal API is unavailable.
        return
