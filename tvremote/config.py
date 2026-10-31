"""Settings and certificate locations, kept in %APPDATA%\\TvRemote."""

import json
import copy
import logging
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
    data = copy.deepcopy(DEFAULTS)
    try:
        loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return data
        for key in ("host", "name"):
            if isinstance(loaded.get(key), str):
                data[key] = loaded[key].strip()
        for key in ("always_on_top", "hover_mode"):
            if isinstance(loaded.get(key), bool):
                data[key] = loaded[key]
        if isinstance(loaded.get("apps"), list):
            data["apps"] = [
                [app[0].strip(), app[1].strip()] for app in loaded["apps"]
                if isinstance(app, (list, tuple)) and len(app) == 2
                and all(isinstance(item, str) and item.strip() for item in app)
            ]
    except (OSError, ValueError):
        logging.getLogger(__name__).warning("Could not read settings; using defaults")
    return data


def save(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_FILE)
