"""
ASGI config for projectz project.

Handles WebSocket connections for real-time communication.
For standard HTTP traffic, use WSGI (Gunicorn) on a separate process.

Architecture:
- ASGI (this file): Handles WebSocket connections on port 9000 (Uvicorn)
- WSGI (wsgi.py): Handles HTTP requests on port 8000 (Gunicorn)
- Nginx: Routes /ws/* to ASGI, other requests to WSGI

This hybrid approach ensures:
- WebSocket persistence and low latency
- Legacy synchronous code stability
- Horizontal scalability
"""

import os
import django

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projectz.settings")

# Initialize Django ASGI application early to ensure AppRegistry is populated
django.setup()

# Import websocket patterns AFTER django.setup()
from core.realtime.routing import websocket_urlpatterns
from core.realtime.auth import JWTAuthMiddleware

# Get the standard Django ASGI application
django_asgi_app = get_asgi_application()

# ProtocolTypeRouter:
# - "http": Uses standard Django WSGI application
# - "websocket": Routes WebSocket connections through JWT auth to consumers
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})

try:
    from projectz.autostart import start_internal_api_if_needed

    start_internal_api_if_needed()
except Exception:
    pass
