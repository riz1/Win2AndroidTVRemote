import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from tvremote import config
from tvremote.connection import TvConnection
from tvremote.ui import RemoteApp


class SettingsTests(unittest.TestCase):
    def test_invalid_settings_and_shortcuts_are_safe(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            target = Path(directory) / "config.json"
            with patch.object(config, "APP_DIR", Path(directory)), patch.object(config, "CONFIG_FILE", target):
                for value in ([], None, 17, "bad"):
                    target.write_text(json.dumps(value))
                    self.assertEqual(config.load(), config.DEFAULTS)
                target.write_text(json.dumps({"host": 123, "always_on_top": "false",
                                               "apps": [None, ["bad"], ["TV", "link"]]}))
                result = config.load()
                self.assertEqual(result["host"], "")
                self.assertFalse(result["always_on_top"])
                self.assertEqual(result["apps"], [["TV", "link"]])
                config.save(result)
                self.assertEqual(config.load(), result)
                self.assertFalse(target.with_suffix(".tmp").exists())

    def test_defaults_are_not_shared(self):
        with patch.object(config, "CONFIG_FILE", Path("nonexistent-settings.json")):
            loaded = config.load()
            loaded["apps"][0][0] = "changed"
            self.assertEqual(config.DEFAULT_APPS[0][0], "YouTube")


class InputTests(unittest.TestCase):
    def setUp(self):
        self.app = RemoteApp.__new__(RemoteApp)
        self.app.conn = Mock()
        self.app.text_var = Mock()
        self.app.status = Mock()
        self.app.pad = Mock()
        self.app.sent_text = ""
        self.app.connected = True

    def edit(self, text):
        self.app.text_var.get.return_value = text
        self.app._text_changed()

    def test_typing_does_not_repeat_previous_characters(self):
        for text in ("c", "ca", "cat"):
            self.edit(text)
        self.assertEqual([c.args[0] for c in self.app.conn.text.call_args_list], ["c", "a", "t"])
        self.app.conn.key.assert_not_called()

    def test_replacement_deletion_and_paste(self):
        self.edit("cat")
        self.app.conn.reset_mock()
        self.edit("coat")
        self.assertEqual(self.app.conn.key.call_count, 2)
        self.app.conn.text.assert_called_once_with("oat")
        self.app.conn.reset_mock()
        self.edit("")
        self.assertEqual(self.app.conn.key.call_count, 4)
        self.app.conn.text.assert_not_called()
        self.edit("pasted text")
        self.app.conn.text.assert_called_once_with("pasted text")

    def test_submit_is_one_enter_and_no_deletions(self):
        self.edit("cat")
        self.app.conn.reset_mock()
        self.assertEqual(self.app._text_submit(), "break")
        self.app.conn.key.assert_called_once_with("ENTER")
        self.app.text_var.set.assert_called_once_with("")

    def test_offline_typing_does_not_advance_sent_state(self):
        self.app.connected = False
        self.edit("cat")
        self.assertEqual(self.app.sent_text, "")
        self.app.conn.text.assert_not_called()

    def test_wheel_stops_bubbling_and_accumulates_small_deltas(self):
        self.app.root = Mock()
        self.app.entry = object()
        self.app.dialog = None
        self.app.wheel_accum = 0
        self.app.send = Mock()
        for _ in range(3):
            self.assertEqual(self.app._wheel(SimpleNamespace(delta=40)), "break")
        self.app.send.assert_called_once_with("VOLUME_UP")
        self.app.dialog = object()
        self.app._wheel(SimpleNamespace(delta=120))
        self.app.send.assert_called_once()

    def test_navigation_ring_hit_targets(self):
        self.app.touch_mode = False
        self.app.pad.winfo_width.return_value = 300
        self.app.send = Mock()
        for x, y, expected in [(150, 112, "DPAD_CENTER"), (150, 42, "DPAD_UP"),
                               (150, 182, "DPAD_DOWN"), (80, 112, "DPAD_LEFT"),
                               (220, 112, "DPAD_RIGHT")]:
            self.app._pad_press(SimpleNamespace(x=x, y=y))
            self.app._pad_release(SimpleNamespace(x=x, y=y))
            self.app.send.assert_called_with(expected)
        self.assertEqual(self.app.send.call_count, 5)
        self.app._pad_press(SimpleNamespace(x=5, y=5))
        self.app._pad_release(SimpleNamespace(x=5, y=5))
        self.assertEqual(self.app.send.call_count, 5)

    def test_ring_click_tolerates_small_pointer_movement(self):
        self.app.touch_mode = False
        self.app.pad.winfo_width.return_value = 300
        self.app.send = Mock()
        self.app._pad_press(SimpleNamespace(x=150, y=112))
        self.app._pad_drag(SimpleNamespace(x=152, y=114))
        self.app._pad_release(SimpleNamespace(x=152, y=114))
        self.app.send.assert_called_once_with("DPAD_CENTER")


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = TvConnection.__new__(TvConnection)
        self.conn.loop = asyncio.get_running_loop()
        self.conn.remote = Mock()
        self.conn._emit = Mock()
        self.conn._operation = None
        self.conn._operations = set()

    async def test_pair_code_validation_and_retry(self):
        self.conn.remote.async_finish_pairing = AsyncMock()
        await self.conn._finish_pairing("ZZ1234")
        self.conn.remote.async_finish_pairing.assert_not_called()
        self.assertEqual(self.conn._emit.call_args.args[0], "pair_code")

    async def test_wrong_code_can_be_retried(self):
        from androidtvremote2 import InvalidAuth
        self.conn.remote.async_finish_pairing = AsyncMock(side_effect=InvalidAuth())
        await self.conn._finish_pairing("abcdef")
        self.conn.remote.async_finish_pairing.assert_awaited_once_with("ABCDEF")
        self.assertEqual(self.conn._emit.call_args.args[0], "pair_code")

    async def test_connection_operations_cancel_and_wait_for_predecessor(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def first():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def second():
            self.assertTrue(cancelled.is_set())

        self.conn._begin_operation(first)
        await started.wait()
        self.conn._begin_operation(second)
        await self.conn._operation
        self.assertTrue(cancelled.is_set())

    async def test_rapid_switches_wait_for_original_cleanup(self):
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def first():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        async def last():
            self.assertTrue(cleaned.is_set())

        self.conn._begin_operation(first)
        await started.wait()
        self.conn._begin_operation(AsyncMock())
        self.conn._begin_operation(last)
        await self.conn._operation

    async def test_discovery_releases_resources_on_cancel(self):
        zeroconf = Mock()
        zeroconf.async_close = AsyncMock()
        browser = Mock()
        browser.async_cancel = AsyncMock()
        with patch("tvremote.connection.AsyncZeroconf", return_value=zeroconf), \
                patch("tvremote.connection.AsyncServiceBrowser", return_value=browser):
            task = asyncio.create_task(self.conn._discover(timeout=60))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        browser.async_cancel.assert_awaited_once()
        zeroconf.async_close.assert_awaited_once()

    async def test_old_tv_callbacks_are_ignored_after_switching(self):
        first, second = Mock(), Mock()
        with patch("tvremote.connection.AndroidTVRemote", side_effect=[first, second]):
            self.conn._make_remote("first-tv")
            callback = first.add_is_available_updated_callback.call_args.args[0]
            self.conn._make_remote("second-tv")
            self.conn._emit.reset_mock()
            callback(False)
            self.conn._emit.assert_not_called()


class ShutdownTests(unittest.TestCase):
    def test_close_stops_thread_and_is_idempotent(self):
        conn = TvConnection()
        conn.close()
        conn.close()
        conn.thread.join(timeout=3)
        self.assertFalse(conn.thread.is_alive())
        self.assertTrue(conn.loop.is_closed())
        conn.key("HOME")


if __name__ == "__main__":
    unittest.main()
