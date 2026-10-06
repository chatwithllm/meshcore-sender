"""Test native transport lifecycle with SDK and HA dependencies replaced."""

import ast
import asyncio
import importlib.util
from pathlib import Path
import time
import math
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
            commands=SimpleNamespace(get_contacts=AsyncMock(return_value=SimpleNamespace(type="contacts")),
                                     get_bat=AsyncMock(return_value=SimpleNamespace(type="battery", payload={"level": 3987})),
                                     get_channel=AsyncMock(return_value=SimpleNamespace(
                type="channel", payload={"channel_name": "Actual channel"}))),
            subscribe=Mock(), start_auto_message_fetching=AsyncMock(),
            disconnect=AsyncMock(), contacts={}, is_connected=True,
        )
        self.tcp = Mock()
        self.ble = Mock()
        self.sdk = Mock(return_value=self.radio)
        namespace = {"asyncio": asyncio, "time": time, "math": math,
                     "NativeRangeTest": range_module.NativeRangeTest,
                     "MeshCoreError": RuntimeError,
                     "TCPConnection": self.tcp, "ProxyBLEConnection": self.ble,
                     "MeshCore": self.sdk,
                     "EventType": SimpleNamespace(ERROR="error", CONTACT_MSG_RECV="dm",
                                                  CHANNEL_MSG_RECV="channel", BATTERY="battery")}
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
        self.radio.commands.get_contacts.assert_awaited_once_with(timeout=30)
        self.ble.assert_not_called()
        self.assertEqual(result["nodes"][0]["name"], "Actual channel")
        await client.close()
        self.radio.disconnect.assert_awaited_once()

    async def test_remote_stop_excludes_controller_duplicate_and_keeps_summary_out_of_counts(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        client.send_one = AsyncMock(return_value={"ok": True, "acked": False})
        client.range.state.update(running=True, targets=["dm:OptimusPrime", "chan:1"],
            started_by="Remote: OptimusPrime", started_via="LoRa", sent=4, acked=2)
        result = await client.request("POST", "/api/range/stop", {
            "stopped_by": "OptimusPrime", "stopped_via": "LoRa", "summary_exclude": "dm:OptimusPrime"})
        self.assertTrue(result["was_running"])
        self.assertIn("Stop: OptimusPrime (LoRa)", "\n".join(result["summary_messages"]))
        self.assertTrue(all(call.args[0] == "chan:1" for call in client.send_one.call_args_list))
        self.assertEqual(client.range.state["sent"], 4)
        self.assertEqual(client.range.state["acked"], 2)
        count = client.send_one.await_count
        await client.request("POST", "/api/range/stop")
        self.assertEqual(client.send_one.await_count, count)

    async def test_ha_summary_attempts_all_targets_even_if_one_is_unavailable(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        async def send(target, text, timeout):
            if target == "dm:Missing": raise ConnectionError()
            return {"ok": True, "acked": True}
        client.send_one = AsyncMock(side_effect=send)
        deliveries = await client._send_range_summary({"targets": ["dm:Missing", "dm:OptimusPrime"],
            "summary_messages": ["Range test stopped."]}, None)
        self.assertFalse(deliveries[0]["ok"])
        self.assertTrue(deliveries[1]["acked"])

    async def test_direct_mode_still_uses_ble(self):
        client = self.Client(self.hass, "AA:BB:CC:DD:EE:FF")
        await client._ensure_connected()
        self.ble.assert_called_once_with(self.hass, "AA:BB:CC:DD:EE:FF")
        self.tcp.assert_not_called()
        await client.close()

    async def test_battery_is_local_millivolts_and_cached(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        first = await client.request("GET", "/api/health")
        second = await client.request("GET", "/api/health")
        self.assertEqual(first["battery"]["voltage"], 3.987)
        self.assertTrue(first["battery"]["available"])
        self.assertEqual(first["battery"], second["battery"])
        self.radio.commands.get_bat.assert_awaited_once()
        self.assertEqual(client.range.state["sent"], 0)

    async def test_battery_failure_does_not_hide_other_health(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        await client.request("GET", "/api/health")
        client._battery_checked_at = time.monotonic() - 61
        self.radio.commands.get_bat.side_effect = TimeoutError()
        health = await client.request("GET", "/api/health")
        self.assertTrue(health["radio_ok"])
        self.assertFalse(health["battery"]["available"])
        self.assertEqual(health["battery"]["voltage"], 3.987)
        await client.request("GET", "/api/health")
        self.assertEqual(self.radio.commands.get_bat.await_count, 2)

    async def test_invalid_voltage_and_wrong_events_are_unavailable(self):
        for level in (0, -1, float('nan'), float('inf'), 65536, True, "3987", None):
            client = self.Client(self.hass, "bridge", host="bridge")
            self.radio.commands.get_bat.return_value = SimpleNamespace(type="battery", payload={"level": level})
            result = await client.request("GET", "/api/health")
            self.assertFalse(result["battery"]["available"])
        self.radio.commands.get_bat.return_value = SimpleNamespace(type="error", payload={"level": 3987})
        client = self.Client(self.hass, "bridge", host="bridge")
        self.assertFalse((await client.request("GET", "/api/health"))["battery"]["available"])

    async def test_cached_battery_expires_and_cancellation_is_not_swallowed(self):
        client = self.Client(self.hass, "bridge", host="bridge")
        await client.request("GET", "/api/health")
        client.battery["sampled_at"] = time.time() - 181
        self.assertFalse((await client._battery_status())["available"])
        client._battery_checked_at = None
        self.radio.commands.get_bat.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await client.request("GET", "/api/health")

    async def test_failed_bridge_handshake_cleans_up(self):
        self.radio.connect.side_effect = ConnectionError("Connection refused")
        client = self.Client(self.hass, "bridge.local:5000", host="bridge.local")
        with self.assertRaisesRegex(RuntimeError, "Connection refused"):
            await client.request("GET", "/api/nodes")
        self.radio.disconnect.assert_awaited_once()
        self.assertIsNone(client.mc)

    async def test_failed_contact_fetch_does_not_create_empty_success(self):
        self.radio.commands.get_contacts.return_value = SimpleNamespace(type="error")
        client = self.Client(self.hass, "bridge.local:5000", host="bridge.local")
        with self.assertRaisesRegex(RuntimeError, "contact retrieval failed"):
            await client.request("GET", "/api/nodes")
        self.radio.disconnect.assert_awaited_once()
        self.assertIsNone(client.mc)

    async def test_coordinates_keep_sdk_degrees_and_reject_invalid_gps(self):
        self.radio.contacts={'a':{'adv_name':'GPS repeater','type':2,'adv_lat':39.7,'adv_lon':-85.99},
                             'b':{'adv_name':'No GPS','type':2,'adv_lat':0,'adv_lon':0},
                             'c':{'adv_name':'Bad GPS','type':2,'adv_lat':float('nan'),'adv_lon':190}}
        client=self.Client(self.hass,'bridge',host='bridge')
        nodes=(await client.request('GET','/api/nodes'))['nodes']
        gps=next(n for n in nodes if n['name']=='GPS repeater')
        self.assertEqual(gps['lat'],39.7)
        self.assertEqual(gps['lon'],-85.99)
        self.assertTrue(all('lat' not in n for n in nodes if n['name'] in ('No GPS','Bad GPS')))
        await client.close()
