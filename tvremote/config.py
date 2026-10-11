"""Settings and certificate locations, kept in %APPDATA%\\TvRemote."""

import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TvRemote"
CERT_FILE = APP_DIR / "cert.pem"
KEY_FILE = APP_DIR / "key.pem"
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "log.txt"

# Deep links or package names. Edit "apps" in config.json to change the list.
DEFAULT_APPS = [
    ["YouTube", "https://www.youtube.com"],
]

DEFAULTS = {
    "host": "",
    "name": "",
    "always_on_top": False,
    "hover_mode": False,
    "apps": DEFAULT_APPS,
}


def load() -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
