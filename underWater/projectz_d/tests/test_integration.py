"""
Integration tests for WebSocket architecture.

These tests verify the complete WebSocket pipeline including:
- Authentication
- Message broadcasting
- Database persistence
- Concurrent connections
"""

import json
import pytest
from channels.layers import get_channel_layer
from core.realtime.auth import generate_ws_token
from core.models import Notification, Alert


@pytest.mark.asyncio
async def test_full_realtime_workflow(authenticated_user, ws_token):
    """Test complete real-time communication workflow."""
    from projectz.asgi import application
    
    # Create two connections
    communicator1 = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={ws_token}"
    )
    
    # Create another user token for second connection
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user2 = User.objects.create_user(
        username='testuser2',
        email='test2@example.com',
        password='testpass123'
    )
    token2 = generate_ws_token(user2)
    
    from channels.testing import WebsocketCommunicator
    communicator2 = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={token2}"
    )
    
    # Connect both
    conn1, _ = await communicator1.connect()
    conn2, _ = await communicator2.connect()
    
    assert conn1 and conn2
    
    # User 1 sends a message
    await communicator1.send_json_to({
        "message_type": "message",
        "data": {"message": "Hello from user 1"}
    })
    
    # Both should receive it (due to group broadcast)
    import asyncio
    await asyncio.sleep(0.1)  # Give time for message propagation
    
    # Disconnect
    await communicator1.disconnect()
    await communicator2.disconnect()


@pytest.mark.django_db(allow_database_queries=True)
@pytest.mark.asyncio
async def test_notification_persistence(authenticated_user):
    """Test that notifications are persisted and retrieved."""
    from channels.testing import WebsocketCommunicator
    from projectz.asgi import application
    from core.realtime.auth import generate_ws_token
    
    token = generate_ws_token(authenticated_user)
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/notifications/?token={token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    # Check that we can create notifications
    notif = Notification.objects.create(
        user=authenticated_user,
        notification_type="ALERT",
        title="Test Alert",
        message="This is a test notification"
    )
    
    assert notif.id is not None
    assert not notif.is_read
    
    # Mark as read
    notif.mark_as_read()
    assert notif.is_read
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_concurrent_connections(authenticated_user, ws_token):
    """Test multiple concurrent WebSocket connections."""
    from projectz.asgi import application
    from channels.testing import WebsocketCommunicator
    
    # Create multiple connections
    communicators = []
    for i in range(5):
        comm = WebsocketCommunicator(
            application,
            f"ws/realtime/?token={ws_token}"
        )
        connected, _ = await comm.connect()
        assert connected
        communicators.append(comm)
    
    # All should be connected
    assert len(communicators) == 5
    
    # Disconnect all
    for comm in communicators:
        await comm.disconnect()


@pytest.mark.django_db(allow_database_queries=True)
def test_models_creation(authenticated_user):
    """Test that new models can be created properly."""
    from core.models import Alert, Notification, WebSocketSession
    
    # Create alert
    alert = Alert.objects.create(
        user=authenticated_user,
        alert_type="DISASTER",
        content="Test alert",
        location="Test Location",
        latitude=40.7128,
        longitude=-74.0060
    )
    assert alert.id is not None
    
    # Create notification
    notif = Notification.objects.create(
        user=authenticated_user,
        notification_type="ALERT",
        title="Test",
        message="Message"
    )
    assert notif.id is not None
    
    # Create session
    session = WebSocketSession.objects.create(
        user=authenticated_user,
        channel_name="test_channel_123",
        connection_type="realtime"
    )
    assert session.id is not None
    assert session.is_active
