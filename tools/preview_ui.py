"""Open the real Windows UI with sample data, without connecting to a TV."""
import copy
import ctypes
import queue
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvremote import config
from tvremote.ui import RemoteApp


def save_window(root, output):
    """Render only this preview window into a bitmap (Windows, Pillow required)."""
    from ctypes import wintypes
    from PIL import Image

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                               ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    hwnd = user32.GetParent(root.winfo_id())
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    source = user32.GetWindowDC(hwnd)
    memory = gdi32.CreateCompatibleDC(source)
    bitmap = gdi32.CreateCompatibleBitmap(source, width, height)
    old = gdi32.SelectObject(memory, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory, 2):
            raise RuntimeError("Could not render preview window")
        gdi32.SelectObject(memory, old)
        import struct
        header = ctypes.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, width, -height,
                                             1, 32, 0, width * height * 4, 0, 0, 0, 0))
        pixels = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(memory, bitmap, 0, height, pixels, header, 0):
            raise RuntimeError("Could not read preview bitmap")
        Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1).save(output)
        print(f"Saved {output}: {width}x{height}")
    finally:
        gdi32.SelectObject(memory, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(hwnd, source)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass

settings = copy.deepcopy(config.DEFAULTS)
settings.update(host="192.0.2.10", name="Living Room TV")
connection = Mock()
connection.events = queue.Queue()
connection.thread.is_alive.return_value = False
root = tk.Tk()
root.iconbitmap(default=str(ROOT / "assets" / "remote.ico"))
with patch("tvremote.ui.config.load", return_value=settings), \
        patch("tvremote.ui.config.save"), \
        patch("tvremote.ui.TvConnection", return_value=connection):
    app = RemoteApp(root)
    app._handle("connected", True)
    app._handle("volume", {"level": 16, "max": 100, "muted": False})
    app._handle("app", "com.google.android.youtube.tv")
    root.geometry("+120+60")
    if "--screenshot" in sys.argv:
        def capture():
            try:
                save_window(root, ROOT / "docs" / "screenshot.png")
            finally:
                root.destroy()
        root.after(700, capture)
    root.mainloop()
