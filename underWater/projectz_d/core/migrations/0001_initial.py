from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("legacy_user_id", models.IntegerField(blank=True, null=True, unique=True)),
                ("phone", models.CharField(blank=True, max_length=20, null=True)),
                (
                    "role",
                    models.CharField(
                        choices=[("ADMIN", "ADMIN"), ("USER", "USER")],
                        default="USER",
                        max_length=10,
                    ),
                ),
                ("is_blocked", models.BooleanField(default=False)),
                ("must_change_password", models.BooleanField(default=False)),
                ("password_plain", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
