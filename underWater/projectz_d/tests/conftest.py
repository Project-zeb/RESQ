"""
Test configuration and fixtures for WebSocket testing.

This module provides pytest configuration and common fixtures
for testing Django Channels consumers.
"""

import os
import django
import pytest
from django.conf import settings
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from core.realtime.auth import generate_ws_token

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'projectz.settings')
django.setup()


def pytest_configure():
    """Configure pytest for Django and channels testing."""
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
            INSTALLED_APPS=[
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'channels',
                'core',
            ],
            CHANNEL_LAYERS={
                'default': {
                    'BACKEND': 'channels.layers.InMemoryChannelLayer'
                }
            }
        )


@pytest.fixture
def channel_layer():
    """Provide in-memory channel layer for testing."""
    return get_channel_layer()


@pytest.fixture
def authenticated_user(db):
    """Create a test user for authentication."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
    return user


@pytest.fixture
def ws_token(authenticated_user):
    """Generate a valid WebSocket token."""
    return generate_ws_token(authenticated_user)


@pytest.fixture
async def ws_communicator(ws_token):
    """Create a WebSocket communicator for testing."""
    from projectz.asgi import application
    
    communicator = WebsocketCommunicator(
        application,
        f"ws/realtime/?token={ws_token}"
    )
    return communicator


# Async test support
pytest_plugins = ('pytest_asyncio',)
