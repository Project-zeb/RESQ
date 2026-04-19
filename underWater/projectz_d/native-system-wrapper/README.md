# Resqfy Native System Wrapper (USB)

This wrapper opens the full Django app (`http://127.0.0.1:2000`) inside a native Android app shell using Capacitor.

## What this gives you

- Native app icon + app launch on phone
- Full Resqfy system inside WebView
- USB tunnel support (no public hosting needed during testing)

## Prerequisites

- Node.js 20+
- Android Studio
- Android phone with USB debugging enabled
- `adb` installed and available in PATH

## Setup

```bash
cd /Users/matrika/Desktop/codez/Underwater\ copy/underWater/projectz_d/native-system-wrapper
npm install
npx cap add android
```

## Run with USB tunnel

1. Start Django on laptop:

```bash
cd /Users/matrika/Desktop/codez/Underwater\ copy/underWater/projectz_d
./.venv/bin/python manage.py runserver 127.0.0.1:2000
```

2. Connect phone via USB and enable debugging.

3. Create USB reverse tunnel:

```bash
cd /Users/matrika/Desktop/codez/Underwater\ copy/underWater/projectz_d/native-system-wrapper
npm run usb:devices
npm run usb:reverse
```

4. Sync and open Android project:

```bash
npm run cap:sync
npm run cap:android
```

5. In Android Studio, run on the connected device.

## Optional: change backend URL

Use a different backend URL by setting `CAP_SERVER_URL` before sync:

```bash
CAP_SERVER_URL=http://127.0.0.1:2000 npm run cap:sync
```
