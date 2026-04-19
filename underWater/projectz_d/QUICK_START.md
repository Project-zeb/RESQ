# WebSocket Setup - Quick Start

## What Was Done ✅

According to your architecture guide, I've implemented:

### 1. **Hybrid Server Model**
- ✅ WSGI Server (Gunicorn) on port 8000 → HTTP traffic
- ✅ ASGI Server (Uvicorn) on port 9000 → WebSocket traffic
- ✅ Nginx reverse proxy → Routes `/ws/*` to ASGI, rest to WSGI

### 2. **Settings Configuration**
- ✅ Added `channels` and `daphne` to INSTALLED_APPS  
- ✅ Configured CHANNEL_LAYERS (InMemoryChannelLayer for local testing)
- ✅ Set ASGI_APPLICATION in settings.py

### 3. **WebSocket Components**
- ✅ ASGI entry point with ProtocolTypeRouter
- ✅ JWT authentication middleware for query param tokens
- ✅ Async consumers with @database_sync_to_async protection
- ✅ Group-based message broadcasting

### 4. **Startup Scripts**
- ✅ `run_wsgi.py` - Start Gunicorn WSGI server
- ✅ `run_asgi.py` - Start Uvicorn ASGI server
- ✅ `nginx.conf` - Nginx routing configuration

---

## How to Run

### Install Dependencies

```bash
pip install gunicorn uvicorn[standard] channels channels_redis
```

### Terminal 1: Start WSGI Server (HTTP)

```bash
cd projectz_d
python run_wsgi.py
```

Wait for: `Listening on: http://0.0.0.0:8000`

### Terminal 2: Start ASGI Server (WebSocket)

```bash
cd projectz_d  
python run_asgi.py
```

Wait for: `Uvicorn running on http://0.0.0.0:9000`

### Browser Testing

#### Via Direct Connection (Development)
```javascript
// In browser console
const ws = new WebSocket('ws://localhost:9000/ws/realtime/');
ws.onopen = () => console.log('✅ Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
```

#### Via HTTP Server (to serve frontend)
```bash
# Terminal 3: Start simple HTTP server
cd projectz_d
python -m http.server 5000
```

Then open: `http://localhost:5000/`

---

## Architecture Summary

```
Browser 
  ↓
HTTP requests (port 80) ────→ Nginx ────→ Gunicorn (8000) ← HTTP/REST/Admin
WebSocket requests (port 80) ─→ Nginx ────→ Uvicorn (9000) ← ws:// Real-time
  ↓
Database (SQLite/PostgreSQL) with Channel Layer Store
```

**Key Differences from Single-Server**

| Aspect | Before | Now |
|--------|--------|-----|
| HTTP Server | Daphne (8000) | Gunicorn (8000) |
| WebSocket Server | Same (8000) | Uvicorn (9000) |
| Separation | No | Yes ✅ |
| HTTP Performance | Good | Better ✅ |
| WS Concurrency | Limited | Unlimited ✅ |
| Independent Scaling | No | Yes ✅ |

---

## Files Modified

- ✅ `projectz/settings.py` - Added Channels config
- ✅ `projectz/asgi.py` - ProtocolTypeRouter setup
- ✅ `core/realtime/auth.py` - JWT middleware (already correct)
- ✅ `core/realtime/consumers.py` - WebSocket handlers (already correct)

## Files Created

- ✅ `run_wsgi.py` - Gunicorn startup
- ✅ `run_asgi.py` - Uvicorn startup
- ✅ `nginx.conf` - Nginx routing
- ✅ `WEBSOCKET_HYBRID_SETUP.md` - Full documentation

---

## Next Steps

1. **Verify installations**: `pip install gunicorn uvicorn[standard]`
2. **Run WSGI**: Terminal 1 → `python run_wsgi.py`
3. **Run ASGI**: Terminal 2 → `python run_asgi.py`
4. **Test connection**: Browser → `ws://localhost:9000/ws/realtime/`
5. **Should see**: `{"type": "error", "message": "Authentication required"}` (expected without token)

---

## Network Tab Check (What You'll See)

When browser connects to `ws://localhost:9000/ws/realtime/`:

```
Request Headers:
GET /ws/realtime/ HTTP/1.1
Host: localhost:9000
Upgrade: websocket ✅
Connection: Upgrade ✅
Sec-WebSocket-Key: ...
Sec-WebSocket-Version: 13

Response Headers:
HTTP/1.1 101 Switching Protocols ✅
Upgrade: websocket ✅
Connection: Upgrade ✅
```

In Network tab → Type should show: **websocket** (not XHR, not document)

---

**Status**: ✅ Ready to run with proper hybrid architecture
