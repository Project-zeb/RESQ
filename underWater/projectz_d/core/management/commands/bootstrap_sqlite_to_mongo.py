from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError, ProgrammingError

from core.models import Disaster, UserProfile


def _is_mongo_engine(engine):
    text = str(engine or "").lower()
    return "mongodb" in text or "djongo" in text


def _is_sqlite_engine(engine):
    return "sqlite3" in str(engine or "").lower()


class Command(BaseCommand):
    help = (
        "One-time bootstrap from SQLite fallback to MongoDB primary. "
        "Copies auth users, user profiles, and disasters with upsert logic."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=getattr(settings, "SQLITE_FALLBACK_ALIAS", "fallback_sqlite"),
            help="Source DB alias (default: fallback_sqlite).",
        )
        parser.add_argument(
            "--target",
            default="default",
            help="Target DB alias (default: default).",
        )
        parser.add_argument(
            "--skip-disasters",
            action="store_true",
            help="Skip copying disasters.",
        )

    def handle(self, *args, **options):
        source_alias = str(options.get("source") or "fallback_sqlite").strip()
        target_alias = str(options.get("target") or "default").strip()
        skip_disasters = bool(options.get("skip_disasters"))

        if source_alias not in connections:
            raise CommandError(f"Source alias '{source_alias}' is not configured.")
        if target_alias not in connections:
            raise CommandError(f"Target alias '{target_alias}' is not configured.")

        source_engine = str(connections[source_alias].settings_dict.get("ENGINE") or "")
        target_engine = str(connections[target_alias].settings_dict.get("ENGINE") or "")

        if not _is_sqlite_engine(source_engine):
            raise CommandError(
                f"Source alias '{source_alias}' is not SQLite (ENGINE={source_engine})."
            )
        if not _is_mongo_engine(target_engine):
            raise CommandError(
                f"Target alias '{target_alias}' is not MongoDB (ENGINE={target_engine})."
            )

        UserModel = get_user_model()
        user_id_map = {}

        users_created = 0
        users_updated = 0
        profiles_created = 0
        profiles_updated = 0
        profiles_skipped = 0
        disasters_created = 0
        disasters_updated = 0
        disasters_skipped = 0

        source_users = list(UserModel.objects.using(source_alias).all())
        self.stdout.write(f"Source users: {len(source_users)}")
        for src_user in source_users:
            target_user = UserModel.objects.using(target_alias).filter(username=src_user.username).first()
            if target_user is None and getattr(src_user, "email", None):
                target_user = (
                    UserModel.objects.using(target_alias)
                    .filter(email__iexact=src_user.email)
                    .first()
                )

            if target_user is None:
                create_payload = {
                    "username": src_user.username,
                    "email": src_user.email,
                    "password": src_user.password,
                    "first_name": src_user.first_name,
                    "last_name": src_user.last_name,
                    "is_active": src_user.is_active,
                    "is_staff": src_user.is_staff,
                    "is_superuser": src_user.is_superuser,
                    "last_login": src_user.last_login,
                    "date_joined": src_user.date_joined,
                }
                if not UserModel.objects.using(target_alias).filter(pk=src_user.pk).exists():
                    create_payload["id"] = src_user.pk
                target_user = UserModel(**create_payload)
                target_user.save(using=target_alias)
                users_created += 1
            else:
                update_fields = []
                for field_name in (
                    "email",
                    "password",
                    "first_name",
                    "last_name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "last_login",
                    "date_joined",
                ):
                    src_value = getattr(src_user, field_name)
                    if getattr(target_user, field_name) != src_value:
                        setattr(target_user, field_name, src_value)
                        update_fields.append(field_name)
                if update_fields:
                    target_user.save(using=target_alias, update_fields=update_fields)
                    users_updated += 1

            user_id_map[src_user.pk] = target_user.pk

        source_profiles = list(UserProfile.objects.using(source_alias).all())
        self.stdout.write(f"Source profiles: {len(source_profiles)}")
        for src_profile in source_profiles:
            target_user_id = user_id_map.get(src_profile.user_id)
            if not target_user_id:
                profiles_skipped += 1
                continue

            target_profile = UserProfile.objects.using(target_alias).filter(user_id=target_user_id).first()
            profile_payload = {
                "legacy_user_id": src_profile.legacy_user_id,
                "phone": src_profile.phone,
                "role": src_profile.role,
                "is_blocked": src_profile.is_blocked,
                "must_change_password": src_profile.must_change_password,
                "password_plain": src_profile.password_plain,
                "legacy_password_hash": src_profile.legacy_password_hash,
            }

            if target_profile is None:
                target_profile = UserProfile(user_id=target_user_id, **profile_payload)
                target_profile.save(using=target_alias)
                profiles_created += 1
            else:
                update_fields = []
                for field_name, src_value in profile_payload.items():
                    if getattr(target_profile, field_name) != src_value:
                        setattr(target_profile, field_name, src_value)
                        update_fields.append(field_name)
                if update_fields:
                    target_profile.save(using=target_alias, update_fields=update_fields)
                    profiles_updated += 1

        if not skip_disasters:
            try:
                source_disasters = list(Disaster.objects.using(source_alias).all())
            except (OperationalError, ProgrammingError):
                source_disasters = []
            self.stdout.write(f"Source disasters: {len(source_disasters)}")

            for src_disaster in source_disasters:
                reporter_target_id = user_id_map.get(src_disaster.reporter_id)
                if not reporter_target_id:
                    disasters_skipped += 1
                    continue
                admin_target_id = user_id_map.get(src_disaster.admin_id) if src_disaster.admin_id else None

                target_disaster = (
                    Disaster.objects.using(target_alias)
                    .filter(disaster_id=src_disaster.disaster_id)
                    .first()
                )
                disaster_payload = {
                    "verify_status": src_disaster.verify_status,
                    "created_at": src_disaster.created_at,
                    "media": src_disaster.media,
                    "media_type": src_disaster.media_type,
                    "reporter_id": reporter_target_id,
                    "admin_id": admin_target_id,
                    "disaster_type": src_disaster.disaster_type,
                    "description": src_disaster.description,
                    "latitude": src_disaster.latitude,
                    "longitude": src_disaster.longitude,
                    "address_text": src_disaster.address_text,
                }

                if target_disaster is None:
                    target_disaster = Disaster(disaster_id=src_disaster.disaster_id, **disaster_payload)
                    target_disaster.save(using=target_alias)
                    disasters_created += 1
                else:
                    update_fields = []
                    for field_name, src_value in disaster_payload.items():
                        if getattr(target_disaster, field_name) != src_value:
                            setattr(target_disaster, field_name, src_value)
                            update_fields.append(field_name)
                    if update_fields:
                        target_disaster.save(using=target_alias, update_fields=update_fields)
                        disasters_updated += 1

        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))
        self.stdout.write(
            self.style.SUCCESS(
                "Users created/updated: "
                f"{users_created}/{users_updated}; "
                "Profiles created/updated: "
                f"{profiles_created}/{profiles_updated} (skipped={profiles_skipped}); "
                "Disasters created/updated/skipped: "
                f"{disasters_created}/{disasters_updated}/{disasters_skipped}"
            )
        )
