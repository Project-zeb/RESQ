def create_app(*args, **kwargs):
    import os

    from django.core.wsgi import get_wsgi_application

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "internal_api.settings")
    return get_wsgi_application()


__all__ = ["create_app"]
