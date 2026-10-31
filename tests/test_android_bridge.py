"""Exercise Android's protocol adapter on desktop without a TV or Android SDK."""
import asyncio
import importlib.util
import json
from pathlib import Path
import queue
import unittest
from unittest.mock import AsyncMock, Mock, patch

spec = importlib.util.spec_from_file_location(
    "remote_bridge", Path(__file__).resolve().parents[1] / "android/app/src/main/python/remote_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class AndroidBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = bridge.Engine.__new__(bridge.Engine)
        self.engine.events = queue.Queue()
        self.engine.loop = asyncio.get_running_loop()
        self.engine.remote = Mock()
        self.engine.host = "test-tv"
        self.engine.connected = True
        self.engine.closed = False
        self.engine.operations = set()
        self.engine.directory = Path("unused-test-directory")

    async def test_invalid_pair_code_stays_retryable(self):
        self.engine.remote.async_finish_pairing = AsyncMock()
        await self.engine._finish("XYZ")
        self.engine.remote.async_finish_pairing.assert_not_called()
        self.assertEqual(json.loads(self.engine.poll())[0][0], "pair_code")

    async def test_rejected_code_stays_retryable(self):
        self.engine.remote.async_finish_pairing = AsyncMock(side_effect=bridge.InvalidAuth())
        await self.engine._finish("ABC123")
        self.assertEqual(json.loads(self.engine.poll())[0][0], "pair_code")

    async def test_commands_are_sent_once(self):
        self.engine._send("text", "cat")
        self.engine._send("key", "ENTER")
        self.engine.remote.send_text.assert_called_once_with("cat")
        self.engine.remote.send_key_command.assert_called_once_with("ENTER")

    async def test_offline_commands_are_not_sent(self):
        self.engine.connected = False
        self.engine._send("key", "POWER")
        self.engine.remote.send_key_command.assert_not_called()
        self.assertEqual(json.loads(self.engine.poll())[0][0], "error")

    async def test_suspend_clears_stale_pairing_events(self):
        remote = self.engine.remote
        self.engine.emit("need_pair")
        await self.engine._suspend()
        remote.disconnect.assert_called_once()
        self.assertEqual(json.loads(self.engine.poll()), [["connected", False]])

    async def test_connect_auth_failure_requests_pairing(self):
        remote = Mock()
        remote.async_generate_cert_if_missing = AsyncMock()
        remote.async_connect = AsyncMock(side_effect=bridge.InvalidAuth())
        with patch.object(bridge, "AndroidTVRemote", return_value=remote):
            await self.engine._connect("tv")
        self.assertEqual(json.loads(self.engine.poll())[-1][0], "need_pair")

    async def test_new_operation_cancels_previous(self):
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def first():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        async def second():
            self.assertTrue(cleaned.is_set())

        self.engine._replace(first, ())
        await started.wait()
        self.engine._replace(second, ())
        await asyncio.gather(*self.engine.operations, return_exceptions=True)
        self.assertTrue(cleaned.is_set())
