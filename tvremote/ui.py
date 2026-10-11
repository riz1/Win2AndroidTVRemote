"""Tk window: touchpad, buttons, keyboard and text input."""

import queue
import tkinter as tk
from tkinter import messagebox, simpledialog

from . import config
from .connection import TvConnection

BG = "#1e1f24"
PANEL = "#2a2c33"
PAD = "#33363f"
FG = "#e8e8ec"
DIM = "#9a9caa"
ACCENT = "#4f8cff"
OK = "#3ecf6e"
BAD = "#e5534b"
POWER = "#5a2a2d"

PAD_SIZE = (360, 190)
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
            bd=0, padx=4, pady=7, font=("Segoe UI", font_size), takefocus=0,
            cursor="hand2", **kw,
        )

    def _section(self, parent, title: str) -> tk.Frame:
        tk.Label(parent, text=title.upper(), bg=BG, fg=DIM,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(10, 3))
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
        outer = tk.Frame(root, bg=BG, padx=14, pady=12)
        outer.pack(fill="both")

        # Header: state dot, TV name, options.
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        self.dot = tk.Canvas(head, width=12, height=12, bg=BG, highlightthickness=0)
        self.dot_id = self.dot.create_oval(1, 1, 11, 11, fill=BAD, outline="")
        self.dot.pack(side="left")
        self.title = tk.Label(head, text=self.cfg["name"] or "No TV", bg=BG, fg=FG,
                              font=("Segoe UI Semibold", 12))
        self.title.pack(side="left", padx=6)
        self._button(head, "Change TV", self.open_connect_dialog, width=9,
                     font_size=9).pack(side="right")
        self.top_var = tk.BooleanVar(value=self.cfg["always_on_top"])
        tk.Checkbutton(head, text="On top", variable=self.top_var, command=self._toggle_top,
                       bg=BG, fg=DIM, selectcolor=PANEL, activebackground=BG,
                       activeforeground=FG, takefocus=0).pack(side="right", padx=6)

        # Touchpad.
        w, h = PAD_SIZE
        self.pad = tk.Canvas(outer, width=w, height=h, bg=PAD, highlightthickness=2,
                             highlightbackground=PAD, highlightcolor=ACCENT, cursor="hand2")
        self.pad.pack(pady=(12, 4), fill="x", padx=2)
        self.hint_id = self.pad.create_text(w // 2, h // 2 - 14, fill=DIM, font=("Segoe UI", 10),
                             justify="center",
                             text="Drag to move · Click = OK\nRight-click = Back · "
                                  "Middle = Home\nWheel / two fingers = Volume")
        self.flash_id = self.pad.create_text(w // 2, h - 30, fill=ACCENT, text="",
                                             font=("Segoe UI Semibold", 13))
        self.pad.bind("<Configure>", self._pad_resized)
        self.pad.bind("<ButtonPress-1>", self._pad_press)
        self.pad.bind("<B1-Motion>", self._pad_drag)
        self.pad.bind("<ButtonRelease-1>", self._pad_release)
        self.pad.bind("<Motion>", self._pad_hover)
        self.pad.bind("<Leave>", lambda e: setattr(self, "anchor", None))
        self.pad.bind("<Button-3>", lambda e: self.send("BACK"))
        self.pad.bind("<Button-2>", lambda e: self.send("HOME"))
        self.pad.bind("<MouseWheel>", self._wheel)
        root.bind("<MouseWheel>", self._wheel)

        self.hover_var = tk.BooleanVar(value=self.cfg["hover_mode"])
        tk.Checkbutton(outer, text="Hover mode (move the pointer on the pad, no click needed)",
                       variable=self.hover_var, command=self._toggle_hover, bg=BG, fg=DIM,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       takefocus=0, font=("Segoe UI", 8)).pack(anchor="w")

        # Navigation.
        self._button_grid(self._section(outer, "Navigate"), [
            self._key_button("◀  Back", "BACK"),
            self._key_button("⌂  Home", "HOME"),
            self._key_button("☰  Menu", "MENU"),
        ], columns=3)

        # Volume and playback.
        self._button_grid(self._section(outer, "Volume & play"), [
            self._key_button("−", "VOLUME_DOWN", font_size=14),
            self._key_button("🔇", "VOLUME_MUTE", font_size=12),
            self._key_button("+", "VOLUME_UP", font_size=14),
            self._key_button("⏯", "MEDIA_PLAY_PAUSE", font_size=12, bg=PAD),
        ], columns=4)

        # TV functions and app shortcuts.
        tv_items = [
            self._key_button("Power", "POWER", bg=POWER),
            self._key_button("⇄  Input", "TV_INPUT"),
            self._key_button("⚙  Settings", "SETTINGS"),
        ]
        tv_items += [(f"▶  {name}", lambda l=link: self.conn.launch(l), {"bg": PAD})
                     for name, link in self.cfg["apps"]]
        self._button_grid(self._section(outer, "TV & apps"), tv_items, columns=2)

        # Text input.
        txt = self._section(outer, "Type on TV  (select a search box on the TV first)")
        self.text_var = tk.StringVar()
        self.entry = tk.Entry(txt, textvariable=self.text_var, bg=PANEL, fg=FG,
                              insertbackground=FG, relief="flat", font=("Segoe UI", 11),
                              width=10, highlightthickness=1, highlightbackground=PANEL,
                              highlightcolor=ACCENT)
        self.entry.pack(side="left", ipady=5, fill="x", expand=True, padx=(2, 0))
        self._button(txt, "✕", self._text_clear, width=3).pack(side="right", padx=(4, 2))
        self._button(txt, "Send ⏎", self._text_submit, width=7, bg=ACCENT).pack(
            side="right", padx=(4, 0))
        self.text_var.trace_add("write", self._text_changed)
        self.entry.bind("<Return>", lambda e: self._text_submit())
        self.entry.bind("<Escape>", lambda e: self._leave_text())

        tk.Label(outer, text=HELP, bg=BG, fg=DIM, font=("Segoe UI", 8),
                 justify="left").pack(anchor="w", pady=(12, 0))

        # Status bar.
        self.status = tk.Label(root, text="", bg=PANEL, fg=DIM, font=("Segoe UI", 9),
                               anchor="w", padx=14, pady=5, wraplength=PAD_SIZE[0])
        self.status.pack(fill="x", side="bottom")
        self.pad.focus_set()

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
        key = NAV_KEYS.get(event.keysym)
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
        self.pad.coords(self.hint_id, event.width // 2, event.height // 2 - 14)
        self.pad.coords(self.flash_id, event.width // 2, event.height - 30)

    def _pad_press(self, event) -> None:
        self.pad.focus_set()
        self.anchor = (event.x, event.y)
        self.dragged = False

    def _pad_drag(self, event) -> None:
        if self.anchor and self._step(event.x, event.y):
            self.dragged = True

    def _pad_release(self, event) -> None:
        if not self.dragged:
            self.send("DPAD_CENTER")
        self.anchor = None if not self.hover_var.get() else (event.x, event.y)

    def _pad_hover(self, event) -> None:
        if not self.hover_var.get():
            return
        if self.anchor is None:
            self.anchor = (event.x, event.y)
            return
        if self._step(event.x, event.y):
            # Put the pointer back in the middle so that it does not leave the pad.
            cx, cy = self.pad.winfo_width() // 2, self.pad.winfo_height() // 2
            self.anchor = (cx, cy)
            self.pad.event_generate("<Motion>", warp=True, x=cx, y=cy)

    def _wheel(self, event) -> None:
        if self.root.focus_get() is self.entry:
            return
        self.wheel_accum += event.delta
        while abs(self.wheel_accum) >= WHEEL_STEP:
            up = self.wheel_accum > 0
            self.send("VOLUME_UP" if up else "VOLUME_DOWN")
            self.wheel_accum -= WHEEL_STEP if up else -WHEEL_STEP

    # ---- text ----------------------------------------------------------------------

    def _text_changed(self, *_) -> None:
        value = self.text_var.get()
        if value == self.sent_text:
            return
        if value:
            self.conn.text(value)  # the TV field gets the full text
        else:
            for _ in self.sent_text:
                self.conn.key("DEL")
        self.sent_text = value

    def _text_submit(self) -> None:
        self.conn.key("ENTER")
        self.sent_text = ""
        self.text_var.set("")
        self._leave_text()

    def _text_clear(self) -> None:
        self.text_var.set("")

    def _leave_text(self) -> str:
        self.pad.focus_set()
        return "break"

    # ---- options -------------------------------------------------------------------

    def _toggle_top(self) -> None:
        self.cfg["always_on_top"] = self.top_var.get()
        self.root.attributes("-topmost", self.cfg["always_on_top"])
        config.save(self.cfg)

    def _toggle_hover(self) -> None:
        self.cfg["hover_mode"] = self.hover_var.get()
        self.anchor = None
        config.save(self.cfg)

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
        name = next((n for n, ip in self.found if ip == host), self.cfg["name"] or host)
        self.cfg.update(host=host, name=name)
        config.save(self.cfg)
        self.title.configure(text=name)
        self._close_dialog()
        self.conn.connect(host)

    def _close_dialog(self) -> None:
        if self.dialog:
            self.dialog.destroy()
            self.dialog = None

    # ---- events from the connection thread -----------------------------------------

    def _poll_events(self) -> None:
        try:
            while True:
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
            self.dot.itemconfigure(self.dot_id, fill=OK if value else BAD)
            self.status.configure(text="Connected" if value else "Disconnected", fg=DIM)
        elif kind == "app":
            self.status.configure(text=f"App: {value}", fg=DIM)
        elif kind == "found":
            self.found = value
            self._fill_list()
        elif kind == "need_pair":
            if messagebox.askyesno("Win2AndroidTV Remote", "This TV is not paired yet. Pair now?\n"
                                   "A code will show on the TV screen."):
                self.conn.start_pairing()
        elif kind == "pair_code":
            code = simpledialog.askstring("Pair with TV", "Type the code on the TV screen:",
                                          parent=self.root)
            if code:
                self.conn.finish_pairing(code)
            else:
                self.status.configure(text="Pairing cancelled", fg=DIM)

    def quit(self) -> None:
        self.conn.close()
        self.root.after(150, self.root.destroy)
