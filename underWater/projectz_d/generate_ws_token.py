#!/usr/bin/env python
"""
Generate a WebSocket authentication token for testing.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projectz.settings")
django.setup()

from django.contrib.auth import get_user_model
from core.realtime.auth import generate_ws_token

User = get_user_model()

# Get first admin user or create test user
try:
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.filter(is_staff=True).first()
    if not user:
        user = User.objects.first()
    
    if user:
        token = generate_ws_token(user)
        print(f"\n✅ Token for user: {user.username}")
        print(f"Token: {token}\n")
        ws_port = os.getenv("ASGI_PORT", "9000")
        print(f"WebSocket URL with token:")
        print(f"ws://localhost:{ws_port}/ws/alerts/?token={token}\n")
        print("Copy the full URL above and paste it in the WebSocket Test HTML file")
    else:
        print("❌ No users found. Create a user first with: python manage.py createsuperuser")
except Exception as e:
    print(f"❌ Error: {e}")
