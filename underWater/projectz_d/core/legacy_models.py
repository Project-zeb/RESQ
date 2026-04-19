from django.db import models


class LegacyUser(models.Model):
    user_id = models.AutoField(primary_key=True, db_column="User_id")
    full_name = models.CharField(max_length=100)
    username = models.CharField(max_length=30, unique=True)
    email_id = models.CharField(max_length=100, unique=True)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(null=True, blank=True)
    password_hash = models.CharField(max_length=255)
    password_plain = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(max_length=10, default="USER")
    must_change_password = models.BooleanField(default=False)
    phone = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "Users"

    def __str__(self):
        return f"{self.username} ({self.user_id})"
