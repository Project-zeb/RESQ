"""
Asynchronous WebSocket consumers for real-time communication.

These consumers handle WebSocket connections for alerts, notifications,
and live updates with proper authentication and message broadcasting.

IMPORTANT: All database operations must use @database_sync_to_async
to prevent blocking the event loop.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
import logging

logger = logging.getLogger(__name__)


class RealTimeConsumer(AsyncWebsocketConsumer):
    """
    Main real-time WebSocket consumer for handling persistent connections.
    
    Supports:
    - Real-time alerts and notifications
    - Live data broadcasts
    - Group-based messaging
    
    Architecture:
    - Uses Channels groups for scalable broadcasting
    - Thread-safe database operations via @database_sync_to_async
    - Graceful disconnection with cleanup
    """
    
    async def connect(self):
        """
        Handle WebSocket connection.
        
        The user is already authenticated via JWTAuthMiddleware
        and available in scope['user'].
        """
        self.user = self.scope.get("user", AnonymousUser())
        
        # Group name for broadcasting to all connected users
        self.global_group = "global_broadcast"
        
        # User-specific group for private messages
        if self.user and self.user.is_authenticated:
            self.user_group = f"user_{self.user.id}"
            # Only use channel layer if it's available (Redis, etc.)
            if self.channel_layer:
                await self.channel_layer.group_add(self.user_group, self.channel_name)
        else:
            self.user_group = None
        
        # Add to global group for broadcasts (only if channel layer exists)
        if self.channel_layer:
            await self.channel_layer.group_add(self.global_group, self.channel_name)
        
        await self.accept()
        logger.info(f"WebSocket connection established for user: {self.user}")

    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        
        CRITICAL: Must clean up group memberships to prevent memory leaks.
        """
        # Remove from global group (only if channel layer exists)
        if self.channel_layer:
            await self.channel_layer.group_discard(self.global_group, self.channel_name)
        
        # Remove from user-specific group
        if self.user_group and self.channel_layer:
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        
        logger.info(f"WebSocket disconnected for user: {self.user}, code: {close_code}")

    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages.
        
        Expected message format:
        {
            "type": "message|alert|update",
            "data": {...},
            "target": "global|user" (optional, defaults to global)
        }
        """
        try:
            data = json.loads(text_data)

            # Accept both "message_type" and legacy "type" fields
            message_type = data.get("message_type") or data.get("type") or "message"
            target = data.get("target", "global")

            # Back-compat: allow flat payloads like {"message": "..."} or {"content": "..."}
            if "data" not in data:
                inferred = {}
                if "message" in data:
                    inferred["message"] = data.get("message")
                if "content" in data:
                    inferred["content"] = data.get("content")
                if inferred:
                    data["data"] = inferred
            
            if message_type == "message" and target == "global":
                await self._handle_global_message(data)
            elif message_type == "alert":
                await self._handle_alert(data)
            elif message_type == "update":
                await self._handle_update(data)
            else:
                await self.send_error("Invalid message type")
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
            logger.warning(f"Invalid JSON received from user: {self.user}")
        except Exception as e:
            await self.send_error(f"Error processing message: {str(e)}")
            logger.error(f"Error in receive: {str(e)}", exc_info=True)

    async def _handle_global_message(self, data):
        """
        Handle global broadcast messages.
        
        Authorization: Authenticated users only
        """
        if not (self.user and self.user.is_authenticated):
            await self.send_error("Authentication required")
            return
        
        message_data = data.get("data", {})
        message_text = message_data.get("message") or message_data.get("content")
        
        if self.channel_layer:
            await self.channel_layer.group_send(
                self.global_group,
                {
                    "type": "broadcast_message",
                    "message": message_text,
                    "user": self.user.username,
                    "user_id": self.user.id,
                }
            )

    async def _handle_alert(self, data):
        """
        Handle alert messages with persistence.
        
        Authorization: Authenticated users only
        """
        if not (self.user and self.user.is_authenticated):
            await self.send_error("Authentication required")
            return
        
        alert_data = data.get("data", {})
        
        # Persist alert to database asynchronously
        await self._save_alert(
            user_id=self.user.id,
            alert_type=alert_data.get("type"),
            content=alert_data.get("content"),
            location=alert_data.get("location")
        )
        
        # Broadcast alert to global group
        if self.channel_layer:
            await self.channel_layer.group_send(
                self.global_group,
                {
                    "type": "broadcast_alert",
                    "alert_type": alert_data.get("type"),
                    "content": alert_data.get("content"),
                    "location": alert_data.get("location"),
                    "user_id": self.user.id,
                    "timestamp": str(__import__('django.utils.timezone', fromlist=['now']).now()),
                }
            )

    async def _handle_update(self, data):
        """
        Handle live update messages.
        
        Used for real-time data synchronization.
        """
        update_data = data.get("data", {})
        
        # Send to user-specific group if authenticated
        if self.user_group and self.channel_layer:
            await self.channel_layer.group_send(
                self.user_group,
                {
                    "type": "broadcast_update",
                    "update": update_data,
                }
            )

    @database_sync_to_async
    def _save_alert(self, user_id, alert_type, content, location):
        """
        Persist alert to database.
        
        Database operations must be wrapped with @database_sync_to_async
        to prevent blocking the async event loop.
        """
        try:
            from core.models import Alert
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            Alert.objects.create(
                user=user,
                alert_type=alert_type,
                content=content,
                location=location,
            )
            logger.info(f"Alert saved for user {user_id}: {alert_type}")
        except Exception as e:
            logger.error(f"Error saving alert: {str(e)}", exc_info=True)

    async def send_error(self, error_message):
        """Send error message to client."""
        await self.send(text_data=json.dumps({
            "type": "error",
            "message": error_message
        }))

    # Group event handlers (type matches the routing event type)

    async def broadcast_message(self, event):
        """
        Broadcast message to WebSocket client.
        
        Called by group_send() with type='broadcast_message'
        """
        await self.send(text_data=json.dumps({
            "type": "message",
            "message": event["message"],
            "user": event.get("user"),
            "user_id": event.get("user_id"),
        }))

    async def broadcast_alert(self, event):
        """
        Broadcast alert to WebSocket client.
        
        Called by group_send() with type='broadcast_alert'
        """
        await self.send(text_data=json.dumps({
            "type": "alert",
            "alert_type": event.get("alert_type"),
            "content": event.get("content"),
            "location": event.get("location"),
            "user_id": event.get("user_id"),
            "timestamp": event.get("timestamp"),
        }))

    async def broadcast_update(self, event):
        """
        Broadcast update to WebSocket client.
        
        Called by group_send() with type='broadcast_update'
        """
        await self.send(text_data=json.dumps({
            "type": "update",
            "data": event.get("update"),
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Specialized consumer for user-specific notifications.
    
    Only authenticated users can connect.
    Groups notifications by user_id for privacy.
    """
    
    async def connect(self):
        """Connect to user-specific notification channel."""
        self.user = self.scope.get("user", AnonymousUser())
        
        if not (self.user and self.user.is_authenticated):
            await self.close()
            return
        
        self.notification_group = f"notifications_{self.user.id}"
        if self.channel_layer:
            await self.channel_layer.group_add(self.notification_group, self.channel_name)
        await self.accept()
        logger.info(f"Notification consumer connected for user: {self.user.id}")

    async def disconnect(self, close_code):
        """Cleanup on disconnect."""
        if self.user and self.user.is_authenticated and self.channel_layer:
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )
        logger.info(f"Notification consumer disconnected for user: {self.user.id}")

    async def receive(self, text_data):
        """Handle notification-related messages."""
        try:
            data = json.loads(text_data)
            
            if data.get("action") == "mark_read":
                notification_id = data.get("notification_id")
                await self._mark_notification_read(notification_id, self.user.id)
                
                if self.channel_layer:
                    await self.channel_layer.group_send(
                        self.notification_group,
                        {
                            "type": "notification_updated",
                            "notification_id": notification_id,
                            "status": "read",
                        }
                    )
            elif data.get("action") == "mark_all_read":
                await self._mark_all_notifications_read(self.user.id)
                
                if self.channel_layer:
                    await self.channel_layer.group_send(
                        self.notification_group,
                        {
                            "type": "all_notifications_updated",
                            "status": "read_all",
                        }
                    )
                
        except Exception as e:
            logger.error(f"Error in NotificationConsumer.receive: {str(e)}", exc_info=True)
            await self.send_error("Error processing request")

    @database_sync_to_async
    def _mark_notification_read(self, notification_id, user_id):
        """Mark a notification as read."""
        try:
            from core.models import Notification
            notification = Notification.objects.get(id=notification_id, user_id=user_id)
            notification.is_read = True
            notification.save()
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")

    @database_sync_to_async
    def _mark_all_notifications_read(self, user_id):
        """Mark all notifications for user as read."""
        try:
            from core.models import Notification
            Notification.objects.filter(user_id=user_id, is_read=False).update(is_read=True)
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")

    async def send_error(self, error_message):
        """Send error message."""
        await self.send(text_data=json.dumps({
            "type": "error",
            "message": error_message
        }))

    async def send_notification(self, event):
        """Send notification to user."""
        await self.send(text_data=json.dumps({
            "type": "notification",
            "notification_id": event.get("notification_id"),
            "title": event.get("title"),
            "message": event.get("message"),
            "data": event.get("data"),
        }))

    async def notification_updated(self, event):
        """Notification status updated."""
        await self.send(text_data=json.dumps({
            "type": "notification_updated",
            "notification_id": event.get("notification_id"),
            "status": event.get("status"),
        }))

    async def all_notifications_updated(self, event):
        """All notifications updated."""
        await self.send(text_data=json.dumps({
            "type": "all_notifications_updated",
            "status": event.get("status"),
        }))
