"""Bounded remote inspection through the existing companion, never a second owner."""

import asyncio
from contextlib import contextmanager
import logging
import math
import re
import secrets
import time

from meshcore import EventType
from meshcore.packets import BinaryReqType
from meshcore.parsing import lpp_parse, parse_status


SERVICES = ("remote_status", "remote_telemetry", "remote_neighbors", "remote_command",
            "remote_login", "remote_logout", "trace")
FIELDS = ("firmware", "board", "role", "battery_voltage", "battery_mv", "battery_percent",
          "power_source", "charging_state", "uptime", "queue_length", "tx_power", "radio",
          "out_path_len", "out_path", "last_rssi", "last_snr", "neighbor_count", "neighbors")
MAX_AGE = 7200


class AdminError(Exception):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def safe_command(command, mode="read_only", allow_mutation=False):
    """Fail closed, including command chaining and read-command variants that write."""
    if not isinstance(command, str) or not command.strip() or len(command.encode()) > 150:
        raise AdminError("invalid_command", "Use one command of at most 150 UTF-8 bytes")
    if any(ord(c) < 32 or ord(c) == 127 for c in command) or any(c in command for c in ";|&`\\"):
        raise AdminError("invalid_command", "Command separators and control characters are not allowed")
    command = " ".join(command.strip().split())
    lower = command.lower()
    if mode not in ("read_only", "admin"):
        raise AdminError("invalid_mode", "Mode must be read_only or admin")
    readonly = (lower in ("ver", "board", "clock", "neighbors", "stats-core", "stats-radio", "stats-packets")
                or lower.startswith("get "))
    mutation = (lower.split()[0] in ("set", "reboot", "poweroff", "shutdown", "erase", "password",
                "neighbor.remove", "time", "clkreboot", "advert", "advert.zerohop", "discover.neighbors")
                or lower in ("clear stats", "start ota", "clock sync"))
    if not readonly and not mutation:
        raise AdminError("unsupported", "Command is not in the supported inspection or mutation lists")
    if mutation and not allow_mutation:
        raise AdminError("mutation_blocked", "This command is mutating and requires allow_mutation: true")
    return command


class _QuietSDK(logging.Filter):
    def filter(self, record):
        # SDK DEBUG output contains raw frames, including login credentials.
        record.msg, record.args = "MeshCore sensitive administration frame redacted", ()
        record.exc_info, record.exc_text = None, None
        return True


class _PacketLogRedaction(_QuietSDK):
    """Keep late CLI replies and raw credential frames out of SDK DEBUG logs too."""
    meshcore_payload_redactor = True

    def filter(self, record):
        if any(marker in record.getMessage() for marker in (
                "Received data:", "Sending raw data:", "sending pkt", "Dispatching event:",
                "Sending command to", "Command error:")):
            return super().filter(record)
        return True


@contextmanager
def sensitive_logs():
    logger = logging.getLogger("meshcore")
    guard = _QuietSDK()
    logger.addFilter(guard)
    try:
        yield
    finally:
        logger.removeFilter(guard)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def parse_binary(action, raw, count=8, offset=0):
    """Validate wire lengths before using SDK decoders (which accept short slices)."""
    if not isinstance(raw, str):
        raise ValueError("Missing binary payload")
    data = bytes.fromhex(raw)
    if action == "remote_status":
        if len(data) < 52:
            raise ValueError("Short status payload")
        status = parse_status(data, pubkey_prefix="")
        mv = number(status.get("bat"))
        return {"battery_mv": mv if mv and mv > 0 else None,
                "battery_voltage": mv / 1000 if mv and mv > 0 else None,
                "uptime": status["uptime"], "queue_length": status["tx_queue_len"],
                "last_rssi": status["last_rssi"], "last_snr": status["last_snr"],
                "status": status}
    if action == "remote_telemetry":
        telemetry = lpp_parse(data)
        fields = {"telemetry": telemetry}
        for item in telemetry:
            value = number(item.get("value"))
            if item.get("channel") == 1 and item.get("type") == "voltage" and value is not None and value > 0:
                fields.update(battery_voltage=value, battery_mv=round(value * 1000))
        return fields
    if len(data) < 4:
        raise ValueError("Short neighbor payload")
    total, returned = int.from_bytes(data[:2], "little"), int.from_bytes(data[2:4], "little")
    if returned > count or returned > total or len(data) != 4 + returned * 9:
        raise ValueError("Invalid neighbor count or payload length")
    neighbors = [{"public_key_prefix": data[i:i+4].hex(),
                  "seconds_ago": int.from_bytes(data[i+4:i+8], "little"),
                  "snr": int.from_bytes(data[i+8:i+9], "little", signed=True) / 4}
                 for i in range(4, len(data), 9)]
    return {"neighbor_count": total, "neighbors": neighbors, "offset": offset,
            "returned_count": returned, "truncated": offset + returned < total}


def parse_cli(command, text):
    lower = command.lower()
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty CLI reply")
    if re.search(r"\b(unknown command|unsupported|not supported|invalid command)\b", stripped, re.I):
        raise AdminError("unsupported", "Repeater does not support this command")
    if re.search(r"\b(unauthorized|permission denied|not authorized|login required)\b", stripped, re.I):
        raise AdminError("auth_failed", "Repeater denied this command")
    fields = {"reply": stripped}
    if lower in ("ver", "board"):
        fields["firmware" if lower == "ver" else "board"] = stripped
    elif lower == "get tx":
        match = re.fullmatch(r"(?:[><=:\s]*(?:tx(?: power)?[:=\s]*)?)?(-?\d+(?:\.\d+)?)\s*(?:dBm)?", stripped, re.I)
        if not match:
            raise ValueError("Unrecognized tx power response")
        fields["tx_power"] = float(match.group(1))
    elif lower == "get radio":
        fields["radio"] = stripped
    return fields


class RepeaterAdmin:
    """Persist identity/credentials; cache observations separately with source timestamps."""

    def __init__(self, coordinator, store):
        self.coordinator, self.client, self.store = coordinator, coordinator.client, store
        self.records, self.passwords, self.callbacks = {}, {}, []
        self.active = False
        self.last_sent = 0
        self.last_cli = {}
        self.cli_deferred_until = {}
        self.authenticated = {}
        logger = logging.getLogger("meshcore")
        if not any(getattr(guard, "meshcore_payload_redactor", False) for guard in logger.filters):
            logger.addFilter(_PacketLogRedaction())

    async def load(self):
        data = await self.store.async_load() or {}
        self.passwords = data.get("passwords", {})
        for key, value in data.get("tracked", {}).items():
            if re.fullmatch(r"[0-9a-f]{64}", key):
                self.records[key] = self._record(key, value.get("target_name", key[:12]))
                for field in ("request_successes", "request_failures"):
                    self.records[key][field] = value.get(field, 0)

    @staticmethod
    def _record(key, name):
        return {"target_name": name, "public_key": key, "public_key_prefix": key[:12],
                "online": None, "request_success": False, "error": None,
                "request_successes": 0, "request_failures": 0, "last_seen_at": None,
                "last_attempt_at": None, "field_updated_at": {},
                **dict.fromkeys(FIELDS)}

    async def save(self):
        await self.store.async_save({"passwords": self.passwords, "tracked": {
            key: {field: record[field] for field in ("target_name", "request_successes", "request_failures")}
            for key, record in self.records.items()}})

    def listen(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)

    def track(self, contact):
        key = contact["public_key"].lower()
        if key not in self.records:
            self.records[key] = self._record(key, contact.get("adv_name") or key[:12])
            for callback in tuple(self.callbacks):
                callback(key)
        else:
            self.records[key]["target_name"] = contact.get("adv_name") or key[:12]
        return key

    def find(self, target):
        mc = getattr(self.client, "mc", None)
        if mc is None or not mc.is_connected:
            raise AdminError("not_connected", "The Home Assistant companion is not connected")
        target = target.strip().removeprefix("dm:")
        contacts = list(mc.contacts.values())
        hex_target = bool(re.fullmatch(r"[0-9a-fA-F]{12,64}", target))
        matches = [c for c in contacts if (c.get("public_key", "").lower().startswith(target.lower())
                   if hex_target else c.get("adv_name", "").casefold() == target.casefold())]
        if len(matches) != 1:
            reason = "contact_not_found" if not matches else "ambiguous_target"
            raise AdminError(reason, "Choose one known repeater by name or at least 12 key characters")
        contact = matches[0]
        if contact.get("type") != 2:
            raise AdminError("unsupported", "Remote repeater administration requires a repeater contact")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", contact.get("public_key", "")):
            raise AdminError("parse_error", "Contact has an invalid public key")
        return contact

    def busy(self):
        snapshot = self.client.range.snapshot()
        return snapshot.get("running") or snapshot.get("finishing")

    async def request(self, action, data):
        started = time.monotonic()
        result = {"action": action, "target_name": data["target"], "public_key_prefix": None,
                  "request_success": False, "online": None, "error": None,
                  "round_trip_ms": None, "raw_response": None, **dict.fromkeys(FIELDS)}
        key = None
        attempted = False
        try:
            command = safe_command(data.get("command"), data.get("mode", "read_only"),
                                   data.get("allow_mutation", False)) if action == "remote_command" else None
            contact = self.find(data["target"])
            key = self.track(contact)
            result.update(target_name=self.records[key]["target_name"], public_key_prefix=key[:12],
                          public_key=key, role="repeater", out_path_len=contact.get("out_path_len"),
                          out_path=contact.get("out_path"), route_source="companion_contact_cache")
            if action == "remote_command" and time.monotonic() < self.cli_deferred_until.get(key, 0):
                raise AdminError("traffic_deferred", "Previous CLI request timed out; wait two minutes to avoid accepting a late reply")
            if not hasattr(self.client, "lock"):
                raise AdminError("unsupported", "Remote administration requires a native HA radio connection")
            if self.active or self.busy() or self.client.lock.locked():
                raise AdminError("traffic_deferred", "Range traffic or another companion operation is active; retry later")
            if time.monotonic() - self.last_sent < 3:
                raise AdminError("traffic_deferred", "Please allow three seconds between administration transactions")
            self.active = True
            try:
                async with self.client.lock:
                    if self.busy():
                        raise AdminError("traffic_deferred", "A range test started; administration was deferred")
                    mc = self.client.mc
                    if mc is None or not mc.is_connected:
                        raise AdminError("not_connected", "Companion disconnected before the request")
                    password = data.get("password", self.passwords.get(key))
                    if action == "remote_login" and password is None:
                        raise AdminError("auth_failed", "Provide a password or save one using remote_login first")
                    attempted = True
                    self.last_sent = time.monotonic()
                    timeout = data.get("timeout", 20)
                    async with asyncio.timeout(timeout):
                        if action != "remote_logout" and password is not None and (
                                action == "remote_login" or self.authenticated.get(key, (None, False))[0] is not mc):
                            login = await self._login(mc, contact, password)
                            result["raw_response"] = {"login": login}
                            if not login.get("is_admin") and action == "remote_command":
                                raise AdminError("auth_failed", "CLI requires an administrator login, not guest access")
                            self.authenticated[key] = (mc, bool(login.get("is_admin")))
                            if action == "remote_login":
                                if data.get("save_password"):
                                    self.passwords[key] = password
                                result.update(login=login, credential_saved=key in self.passwords)
                        if action == "remote_logout":
                            event = await mc.commands.send_logout(contact)
                            self._sent(event, expected=EventType.OK)
                            self.authenticated.pop(key, None)
                            if data.get("forget_password"):
                                self.passwords.pop(key, None)
                            result.update(raw_response=event.payload, ack_scope="companion", online=None)
                        elif action == "remote_command":
                            if key in self.authenticated and not self.authenticated[key][1]:
                                raise AdminError("auth_failed", "CLI requires an administrator login, not guest access")
                            fields, raw = await self._command(mc, contact, command)
                            result.update(fields, raw_response=raw, online=True)
                        elif action == "trace":
                            result.update(await self._trace(mc, contact))
                            result["online"] = True
                        elif action != "remote_login":
                            raw = await self._binary(mc, contact, action, data)
                            result["raw_response"] = raw
                            result.update(parse_binary(action, raw["data"], data.get("count", 8), data.get("offset", 0)), online=True)
                        else:
                            result["online"] = True
                    result["request_success"] = True
            finally:
                self.active = False
        except TimeoutError:
            result.update(error="no_response", message="No correlated reply before timeout; reachability or login may be required", online=False)
            if action == "remote_command" and key:
                self.cli_deferred_until[key] = time.monotonic() + 120
        except AdminError as error:
            result.update(error=error.reason, message=str(error))
            result["raw_response"] = getattr(error, "raw_response", result["raw_response"])
            if error.reason == "auth_failed":
                # A companion login-fail event can itself be a timeout, not a remote rejection.
                result["online"] = None
        except (ValueError, KeyError, TypeError) as error:
            result.update(error="parse_error", message="Response did not match the expected protocol", online=None)
            result["raw_response"] = getattr(error, "raw_response", result["raw_response"])
        except Exception:
            # Do not propagate exception strings: transports may include a frame or credential.
            result.update(error="not_connected", message="Companion transport failed during the request", online=False)
        if attempted:
            result["round_trip_ms"] = round((time.monotonic() - started) * 1000)
        if key:
            record = self.records[key]
            if attempted:
                record["request_successes" if result["request_success"] else "request_failures"] += 1
                record.update(online=result["online"], last_attempt_at=time.time())
                if result["online"]:
                    record["last_seen_at"] = time.time()
            for field in FIELDS:
                if result[field] is not None:
                    record[field] = result[field]
                    record["field_updated_at"][field] = time.time()
            record.update(request_success=result["request_success"], error=result["error"],
                          round_trip_ms=result["round_trip_ms"], raw_response=result["raw_response"])
            result.update(request_successes=record["request_successes"], request_failures=record["request_failures"])
            await self.save()
            self.coordinator.async_update_listeners()
        return result

    @staticmethod
    def _sent(event, expected=EventType.MSG_SENT):
        if event is None:
            raise AdminError("no_response", "Companion did not acknowledge the request")
        if event.type != expected:
            # Numeric wire errors are not evidence of remote authentication or reachability.
            error = AdminError("unsupported" if event.type == EventType.ERROR else "parse_error",
                               "Companion rejected or did not support this request")
            error.raw_response = event.payload
            raise error

    async def _exchange(self, mc, types, sender, match):
        queue = asyncio.Queue()
        subscriptions = [mc.subscribe(event_type, queue.put_nowait) for event_type in types]
        try:
            sent = await sender()
            self._sent(sent)
            while True:
                event = await queue.get()
                if match(event, sent):
                    return event
        finally:
            for subscription in subscriptions:
                mc.unsubscribe(subscription)

    async def _binary(self, mc, contact, action, data):
        if action == "remote_neighbors":
            sender = lambda: mc.commands.req_neighbours_async(contact, count=data.get("count", 8),
                offset=data.get("offset", 0), pubkey_prefix_length=4, timeout=data.get("timeout", 20))
        else:
            kind = BinaryReqType.STATUS if action == "remote_status" else BinaryReqType.TELEMETRY
            sender = lambda: mc.commands.send_binary_req(contact, kind, timeout=data.get("timeout", 20))
        event = await self._exchange(mc, (EventType.BINARY_RESPONSE,), sender,
            lambda event, sent: event.payload.get("tag") == sent.payload["expected_ack"].hex())
        return event.payload

    async def _login(self, mc, contact, password):
        with sensitive_logs():
            try:
                event = await self._exchange(mc, (EventType.LOGIN_SUCCESS, EventType.LOGIN_FAILED),
                    lambda: mc.commands.send_login(contact, password),
                    lambda event, sent: event.payload.get("pubkey_prefix") == contact["public_key"][:12])
            except AdminError as error:
                error.raw_response = {"login_error": "[redacted]"}
                raise
        if event.type == EventType.LOGIN_FAILED:
            raise AdminError("auth_failed", "Login did not succeed (wrong password, unavailable repeater, or login timeout)")
        return event.payload

    async def _command(self, mc, contact, command):
        key = contact["public_key"]
        # Remote CLI replies carry the repeater's clock, not an echoed request tag.
        # Serialize, match source/type, reject already seen timestamps, and never retry a timed-out mutation.
        sensitive = any(word in command.lower() for word in ("password", "secret", "pwd"))
        with sensitive_logs():
            try:
                event = await self._exchange(mc, (EventType.CONTACT_MSG_RECV,),
                    lambda: mc.commands.send_cmd(contact, command, timestamp=int(time.time())),
                    lambda event, sent: event.payload.get("pubkey_prefix") == key[:12]
                    and event.payload.get("txt_type") == 1
                    and event.payload.get("sender_timestamp", 0) > self.last_cli.get(key, 0))
            except AdminError as error:
                if sensitive:
                    error.raw_response = {"command_error": "[redacted]"}
                raise
        self.last_cli[key] = event.payload.get("sender_timestamp", 0)
        raw = {**event.payload, "text": "[redacted]"} if sensitive else event.payload
        try:
            return ({"reply": "[redacted]"} if sensitive else parse_cli(command, event.payload["text"])), raw
        except (ValueError, AdminError) as error:
            error.raw_response = raw
            raise

    async def _trace(self, mc, contact):
        length, mode = contact.get("out_path_len", -1), contact.get("out_path_hash_mode", 0)
        if length < 0 or mode not in (0, 1):
            raise AdminError("unsupported", "Trace requires a known one- or two-byte hash route; no automatic path discovery")
        width = mode + 1
        route = bytes.fromhex(contact.get("out_path", ""))[:length * width]
        if len(route) != length * width:
            raise ValueError("Invalid contact route")
        # Trace must return to our companion: outward route, target, then reversed outward route.
        hops = [route[i:i+width] for i in range(0, len(route), width)]
        path = b"".join(hops) + bytes.fromhex(contact["public_key"][:width*2]) + b"".join(reversed(hops))
        if len(path) > 63:
            raise AdminError("unsupported", "Trace route exceeds the safe packet length")
        tag, auth = secrets.randbits(32), secrets.randbits(32)
        event = await self._exchange(mc, (EventType.TRACE_DATA,),
            lambda: mc.commands.send_trace(tag=tag, auth_code=auth, flags=mode, path=path),
            lambda event, sent: event.payload.get("tag") == tag and event.payload.get("auth") == auth)
        return {"trace": event.payload, "trace_path": path.hex(), "raw_response": event.payload}
