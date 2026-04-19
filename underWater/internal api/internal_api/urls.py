from django.urls import path

from disaster_api import django_views

urlpatterns = [
    path("health", django_views.health, name="health"),
    path("api/alerts", django_views.get_alerts, name="get_alerts"),
    path("api/alerts/<int:alert_id>", django_views.get_alert, name="get_alert"),
    path("api/sources/status", django_views.get_source_status, name="get_source_status"),
    path("api/sync", django_views.run_sync, name="run_sync"),
    path("api/auth/token", django_views.create_access_token, name="create_access_token"),
    path("api/admin/keys", django_views.get_api_keys, name="get_api_keys"),
    path("api/admin/keys/rotate", django_views.rotate_api_keys, name="rotate_api_keys"),
]
