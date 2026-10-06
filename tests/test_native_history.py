"""Saved inbox semantics and native incoming-message lifecycle."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock

from test_native_transport import TransportTests

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"
spec = importlib.util.spec_from_file_location("message_history", ROOT / "history.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HistoryTests(unittest.TestCase):
    def test_bounded_copy_and_reload(self):
        history = module.MessageHistory()
        for seq in range(1005):
            history.append({"text": str(seq), "direction": "out"})
        saved = history.snapshot()
        self.assertEqual(len(saved["messages"]), 1000)
        saved["messages"][0]["text"] = "changed"
        self.assertEqual(history.data["messages"][0]["text"], "5")
        history.favorite("dm:OptimusPrime", True)
        restored = module.MessageHistory(history.snapshot())
        self.assertEqual(restored.data["favorites"], ["dm:OptimusPrime"])

    def test_replayed_incoming_message_is_not_duplicated(self):
        history = module.MessageHistory()
        message = {"conversation": "pk:123", "direction": "in", "sender": "Node",
                   "text": "Hello", "sender_timestamp": 12345}
        self.assertIsNotNone(history.append(message))
        self.assertIsNone(history.append(message))
        self.assertEqual(len(history.snapshot()["messages"]), 1)

    def test_delivery_update_and_changed_callback(self):
        changed = Mock()
        history = module.MessageHistory(changed=changed)
        mid = history.append({"text": "Ping", "direction": "out", "status": "sending"})
        history.update(mid, status="delivered")
        self.assertEqual(history.snapshot()["messages"][0]["status"], "delivered")
        self.assertEqual(changed.call_count, 2)


class InboxTransportTests(TransportTests):
    def setUp(self):
        super().setUp()
        self.hass.bus = SimpleNamespace(async_fire=Mock())
        self.radio.get_contact_by_key_prefix = Mock(return_value={"adv_name": "OptimusPrime"})
        self.radio.get_contact_by_name = Mock(return_value={"adv_name": "OptimusPrime", "public_key": "abcd" * 16})

    async def test_first_message_during_auto_fetch_has_contact_name(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        client.history = module.MessageHistory()
        async def fetching():
            client._receive(SimpleNamespace(payload={"text": "Hello", "pubkey_prefix": "abcdabcdabcd"}))
        self.radio.start_auto_message_fetching.side_effect = fetching
        await client._ensure_connected()
        item = client.history.snapshot()["messages"][0]
        self.assertEqual(item["target"], "dm:OptimusPrime")
        self.assertEqual(item["sender"], "OptimusPrime")
        await client.close()

    async def test_channel_uses_actual_name_and_sender(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        client.history = module.MessageHistory()
        await client._ensure_connected()
        client._receive(SimpleNamespace(payload={"text": "OptimusPrime: Hi", "channel_idx": 1}))
        item = client.history.snapshot()["messages"][0]
        self.assertEqual(item["name"], "Actual channel")
        self.assertEqual(item["sender"], "OptimusPrime")
        self.assertEqual(item["target"], "chan:1")
        await client.close()

    async def test_broadcast_is_not_saved_as_delivered(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        client.history = module.MessageHistory()
        await client._ensure_connected()
        self.radio.commands.send_chan_msg = AsyncMock(return_value=SimpleNamespace(type="sent"))
        await client.send_one("chan:1", "Test")
        self.assertEqual(client.history.snapshot()["messages"][0]["status"], "broadcast")
        await client.close()

    async def test_missing_direct_ack_is_unconfirmed(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        client.history = module.MessageHistory()
        await client._ensure_connected()
        self.radio.commands.send_msg_with_retry = AsyncMock(return_value=None)
        await client.send_one("dm:OptimusPrime", "Test")
        self.assertEqual(client.history.snapshot()["messages"][0]["status"], "unconfirmed")
        await client.close()

    async def test_remote_receives_only_unique_direct_identity_and_fresh_history(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        client.history = module.MessageHistory()
        client.remote = SimpleNamespace(submit=Mock(), close=AsyncMock(), snapshot=Mock(return_value={}))
        client.remote_store = SimpleNamespace(async_save=AsyncMock())
        key = "abcd" * 16
        contact = {"adv_name": "OptimusPrime", "public_key": key}
        self.radio.contacts = {key: contact}
        self.radio.get_contact_by_key_prefix.return_value = contact
        await client._ensure_connected()
        message = {"text": "Status", "pubkey_prefix": key[:12], "sender_timestamp": 100}
        client._receive(SimpleNamespace(payload=message))
        self.assertEqual(client.remote.submit.call_args.args[:4], (key, "OptimusPrime", "Status", 100))
        client._receive(SimpleNamespace(payload=message))
        self.assertEqual(client.remote.submit.call_count, 1)
        client._receive(SimpleNamespace(payload={**message, "channel_idx": 1, "sender_timestamp": 101}))
        self.assertEqual(client.remote.submit.call_count, 1)
        self.radio.contacts["other"] = {"adv_name": "Spoof", "public_key": key[:12] + "0" * 52}
        client._receive(SimpleNamespace(payload={**message, "sender_timestamp": 102}))
        self.assertEqual(client.remote.submit.call_count, 1)
        await client.close()
