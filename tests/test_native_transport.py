"""Test native transport lifecycle with SDK and HA dependencies replaced."""

import ast
import asyncio
import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"
spec = importlib.util.spec_from_file_location("transport_range", ROOT / "range_test.py")
range_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(range_module)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = SimpleNamespace(
            connect=AsyncMock(return_value=SimpleNamespace(type="connected")),
            ensure_contacts=AsyncMock(),
            commands=SimpleNamespace(get_channel=AsyncMock(return_value=SimpleNamespace(
                type="channel", payload={"channel_name": "Actual channel"}))),
            subscribe=Mock(), start_auto_message_fetching=AsyncMock(),
            disconnect=AsyncMock(), contacts={}, is_connected=True,
        )
        self.tcp = Mock()
        self.ble = Mock()
        self.sdk = Mock(return_value=self.radio)
        namespace = {"asyncio": asyncio, "time": time,
                     "NativeRangeTest": range_module.NativeRangeTest,
                     "MeshCoreError": RuntimeError,
                     "TCPConnection": self.tcp, "ProxyBLEConnection": self.ble,
                     "MeshCore": self.sdk,
                     "EventType": SimpleNamespace(ERROR="error", CONTACT_MSG_RECV="dm",
                                                  CHANNEL_MSG_RECV="channel")}
        # Load the production client class without importing Home Assistant.
        source = ast.parse((ROOT / "bluetooth_client.py").read_text())
        node = next(n for n in source.body if isinstance(n, ast.ClassDef)
                    and n.name == "NativeMeshCoreClient")
        exec(compile(ast.Module(body=[node], type_ignores=[]), "native_client", "exec"), namespace)
        self.Client = namespace["NativeMeshCoreClient"]
        self.hass = SimpleNamespace(async_create_background_task=Mock())

    async def test_bridge_uses_tcp_and_loads_actual_channel_names(self):
        client = self.Client(self.hass, "bridge.local:5000", host="bridge.local", port=5000)
        result = await client.request("GET", "/api/nodes")
        self.tcp.assert_called_once_with("bridge.local", 5000)
        self.ble.assert_not_called()
        self.assertEqual(result["nodes"][0]["name"], "Actual channel")
        await client.close()
        self.radio.disconnect.assert_awaited_once()

    async def test_direct_mode_still_uses_ble(self):
        client = self.Client(self.hass, "AA:BB:CC:DD:EE:FF")
        await client._ensure_connected()
        self.ble.assert_called_once_with(self.hass, "AA:BB:CC:DD:EE:FF")
        self.tcp.assert_not_called()
        await client.close()

    async def test_failed_bridge_handshake_cleans_up(self):
        self.radio.connect.side_effect = ConnectionError("Connection refused")
        client = self.Client(self.hass, "bridge.local:5000", host="bridge.local")
        with self.assertRaisesRegex(RuntimeError, "Connection refused"):
            await client.request("GET", "/api/nodes")
        self.radio.disconnect.assert_awaited_once()
        self.assertIsNone(client.mc)
