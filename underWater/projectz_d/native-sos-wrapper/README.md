# ProjectZ Native SOS Wrapper (Android/iOS)

This folder provides a native wrapper using Capacitor with an SOS page bundled inside the app binary.

## Why this exists

- PWA offline cache is strong, but browser/site-data clear can remove service workers and cache.
- Native app binary keeps the SOS page packaged with the app, so it still opens after browser data clears.

## Prerequisites

- Node.js 20+
- Android Studio (for Android build)
- Xcode (for iOS build, macOS only)

## Setup

```bash
cd projectz_v.2/native-sos-wrapper
npm install
npx cap add android
npx cap add ios
npx cap sync
```

## Open in native IDEs

```bash
npm run cap:android
npm run cap:ios
```

## What is bundled

- Offline SOS UI: [www/index.html](www/index.html)
- Emergency call and SMS triggers
- Device geolocation capture (with permission)

## Notes

- Configure phone numbers in [www/index.html](www/index.html) (`SOS_SMS_NUMBER` and `SOS_CALL_NUMBER`).
- On iOS, add location/call/SMS usage descriptions in Xcode project settings when prompted.
- On Android 13+, confirm runtime location permissions are granted.
