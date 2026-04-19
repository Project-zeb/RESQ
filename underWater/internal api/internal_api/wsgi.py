import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "internal_api.settings")

application = get_wsgi_application()

try:
    from disaster_api.django_state import get_state

    get_state()
except Exception:
    pass
