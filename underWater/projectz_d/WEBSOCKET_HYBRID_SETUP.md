# WebSocket Implementation - Hybrid Architecture

## Architecture Overview

The project now uses a **hybrid server model** as specified in your guide:

```
┌─────────────────────────────────────────────────────────┐
│  Browser / Client                                       │
└────────────────────────┬────────────────────────────────┘
                         │
                ┌────────┴────────┐
                │                 │
         HTTP Requests    WebSocket Requests
                │                 │
                ▼                 ▼
        ┌──────────────┐  ┌──────────────┐
        │   Nginx      │  │   Nginx      │
        │  (Port 80)   │  │  (Port 80)   │
        └──────┬───────┘  └──────┬───────┘
               │                 │
               ▼                 ▼
        ┌──────────────┐  ┌──────────────┐
        │  Gunicorn    │  │  Uvicorn     │
        │   (WSGI)     │  │   (ASGI)     │
        │  Port 8000   │  │  Port 9000   │
        │              │  │              │
        │ Django Views │  │  WebSocket   │
        │    API       │  │  Consumers   │
        │   Admin      │  │   Real-time  │
        └──────┬───────┘  └──────┬───────┘
               │                 │
               └────────┬────────┘
                        │
                ┌───────▼────────┐
                │   SQLite DB    │
                │  with Channels │
                │   Layer Store  │
                └────────────────┘
```

## Components

### 1. WSGI Server (Gunicorn) - Port 8000
- Handles standard HTTP requests
- Django views, REST APIs, admin interface
- Synchronous request-response model
- Command: `python run_wsgi.py`

### 2. ASGI Server (Uvicorn) - Port 9000
- Handles WebSocket connections
- Long-lived asynchronous connections
- Real-time alerts and notifications
- Command: `python run_asgi.py`

### 3. Nginx Reverse Proxy - Port 80
- Routes `/` → Gunicorn (WSGI)
- Routes `/ws/` → Uvicorn (ASGI)
- Handles SSL termination
- Configuration: `nginx.conf`

### 4. Channel Layer (In-Memory Local / Dragonfly Production)
- Stores Django Channels group messages
- Enables message passing between processes
- Local: InMemoryChannelLayer (configured in settings)
- Production: Dragonfly (Redis-compatible, 25x faster than Redis)

## How to Run

### Step 1: Configure Django Settings

✅ Already done:
- Added `channels` and `daphne` to INSTALLED_APPS
- Configured CHANNEL_LAYERS (InMemoryChannelLayer for local testing)
- Set ASGI_APPLICATION in settings

### Step 2: Start WSGI Server (Terminal 1)

```bash
cd projectz_d
pip install gunicorn  # If not already installed
python run_wsgi.py
```

Expected output:
```
🌐 Starting WSGI Server (HTTP)
📌 Server: Gunicorn (WSGI)
🔌 Port: 8000
Started server process XXXX
Listening on: http://0.0.0.0:8000
```

### Step 3: Start ASGI Server (Terminal 2)

```bash
cd projectz_d
python run_asgi.py
```

Expected output:
```
⚡ Starting ASGI Server (WebSocket)
📌 Server: Uvicorn (ASGI)
🔌 Port: 9000
Uvicorn running on http://0.0.0.0:9000
```

### Step 4: Access Application

**Via Nginx (Production)**
```
http://localhost        # Uses Nginx on port 80
  → Routes to Gunicorn (8000) or Uvicorn (9000) based on path
```

**Direct (Development)**
- HTTP: `http://localhost:8000`
- WebSocket: `ws://localhost:9000/ws/realtime/`

## Testing WebSocket

### Browser Console

```javascript
const ws = new WebSocket('ws://localhost:9000/ws/realtime/');

ws.onopen = () => {
    console.log('✅ Connected to WebSocket');
    ws.send(JSON.stringify({
        type: 'alert',
        title: 'Test Alert',
        content: 'Hello from browser'
    }));
};

ws.onmessage = (event) => {
    console.log('Message received:', event.data);
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};
```

### Python Client

```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = 'ws://localhost:9000/ws/realtime/'
    async with websockets.connect(uri) as websocket:
        # Send test message
        test_msg = {
            'type': 'alert',
            'title': 'Test Alert',
            'content': 'Hello WebSocket'
        }
        await websocket.send(json.dumps(test_msg))
        
        # Receive response
        response = await websocket.recv()
        print(f'Connected! Response: {response}')

asyncio.run(test_websocket())
```

## File Structure

```
projectz_d/
├── projectz/
│   ├── asgi.py          ← ProtocolTypeRouter (HTTP vs WebSocket)
│   ├── wsgi.py          ← Standard Django WSGI
│   └── settings.py      ← CHANNEL_LAYERS configuration
│
├── core/
│   ├── realtime/
│   │   ├── consumers.py  ← WebSocket message handlers
│   │   ├── routing.py    ← WebSocket URL routes
│   │   └── auth.py       ← JWT authentication
│   └── models.py        ← Alert, Notification, WebSocketSession
│
├── run_wsgi.py          ← Start Gunicorn (HTTP, port 8000)
├── run_asgi.py          ← Start Uvicorn (WebSocket, port 9000)
├── nginx.conf           ← Nginx routing configuration
└── docker-compose.yml   ← (Optional) For containerization
```

## Configuration Reference

### settings.py - CHANNEL_LAYERS

**Local Testing (InMemoryChannelLayer)**
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    },
}
```

**Production (Dragonfly/Redis)**
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("dragonfly-host", 6379)],
            "symmetric_encryption_keys": [SECRET_KEY],
            "connection_kwargs": {
                "socket_connect_timeout": 10,
                "socket_timeout": 10,
            },
            "capacity": 1500,
            "expiry": 10,
        },
    },
}
```

## Required Packages

All installed via pip:
```bash
pip install django channels channels_redis daphne uvicorn[standard] gunicorn
```

## Common Issues & Fixes

### ❌ "Connection refused" on ws://localhost:9000
→ Make sure `python run_asgi.py` is running in another terminal

### ❌ WebSocket connection drops after 60 seconds
→ Nginx timeout issue. Ensure `proxy_read_timeout 86400;` in nginx.conf

### ❌ "Module not found: channels_redis"
→ Install: `pip install channels_redis`

### ❌ CHANNEL_LAYERS not configured
→ Settings.py should have CHANNEL_LAYERS defined (already done)

### ❌ WebSocket connects but no messages
→ Check console for errors. Verify consumers.py has proper async handlers

## Architecture Benefits

✅ **Separation of Concerns**: HTTP and WebSocket on separate servers  
✅ **Stability**: Synchronous code in Gunicorn won't block WebSocket connections  
✅ **Scalability**: Can scale WSGI and ASGI independently  
✅ **Performance**: Uvicorn handles thousands of concurrent WebSocket connections  
✅ **Resilience**: If WSGI crashes, WebSocket continues functioning  

## Status

✅ Settings configured  
✅ ASGI application ready  
✅ Consumer code in place  
✅ Run scripts created  
✅ Nginx configuration provided  

**Next**: Run `python run_wsgi.py` and `python run_asgi.py` in separate terminals.

---

**Project**: UnderWater (project-zeb v2)  
**Architecture**: Hybrid WSGI + ASGI  
**Status**: Ready for testing
