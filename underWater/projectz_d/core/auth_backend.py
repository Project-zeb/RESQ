import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from werkzeug.security import check_password_hash

from core.models import UserProfile


def _looks_like_werkzeug_hash(value):
    text = str(value or "").strip()
    if not text:
        return False
    return text.startswith("pbkdf2:") or text.startswith("scrypt:")


def _verify_legacy_hash(stored_hash, provided_password):
    stored_value = str(stored_hash or "")
    provided_value = str(provided_password or "")
    if not stored_value:
        return False
    if _looks_like_werkzeug_hash(stored_value):
        try:
            return check_password_hash(stored_value, provided_value)
        except Exception:
            return False
    return secrets.compare_digest(stored_value, provided_value)


class ProfileLegacyBackend(ModelBackend):
    """Authenticate against legacy hashes stored on UserProfile."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None

        UserModel = get_user_model()
        user = UserModel.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
        if not user or not user.is_active:
            return None

        profile = UserProfile.objects.filter(user=user).first()
        if not profile or not profile.legacy_password_hash:
            return None

        if not _verify_legacy_hash(profile.legacy_password_hash, password):
            return None

        # Upgrade to Django password hash after successful login.
        user.set_password(password)
        user.save(update_fields=["password"])
        profile.legacy_password_hash = None
        profile.save(update_fields=["legacy_password_hash"])
        return user
