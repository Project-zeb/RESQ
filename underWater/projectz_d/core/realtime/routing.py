"""
WebSocket URL routing for real-time consumers.

Maps WebSocket connections to appropriate async consumers
based on the requested path.

ASGI routing configuration:
- /ws/realtime/ -> RealTimeConsumer
- /ws/alerts/ -> RealTimeConsumer (alias)
- /ws/notifications/ -> NotificationConsumer
"""

from django.urls import re_path
from core.realtime.consumers import RealTimeConsumer, NotificationConsumer

websocket_urlpatterns = [
    # Main real-time WebSocket endpoint
    re_path(r'ws/realtime/$', RealTimeConsumer.as_asgi()),

    # Alerts alias (legacy/frontend convenience)
    re_path(r'ws/alerts/$', RealTimeConsumer.as_asgi()),
    
    # User-specific notifications endpoint
    re_path(r'ws/notifications/$', NotificationConsumer.as_asgi()),
]
