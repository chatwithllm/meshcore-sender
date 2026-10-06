"""MeshCore SDK transport using Home Assistant's proxy-aware BLE devices."""

import asyncio
import time
import math

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from meshcore import EventType, MeshCore
from meshcore.ble_cx import BLEConnection, UART_RX_CHAR_UUID, UART_SERVICE_UUID, UART_TX_CHAR_UUID
from meshcore.tcp_cx import TCPConnection

from .api import MeshCoreError
from .range_test import NativeRangeTest


class ProxyBLEConnection(BLEConnection):
    """Retain HA's BLEDevice backend instead of rebuilding a client by MAC."""

    def __init__(self, hass, address):
        super().__init__(address=address)
        self.hass = hass

    async def connect(self):
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if device is None:
            raise MeshCoreError("Radio not visible to a connectable Home Assistant Bluetooth adapter")
        self.client = await establish_connection(
            BleakClientWithServiceCache, device, device.name or self.address,
            disconnected_callback=self.handle_disconnect,
            ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            ),
        )
        try:
            service = self.client.services.get_service(UART_SERVICE_UUID)
            if service is None:
                raise MeshCoreError("Selected device does not expose the MeshCore UART service")
            self.rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
            if self.rx_char is None:
                raise MeshCoreError("Radio write characteristic is missing")
            # MeshCore radios can require an encrypted link before UART writes.
            await self.client.pair()
            await self.client.start_notify(UART_TX_CHAR_UUID, self.handle_rx)
        except BaseException:
            await self.client.disconnect()
            raise
        return self.address


class NativeMeshCoreClient:
    def __init__(self, hass, address, *, host=None, port=5000):
        self.hass = hass
        self.address = address
        self.host = host
        self.port = port
        self.url = None
        self.mc = None
        self.channels = []
        self.lock = asyncio.Lock()
        self.last_message = None
        self.range = NativeRangeTest(self.send_one, self._create_task)

    def _create_task(self, coro):
        return self.hass.async_create_background_task(coro, "MeshCore range test")

    async def _ensure_connected(self):
        if self.mc is not None and self.mc.is_connected:
            return
        if self.mc is not None:
            await self.mc.disconnect()
            self.mc = None
        transport = (TCPConnection(self.host, self.port) if self.host else
                     ProxyBLEConnection(self.hass, self.address))
        mc = MeshCore(transport, default_timeout=15)
        try:
            event = await asyncio.wait_for(mc.connect(), timeout=30)
            if event is None or event.type == EventType.ERROR:
                raise MeshCoreError("Radio did not respond to the companion handshake")
            contacts = await mc.commands.get_contacts(timeout=30)
            if contacts is None or contacts.type == EventType.ERROR:
                raise MeshCoreError("Radio contact retrieval failed; try setup again when the radio is ready")
            channels = []
            for idx in range(8):
                event = await mc.commands.get_channel(idx)
                if event is None or event.type == EventType.ERROR:
                    break
                name = (event.payload.get("channel_name") or "").strip("\x00").strip()
                channels.append({"id": f"chan:{idx}",
                                 "name": name or ("Public channel" if idx == 0 else f"Channel {idx}"),
                                 "kind": "public" if idx == 0 else "private"})
            mc.subscribe(EventType.CONTACT_MSG_RECV, self._receive)
            mc.subscribe(EventType.CHANNEL_MSG_RECV, self._receive)
            self.mc = mc
            self.channels = channels
            await mc.start_auto_message_fetching()
        except BaseException:
            await mc.disconnect()
            self.mc = None
            raise

    def _receive(self, event):
        payload = event.payload
        prefix = payload.get("pubkey_prefix")
        contact = self.mc.get_contact_by_key_prefix(prefix) if prefix and self.mc else None
        self.last_message = {"text": payload.get("text", ""),
                             "sender": (contact or {}).get("adv_name") or prefix,
                             "channel": payload.get("channel_idx"), "received_at": time.time()}
        if hasattr(self, "history"):
            channel = payload.get("channel_idx")
            name = (contact or {}).get("adv_name") or f"Unknown node {prefix or ''}"
            conversation = f"chan:{channel}" if channel is not None else f"pk:{prefix}"
            target = f"chan:{channel}" if channel is not None else ("dm:" + name if contact else None)
            text = payload.get("text", "")
            sender = name
            if channel is not None:
                name = next((c["name"] for c in self.channels if c["id"] == target), f"Channel {channel}")
                sender, separator, body = text.partition(": ")
                if separator:
                    text = body
                else:
                    sender = "Channel member"
            message_id = self.history.append({"conversation": conversation, "target": target,
                                 "name": name, "sender": sender, "text": text,
                                 "direction": "in", "pubkey_prefix": prefix,
                                 "sender_timestamp": payload.get("sender_timestamp"),
                                 "hops": payload.get("path_len"), "status": "received"})
            if message_id and channel is None and contact and hasattr(self, "remote"):
                # Prefixes identify senders on the companion wire. Reject collisions.
                matches = [c for c in self.mc.contacts.values()
                           if isinstance(prefix, str) and len(prefix) >= 12
                           and c.get("public_key", "").startswith(prefix)]
                if len(matches) == 1 and matches[0].get("public_key") == contact.get("public_key"):
                    self.remote.submit(contact["public_key"], name, text, payload.get("sender_timestamp"),
                        lambda coro: self.hass.async_create_background_task(coro, "MeshCore remote commands"))
        self.hass.bus.async_fire("meshcore_sender_message", {"address": self.address,
                                                             **self.last_message})

    def _nodes(self):
        nodes = list(self.channels)
        for contact in self.mc.contacts.values():
            name = (contact.get("adv_name") or "").strip()
            if name:
                node = {"id": "dm:" + name, "name": name,
                        "kind": {2: "repeater", 3: "room"}.get(contact.get("type"), "node")}
                key = contact.get("public_key")
                if isinstance(key, str) and len(key) == 64:
                    node["public_key"] = key
                try:
                    lat, lon = float(contact.get("adv_lat")), float(contact.get("adv_lon"))
                    # The SDK already converts the wire's microdegrees to degrees.
                    if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
                        node.update(lat=lat, lon=lon)
                except (TypeError, ValueError):
                    pass
                nodes.append(node)
        return nodes

    async def send_one(self, target, text, timeout=20):
        message_id = None
        if hasattr(self, "history"):
            contact = self.mc.get_contact_by_name(target.removeprefix("dm:")) if self.mc and target.startswith("dm:") else None
            prefix = (contact or {}).get("public_key", "")[:12] or None
            name = next((n["name"] for n in self._nodes() if n["id"] == target), target) if self.mc else target
            message_id = self.history.append({"conversation": f"pk:{prefix}" if prefix else target,
                                             "target": target, "name": name, "sender": "You",
                                             "pubkey_prefix": prefix, "text": text,
                                             "direction": "out", "status": "sending"})
        try:
            result = await self._transmit(target, text, timeout)
        except asyncio.CancelledError:
            if message_id:
                self.history.update(message_id, status="unconfirmed")
            raise
        except Exception:
            if message_id:
                self.history.update(message_id, status="failed")
            raise
        if message_id:
            self.history.update(message_id, status=("delivered" if result.get("acked") else
                                "broadcast" if result.get("ok") and target.startswith("chan:") else
                                "unconfirmed" if result.get("ok") else "failed"))
        return result

    async def _transmit(self, target, text, timeout=20):
        async with self.lock:
            await self._ensure_connected()
            started = time.monotonic()
            if target.startswith("chan:"):
                event = await self.mc.commands.send_chan_msg(int(target.split(":", 1)[1]), text)
                ok = event is not None and event.type != EventType.ERROR
                return {"target": target, "ok": ok, "acked": False, "rtt_ms": 0,
                        "out": "Channel broadcast sent" if ok else "Channel broadcast failed"}
            contact = self.mc.get_contact_by_name(target.removeprefix("dm:"))
            if contact is None:
                raise MeshCoreError("Contact is no longer available")
            event = await self.mc.commands.send_msg_with_retry(
                contact, text, timeout=max(2, timeout * .4), min_timeout=2,
                max_attempts=2, max_flood_attempts=1,
            )
            acked = event is not None and event.type != EventType.ERROR
            return {"target": target, "ok": event is None or acked, "acked": acked,
                    "rtt_ms": round((time.monotonic() - started) * 1000),
                    "out": "ACK received" if acked else "No delivery ACK"}

    async def request(self, method, path, payload=None):
        payload = payload or {}
        try:
            if path == "/api/range/status":
                return self.range.snapshot()
            if path == "/api/range/stop":
                return await self.range.stop()
            async with self.lock:
                await self._ensure_connected()
                nodes = self._nodes()
            if path == "/api/nodes":
                return {"nodes": nodes}
            if path == "/api/health":
                return {"radio_ok": True, "nodes": len(nodes), "last_message": self.last_message}
            targets = payload.get("targets", [])
            valid = {node["id"] for node in nodes}
            if not isinstance(targets, list) or not targets or any(t not in valid for t in targets):
                raise MeshCoreError("Choose available contacts or channels")
            if path == "/api/range/start":
                return self.range.start(targets, payload.get("interval", 30), payload.get("prefix", "ping"),
                                        payload.get("started_by", "Home Assistant"))
            if path == "/api/send":
                text = payload.get("text", "").strip()
                if not text or len(text.encode()) > 150:
                    raise MeshCoreError("Message must contain 1 to 150 UTF-8 bytes")
                results = [await self.send_one(target, text) for target in targets]
                return {"ok": all(item["ok"] for item in results), "results": results}
            raise MeshCoreError("Unsupported native radio action")
        except MeshCoreError:
            raise
        except Exception as error:
            raise MeshCoreError(str(error) or "Radio connection failed") from error

    async def close(self):
        if hasattr(self, "remote"):
            await self.remote.close()
            await self.remote_store.async_save(self.remote.snapshot())
        await self.range.stop()
        async with self.lock:
            if self.mc:
                await self.mc.disconnect()
                self.mc = None
        if hasattr(self, "history_store"):
            await self.history_store.async_save(self.history.snapshot())
