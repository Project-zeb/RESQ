from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.models import AlertSnapshot, Disaster, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


class UserAdmin(DjangoUserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-id",)


UserModel = get_user_model()
try:
    admin.site.unregister(UserModel)
except admin.sites.NotRegistered:
    pass

admin.site.register(UserModel, UserAdmin)


@admin.register(Disaster)
class DisasterAdmin(admin.ModelAdmin):
    list_display = ("disaster_id", "disaster_type", "verify_status", "created_at", "reporter", "admin")
    list_filter = ("verify_status", "disaster_type", "media_type")
    search_fields = ("disaster_type", "description")
    ordering = ("-disaster_id",)


@admin.register(AlertSnapshot)
class AlertSnapshotAdmin(admin.ModelAdmin):
    list_display = ("snapshot_key", "saved_at_utc", "source_mode", "alerts_count")
    list_filter = ("source_mode",)
    ordering = ("-saved_at_utc",)
