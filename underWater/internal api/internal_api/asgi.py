import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "internal_api.settings")

application = get_asgi_application()

try:
    from disaster_api.django_state import get_state

    get_state()
except Exception:
    pass
