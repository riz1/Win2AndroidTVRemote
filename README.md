# Win2AndroidTV Remote

Control your Android TV / Google TV from a Windows laptop. Use the laptop keyboard instead of the on-screen keyboard, and use the mouse or trackpad to navigate.

<p align="center"><img src="docs/screenshot.png" alt="Win2AndroidTV Remote window" width="360"></p>

## Features

- **Touchpad navigation** – drag on the pad to move Up / Down / Left / Right. Click is OK, right-click is Back, middle-click is Home.
- **Hover mode** – move the pointer on the pad to navigate, with no click.
- **Volume** – mouse wheel or two-finger scroll, PgUp / PgDn, `+` / `−`, and Mute.
- **Type with your keyboard** – the text you type shows in the TV search box at the same time.
- **Buttons** – Back, Home, Menu, Play/Pause, Power, Input, Settings and app shortcuts (YouTube by default).
- **Auto-discovery** – finds the TVs on your network. Pair one time and it connects automatically after that.
- **No developer mode, no ADB** – it uses the Android TV Remote protocol v2, the same protocol as the Google TV phone app.
- **Always on top** option for a small remote beside your other windows.

## Requirements

- Windows 10 or 11.
- An Android TV or Google TV device (TV, Chromecast with Google TV, NVIDIA Shield, Mi Box, and others) with the **Android TV Remote Service**. Most devices have it.
- The laptop and the TV must be on the same network.

## Download and run

1. Download `Win2AndroidTVRemote.exe` from the [Releases](../../releases) page.
2. Double-click it. You do not need Python.
3. If Windows SmartScreen shows a warning, click **More info**, then **Run anyway**. The exe has no code signature.
4. If Windows Firewall asks, allow network access. The app must find the TV on your network.

## First connection

1. The app searches for TVs. Double-click your TV in the list, or type its IP address and click **Connect**.
2. Click **Yes** to pair. A 6-digit code shows on the TV screen.
3. Type the code in the app.

The app keeps the pairing. The next time, it connects automatically.

## Controls

| Action | Mouse / trackpad | Keyboard |
|---|---|---|
| Move | Drag on the pad (or Hover mode) | Arrow keys |
| OK | Click on the pad | Enter |
| Back | Right-click on the pad | Esc or Backspace |
| Home | Middle-click on the pad | Home |
| Volume up / down | Wheel or two-finger scroll | PgUp / PgDn or `+` / `−` |
| Mute | – | M or F8 |
| Play / Pause | – | Space |
| Menu | – | F1 or the Menu key |
| Type text | Click the text box | T or `/` |

**Type text:** first select a search box on the TV. Then type in the app text box. Press Enter to send the search. Press Esc to go back to navigation.

## Settings

Settings, the pairing certificate and a log file are in `%APPDATA%\TvRemote\`.

To change the app shortcuts, edit `"apps"` in `config.json`. Use a deep link or an Android package name:

```json
"apps": [
  ["YouTube", "https://www.youtube.com"],
  ["Netflix", "https://www.netflix.com/title"]
]
```

To pair again, delete `cert.pem` and `key.pem`.

## Run from source

Install Python 3.10 or later, then run:

```bat
run.bat
```

`run.bat` makes a `.venv`, installs the requirements and starts the app.

## Build the exe

```bat
build.bat
```

The result is `dist\Win2AndroidTVRemote.exe`.

## Troubleshooting

- **No TV in the list** – make sure that the TV is on and on the same network. Type the TV IP address manually. Some routers block device discovery (mDNS).
- **Cannot connect** – on the TV, make sure that the *Android TV Remote Service* app is installed and up to date.
- **Text does not show on the TV** – select a text field on the TV first. Some apps do not accept text from a remote keyboard.
- **Errors** – look in `%APPDATA%\TvRemote\log.txt`.

## Credits

- [androidtvremote2](https://github.com/tronikos/androidtvremote2) – Android TV Remote protocol v2 library.
- [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf) – network discovery.

## License

[MIT](LICENSE)
