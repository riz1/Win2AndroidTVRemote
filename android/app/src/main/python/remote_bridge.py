"""Android-facing API; all TV I/O stays on a background asyncio loop."""
import asyncio
import json
from pathlib import Path
import queue
import re
import threading

from androidtvremote2 import AndroidTVRemote, InvalidAuth, ConnectionClosed


class Engine:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self.remote = None
        self.host = ""
        self.closed = False
        self.connected = False
        self.operations = set()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self.loop)
            for task in tasks:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            if self.remote:
                self.remote.disconnect()
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()

    def emit(self, kind, value=None):
        self.events.put([kind, value])

    def poll(self):
        result = []
        for _ in range(100):
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                break
        return json.dumps(result)

    def _submit(self, method, *args):
        if not self.closed:
            self.loop.call_soon_threadsafe(self._replace, method, args)

    def _replace(self, method, args):
        previous = tuple(self.operations)
        for task in previous:
            task.cancel()

        async def run():
            await asyncio.gather(*previous, return_exceptions=True)
            try:
                await asyncio.wait_for(method(*args), 25)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._disconnect()
                self.emit("error", str(exc) or "TV did not respond. Try reconnecting.")

        task = self.loop.create_task(run())
        self.operations.add(task)
        task.add_done_callback(self.operations.discard)

    def connect(self, host):
        self._submit(self._connect, host.strip())

    async def _connect(self, host):
        self._disconnect()
        self.host = host
        self.emit("status", "Connecting…")
        remote = AndroidTVRemote("TV Remote for Android", str(self.directory / "cert.pem"),
                                 str(self.directory / "key.pem"), host, loop=self.loop)
        self.remote = remote

        def current(kind, value=None):
            if self.remote is remote:
                if kind == "connected":
                    self.connected = bool(value)
                self.emit(kind, value)

        remote.add_is_available_updated_callback(lambda value: current("connected", value))
        remote.add_volume_info_updated_callback(lambda value: current("volume", value))
        remote.add_current_app_updated_callback(lambda value: current("app", value))
        await remote.async_generate_cert_if_missing()
        try:
            await remote.async_connect()
        except InvalidAuth:
            current("need_pair")
            return
        self.connected = True
        remote.keep_reconnecting(lambda: current("need_pair"))
        current("connected", True)
        if remote.volume_info:
            current("volume", remote.volume_info)

    def pair(self):
        self._submit(self._pair)

    async def _pair(self):
        if self.remote is None:
            raise ValueError("Choose a TV first.")
        self.remote.disconnect()
        self.connected = False
        await self.remote.async_start_pairing()
        self.emit("pair_code", "Enter the six-character code shown on your TV.")

    def finish_pairing(self, code):
        self._submit(self._finish, code.strip().upper())

    async def _finish(self, code):
        if not re.fullmatch(r"[0-9A-F]{6}", code):
            self.emit("pair_code", "Use six characters: 0–9 and A–F.")
            return
        if self.remote is None:
            raise ValueError("Reconnect to your TV to pair again.")
        try:
            await self.remote.async_finish_pairing(code)
        except InvalidAuth:
            self.emit("pair_code", "Incorrect code. Check your TV and try again.")
            return
        await self._connect(self.host)

    def send(self, kind, value):
        if not self.closed:
            self.loop.call_soon_threadsafe(self._send, kind, value)

    def _send(self, kind, value):
        if not self.remote or not self.connected:
            self.emit("error", "Connect to a TV first.")
            return
        try:
            if kind == "key":
                self.remote.send_key_command(value)
            elif kind == "text" and value:
                self.remote.send_text(value)
            elif kind == "app":
                self.remote.send_launch_app_command(value)
        except ConnectionClosed:
            self.connected = False
            self.emit("connected", False)
        except Exception as exc:
            self.emit("error", str(exc))

    def _disconnect(self):
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
        old, self.remote = self.remote, None
        if old:
            old.disconnect()
        self.connected = False
        self.emit("connected", False)

    async def _suspend(self):
        self._disconnect()

    def suspend(self):
        self._submit(self._suspend)

    def close(self):
        if not self.closed:
            self.closed = True
            self.loop.call_soon_threadsafe(self.loop.stop)
