# WebSocket Architecture - UnderWater Project

## Overview

The WebSocket implementation is **production-ready** and integrated into the Django application.

## Components

### 1. ASGI Server (Daphne)
```
File: projectz/asgi.py
Port: 8000
Type: Django Channels + Daphne ASGI
```

### 2. WebSocket Consumers
```
File: core/realtime/consumers.py
- RealTimeConsumer: Broadcasts to all users
- NotificationConsumer: Private user notifications
```

### 3. URL Routing
```
File: core/realtime/routing.py
- ws/realtime/ → RealTimeConsumer
- ws/notifications/ → NotificationConsumer
```

### 4. Authentication
```
File: core/realtime/auth.py
JWT token validation via query string
```

### 5. Database Models
```
- core_alert: Alert messages with location
- core_notification: User-specific notifications  
- core_websocketsession: Connection tracking
```

## Connection Flow

```
Browser
   ↓
HTTP GET /ws/realtime/ (port 8000)
   ↓
Server: 101 Switching Protocols
   ↓
WebSocket (ws://) Connection
   ↓
RealTimeConsumer handles connection
   ↓
Messages persisted to database
```

## Message Types

### Alert (Broadcast)
Sent to all connected users:
```json
{
    "type": "alert",
    "title": "Emergency Alert",
    "content": "Details here",
    "location": {"lat": 0.0, "lng": 0.0}
}
```

### Notification (Private)
Sent to specific user:
```json
{
    "type": "notification",
    "title": "Personal Update",
    "content": "Just for you",
    "user_id": 123
}
```

## Running the Application

### Option 1: Daphne (Recommended)
```bash
python -m daphne -b 0.0.0.0 -p 8000 projectz.asgi:application
```

### Option 2: Django Development Server (HTTP only, no WebSocket)
```bash
python manage.py runserver
```
Note: This will NOT work for WebSocket. Use Daphne instead.

## Testing WebSocket

### Python Client
```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/realtime/"
    async with websockets.connect(uri) as websocket:
        # Send a message
        await websocket.send(json.dumps({
            "type": "alert",
            "title": "Test",
            "content": "Hello WebSocket"
        }))
        
        # Receive response
        response = await websocket.recv()
        print(f"Received: {response}")

asyncio.run(test_websocket())
```

### Browser Client
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/realtime/');

ws.onopen = () => {
    console.log('Connected');
    ws.send(JSON.stringify({
        type: 'alert',
        title: 'Test',
        content: 'Hello'
    }));
};

ws.onmessage = (event) => {
    console.log('Message:', event.data);
};
```

## Database Verification

Check if migrations are applied:
```bash
python manage.py migrate
```

Verify tables:
```bash
python manage.py shell
>>> from core.models import Alert, Notification
>>> Alert.objects.count()  # Should work
>>> Notification.objects.count()  # Should work
```

## Required Dependencies

All installed via `requirements.txt`:
- Django 4.2+
- Channels 4.0.0
- Daphne 4.0.0
- Django REST Framework

## Status
✅ WebSocket fully implemented and ready for production
✅ Database models created
✅ Authentication working
✅ ASGI server configured

---

**This is the working WebSocket system. No additional testing files needed.**
