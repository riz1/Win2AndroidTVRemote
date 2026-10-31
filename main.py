"""Start the TV Remote window."""

import ctypes
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import tkinter as tk

from tvremote import config
from tvremote.ui import RemoteApp


def place_on_right(root: tk.Tk) -> None:
    """Place the complete window inside the primary screen's usable area."""
    root.update_idletasks()
    left, top, right, bottom = 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
    border, caption = 8, 32
    try:
        from ctypes import wintypes

        area = wintypes.RECT()
        user32 = ctypes.windll.user32
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
            left, top, right, bottom = area.left, area.top, area.right, area.bottom
        border = user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92)
        caption = user32.GetSystemMetrics(4)
    except (AttributeError, OSError):
        pass
    width, height = root.winfo_reqwidth(), root.winfo_reqheight()
    x = max(left, right - width - 2 * border - 20)
    y = max(top, top + (bottom - top - height - caption - 2 * border) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")


def main() -> None:
    config.APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(handlers=[RotatingFileHandler(
                            config.LOG_FILE, maxBytes=1_000_000, backupCount=2,
                            encoding="utf-8")], level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on high-DPI screens
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Win2AndroidTV.Remote")
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.withdraw()
    icon = Path(__file__).resolve().parent / "assets" / "remote.ico"
    if icon.exists():
        root.iconbitmap(default=str(icon))
    RemoteApp(root)
    place_on_right(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
