# WebSocket Frontend (React SPA)

The frontend has transitioned to a standalone React application located at:

`/Users/matrika/Desktop/codez/Underwater/underWater/projectz_d/frontend_react`

This replaces the legacy vanilla JavaScript client and template-based setup.

## Quick Start
1. Install dependencies:
   ```bash
   cd /Users/matrika/Desktop/codez/Underwater/underWater/projectz_d/frontend_react
   npm install
   ```
2. Configure environment:
   ```bash
   cp .env.example .env
   ```
3. Run the dev server:
   ```bash
   npm run dev
   ```

## Django Serving (Production)
If you want Django to serve the SPA at `/`, build the frontend:
```bash
cd /Users/matrika/Desktop/codez/Underwater/underWater/projectz_d/frontend_react
npm run build
```
Django will serve `frontend_react/dist/index.html` and static assets automatically.

## Default WebSocket Endpoint
- `VITE_WS_PATH=/ws/alerts/`
- Set `VITE_WS_BASE_URL=ws://localhost:9000` for local ASGI

## Features Included
- Single shared socket for the whole app
- JWT auth via query string
- Exponential backoff reconnect
- Offline queueing
- Token refresh helper (optional in-frame refresh)

## Legacy Note
The previous template-based `websocket-client.js` flow is deprecated. All real-time functionality should now be driven from the React app.
