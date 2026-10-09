"""Exercise the production protocol manager with the pinned SDK and a fake radio."""

import ast
import asyncio
import importlib.util
import logging
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from meshcore import EventType
from meshcore.events import Event
from meshcore.packets import BinaryReqType
import voluptuous as vol
import yaml

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"
spec = importlib.util.spec_from_file_location("repeater_admin", ROOT / "repeater_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
KEY = "ab208ae4456d" + "a" * 52
CONTACT = {"public_key": KEY, "adv_name": "BlairOneW", "type": 2,
           "out_path_len": 2, "out_path": "1234", "out_path_hash_mode": 0}


def status_bytes():
    wire = bytearray(56)
    for offset, width, value, signed in ((0, 2, 4050, False), (2, 2, 3, False),
            (6, 2, -92, True), (20, 4, 86400, False), (42, 2, 26, True)):
        wire[offset:offset+width] = value.to_bytes(width, "little", signed=signed)
    return wire.hex()


class FakeRadio:
    def __init__(self):
        self.contacts = {KEY: CONTACT.copy()}
        self.is_connected = True
        self.listeners = []
        self.sent_count = 0
        self.response = Event(EventType.BINARY_RESPONSE, {"tag": "01020304", "data": status_bytes()})
        self.login_response = Event(EventType.LOGIN_SUCCESS, {"pubkey_prefix": KEY[:12], "is_admin": True})
        self.cli_response = Event(EventType.CONTACT_MSG_RECV, {
            "pubkey_prefix": KEY[:12], "txt_type": 1, "sender_timestamp": 100, "text": "22"})
        self.sent_event = Event(EventType.MSG_SENT, {"expected_ack": bytes.fromhex("01020304")})
        self.commands = SimpleNamespace(send_binary_req=AsyncMock(side_effect=self.binary),
            req_neighbours_async=AsyncMock(side_effect=self.binary),
            send_cmd=AsyncMock(side_effect=self.command), send_login=AsyncMock(side_effect=self.login),
            send_logout=AsyncMock(return_value=Event(EventType.OK, {})),
            send_trace=AsyncMock(side_effect=self.trace))

    def subscribe(self, kind, callback):
        subscription = (kind, callback)
        self.listeners.append(subscription)
        return subscription

    def unsubscribe(self, subscription):
        self.listeners.remove(subscription)

    def emit(self, event):
        if event:
            for kind, callback in tuple(self.listeners):
                if kind == event.type:
                    callback(event)

    async def binary(self, *args, **kwargs):
        self.sent_count += 1
        self.emit(self.response)  # Reply can arrive before send returns.
        return self.sent_event

    async def login(self, *args, **kwargs):
        self.sent_count += 1
        self.emit(self.login_response)
        return self.sent_event

    async def command(self, *args, **kwargs):
        self.sent_count += 1
        self.emit(self.cli_response)
        return self.sent_event

    async def trace(self, *args, **kwargs):
        self.sent_count += 1
        self.emit(Event(EventType.TRACE_DATA, {"tag": kwargs["tag"], "auth": kwargs["auth_code"], "path": []}))
        return self.sent_event


class SafetyTests(unittest.TestCase):
    def test_readonly_allowlist(self):
        for command in ("ver", "board", "clock", "get tx", "get radio", "neighbors", "stats-core", "stats-radio", "stats-packets"):
            self.assertEqual(admin.safe_command(command), command)

    def test_every_mutation_requires_explicit_permission_even_admin_mode(self):
        for command in ("set tx 30", "reboot", "poweroff", "shutdown", "erase", "password x",
                "neighbor.remove ab", "clear stats", "start ota", "time 123", "clkreboot",
                "advert", "advert.zerohop", "discover.neighbors", "clock sync"):
            for mode in ("read_only", "admin"):
                with self.assertRaises(admin.AdminError) as error:
                    admin.safe_command(command, mode)
                self.assertEqual(error.exception.reason, "mutation_blocked")
            self.assertEqual(admin.safe_command(command, allow_mutation=True), command)

    def test_injection_and_unknown_commands_fail_closed(self):
        for command in ("get tx\nreboot", "get tx; reboot", "get tx\x00set tx 30", "get tx|reboot", "get tx&reboot", "get tx\\reboot", "reset", "clock clear", "", "a" * 151):
            with self.assertRaises(admin.AdminError):
                admin.safe_command(command, allow_mutation=True)

    def test_binary_status_units_and_unknown_percent(self):
        fields = admin.parse_binary("remote_status", status_bytes())
        self.assertEqual(fields["battery_voltage"], 4.05)
        self.assertEqual(fields["battery_mv"], 4050)
        self.assertEqual(fields["uptime"], 86400)
        self.assertEqual(fields["last_rssi"], -92)
        self.assertEqual(fields["last_snr"], 6.5)
        self.assertNotIn("battery_percent", fields)
        for raw in ("ab", "xyz", None):
            with self.assertRaises(ValueError):
                admin.parse_binary("remote_status", raw)

    def test_neighbor_parse_and_paging(self):
        raw = (b"\x14\x00\x01\x00" + bytes.fromhex("11223344") + (25).to_bytes(4, "little") + b"\xfc").hex()
        result = admin.parse_binary("remote_neighbors", raw)
        self.assertEqual(result["neighbor_count"], 20)
        self.assertEqual(result["neighbors"][0]["snr"], -1)
        self.assertTrue(result["truncated"])
        with self.assertRaises(ValueError):
            admin.parse_binary("remote_neighbors", raw[:-2])

    def test_telemetry_voltage_and_temperature(self):
        result = admin.parse_binary("remote_telemetry", "017401a4026700dc")
        self.assertEqual(result["battery_voltage"], 4.2)
        self.assertEqual(result["telemetry"][1]["type"], "temperature")

    def test_cli_parsing(self):
        for text in ("22", "> 22", "TX: 22 dBm"):
            self.assertEqual(admin.parse_cli("get tx", text)["tx_power"], 22)
        self.assertEqual(admin.parse_cli("board", "RAK3401")["board"], "RAK3401")
        self.assertEqual(admin.parse_cli("ver", "v1.12")["firmware"], "v1.12")
        with self.assertRaises(ValueError):
            admin.parse_cli("get tx", "unrelated reply")
        with self.assertRaises(admin.AdminError):
            admin.parse_cli("stats-core", "unknown command")

    def test_sensitive_sdk_logs_redacted(self):
        logger = logging.getLogger("meshcore")
        with self.assertLogs("meshcore", level="DEBUG") as logs:
            with admin.sensitive_logs():
                logger.debug("password %s", "secret-value")
        self.assertNotIn("secret-value", " ".join(logs.output))

    def test_action_schema_and_yaml_fields(self):
        tree = ast.parse((ROOT / "admin_services.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "schemas")
        namespace = {"vol": vol, "cv": SimpleNamespace(string=str, boolean=vol.Boolean()), "SERVICES": admin.SERVICES}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "schemas", "exec"), namespace)
        schemas = namespace["schemas"]()
        descriptions = yaml.safe_load((ROOT / "services.yaml").read_text())
        for name, schema in schemas.items():
            data = {"target": KEY[:12]}
            if name == "remote_command":
                data["command"] = "get tx"
            parsed = schema(data)
            self.assertEqual(parsed["timeout"], 20)
            self.assertIn(name, descriptions)
            self.assertEqual({str(key) for key in schema.schema}, set(descriptions[name]["fields"]))
        self.assertEqual(schemas["remote_command"]({"target": KEY, "command": "get tx"})["mode"], "read_only")
        for values in ({"count": 17}, {"offset": -1}, {"timeout": 61}, {"unknown": True}):
            with self.assertRaises(vol.Invalid):
                schemas["remote_neighbors"]({"target": KEY, **values})


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mc = FakeRadio()
        self.running = False
        client = SimpleNamespace(mc=self.mc, lock=asyncio.Lock(),
            range=SimpleNamespace(snapshot=lambda: {"running": self.running}))
        self.coordinator = SimpleNamespace(client=client, async_update_listeners=Mock())
        self.store = SimpleNamespace(async_save=AsyncMock(), async_load=AsyncMock(return_value=None))
        self.manager = admin.RepeaterAdmin(self.coordinator, self.store)

    async def request(self, action="remote_status", **kwargs):
        self.manager.last_sent = 0
        return await self.manager.request(action, {"target": KEY[:12], "timeout": .02, **kwargs})

    async def test_status_fast_response_creates_tracking_and_counts(self):
        callback = Mock()
        self.manager.listen(callback)
        result = await self.request()
        self.assertTrue(result["request_success"], result)
        self.assertTrue(result["online"])
        self.assertEqual(result["target_name"], "BlairOneW")
        self.assertEqual(result["request_successes"], 1)
        self.assertIsNone(result["battery_percent"])
        callback.assert_called_once_with(KEY)
        self.assertEqual(self.mc.listeners, [])
        self.mc.commands.send_binary_req.assert_awaited_once_with(CONTACT, BinaryReqType.STATUS, timeout=.02)

    async def test_no_response_is_not_online_and_cleans_subscriptions(self):
        self.mc.response = None
        result = await self.request()
        self.assertEqual(result["error"], "no_response")
        self.assertFalse(result["online"])
        self.assertEqual(result["request_failures"], 1)
        self.assertEqual(self.mc.listeners, [])

    async def test_wrong_binary_tag_is_ignored(self):
        self.mc.response.payload["tag"] = "wrong"
        self.assertEqual((await self.request())["error"], "no_response")

    async def test_missing_and_ambiguous_contact(self):
        self.mc.contacts = {}
        self.assertEqual((await self.request())["error"], "contact_not_found")
        self.mc.contacts = {KEY: CONTACT, "other": {**CONTACT, "public_key": KEY[:-1] + "b"}}
        self.assertEqual((await self.request())["error"], "ambiguous_target")
        self.assertEqual(self.mc.sent_count, 0)

    async def test_not_connected(self):
        self.mc.is_connected = False
        self.assertEqual((await self.request())["error"], "not_connected")

    async def test_running_test_defers_without_airtime_or_failure_count(self):
        self.running = True
        result = await self.request()
        self.assertEqual(result["error"], "traffic_deferred")
        self.assertEqual(result["request_failures"], 0)
        self.assertIsNone(result["online"])
        self.assertEqual(self.mc.sent_count, 0)

    async def test_busy_lock_defers(self):
        async with self.coordinator.client.lock:
            self.assertEqual((await self.request())["error"], "traffic_deferred")

    async def test_mutation_blocked_before_any_airtime(self):
        result = await self.request("remote_command", command="reboot")
        self.assertEqual(result["error"], "mutation_blocked")
        self.assertEqual(self.mc.sent_count, 0)

    async def test_cli_identity_type_and_duplicate_filters(self):
        result = await self.request("remote_command", command="get tx")
        self.assertEqual(result["tx_power"], 22)
        result = await self.request("remote_command", command="get tx")
        self.assertEqual(result["error"], "no_response")
        self.assertEqual((await self.request("remote_command", command="get tx"))["error"], "traffic_deferred")

    async def test_cli_wrong_sender_or_chat_is_not_reply(self):
        self.mc.cli_response.payload["txt_type"] = 0
        self.assertEqual((await self.request("remote_command", command="get tx"))["error"], "no_response")
        self.manager.cli_deferred_until.clear()
        self.mc.cli_response.payload.update(txt_type=1, pubkey_prefix="ff"*6)
        self.assertEqual((await self.request("remote_command", command="get tx"))["error"], "no_response")

    async def test_cli_parse_error_preserves_raw(self):
        self.mc.cli_response.payload["text"] = "bad tx value"
        result = await self.request("remote_command", command="get tx")
        self.assertEqual(result["error"], "parse_error")
        self.assertEqual(result["raw_response"]["text"], "bad tx value")

    async def test_malformed_binary_preserves_raw(self):
        self.mc.response.payload["data"] = "ff"
        result = await self.request()
        self.assertEqual(result["error"], "parse_error")
        self.assertEqual(result["raw_response"]["data"], "ff")

    async def test_login_save_restore_without_assuming_online(self):
        result = await self.request("remote_login", password="safe-test", save_password=True)
        self.assertTrue(result["request_success"])
        self.assertNotIn("safe-test", str(result))
        saved = self.store.async_save.call_args.args[0]
        self.store.async_load.return_value = saved
        restored = admin.RepeaterAdmin(self.coordinator, self.store)
        await restored.load()
        self.assertEqual(restored.passwords[KEY], "safe-test")
        self.assertIsNone(restored.records[KEY]["online"])
        self.assertIsNone(restored.records[KEY]["battery_voltage"])

    async def test_saved_password_login_after_restart(self):
        self.manager.passwords[KEY] = "safe-test"
        self.assertTrue((await self.request())["request_success"])
        self.assertEqual(self.mc.sent_count, 2)
        self.assertTrue((await self.request())["request_success"])
        self.assertEqual(self.mc.sent_count, 3)

    async def test_login_failure_and_wrong_identity(self):
        self.mc.login_response = Event(EventType.LOGIN_FAILED, {"pubkey_prefix": KEY[:12]})
        self.assertEqual((await self.request("remote_login", password="x"))["error"], "auth_failed")
        self.mc.login_response.payload["pubkey_prefix"] = "ff"*6
        self.assertEqual((await self.request("remote_login", password="x"))["error"], "no_response")
        self.assertEqual(self.mc.listeners, [])

    async def test_login_without_credential_no_guess(self):
        self.assertEqual((await self.request("remote_login"))["error"], "auth_failed")
        self.assertEqual(self.mc.sent_count, 0)

    async def test_logout_companion_ack_not_remote_online(self):
        self.manager.passwords[KEY] = "x"
        result = await self.request("remote_logout", forget_password=True)
        self.assertTrue(result["request_success"])
        self.assertIsNone(result["online"])
        self.assertEqual(result["ack_scope"], "companion")
        self.assertNotIn(KEY, self.manager.passwords)

    async def test_password_mutation_reply_redacted(self):
        self.mc.cli_response.payload["text"] = "password x"
        result = await self.request("remote_command", command="password x", allow_mutation=True)
        self.assertEqual(result["reply"], "[redacted]")
        self.assertEqual(result["raw_response"]["text"], "[redacted]")

    async def test_trace_roundtrip_path_and_no_discovery(self):
        result = await self.request("trace")
        self.assertTrue(result["request_success"], result)
        self.assertEqual(result["trace_path"], "1234ab3412")
        self.mc.contacts[KEY]["out_path_len"] = -1
        self.assertEqual((await self.request("trace"))["error"], "unsupported")

    async def test_local_rejection_not_reported_as_online(self):
        self.mc.sent_event = Event(EventType.ERROR, {"code": 6})
        result = await self.request()
        self.assertEqual(result["error"], "unsupported")
        self.assertIsNone(result["online"])
        self.assertEqual(self.mc.listeners, [])

    async def test_cancel_releases_lock_subscription_and_lane(self):
        self.mc.response = None
        task = asyncio.create_task(self.request(timeout=60))
        await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.manager.active)
        self.assertFalse(self.coordinator.client.lock.locked())
        self.assertEqual(self.mc.listeners, [])

    async def test_credentials_never_in_public_record(self):
        await self.request("remote_login", password="test-secret", save_password=True)
        self.assertNotIn("test-secret", str(self.manager.records))

    async def test_guest_login_cannot_execute_cli(self):
        self.mc.login_response.payload["is_admin"] = False
        await self.request("remote_login", password="guest")
        self.assertEqual((await self.request("remote_command", command="get tx"))["error"], "auth_failed")
        self.mc.commands.send_cmd.assert_not_awaited()


class EntityTests(unittest.TestCase):
    def setUp(self):
        class CoordinatorEntity:
            def __init__(self, coordinator):
                self.coordinator = coordinator
        class SensorEntity:
            pass
        class BinarySensorEntity:
            pass
        class ButtonEntity:
            pass
        tree = ast.parse((ROOT / "repeater_entity.py").read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        self.classes = {"CoordinatorEntity": CoordinatorEntity, "SensorEntity": SensorEntity,
            "BinarySensorEntity": BinarySensorEntity, "ButtonEntity": ButtonEntity, "DeviceInfo": dict,
            "slugify": lambda s: s.lower(), "DOMAIN": "meshcore_sender", "time": time,
            "MAX_AGE": admin.MAX_AGE, "SensorStateClass": SimpleNamespace(MEASUREMENT="measurement"),
            "BinarySensorDeviceClass": SimpleNamespace(CONNECTIVITY="connectivity")}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "entities", "exec"), self.classes)
        self.record = admin.RepeaterAdmin._record(KEY, "BlairOneW")
        self.coordinator = SimpleNamespace(entry=SimpleNamespace(entry_id="entry"),
            repeater_admin=SimpleNamespace(records={KEY: self.record}))

    def test_unknown_then_live_then_stale_online(self):
        entity = self.classes["RepeaterOnline"](self.coordinator, KEY, "online", "Online")
        self.assertIsNone(entity.is_on)
        self.record.update(online=True, last_attempt_at=time.time())
        self.assertTrue(entity.is_on)
        self.record["last_attempt_at"] -= 7201
        self.assertIsNone(entity.is_on)
        self.assertEqual(entity._attr_suggested_object_id, "meshcore_blaironew_online")

    def test_sensor_expiry_and_persistent_counts(self):
        sensor = self.classes["RepeaterSensor"](self.coordinator, KEY, "battery_voltage", "Battery", "V", "voltage")
        self.assertIsNone(sensor.native_value)
        self.record["battery_voltage"] = 4.05
        self.record["field_updated_at"]["battery_voltage"] = time.time()
        self.assertEqual(sensor.native_value, 4.05)
        self.assertEqual(sensor._attr_state_class, "measurement")
        self.record["field_updated_at"]["battery_voltage"] -= 7201
        self.assertIsNone(sensor.native_value)
        counter = self.classes["RepeaterSensor"](self.coordinator, KEY, "request_successes", "Successes", None, None)
        self.assertEqual(counter.native_value, 0)


class ActionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tree = ast.parse((ROOT / "admin_services.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_register_admin_services")
        registry = {}
        def register(name, service, handler, **kwargs):
            registry[service] = (handler, kwargs)
        self.manager = SimpleNamespace(request=AsyncMock(return_value={"request_success": True}))
        self.hass = SimpleNamespace(
            data={"meshcore_sender": {"entry": SimpleNamespace(client=SimpleNamespace(url=None), repeater_admin=self.manager)}},
            auth=SimpleNamespace(async_get_user=AsyncMock(return_value=SimpleNamespace(is_admin=False))),
            services=SimpleNamespace(has_service=lambda *args: False, async_register=register))
        namespace = {"DOMAIN": "meshcore_sender", "schemas": lambda: {name: "schema" for name in admin.SERVICES},
                     "SupportsResponse": SimpleNamespace(OPTIONAL="optional")}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "registration", "exec"), namespace)
        await namespace["async_register_admin_services"](self.hass)
        self.registry = registry

    async def call(self, user_id="user", **data):
        return await self.registry["remote_status"][0](SimpleNamespace(
            context=SimpleNamespace(user_id=user_id), service="remote_status", data={"target": KEY, **data}))

    async def test_all_actions_support_responses(self):
        self.assertEqual(set(self.registry), set(admin.SERVICES))
        for _, kwargs in self.registry.values():
            self.assertEqual(kwargs["supports_response"], "optional")

    async def test_nonadmin_cannot_issue_any_radio_request(self):
        self.assertEqual((await self.call())["error"], "forbidden")
        self.manager.request.assert_not_awaited()

    async def test_admin_and_trusted_local_automation(self):
        self.hass.auth.async_get_user.return_value.is_admin = True
        self.assertTrue((await self.call())["request_success"])
        self.assertTrue((await self.call(user_id=None))["request_success"])

    async def test_missing_entry_and_server_mode(self):
        self.assertEqual((await self.call(user_id=None, entry_id="wrong"))["error"], "not_connected")
        self.hass.data["meshcore_sender"]["entry"].client.url = "http://server"
        self.assertEqual((await self.call(user_id=None))["error"], "unsupported")
        self.manager.request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
