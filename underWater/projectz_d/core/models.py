from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("ADMIN", "ADMIN"),
        ("USER", "USER"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    legacy_user_id = models.IntegerField(null=True, blank=True, unique=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="USER")
    is_blocked = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    password_plain = models.CharField(max_length=255, null=True, blank=True)
    legacy_password_hash = models.CharField(max_length=512, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} profile"


class Disaster(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("video", "video"),
        ("image", "image"),
    ]

    disaster_id = models.AutoField(primary_key=True, db_column="Disaster_id")
    verify_status = models.BooleanField(default=False)
    created_at = models.DateTimeField(null=True, blank=True)
    media = models.BinaryField(null=True, blank=True)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, null=True, blank=True)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="reporter_id",
        related_name="reported_disasters",
        db_constraint=False,
    )
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        db_column="admin_id",
        related_name="verified_disasters",
        null=True,
        blank=True,
        db_constraint=False,
    )
    disaster_type = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    address_text = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "Disasters"

    def __str__(self):
        return f"{self.disaster_type} #{self.disaster_id}"


class AlertSnapshot(models.Model):
    snapshot_key = models.CharField(max_length=128, primary_key=True)
    saved_at_utc = models.CharField(max_length=32)
    scope = models.CharField(max_length=32, null=True, blank=True)
    coverage_filter = models.CharField(max_length=32, null=True, blank=True)
    source_mode = models.CharField(max_length=64, null=True, blank=True)
    payload_json = models.TextField()
    alerts_count = models.IntegerField(default=0)

    class Meta:
        managed = True
        db_table = "AlertSnapshots"

    def __str__(self):
        return f"{self.snapshot_key} ({self.alerts_count})"


# ============================================================================
# Real-Time WebSocket Models (Channels)
# ============================================================================
# These models support the new WebSocket infrastructure for real-time
# alerts, notifications, and live data updates via Django Channels.
# ============================================================================


class Alert(models.Model):
    """
    Real-time alert model for WebSocket broadcasts.
    
    Stores user-generated or system alerts that are broadcast
    to connected WebSocket clients in real-time.
    """
    ALERT_TYPE_CHOICES = [
        ("DISASTER", "Disaster Report"),
        ("SOS", "SOS Request"),
        ("UPDATE", "Status Update"),
        ("WARNING", "System Warning"),
        ("INFO", "Information"),
    ]
    
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="realtime_alerts",
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    content = models.TextField()
    location = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["alert_type", "-created_at"]),
        ]
    
    def __str__(self):
        return f"{self.alert_type} by {self.user.username} at {self.created_at}"


class Notification(models.Model):
    """
    User notification model for real-time delivery via WebSocket.
    
    Personalized notifications that are sent only to specific users
    through their individual WebSocket connections.
    """
    NOTIFICATION_TYPE_CHOICES = [
        ("ALERT", "Alert Notification"),
        ("MESSAGE", "Direct Message"),
        ("SYSTEM", "System Notification"),
        ("REMINDER", "Reminder"),
    ]
    
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]
    
    def __str__(self):
        return f"{self.notification_type} for {self.user.username}: {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read and update timestamp."""
        self.is_read = True
        self.read_at = timezone.now()
        self.save()


class WebSocketSession(models.Model):
    """
    Track active WebSocket connections for analytics and monitoring.
    
    Useful for:
    - Tracking concurrent users
    - Monitoring connection patterns
    - Analytics and debugging
    """
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="websocket_sessions",
        null=True,
        blank=True,
    )
    channel_name = models.CharField(max_length=255, unique=True)
    connection_type = models.CharField(
        max_length=20,
        choices=[("realtime", "Real-time"), ("notifications", "Notifications")],
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ["-connected_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["connection_type", "is_active"]),
        ]
    
    def __str__(self):
        return f"{self.connection_type} session for {self.user} ({self.id})"
    
    def disconnect(self):
        """Mark session as disconnected."""
        self.is_active = False
        self.disconnected_at = timezone.now()
        self.save()

