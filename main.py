"""Start the TV Remote window."""

import ctypes
import logging
import tkinter as tk

from tvremote import config
from tvremote.ui import RemoteApp


def main() -> None:
    config.APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=config.LOG_FILE, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on high-DPI screens
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    RemoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
