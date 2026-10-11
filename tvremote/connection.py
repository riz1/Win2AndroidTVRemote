"""Android TV Remote protocol v2 connection, run on a background asyncio loop."""

import asyncio
import logging
import queue
import threading

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth
from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from . import config

LOG = logging.getLogger(__name__)
SERVICE = "_androidtvremote2._tcp.local."
CLIENT_NAME = "Win2AndroidTV Remote"


class TvConnection:
    """Thread-safe front end. Events go to `self.events` as (kind, value) tuples.

    Kinds: "status" (text), "connected" (bool), "need_pair", "pair_code",
    "volume" (VolumeInfo), "app" (package), "found" (list of (name, ip)), "error" (text).
    """

    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self.remote: AndroidTVRemote | None = None
        self.host = ""
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    # ---- called from the UI thread -------------------------------------------------

    def discover(self) -> None:
        self._submit(self._discover())

    def connect(self, host: str) -> None:
        self._submit(self._connect(host))

    def start_pairing(self) -> None:
        self._submit(self._start_pairing())

    def finish_pairing(self, code: str) -> None:
        self._submit(self._finish_pairing(code))

    def key(self, name: str) -> None:
        self.loop.call_soon_threadsafe(self._send, "key", name)

    def text(self, value: str) -> None:
        self.loop.call_soon_threadsafe(self._send, "text", value)

    def launch(self, link: str) -> None:
        self.loop.call_soon_threadsafe(self._send, "launch", link)

    def close(self) -> None:
        if self.remote:
            self.loop.call_soon_threadsafe(self.remote.disconnect)

    # ---- loop thread ---------------------------------------------------------------

    def _emit(self, kind: str, value=None) -> None:
        self.events.put((kind, value))

    def _submit(self, coro) -> None:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        future.add_done_callback(self._report)

    def _report(self, future) -> None:
        exc = future.exception()
        if exc:
            LOG.exception("Task failed", exc_info=exc)
            self._emit("error", str(exc) or type(exc).__name__)

    def _send(self, kind: str, value: str) -> None:
        if not self.remote:
            self._emit("status", "Not connected")
            return
        try:
            if kind == "key":
                self.remote.send_key_command(value)
            elif kind == "text":
                self.remote.send_text(value)
            else:
                self.remote.send_launch_app_command(value)
        except ConnectionClosed:
            self._emit("status", "Connection lost, retrying...")
        except Exception as exc:  # noqa: BLE001 - show any send error in the UI
            LOG.exception("Send failed")
            self._emit("error", str(exc))

    async def _discover(self, timeout: float = 3.0) -> None:
        self._emit("status", "Searching the network...")
        names: list[str] = []

        def on_change(zeroconf, service_type, name, state_change):
            if state_change is ServiceStateChange.Added and name not in names:
                names.append(name)

        aiozc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        browser = AsyncServiceBrowser(aiozc.zeroconf, SERVICE, handlers=[on_change])
        await asyncio.sleep(timeout)
        found = []
        for name in names:
            info = AsyncServiceInfo(SERVICE, name)
            if await info.async_request(aiozc.zeroconf, 1500):
                addresses = info.parsed_addresses(IPVersion.V4Only)
                if addresses:
                    found.append((name.removesuffix("." + SERVICE), addresses[0]))
        await browser.async_cancel()
        await aiozc.async_close()
        self._emit("found", found)
        self._emit("status", f"Found {len(found)} TV(s)")

    def _make_remote(self, host: str) -> AndroidTVRemote:
        if self.remote:
            self.remote.disconnect()
        self.host = host
        remote = AndroidTVRemote(
            CLIENT_NAME, str(config.CERT_FILE), str(config.KEY_FILE), host, loop=self.loop
        )
        remote.add_volume_info_updated_callback(lambda v: self._emit("volume", v))
        remote.add_current_app_updated_callback(lambda a: self._emit("app", a))
        remote.add_is_available_updated_callback(lambda ok: self._emit("connected", ok))
        self.remote = remote
        return remote

    async def _connect(self, host: str) -> None:
        remote = self._make_remote(host)
        await remote.async_generate_cert_if_missing()
        self._emit("status", f"Connecting to {host}...")
        try:
            await remote.async_connect()
        except InvalidAuth:
            self._emit("need_pair")
            return
        except (CannotConnect, ConnectionClosed) as exc:
            self._emit("connected", False)
            self._emit("status", f"Cannot connect to {host}. Is the TV on? ({exc})")
            return
        remote.keep_reconnecting(lambda: self._emit("need_pair"))
        self._emit("connected", True)
        if remote.volume_info:
            self._emit("volume", remote.volume_info)
        if remote.current_app:
            self._emit("app", remote.current_app)

    async def _start_pairing(self) -> None:
        remote = self.remote or self._make_remote(self.host)
        await remote.async_generate_cert_if_missing()
        self._emit("status", "Look at the TV for the pairing code")
        await remote.async_start_pairing()
        self._emit("pair_code")

    async def _finish_pairing(self, code: str) -> None:
        try:
            await self.remote.async_finish_pairing(code.strip())
        except (InvalidAuth, ConnectionClosed) as exc:
            self._emit("error", f"Pairing failed: {exc}")
            return
        self._emit("status", "Paired")
        await self._connect(self.host)
