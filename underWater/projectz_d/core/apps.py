from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from core import signals  # noqa: F401
        from core import django_compat

        django_compat.patch_basecontext_copy()

        try:
            from projectz.autostart import start_internal_api_if_needed

            start_internal_api_if_needed()
        except Exception:
            pass
