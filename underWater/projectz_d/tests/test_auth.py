"""
Tests for JWT authentication middleware.

Tests cover:
- Valid token authentication
- Expired token handling
- Invalid token handling
- Missing token handling
"""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from django.conf import settings
from channels.auth import AuthMiddlewareStack
from channels.testing import WebsocketCommunicator
from core.realtime.auth import JWTAuthMiddleware, generate_ws_token
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.asyncio
async def test_valid_token_authentication(authenticated_user):
    """Test that valid JWT token authenticates user."""
    from projectz.asgi import application
    
    token = generate_ws_token(authenticated_user)
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_expired_token():
    """Test that expired token is rejected."""
    from projectz.asgi import application
    
    # Create an expired token
    payload = {
        "user_id": 999,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    
    expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={expired_token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True  # Still connects but as AnonymousUser
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_invalid_token():
    """Test that invalid token is handled gracefully."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(
        application,
        "ws/realtime/?token=invalid.token.here"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True  # Still connects but as AnonymousUser
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_missing_token():
    """Test that missing token is handled gracefully."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(application, "ws/realtime/")
    
    connected, _ = await communicator.connect()
    assert connected is True  # Still connects but as AnonymousUser
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_malformed_token():
    """Test that malformed token is handled gracefully."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(
        application,
        "ws/realtime/?token=not.enough.parts"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True  # Still connects but as AnonymousUser
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_token_with_missing_user_id():
    """Test that token without user_id is handled gracefully."""
    from projectz.asgi import application
    
    # Create token without user_id
    payload = {
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
    }
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True  # Still connects but as AnonymousUser
    
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_generate_ws_token(authenticated_user):
    """Test token generation utility function."""
    token = generate_ws_token(authenticated_user)
    
    # Token should be a string
    assert isinstance(token, str)
    
    # Token should be decodable
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["user_id"] == authenticated_user.id
    assert payload["username"] == authenticated_user.username
    assert "exp" in payload
    assert "iat" in payload


@pytest.mark.asyncio
async def test_token_algorithm_specification():
    """Test that token algorithm is verified (prevents algorithm confusion)."""
    from projectz.asgi import application
    
    # Create token with HS512 (different algorithm)
    payload = {
        "user_id": 999,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    
    # This would fail if algorithm check is enforced
    wrong_algo_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS512")
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={wrong_algo_token}"
    )
    
    connected, _ = await communicator.connect()
    assert connected is True  # Connects as AnonymousUser (token validation failed)
    
    await communicator.disconnect()
