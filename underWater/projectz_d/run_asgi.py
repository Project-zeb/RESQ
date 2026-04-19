#!/usr/bin/env python
"""
Run the ASGI server for WebSocket support.

Usage:
  python run_asgi.py

Environment variables (optional):
  ASGI_HOST, ASGI_PORT, ASGI_WORKERS, ASGI_LOOP, ASGI_LOG_LEVEL
"""
import os
import uvicorn

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projectz.settings")


def main() -> None:
    host = os.getenv("ASGI_HOST", "0.0.0.0")
    port = int(os.getenv("ASGI_PORT", "9000"))
    workers = int(os.getenv("ASGI_WORKERS", "1"))
    loop = os.getenv("ASGI_LOOP", "uvloop")
    if loop == "uvloop":
        try:
            import uvloop  # noqa: F401
        except Exception:
            loop = "asyncio"
    log_level = os.getenv("ASGI_LOG_LEVEL", "info")

    uvicorn.run(
        "projectz.asgi:application",
        host=host,
        port=port,
        workers=workers,
        loop=loop,
        log_level=log_level,
        access_log=True,
    )


if __name__ == "__main__":
    main()
