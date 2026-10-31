# TV Remote for Android

A small native Android interface using `androidtvremote2` through Chaquopy for the TV protocol. The phone connects directly to your TV: no Windows app, server, account, ADB, or TV developer mode is required.

## Install and connect

1. Copy `dist/TV-Remote-Android.apk` to your phone and open it. Allow installation from your chosen file manager if Android asks.
2. Connect your phone and TV to the same Wi-Fi network.
3. Open **TV Remote**, tap **TVs**, and select a discovered TV. If discovery is blocked by your router, enter its IP address.
4. Tap **Pair** and enter the six-character code displayed on the TV.

Requires a **64-bit Android phone running Android 7.0 or newer**, and an Android TV / Google TV with Android TV Remote Service. Includes ARM64 and x86-64 support. The initial APK is debug-signed for personal sideloading, not a Play Store release.

## Controls

- Circular D-pad, OK, Back, Home, Menu, power, input, settings, volume, mute, and playback.
- **Touchpad** mode: swipe to navigate, tap for OK, hold and release for Back.
- Phone volume buttons control the TV while the app is open and connected.
- **Send text** inserts the complete typed text once. **Enter** inserts any pending text and submits. **Clear** only clears the phone input. First select the intended text field on the TV.
- The selected TV and pairing identity are stored in app-private storage. The app disconnects in the background and reconnects when reopened. Uninstalling clears the pairing identity.

## Build on Windows

Python 3.12 is required. No Android Studio installation is necessary:

```powershell
./android/build.ps1 -Setup
```

The setup script downloads checksum-verified official Temurin JDK, Gradle, and Android SDK archives into ignored `build/android-tools/`. The build script installs SDK 35, accepts the required Android SDK licenses, and builds the APK. Subsequent builds use `./android/build.ps1`.

Output: `dist/TV-Remote-Android.apk`.

Keep `build/android-tools/android-user/debug.keystore` to sign future personal builds consistently. Deleting or replacing that signing key may require uninstalling the old APK before installing a new one, which also removes saved pairing.

## Implementation

- Native Java Android views, with a custom canvas navigation pad. No web server or WebView.
- Android `NsdManager` handles network discovery.
- Python TLS/protocol operations run on a background asyncio loop; the UI communicates through a single worker and event queue.
- `remote_bridge.py` is a small Android-specific adapter. Desktop UI code is not packaged.
- Network permissions only; no advertising, analytics, location, or contacts access.

## Third-party software

- [androidtvremote2](https://github.com/tronikos/androidtvremote2), Apache-2.0.
- [Chaquopy](https://github.com/chaquo/chaquopy), MIT.
- [cryptography](https://github.com/pyca/cryptography), Apache-2.0 / BSD-3-Clause.
- [protobuf](https://github.com/protocolbuffers/protobuf), BSD-3-Clause.
- [aiofiles](https://github.com/Tinche/aiofiles), Apache-2.0.

Protocol-adapter tests run with the desktop test suite: `.venv/Scripts/python.exe -m unittest discover -s tests -v`.
