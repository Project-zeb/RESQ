from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(sender, instance, created, **kwargs):
    if not created:
        return
    UserProfile.objects.get_or_create(
        user=instance,
        defaults={
            "role": "ADMIN" if (instance.is_staff or instance.is_superuser) else "USER",
            "is_blocked": False,
            "must_change_password": False,
        },
    )
