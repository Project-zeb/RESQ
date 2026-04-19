import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projectz.settings")

application = get_wsgi_application()

try:
    from projectz.autostart import start_internal_api_if_needed

    start_internal_api_if_needed()
except Exception:
    pass
