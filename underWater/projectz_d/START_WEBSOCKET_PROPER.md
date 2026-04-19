# WebSocket Setup (Correct for Your Architecture)

You have **TWO services** that need to run together:

## Service 1: Internal API (Port 5100)

**Terminal 1** - From `internal api` folder:
```bash
cd ../internal\ api
python run.py
```

Wait for: `Starting development server at http://0.0.0.0:5100/`

---

## Service 2: Main App with WebSocket (Port 8000)

**Terminal 2** - From `projectz_d` folder, use **Daphne** (ASGI server):

```bash
cd projectz_d
daphne -b 0.0.0.0 -p 8000 projectz.asgi:application
```

Wait for: `WebSocket ASGI app booted in...` or server listening message

---

## Why Daphne?

`manage.py runserver` = WSGI only, **cannot** handle WebSocket

`daphne` = ASGI server, handles **both** HTTP and WebSocket on same port 8000

Your `asgi.py` is already configured with `ProtocolTypeRouter` to:
- Route HTTP requests normally
- Route WebSocket requests to consumers

---

## Test WebSocket

### Browser Console (F12)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/realtime/');
ws.onopen = () => console.log('✅ Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
```

Expected: `✅ Connected` appears

If NOT connected:
```
WebSocket is closed with code 1006
```
= Check that Daphne is running on Terminal 2

---

## Check Both Services Running

```bash
# Terminal 3 - Check ports
netstat -ano | findstr :5100
netstat -ano | findstr :8000
```

Should show:
- Port 5100: LISTENING (Internal API - run.py)
- Port 8000: LISTENING (Main App - daphne)

---

## What Your Setup Does

```
Internal API (port 5100)          Main App (port 8000 with WebSocket)
├─ disaster_api                   ├─ Django views/admin (HTTP)
├─ Models                         ├─ WebSocket consumers (WS://)
└─ API endpoints                  └─ core/realtime/
     ↓                                  ├─ consumers.py
   Called by                           ├─ routing.py
   projectz_d                          └─ auth.py
```

Your `projectz/autostart.py` tries to auto-start internal API, but manual start is cleaner.

---

## If Daphne Fails

**Check what's using port 8000:**
```bash
netstat -ano | findstr :8000
# Look for PID, then kill it:
taskkill /PID <PID> /F
```

**If Daphne not installed:**
```bash
pip install daphne
```

**Verify settings.py has Daphne configured:**
```bash
grep -n "daphne" projectz/settings.py
# Should show: "daphne" in INSTALLED_APPS
```

---

## Next: Create a Simple Test HTML File

Once both services are running, you can test with a browser HTML file instead of console commands.

Should I create that for you?
