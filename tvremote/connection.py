"""Android TV Remote protocol v2 connection, run on a background asyncio loop."""

import asyncio
import logging
import queue
import re
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
        self._closed = False
        self._operation = None
        self._operations = set()
        self._discovery = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            if self.remote:
                self.remote.disconnect()
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()

    # ---- called from the UI thread -------------------------------------------------

    def discover(self) -> None:
        self._schedule(self._begin_discovery)

    def connect(self, host: str) -> None:
        self._schedule(self._begin_operation, self._connect, host.strip())

    def start_pairing(self) -> None:
        self._schedule(self._begin_operation, self._start_pairing)

    def finish_pairing(self, code: str) -> None:
        self._schedule(self._begin_operation, self._finish_pairing, code)

    def cancel_pairing(self) -> None:
        self._schedule(self._begin_operation, self._cancel_pairing)

    def key(self, name: str) -> None:
        self._schedule(self._send, "key", name)

    def text(self, value: str) -> None:
        self._schedule(self._send, "text", value)

    def launch(self, link: str) -> None:
        self._schedule(self._send, "launch", link)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.loop.call_soon_threadsafe(self.loop.stop)

    # ---- loop thread ---------------------------------------------------------------

    def _emit(self, kind: str, value=None) -> None:
        self.events.put((kind, value))

    def _schedule(self, callback, *args) -> None:
        if not self._closed:
            self.loop.call_soon_threadsafe(callback, *args)

    def _begin_discovery(self) -> None:
        if self._discovery is None or self._discovery.done():
            self._discovery = self.loop.create_task(self._discover())
            self._discovery.add_done_callback(self._report)

    def _begin_operation(self, operation, *args) -> None:
        previous = tuple(self._operations)
        for task in previous:
            task.cancel()

        async def run():
            if previous:
                await asyncio.gather(*previous, return_exceptions=True)
            try:
                await asyncio.wait_for(operation(*args), timeout=25)
            except asyncio.TimeoutError:
                if self.remote:
                    self.remote.disconnect()
                self._emit("connected", False)
                self._emit("error", "TV did not respond. Try connecting again.")

        self._operation = self.loop.create_task(run())
        self._operations.add(self._operation)
        self._operation.add_done_callback(self._operations.discard)
        self._operation.add_done_callback(self._report)

    def _report(self, future) -> None:
        if future.cancelled():
            return
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
            self._emit("connected", False)
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
        found = []
        try:
            await asyncio.sleep(timeout)
            for name in list(names):
                info = AsyncServiceInfo(SERVICE, name)
                if await info.async_request(aiozc.zeroconf, 1500):
                    addresses = info.parsed_addresses(IPVersion.V4Only)
                    if addresses:
                        found.append((name.removesuffix("." + SERVICE), addresses[0]))
        finally:
            try:
                await browser.async_cancel()
            finally:
                await aiozc.async_close()
        self._emit("found", found)
        self._emit("status", f"Found {len(found)} TV(s)")

    def _make_remote(self, host: str) -> AndroidTVRemote:
        old, self.remote = self.remote, None
        if old:
            old.disconnect()
        self.host = host
        remote = AndroidTVRemote(
            CLIENT_NAME, str(config.CERT_FILE), str(config.KEY_FILE), host, loop=self.loop
        )
        def emit_current(kind, value=None):
            if self.remote is remote:
                self._emit(kind, value)
        remote.add_volume_info_updated_callback(lambda v: emit_current("volume", v))
        remote.add_current_app_updated_callback(lambda a: emit_current("app", a))
        remote.add_is_available_updated_callback(lambda ok: emit_current("connected", ok))
        self.remote = remote
        return remote

    async def _connect(self, host: str) -> None:
        remote = self._make_remote(host)
        self._emit("connected", False)
        await remote.async_generate_cert_if_missing()
        self._emit("status", f"Connecting to {host}...")
        try:
            await remote.async_connect()
        except InvalidAuth:
            self._emit("need_pair")
            return
        except (CannotConnect, ConnectionClosed) as exc:
            remote.disconnect()
            self._emit("connected", False)
            self._emit("status", f"Cannot connect to {host}. Is the TV on? ({exc})")
            return
        remote.keep_reconnecting(
            lambda: self._emit("need_pair") if self.remote is remote else None)
        self._emit("connected", True)
        if remote.volume_info:
            self._emit("volume", remote.volume_info)
        if remote.current_app:
            self._emit("app", remote.current_app)

    async def _start_pairing(self) -> None:
        if not self.host:
            self._emit("error", "Select a TV first.")
            return
        remote = self.remote or self._make_remote(self.host)
        remote.disconnect()
        await remote.async_generate_cert_if_missing()
        self._emit("status", "Look at the TV for the pairing code")
        await remote.async_start_pairing()
        self._emit("pair_code")

    async def _finish_pairing(self, code: str) -> None:
        code = code.strip().upper()
        if not re.fullmatch(r"[0-9A-F]{6}", code):
            self._emit("pair_code", "Enter all six characters (0–9 and A–F) shown on the TV.")
            return
        if self.remote is None:
            self._emit("error", "Select a TV and start pairing first.")
            return
        try:
            await self.remote.async_finish_pairing(code)
        except InvalidAuth:
            self._emit("pair_code", "Incorrect code. Try the six characters on the TV again.")
            return
        except ConnectionClosed:
            self._emit("error", "Pairing connection closed. Connect to the TV to try again.")
            self.remote.disconnect()
            return
        self._emit("status", "Paired")
        await self._connect(self.host)

    async def _cancel_pairing(self) -> None:
        if self.remote:
            self.remote.disconnect()
        self._emit("connected", False)
        self._emit("status", "Pairing cancelled")
