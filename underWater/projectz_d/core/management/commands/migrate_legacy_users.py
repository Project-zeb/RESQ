import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from core.legacy_models import LegacyUser
from core.models import UserProfile


def _looks_like_werkzeug_hash(value):
    text = str(value or "").strip()
    if not text:
        return False
    return text.startswith("pbkdf2:") or text.startswith("scrypt:")


def _split_name(full_name):
    text = str(full_name or "").strip()
    if not text:
        return "", ""
    parts = text.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _unique_username(UserModel, base_username, legacy_id):
    base = (base_username or "").strip() or f"user_{legacy_id}"
    candidate = base[:150]
    if not UserModel.objects.filter(username=candidate).exists():
        return candidate
    suffix = f"_{legacy_id}"
    trimmed = (base[:150 - len(suffix)] or "user") + suffix
    candidate = trimmed
    if not UserModel.objects.filter(username=candidate).exists():
        return candidate
    counter = 1
    while True:
        suffix = f"_{legacy_id}_{counter}"
        candidate = (base[:150 - len(suffix)] or "user") + suffix
        if not UserModel.objects.filter(username=candidate).exists():
            return candidate
        counter += 1


class Command(BaseCommand):
    help = "Migrate legacy Users table into Django auth_user and UserProfile."

    def add_arguments(self, parser):
        parser.add_argument(
            "--drop-legacy",
            action="store_true",
            help="Drop legacy Users table after migration (dangerous; ensures DB has no FK dependencies).",
        )
        parser.add_argument(
            "--rename-legacy",
            action="store_true",
            help="Rename legacy Users table to Users_legacy after migration.",
        )

    def handle(self, *args, **options):
        drop_legacy = options.get("drop_legacy", False)
        rename_legacy = options.get("rename_legacy", False)
        if drop_legacy and rename_legacy:
            raise ValueError("Choose only one of --drop-legacy or --rename-legacy")

        legacy_table = self._resolve_legacy_table()
        if legacy_table:
            LegacyUser._meta.db_table = legacy_table

        fixed_admin_email = str(os.getenv("FIXED_ADMIN_EMAIL", "") or "").strip().lower()
        fixed_admin_username = str(os.getenv("FIXED_ADMIN_USERNAME", "") or "").strip().lower()
        store_plain = str(os.getenv("STORE_PLAIN_PASSWORDS", "true") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        UserModel = get_user_model()
        legacy_users = []
        if legacy_table:
            legacy_users = list(LegacyUser.objects.all())
            if not legacy_users:
                self.stdout.write(self.style.WARNING("No legacy users found; nothing to migrate."))
        else:
            self.stdout.write(self.style.WARNING("Legacy Users table not found; skipping legacy migration."))

        mapping = {}
        migrated = 0
        updated = 0

        if legacy_users:
            with transaction.atomic():
                for legacy in legacy_users:
                    profile = UserProfile.objects.select_related("user").filter(legacy_user_id=legacy.user_id).first()
                    user = profile.user if profile else None

                    if user is None and legacy.username:
                        user = UserModel.objects.filter(username=legacy.username).first()
                    if user is None and legacy.email_id:
                        user = UserModel.objects.filter(email__iexact=legacy.email_id).first()

                    created = False
                    if user is None:
                        username = _unique_username(UserModel, legacy.username, legacy.user_id)
                        user = UserModel.objects.create(
                            username=username,
                            email=str(legacy.email_id or ""),
                            is_active=not bool(legacy.is_blocked),
                        )
                        created = True

                    is_fixed_admin = (
                        bool(fixed_admin_email)
                        and bool(fixed_admin_username)
                        and str(legacy.email_id or "").strip().lower() == fixed_admin_email
                        and str(legacy.username or "").strip().lower() == fixed_admin_username
                    )
                    role_value = str(legacy.role or "USER").strip().upper()
                    is_admin = role_value == "ADMIN" or is_fixed_admin

                    first_name, last_name = _split_name(legacy.full_name)
                    update_fields = []
                    if legacy.email_id and user.email != legacy.email_id:
                        user.email = legacy.email_id
                        update_fields.append("email")
                    if first_name and user.first_name != first_name:
                        user.first_name = first_name
                        update_fields.append("first_name")
                    if last_name and user.last_name != last_name:
                        user.last_name = last_name
                        update_fields.append("last_name")
                    if user.is_staff != is_admin:
                        user.is_staff = is_admin
                        update_fields.append("is_staff")
                    if user.is_superuser != is_fixed_admin:
                        user.is_superuser = is_fixed_admin
                        update_fields.append("is_superuser")
                    if user.is_active != (not bool(legacy.is_blocked)):
                        user.is_active = not bool(legacy.is_blocked)
                        update_fields.append("is_active")

                    if legacy.password_plain:
                        user.set_password(legacy.password_plain)
                        update_fields.append("password")
                    elif legacy.password_hash:
                        if _looks_like_werkzeug_hash(legacy.password_hash):
                            user.set_unusable_password()
                            update_fields.append("password")
                        else:
                            user.set_password(legacy.password_hash)
                            update_fields.append("password")
                    elif not user.has_usable_password():
                        user.set_unusable_password()
                        update_fields.append("password")

                    if update_fields:
                        user.save(update_fields=update_fields)

                    profile_defaults = {
                        "role": "ADMIN" if is_admin else "USER",
                        "is_blocked": bool(legacy.is_blocked),
                        "must_change_password": bool(legacy.must_change_password),
                        "legacy_user_id": legacy.user_id,
                    }
                    profile, profile_created = UserProfile.objects.get_or_create(user=user, defaults=profile_defaults)

                    profile_update_fields = []
                    if profile.legacy_user_id != legacy.user_id:
                        profile.legacy_user_id = legacy.user_id
                        profile_update_fields.append("legacy_user_id")
                    if profile.role != ("ADMIN" if is_admin else "USER"):
                        profile.role = "ADMIN" if is_admin else "USER"
                        profile_update_fields.append("role")
                    if profile.is_blocked != bool(legacy.is_blocked):
                        profile.is_blocked = bool(legacy.is_blocked)
                        profile_update_fields.append("is_blocked")
                    if profile.must_change_password != bool(legacy.must_change_password):
                        profile.must_change_password = bool(legacy.must_change_password)
                        profile_update_fields.append("must_change_password")
                    if legacy.phone and profile.phone != legacy.phone:
                        profile.phone = legacy.phone
                        profile_update_fields.append("phone")
                    if store_plain and legacy.password_plain and profile.password_plain != legacy.password_plain:
                        profile.password_plain = legacy.password_plain
                        profile_update_fields.append("password_plain")
                    if not store_plain and profile.password_plain:
                        profile.password_plain = None
                        profile_update_fields.append("password_plain")
                    if legacy.password_hash and _looks_like_werkzeug_hash(legacy.password_hash):
                        if profile.legacy_password_hash != legacy.password_hash:
                            profile.legacy_password_hash = legacy.password_hash
                            profile_update_fields.append("legacy_password_hash")
                    elif profile.legacy_password_hash:
                        profile.legacy_password_hash = None
                        profile_update_fields.append("legacy_password_hash")

                    if profile_update_fields:
                        profile.save(update_fields=profile_update_fields)

                    mapping[legacy.user_id] = user.id
                    if created or profile_created:
                        migrated += 1
                    else:
                        updated += 1

        if mapping:
            self._update_disaster_foreign_keys(mapping)

        self._sanitize_overlong_passwords()

        if legacy_users:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Migration complete. Created: {migrated}, Updated: {updated}, Mapped: {len(mapping)}"
                )
            )

        if rename_legacy:
            self._rename_legacy_table()
        elif drop_legacy:
            self._drop_legacy_table()

    def _resolve_legacy_table(self):
        try:
            tables = set(connection.introspection.table_names())
        except Exception:
            return None
        if "Users" in tables:
            return "Users"
        if "Users_legacy" in tables:
            return "Users_legacy"
        return None

    def _update_disaster_foreign_keys(self, mapping):
        try:
            with connection.cursor() as cursor:
                for legacy_id, new_id in mapping.items():
                    cursor.execute(
                        "UPDATE Disasters SET reporter_id = %s WHERE reporter_id = %s",
                        [new_id, legacy_id],
                    )
                    cursor.execute(
                        "UPDATE Disasters SET admin_id = %s WHERE admin_id = %s",
                        [new_id, legacy_id],
                    )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not update Disasters IDs: {exc}"))

    def _sanitize_overlong_passwords(self):
        UserModel = get_user_model()
        updated = 0
        for user in UserModel.objects.all():
            password_value = str(user.password or "")
            if not password_value:
                continue
            if len(password_value) <= 128:
                continue
            profile = UserProfile.objects.filter(user=user).first()
            if profile is None:
                profile = UserProfile.objects.create(
                    user=user,
                    role="ADMIN" if (user.is_staff or user.is_superuser) else "USER",
                    is_blocked=not user.is_active,
                )
            if password_value.startswith("werkzeug$"):
                profile.legacy_password_hash = password_value.split("$", 1)[1]
            else:
                profile.legacy_password_hash = password_value
            profile.save(update_fields=["legacy_password_hash"])
            user.set_unusable_password()
            user.save(update_fields=["password"])
            updated += 1
        if updated:
            self.stdout.write(self.style.SUCCESS(f"Sanitized {updated} overlong password hashes"))

    def _rename_legacy_table(self):
        try:
            with connection.cursor() as cursor:
                vendor = connection.vendor
                if vendor == "sqlite":
                    cursor.execute("ALTER TABLE Users RENAME TO Users_legacy")
                else:
                    cursor.execute("RENAME TABLE Users TO Users_legacy")
            self.stdout.write(self.style.SUCCESS("Renamed Users table to Users_legacy"))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not rename Users table: {exc}"))

    def _drop_legacy_table(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE Users")
            self.stdout.write(self.style.SUCCESS("Dropped Users table"))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not drop Users table: {exc}"))
