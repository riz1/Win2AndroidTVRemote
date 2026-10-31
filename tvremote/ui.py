"""Tk window: touchpad, buttons, keyboard and text input."""

import queue
import tkinter as tk
from tkinter import messagebox, simpledialog

from . import config
from .connection import TvConnection

BG = "#14171c"
PANEL = "#232830"
PAD = "#2e3540"
FG = "#f3f4f6"
DIM = "#a6b3c6"
ACCENT = "#77aaff"
OK = "#3ecf6e"
BAD = "#e5534b"
POWER = "#5a2a2d"

PAD_SIZE = (270, 150)
STEP = 40  # pixels of movement for one D-pad step
WHEEL_STEP = 120  # wheel delta for one volume step

# Keyboard in navigation mode -> TV key.
NAV_KEYS = {
    "Up": "DPAD_UP",
    "Down": "DPAD_DOWN",
    "Left": "DPAD_LEFT",
    "Right": "DPAD_RIGHT",
    "Return": "DPAD_CENTER",
    "KP_Enter": "DPAD_CENTER",
    "Escape": "BACK",
    "BackSpace": "BACK",
    "Home": "HOME",
    "Prior": "VOLUME_UP",
    "Next": "VOLUME_DOWN",
    "plus": "VOLUME_UP",
    "equal": "VOLUME_UP",
    "KP_Add": "VOLUME_UP",
    "minus": "VOLUME_DOWN",
    "KP_Subtract": "VOLUME_DOWN",
    "F8": "VOLUME_MUTE",
    "m": "VOLUME_MUTE",
    "space": "MEDIA_PLAY_PAUSE",
    "App": "MENU",
    "F1": "MENU",
}

HELP = (
    "Keyboard: arrows move · Enter OK · Esc/Backspace back · Home\n"
    "PgUp/PgDn or +/− volume · M mute · Space play/pause · T type text"
)


class RemoteButton(tk.Canvas):
    """Small rounded control with consistent hover and press feedback."""

    def __init__(self, parent, text, command, width, height, bg, fg, font_size):
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, cursor="hand2", takefocus=0)
        self.label, self.command = text, command
        self.base, self.ink, self.font_size = bg, fg, font_size
        self.hovered = False
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", lambda e: self.draw(PAD))
        self.bind("<ButtonRelease-1>", self._release)

    def _hover(self, active):
        self.hovered = active
        self.draw()

    def _release(self, event):
        self.draw()
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.command()
        return "break"

    def draw(self, color=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        r = min(14, h / 2)
        self.create_polygon(r, 1, w-r, 1, w-1, 1, w-1, r, w-1, h-r,
                            w-1, h-1, w-r, h-1, r, h-1, 1, h-1, 1, h-r,
                            1, r, 1, 1, smooth=True,
                            fill=color or (PAD if self.hovered else self.base), outline="")
        if self.label == "⏻":
            # Draw the power symbol so it also works on Windows fonts lacking U+23FB.
            cx, cy = w / 2, h / 2
            self.create_arc(cx-9, cy-9, cx+9, cy+9, start=130, extent=280,
                            style="arc", outline=self.ink, width=2)
            self.create_line(cx, cy-12, cx, cy-1, fill=self.ink, width=2)
        else:
            self.create_text(w / 2, h / 2, text=self.label, fill=self.ink,
                             font=("Segoe UI", self.font_size))


class RemoteApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = config.load()
        self.conn = TvConnection()
        self.found: list[tuple[str, str]] = []
        self.dialog: tk.Toplevel | None = None
        self.sent_text = ""
        self.wheel_accum = 0
        self.anchor: tuple[int, int] | None = None
        self.dragged = False
        self.flash_job = None
        self.connected = False
        self.closing = False

        root.title("Win2AndroidTV Remote")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.attributes("-topmost", self.cfg["always_on_top"])
        root.protocol("WM_DELETE_WINDOW", self.quit)

        self._build()
        self._bind_keys()
        root.after(50, self._poll_events)

        if self.cfg["host"]:
            self.conn.connect(self.cfg["host"])
        else:
            root.after(200, self.open_connect_dialog)

    # ---- layout --------------------------------------------------------------------

    def _button(self, parent, text, command, width=7, bg=PANEL, font_size=10,
                **kw) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, width=width, bg=bg, fg=FG,
            activebackground=ACCENT, activeforeground="white", relief="flat",
            bd=0, padx=4, pady=4, font=("Segoe UI", font_size), takefocus=0,
            cursor="hand2", **kw,
        )

    def _section(self, parent, title: str) -> tk.Frame:
        tk.Label(parent, text=title.upper(), bg=BG, fg=DIM,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(7, 3))
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x")
        return frame

    def _button_grid(self, parent, items, columns: int) -> None:
        """Put (label, command, options) buttons in equal-width columns."""
        for col in range(columns):
            parent.columnconfigure(col, weight=1, uniform="btn")
        for i, (label, command, opts) in enumerate(items):
            self._button(parent, label, command, width=1, **opts).grid(
                row=i // columns, column=i % columns, sticky="ew", padx=2, pady=2)

    def _key_button(self, label: str, key: str, **opts):
        return (label, lambda: self.send(key), opts)

    def _build(self) -> None:
        root = self.root
        outer = tk.Frame(root, bg=BG, padx=18, pady=16)
        outer.pack(fill="both")
        # A narrow silhouette and one dominant control, like a physical remote.
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        self.dot = tk.Canvas(head, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot_id = self.dot.create_oval(2, 2, 8, 8, fill=BAD, outline="")
        self.dot.pack(side="left", padx=(0, 5))
        self.title = tk.Label(head, text=self.cfg["name"] or "Choose a TV", bg=BG, fg=FG,
                              font=("Segoe UI Semibold", 12), anchor="w", width=20)
        self.title.pack(side="left", fill="x", expand=True)
        self._pill(head, "···", self._options, width=36, height=30).pack(side="right")
        self.app_label = tk.Label(outer, text="Your TV, a little closer.", bg=BG, fg=DIM,
                                  font=("Segoe UI", 9), anchor="w", width=32)
        self.app_label.pack(fill="x", pady=(3, 16))

        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill="x")
        self._pill(actions, "⏻", lambda: self.send("POWER"), width=48, height=42,
                   bg=POWER, fg="#ffb0ae", font_size=19).pack(side="left")
        self._pill(actions, "Input", lambda: self.send("TV_INPUT"), width=72,
                   height=42).pack(side="right")

        modes = tk.Frame(outer, bg=BG)
        modes.pack(pady=(12, 0))
        self.touch_mode = False
        self.remote_tab = self._pill(modes, "Remote", lambda: self._set_mode(False),
                                    width=100, height=30, bg=PAD)
        self.remote_tab.pack(side="left", padx=2)
        self.touch_tab = self._pill(modes, "Touchpad", lambda: self._set_mode(True),
                                   width=100, height=30, bg=BG)
        self.touch_tab.pack(side="left", padx=2)
        self.pad = tk.Canvas(outer, width=300, height=238, bg=BG,
                             highlightthickness=0, cursor="hand2", takefocus=1)
        self.pad.pack(fill="x")
        self.pad.bind("<Configure>", self._pad_resized)
        self.pad.bind("<ButtonPress-1>", self._pad_press)
        self.pad.bind("<B1-Motion>", self._pad_drag)
        self.pad.bind("<ButtonRelease-1>", self._pad_release)
        self.pad.bind("<Motion>", self._pad_hover)
        self.pad.bind("<Leave>", self._pad_leave)
        self.pad.bind("<Button-3>", lambda e: self.send("BACK"))
        self.pad.bind("<Button-2>", lambda e: self.send("HOME"))
        self.pad.bind("<MouseWheel>", self._wheel)
        root.bind("<MouseWheel>", self._wheel)
        self.top_var = tk.BooleanVar(value=self.cfg["always_on_top"])
        self.hover_var = tk.BooleanVar(value=self.cfg["hover_mode"])
        self._draw_pad()

        nav = tk.Frame(outer, bg=BG)
        nav.pack(fill="x", pady=(0, 12))
        for label, key in [("Back", "BACK"), ("Home", "HOME"), ("Menu", "MENU")]:
            self._pill(nav, label, lambda k=key: self.send(k), width=90, height=38).pack(
                side="left", expand=True, fill="x", padx=3)

        media = tk.Frame(outer, bg=BG)
        media.pack(fill="x")
        for label, key, width in [("−", "VOLUME_DOWN", 52), ("Mute", "VOLUME_MUTE", 64),
                                  ("+", "VOLUME_UP", 52), ("Play / Pause", "MEDIA_PLAY_PAUSE", 108)]:
            self._pill(media, label, lambda k=key: self.send(k), width=width, height=42).pack(
                side="left", expand=True, fill="x", padx=3)
        self.volume = tk.Label(outer, text="Volume —", bg=BG, fg=DIM,
                               font=("Segoe UI", 8))
        self.volume.pack(pady=(5, 12))

        if self.cfg["apps"]:
            shortcuts = tk.Frame(outer, bg=BG)
            shortcuts.pack(fill="x", pady=(0, 14))
            for i, (name, link) in enumerate(self.cfg["apps"]):
                shortcuts.columnconfigure(i % 2, weight=1, uniform="app")
                self._pill(shortcuts, name, lambda l=link: self.conn.launch(l),
                           width=140, height=34).grid(row=i // 2, column=i % 2,
                                                    sticky="ew", padx=3, pady=2)

        tk.Frame(outer, bg=PAD, height=1).pack(fill="x", pady=(0, 12))
        tk.Label(outer, text="TYPE ON TV", bg=BG, fg=DIM,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(0, 6))
        txt = tk.Frame(outer, bg=PANEL, padx=8, pady=4)
        txt.pack(fill="x")
        self.text_var = tk.StringVar()
        self.entry = tk.Entry(txt, textvariable=self.text_var, bg=PANEL, fg=FG,
                              insertbackground=FG, relief="flat", font=("Segoe UI", 11),
                              width=14, highlightthickness=0)
        self.entry.pack(side="left", ipady=5, fill="x", expand=True)
        self._pill(txt, "×", self._text_clear, width=28, height=30, bg=PANEL).pack(side="left")
        self._pill(txt, "Send", self._text_submit, width=52, height=30,
                   bg=ACCENT, fg=BG).pack(side="right")
        self.text_var.trace_add("write", self._text_changed)
        self.entry.bind("<Return>", lambda e: self._text_submit())
        self.entry.bind("<Escape>", lambda e: self._leave_text())
        tk.Label(outer, text="Select a text field on your TV first.", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))
        self.status = tk.Label(outer, text="", bg=BG, fg=DIM, font=("Segoe UI", 8),
                               anchor="center", wraplength=300)
        self.status.pack(fill="x", pady=(12, 0))
        self.pad.focus_set()

    def _pill(self, parent, text, command, width=80, height=38, bg=PANEL,
              fg=FG, font_size=10):
        return RemoteButton(parent, text, command, width, height, bg, fg, font_size)

    def _options(self) -> None:
        menu = tk.Menu(self.root, tearoff=False, bg=PANEL, fg=FG,
                       activebackground=PAD, activeforeground=FG)
        menu.add_command(label="Change TV…", command=self.open_connect_dialog)
        menu.add_checkbutton(label="Always on top", variable=self.top_var, command=self._toggle_top)
        menu.add_checkbutton(label="Hover navigation (touchpad)", variable=self.hover_var,
                             command=self._toggle_hover)
        menu.add_separator()
        menu.add_command(label="TV settings", command=lambda: self.send("SETTINGS"))
        menu.add_command(label="Keyboard & touchpad help", command=lambda: messagebox.showinfo(
            "Remote controls", HELP + "\n\nTouchpad: drag to navigate, click for OK.\n"
            "Right-click for Back, middle-click for Home.\nScroll to change volume.", parent=self.root))
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def _set_mode(self, touch: bool) -> None:
        self.touch_mode = touch
        self.anchor = None
        self.dragged = False
        self.remote_tab.base = BG if touch else PAD
        self.touch_tab.base = PAD if touch else BG
        self.remote_tab.draw()
        self.touch_tab.draw()
        self._draw_pad()
        self.pad.focus_set()

    def _draw_pad(self) -> None:
        self.pad.delete("all")
        cx = max(self.pad.winfo_width(), 300) / 2
        cy = 112
        if self.touch_mode:
            self.pad.create_rectangle(8, 12, cx * 2 - 8, 210, fill=PANEL, outline=PAD)
            self.hint_id = self.pad.create_text(cx, cy, text="Drag to navigate\nTap to select",
                                               fill=DIM, font=("Segoe UI", 11), justify="center")
        else:
            self.pad.create_oval(cx-101, cy-101, cx+101, cy+101, fill="#0d1014", outline="#343b47", width=1)
            self.pad.create_oval(cx-96, cy-96, cx+96, cy+96, fill=PANEL, outline="")
            for x, y, label in [(cx, cy-70, "⌃"), (cx, cy+70, "⌄"),
                                (cx-70, cy, "‹"), (cx+70, cy, "›")]:
                self.pad.create_text(x, y, text=label, fill=FG, font=("Segoe UI", 23))
            self.pad.create_oval(cx-43, cy-43, cx+43, cy+43, fill=ACCENT, outline="#9fc3ff", width=1)
            self.hint_id = self.pad.create_text(cx, cy, text="OK", fill=BG,
                                               font=("Segoe UI Semibold", 14))
        self.flash_id = self.pad.create_text(cx, 227, fill=ACCENT, text="",
                                             font=("Segoe UI", 8))

    # ---- sending -------------------------------------------------------------------

    def send(self, key: str) -> None:
        self.conn.key(key)
        self.pad.itemconfigure(self.flash_id, text=key.replace("DPAD_", "").replace("_", " "))
        if self.flash_job:
            self.root.after_cancel(self.flash_job)
        self.flash_job = self.root.after(500, lambda: self.pad.itemconfigure(self.flash_id, text=""))

    # ---- keyboard ------------------------------------------------------------------

    def _bind_keys(self) -> None:
        self.root.bind("<KeyPress>", self._key)

    def _key(self, event) -> str | None:
        if event.widget is self.entry or self.dialog:
            return None
        if event.keysym.lower() == "t" or event.keysym == "slash":
            self.entry.focus_set()
            return "break"
        key = NAV_KEYS.get(event.keysym) or NAV_KEYS.get(event.keysym.lower())
        if key:
            self.send(key)
            return "break"
        return None

    # ---- touchpad ------------------------------------------------------------------

    def _step(self, x: int, y: int) -> bool:
        """Send one D-pad key if the pointer moved far enough from the anchor."""
        ax, ay = self.anchor
        dx, dy = x - ax, y - ay
        if max(abs(dx), abs(dy)) < STEP:
            return False
        if abs(dx) >= abs(dy):
            self.send("DPAD_RIGHT" if dx > 0 else "DPAD_LEFT")
            self.anchor = (ax + (STEP if dx > 0 else -STEP), y)
        else:
            self.send("DPAD_DOWN" if dy > 0 else "DPAD_UP")
            self.anchor = (x, ay + (STEP if dy > 0 else -STEP))
        return True

    def _pad_resized(self, event) -> None:
        self._draw_pad()

    def _pad_press(self, event) -> None:
        self.pad.focus_set()
        self.anchor = (event.x, event.y)
        self.dragged = False

    def _pad_drag(self, event) -> None:
        if not self.touch_mode:
            if self.anchor and max(abs(event.x - self.anchor[0]),
                                   abs(event.y - self.anchor[1])) > 6:
                self.dragged = True
            return
        if self.anchor and self._step(event.x, event.y):
            self.dragged = True

    def _pad_release(self, event) -> None:
        if not self.touch_mode:
            if self.dragged or self.anchor is None:
                return
            dx, dy = event.x - self.pad.winfo_width() / 2, event.y - 112
            distance = dx * dx + dy * dy
            if distance <= 43 * 43:
                self.send("DPAD_CENTER")
            elif distance <= 101 * 101:
                if abs(dx) > abs(dy):
                    self.send("DPAD_RIGHT" if dx > 0 else "DPAD_LEFT")
                else:
                    self.send("DPAD_DOWN" if dy > 0 else "DPAD_UP")
            self.anchor = None
            return
        if not self.dragged and 0 <= event.x < self.pad.winfo_width() and 0 <= event.y < self.pad.winfo_height():
            self.send("DPAD_CENTER")
        self.anchor = None if not self.hover_var.get() else (event.x, event.y)

    def _pad_leave(self, event) -> None:
        self.anchor = None
        self.dragged = True

    def _pad_hover(self, event) -> None:
        if not self.touch_mode or not self.hover_var.get():
            return
        if self.anchor is None:
            self.anchor = (event.x, event.y)
            return
        if self._step(event.x, event.y):
            # Put the pointer back in the middle so that it does not leave the pad.
            cx, cy = self.pad.winfo_width() // 2, self.pad.winfo_height() // 2
            self.anchor = (cx, cy)
            self.pad.event_generate("<Motion>", warp=True, x=cx, y=cy)

    def _wheel(self, event) -> str:
        if self.root.focus_get() is self.entry or self.dialog:
            return "break"
        self.wheel_accum += event.delta
        while abs(self.wheel_accum) >= WHEEL_STEP:
            up = self.wheel_accum > 0
            self.send("VOLUME_UP" if up else "VOLUME_DOWN")
            self.wheel_accum -= WHEEL_STEP if up else -WHEEL_STEP
        return "break"  # Do not also run the toplevel's MouseWheel binding.

    # ---- text ----------------------------------------------------------------------

    def _text_changed(self, *_) -> None:
        value = self.text_var.get()
        if value == self.sent_text:
            return
        if not self.connected:
            self.status.configure(text="Connect to a TV before typing.", fg=BAD)
            return
        # The remote inserts text at the TV cursor; resending the whole value
        # duplicates preceding characters. Rewrite only the changed suffix.
        common = 0
        for old, new in zip(self.sent_text, value):
            if old != new:
                break
            common += 1
        for _ in self.sent_text[common:]:
            self.conn.key("DEL")
        if value[common:]:
            self.conn.text(value[common:])
        self.sent_text = value

    def _text_submit(self) -> str:
        if not self.connected:
            self.status.configure(text="Connect to a TV before sending text.", fg=BAD)
            return "break"
        self._text_changed()
        self.conn.key("ENTER")
        self.sent_text = ""
        self.text_var.set("")
        self._leave_text()
        return "break"

    def _text_clear(self) -> None:
        self.text_var.set("")

    def _leave_text(self) -> str:
        self.pad.focus_set()
        return "break"

    # ---- options -------------------------------------------------------------------

    def _toggle_top(self) -> None:
        self.cfg["always_on_top"] = self.top_var.get()
        self.root.attributes("-topmost", self.cfg["always_on_top"])
        self._save_settings()

    def _toggle_hover(self) -> None:
        self.cfg["hover_mode"] = self.hover_var.get()
        self.anchor = None
        self._save_settings()

    def _save_settings(self) -> None:
        try:
            config.save(self.cfg)
        except OSError as exc:
            self.status.configure(text=f"Could not save settings: {exc}", fg=BAD)

    # ---- connect dialog ------------------------------------------------------------

    def open_connect_dialog(self) -> None:
        if self.dialog:
            self.dialog.lift()
            return
        d = self.dialog = tk.Toplevel(self.root, bg=BG, padx=12, pady=10)
        d.title("Select TV")
        d.transient(self.root)
        d.resizable(False, False)
        d.protocol("WM_DELETE_WINDOW", self._close_dialog)
        d.bind("<Return>", lambda e: self._dialog_connect())
        d.bind("<Escape>", lambda e: self._close_dialog())

        tk.Label(d, text="TVs on this network:", bg=BG, fg=FG).pack(anchor="w")
        self.tv_list = tk.Listbox(d, width=44, height=6, bg=PANEL, fg=FG, relief="flat",
                                  selectbackground=ACCENT, highlightthickness=0)
        self.tv_list.pack(pady=4)
        self.tv_list.bind("<Double-Button-1>", lambda e: self._dialog_connect())
        self.tv_list.bind("<<ListboxSelect>>", self._dialog_pick)

        row = tk.Frame(d, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="IP address:", bg=BG, fg=FG).pack(side="left")
        self.ip_var = tk.StringVar(value=self.cfg["host"])
        tk.Entry(row, textvariable=self.ip_var, bg=PANEL, fg=FG, insertbackground=FG,
                 relief="flat", width=18).pack(side="left", padx=6, ipady=3)

        btns = tk.Frame(d, bg=BG)
        btns.pack(fill="x", pady=(6, 0))
        self._button(btns, "Search", self.conn.discover, width=9).pack(side="left")
        self._button(btns, "Connect", self._dialog_connect, width=9).pack(side="right")
        tk.Label(d, text="The TV and the laptop must be on the same Wi-Fi network.",
                 bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))
        self._fill_list()
        self.conn.discover()

    def _fill_list(self) -> None:
        if not self.dialog:
            return
        self.tv_list.delete(0, "end")
        for name, ip in self.found:
            self.tv_list.insert("end", f"{name}  —  {ip}")

    def _dialog_pick(self, _event=None) -> None:
        sel = self.tv_list.curselection()
        if sel:
            self.ip_var.set(self.found[sel[0]][1])

    def _dialog_connect(self) -> None:
        host = self.ip_var.get().strip()
        if not host:
            messagebox.showinfo("Win2AndroidTV Remote", "Select a TV or type its IP address.", parent=self.dialog)
            return
        name = next((n for n, ip in self.found if ip == host), host)
        self.cfg.update(host=host, name=name)
        self._save_settings()
        self.sent_text = ""
        self.text_var.set("")
        self.title.configure(text=name)
        self._close_dialog()
        self.conn.connect(host)

    def _close_dialog(self) -> None:
        if self.dialog:
            self.dialog.destroy()
            self.dialog = None

    # ---- events from the connection thread -----------------------------------------

    def _poll_events(self) -> None:
        if self.closing:
            return
        try:
            for _ in range(100):
                kind, value = self.conn.events.get_nowait()
                self._handle(kind, value)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _handle(self, kind: str, value) -> None:
        if kind == "status":
            self.status.configure(text=value, fg=DIM)
        elif kind == "error":
            self.status.configure(text=value, fg=BAD)
        elif kind == "connected":
            self.connected = value
            if not value:
                self.sent_text = ""
                self.text_var.set("")
                self.volume.configure(text="Volume: —")
                self.app_label.configure(text="Offline · Choose a TV in the ··· menu")
            else:
                self.app_label.configure(text="Ready to watch")
            self.dot.itemconfigure(self.dot_id, fill=OK if value else BAD)
            self.status.configure(text="Connected" if value else "Disconnected", fg=DIM)
        elif kind == "app":
            names = {"com.google.android.youtube.tv": "YouTube", "com.netflix.ninja": "Netflix",
                     "com.google.android.tvlauncher": "Home", "com.google.android.apps.tv.launcherx": "Home"}
            label = names.get(value, str(value).rsplit(".", 1)[-1].replace("_", " ").title())
            self.app_label.configure(text=label[:38])
        elif kind == "volume":
            level, maximum = value.get("level", 0), value.get("max", 0)
            self.volume.configure(text="Volume: Muted" if value.get("muted")
                                  else f"Volume: {level} / {maximum}")
        elif kind == "found":
            self.found = value
            self._fill_list()
        elif kind == "need_pair":
            if messagebox.askyesno("Win2AndroidTV Remote", "This TV is not paired yet. Pair now?\n"
                                   "A code will show on the TV screen."):
                self.conn.start_pairing()
            else:
                self.conn.cancel_pairing()
        elif kind == "pair_code":
            code = simpledialog.askstring("Pair with TV", value or "Type the six-character code on the TV screen:",
                                          parent=self.root)
            if code:
                self.conn.finish_pairing(code)
            else:
                self.conn.cancel_pairing()

    def quit(self) -> None:
        self.closing = True
        self.conn.close()
        self.root.withdraw()
        self._finish_quit()

    def _finish_quit(self) -> None:
        if self.conn.thread.is_alive():
            self.root.after(25, self._finish_quit)
        else:
            self.root.destroy()
