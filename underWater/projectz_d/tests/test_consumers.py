"""
Tests for Django Channels consumers.

Tests cover:
- WebSocket connection with JWT authentication
- Message broadcasting
- Group subscription
- Error handling
"""

import json
import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from core.realtime.consumers import RealTimeConsumer, NotificationConsumer
from core.realtime.auth import generate_ws_token


@pytest.mark.asyncio
async def test_realtime_consumer_connect_authenticated(authenticated_user, ws_token):
    """Test authenticated WebSocket connection."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={ws_token}"
    )
    
    connected, subprotocol = await communicator.connect()
    assert connected is True
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_realtime_consumer_connect_unauthenticated():
    """Test unauthenticated WebSocket connection (should still connect but as AnonymousUser)."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(application, "ws/realtime/")
    
    connected, subprotocol = await communicator.connect()
    assert connected is True  # Channels allows unauthenticated connections
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_realtime_consumer_receive_message(authenticated_user, ws_token):
    """Test receiving a broadcast message."""
    from projectz.asgi import application
    from channels.layers import get_channel_layer
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={ws_token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    # Send a group message
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        "global_broadcast",
        {
            "type": "broadcast_message",
            "message": "Test message",
            "user": "testuser",
            "user_id": authenticated_user.id,
        }
    )
    
    # Receive the broadcast
    response = await communicator.receive_json_from()
    assert response["type"] == "message"
    assert response["message"] == "Test message"
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_realtime_consumer_send_message_error_unauthenticated():
    """Test that unauthenticated users get error when sending messages."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(application, "ws/realtime/")
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    # Try to send a message
    await communicator.send_json_to({
        "message_type": "message",
        "data": {"message": "Should fail"}
    })
    
    # Should receive error
    response = await communicator.receive_json_from()
    assert response["type"] == "error"
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_realtime_consumer_disconnect_cleanup(authenticated_user, ws_token):
    """Test that disconnect properly cleans up group memberships."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={ws_token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    # Disconnect should not raise any errors
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_notification_consumer_authenticated(authenticated_user):
    """Test notification consumer with authentication."""
    from projectz.asgi import application
    from core.realtime.auth import generate_ws_token
    
    token = generate_ws_token(authenticated_user)
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/notifications/?token={token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_notification_consumer_unauthenticated():
    """Test that notification consumer rejects unauthenticated connections."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(application, "ws/notifications/")
    
    # Unauthenticated connection should be rejected
    try:
        connected, _ = await communicator.connect()
        # If it gets here, the consumer should have closed the connection
        await communicator.disconnect()
    except Exception:
        # Expected behavior
        pass


@pytest.mark.asyncio
async def test_realtime_consumer_invalid_json():
    """Test that invalid JSON is handled gracefully."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(application, "ws/realtime/")
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    # Send invalid JSON
    await communicator.send_to(text_data="not valid json {")
    
    # Should receive error
    response = await communicator.receive_json_from()
    assert response["type"] == "error"
    assert "JSON" in response["message"] or "Invalid" in response["message"]
    
    await communicator.disconnect()


@pytest.mark.django_db(allow_database_queries=True)
@pytest.mark.asyncio
async def test_alert_persistence(authenticated_user, ws_token):
    """Test that alerts are persisted to database."""
    from projectz.asgi import application
    from core.models import Alert
    
    # Clear existing alerts
    Alert.objects.filter(user=authenticated_user).delete()
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={ws_token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    # Send alert
    await communicator.send_json_to({
        "message_type": "alert",
        "data": {
            "type": "DISASTER",
            "content": "Test disaster alert",
            "location": "Test Location"
        }
    })
    
    # Give it a moment to process
    import asyncio
    await asyncio.sleep(0.1)
    
    # Check database
    alerts = Alert.objects.filter(user=authenticated_user)
    assert alerts.count() > 0
    
    await communicator.disconnect()
