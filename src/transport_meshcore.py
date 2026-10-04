#!/usr/bin/env python3
"""MeshCore transport using the meshcore Python SDK.

Replaces the meshcore-cli subprocess transport with a persistent BLE connection
via the meshcore Python SDK.  Benefits over the CLI approach:
  * Persistent connection — no 5-10 s reconnect per call
  * Real delivery ACKs from send_msg_with_retry()
  * Live message events via subscriptions (no polling loss)

Public API is identical to the previous CLI-based transport:
  probe()                                       -> dict
  destinations()                                -> (items, error)
  send(targets, text)                           -> [{target, ok, out}]
  send_one_ack(contact_name, text, timeout)     -> (acked, rtt_ms, detail)
  messages(limit)                               -> (messages, error)
  strip_ansi(text)                              -> str

BLE permission: macOS grants Bluetooth only to the process that launched from
an authorised app (Terminal.app, etc.).  Run the server from Terminal, not
from Claude's Bash tool.
"""

import logging
import json
import os
import sys
import threading
import time

# The SDK lives under the python3.11 uv-tools install.  Works transparently
# when the server is invoked with that interpreter; also works with other
# Pythons by inserting the site-packages path explicitly.
_SDK_SITE = ("/Users/assistant/.local/share/uv/tools/meshcore-cli"
             "/lib/python3.11/site-packages")
if _SDK_SITE not in sys.path:
    sys.path.insert(0, _SDK_SITE)

ADDR = os.environ.get("MESHCORE_ADDR", "DDE75E06-4BF2-DB42-7B69-B29FE29CB836")
TIMEOUT = int(os.environ.get("MESHCORE_TIMEOUT", "30"))
PUBLIC = "chan:0"

log = logging.getLogger(__name__)

# ── asyncio bridge ─────────────────────────────────────────────────────────
# One permanent background event loop.  All SDK coroutines run here;
# HTTP-server threads submit work with run_coroutine_threadsafe and block
# for the result.
_loop = None
_loop_ready = threading.Event()


def _loop_main() -> None:
    global _loop
    import asyncio
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_ready.set()
    _loop.run_forever()


threading.Thread(target=_loop_main, daemon=True, name="mc-ioloop").start()
_loop_ready.wait()


def _submit(coro, timeout: float = None):

    """Submit coro to the background loop; block until done or timeout."""
    import asyncio
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    return fut.result(timeout=(timeout or TIMEOUT) + 5)


# ── shared state ────────────────────────────────────────────────────────────
_mc = None                    # meshcore.MeshCore — the live connection
_mc_lock = threading.Lock()   # serialises connect / disconnect
_channels: list = []          # [{id, name, kind}] — cached on connect
_inbox: list = []             # [{scope, sender, text, at, direction, raw}]
_inbox_lock = threading.Lock()
_DRAIN_INTERVAL = int(os.environ.get("MESHCORE_DRAIN_INTERVAL", "8"))  # seconds
_DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _channel_name(idx) -> str:
    try:
        n = int(idx)
    except (TypeError, ValueError):
        n = 0
    for channel in _channels:
        if channel.get("id") == "chan:%d" % n:
            return channel.get("name") or ("Channel %d" % n)
    return "Public channel" if n == 0 else "Channel %d" % n


def _read_channel_aliases() -> dict:
    """Load non-secret display aliases for channel names/slots/hashes.

    MeshCore's channel API may return a generic stored slot name such as
    "private". The CLI also supports a scopes file that maps that stored name
    to a user-facing scope. The app additionally accepts DATA_DIR/channel_names.json
    for local display aliases without touching radio configuration.
    """
    aliases = {}

    scopes_path = os.path.expanduser("~/.config/meshcore/scopes")
    if os.path.exists(scopes_path):
        try:
            with open(scopes_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith(";") or line.startswith("#"):
                        continue
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        aliases[parts[0].strip().lower()] = parts[1].strip()
        except Exception as exc:  # noqa: BLE001 - aliases are optional
            log.warning("could not read channel scopes file: %s", exc)

    names_path = os.path.join(_DATA_DIR, "channel_names.json")
    if os.path.exists(names_path):
        try:
            with open(names_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, str) and value.strip():
                        aliases[str(key).strip().lower()] = value.strip()
                    elif isinstance(value, dict):
                        name = (value.get("name") or value.get("display_name") or "").strip()
                        if name:
                            aliases[str(key).strip().lower()] = name
            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = (item.get("name") or item.get("display_name") or "").strip()
                    keys = [item.get("id"), item.get("slot"), item.get("idx"),
                            item.get("channel_idx"), item.get("raw_name"),
                            item.get("channel_name"), item.get("hash"),
                            item.get("channel_hash")]
                    for key in keys:
                        if name and key is not None:
                            aliases[str(key).strip().lower()] = name
        except Exception as exc:  # noqa: BLE001 - aliases are optional
            log.warning("could not read channel_names.json: %s", exc)

    return aliases


def _channel_display_name(idx, raw_name: str, channel_hash: str = None) -> str:
    raw = (raw_name or "").strip("\x00").strip()
    aliases = _read_channel_aliases()
    keys = [
        "chan:%d" % idx,
        str(idx),
        raw.lower(),
        (channel_hash or "").strip().lower(),
    ]
    for key in keys:
        if key and aliases.get(key):
            return aliases[key]
    if idx == 0:
        return ("Public channel (%s)" % raw) if raw and raw.lower() != "public" else "Public channel"
    return raw or ("Channel %d" % idx)


def _route_hops(path_hex=None, hash_mode=None, contacts=None) -> list:
    try:
        size = int(hash_mode) + 1
    except (TypeError, ValueError):
        size = 1
    if size <= 0:
        size = 1
    raw = (path_hex or "").strip()
    if not raw:
        return []

    chunks = [raw[i:i + size * 2] for i in range(0, len(raw), size * 2)]
    items = []
    contact_list = list((contacts or {}).values())
    for idx, chunk in enumerate(chunks, start=1):
        matches = []
        for contact in contact_list:
            key = (contact.get("public_key") or "").lower()
            if key.startswith(chunk.lower()):
                name = (contact.get("adv_name") or "").strip()
                matches.append(name or key[:8])
        item = {"index": idx, "hash": chunk}
        if len(matches) == 1:
            item["name"] = matches[0]
        elif len(matches) > 1:
            item["name"] = " / ".join(matches[:3])
            item["ambiguous"] = True
        items.append(item)
    return items


def _route_info(path_len=None, path_hex=None, hash_mode=None, contacts=None) -> dict:
    try:
        hops = int(path_len)
    except (TypeError, ValueError):
        return {}
    if hops == 255:
        return {"route_hops": 0, "route_mode": "direct"}
    if hops < 0:
        return {"route_hops": None, "route_mode": "flood"}
    info = {"route_hops": hops, "route_mode": "direct" if hops == 0 else "routed"}
    route_path = _route_hops(path_hex, hash_mode, contacts)
    if route_path:
        info["route_path"] = route_path[:hops] if hops > 0 else []
    return info


def _add_inbox(scope: str, sender, text: str, direction: str = "in", **meta) -> None:
    ts = _now()
    # raw excludes timestamp so drain + subscription don't create duplicates
    raw = "%s|%s|%s|%s" % (direction, scope, sender or "", text)
    with _inbox_lock:
        if not any(m.get("raw") == raw for m in _inbox):
            item = {
                "scope": scope,
                "sender": sender,
                "text": text,
                "at": ts,
                "direction": direction,
                "raw": raw,
            }
            item.update({k: v for k, v in meta.items() if v is not None})
            _inbox.append(item)
        if len(_inbox) > 400:
            del _inbox[:-400]


# ── connection ──────────────────────────────────────────────────────────────

async def _connect_async():
    """Create a BLE connection, subscribe to messages, load contacts/channels."""
    global _mc, _channels
    from meshcore import MeshCore, EventType

    mc = await MeshCore.create_ble(ADDR, default_timeout=15)

    # Subscribe to live incoming DMs
    def _on_dm(event):
        p = event.payload
        pubkey = p.get("pubkey_prefix", "")
        text = (p.get("text") or "").strip()
        contact = mc.get_contact_by_key_prefix(pubkey) if pubkey else None
        name = (contact.get("adv_name") if contact else None) or pubkey[:8] or "unknown"
        _add_inbox(scope=name, sender=name, text=text, direction="in",
                   pubkey_prefix=pubkey,
                   **_route_info(p.get("path_len"), p.get("path"),
                                 p.get("path_hash_mode"), mc.contacts))

    # Subscribe to live incoming channel messages
    def _on_chan(event):
        p = event.payload
        idx = p.get("channel_idx", 0)
        text = (p.get("text") or "").strip()
        scope = _channel_name(idx)
        sender = None
        if ": " in text:
            sender, text = text.split(": ", 1)
        _add_inbox(scope=scope, sender=sender, text=text, direction="in",
                   **_route_info(p.get("path_len"), p.get("path"),
                                 p.get("path_hash_mode"), mc.contacts))

    mc.subscribe(EventType.CONTACT_MSG_RECV, _on_dm)
    mc.subscribe(EventType.CHANNEL_MSG_RECV, _on_chan)

    # Load contact table
    await mc.ensure_contacts()

    # Discover channels 0-7 (MeshCore supports up to 8)
    channels = []
    for idx in range(8):
        ev = await mc.commands.get_channel(idx)
        if ev.type == EventType.ERROR:
            break
        raw_name = (ev.payload.get("channel_name") or "").strip("\x00").strip()
        channel_hash = ev.payload.get("channel_hash")
        name = _channel_display_name(idx, raw_name, channel_hash)
        channels.append({
            "id": "chan:%d" % idx,
            "name": name,
            "raw_name": raw_name,
            "channel_hash": channel_hash,
            "kind": "public" if idx == 0 else "private",
        })

    if not channels:
        channels = [{"id": "chan:0", "name": "Public channel", "kind": "public"}]

    _mc = mc
    _channels = channels
    return True, "connected"


def _get_mc():
    """Return a live MeshCore instance, auto-connecting when needed."""
    global _mc
    with _mc_lock:
        if _mc is not None:
            try:
                connected = _mc.is_connected
            except Exception as _e:
                # is_connected failed — log and assume still connected rather
                # than tear down a potentially live BLE link unnecessarily.
                log.warning("is_connected check raised %s (%s); reusing connection",
                            type(_e).__name__, _e)
                connected = True
            if connected:
                return _mc, None
            # is_connected returned False — link dropped, reconnect below
            try:
                _submit(_mc.disconnect(), timeout=5)
            except Exception:
                pass
            _mc = None
        try:
            ok, detail = _submit(_connect_async(), timeout=25)
            if ok:
                return _mc, None
            return None, "connect failed: %s" % detail
        except Exception as e:
            _mc = None
            return None, "connect error: %s" % e


# ── public API ──────────────────────────────────────────────────────────────

def reconnect():
    """Force-disconnect BLE so the next call reconnects fresh."""
    global _mc
    with _mc_lock:
        if _mc is not None:
            try:
                _submit(_mc.disconnect(), timeout=5)
            except Exception:
                pass
            _mc = None
    return True, "disconnected — will reconnect on next request"


def strip_ansi(text):
    import re
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text or "")


def probe():
    """Connectivity probe. Matches the CLI transport's return shape."""
    sdk_ok = True
    try:
        import meshcore  # noqa: F401
    except ImportError:
        sdk_ok = False

    mc, err = _get_mc()
    return {
        "cli_present": sdk_ok,
        "addr": ADDR,
        "ble_devices_seen": [],     # SDK has no scan-only mode; omit list
        "connect_ok": mc is not None,
        "connect_detail": "" if mc is not None else (err or "unknown error"),
        "hint": (None if mc is not None else
                 "Close MeshCore One (or any app holding the radio) and retry — "
                 "BLE allows only one connection at a time."),
    }


def destinations():
    """Return (items, error) for the destination picker.

    Items: [{id, name, kind}]
      id   = "chan:N" or "dm:ContactName"
      kind = "public" | "private" | "node" | "repeater" | "room"
    """
    mc, err = _get_mc()
    if mc is None:
        return [], err

    # Channels first (cached from connect)
    items = list(_channels)

    # AdvType integers: NONE=0, CHAT=1, REPEATER=2, ROOM=3, SENSOR=4
    _kind_map = {2: "repeater", 3: "room"}

    def _coord(value, low, high):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if (v < low or v > high) and abs(v) > max(abs(low), abs(high)):
            for scale in (1_000_000, 10_000_000):
                scaled = v / scale
                if low <= scaled <= high:
                    v = scaled
                    break
        if v == 0 or v < low or v > high:
            return None
        return v

    for contact in mc.contacts.values():
        name = (contact.get("adv_name") or "").strip()
        if not name:
            continue
        kind = _kind_map.get(contact.get("type", 0), "node")
        item = {"id": "dm:%s" % name, "name": name, "kind": kind}
        key = (contact.get("public_key") or "").strip()
        if key:
            item["key_prefix"] = key[:12]
        lat = _coord(contact.get("adv_lat"), -90, 90)
        lon = _coord(contact.get("adv_lon"), -180, 180)
        if lat is not None and lon is not None:
            item["lat"] = lat
            item["lon"] = lon
        items.append(item)

    if not items:
        return [], "no destinations — device may have no contacts yet"

    seen = set()
    uniq = []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            uniq.append(it)
    return uniq, None


def route(target):
    """Return route metadata for a destination id, based on current contacts."""
    mc, err = _get_mc()
    if mc is None:
        return {"ok": False, "error": err or "not connected"}
    if target.startswith("chan:"):
        return {"ok": True, "target": target, "route_hops": None,
                "route_mode": "flood", "route_path": []}

    who = target.split(":", 1)[1] if ":" in target else target
    contact = mc.get_contact_by_name(who)
    if contact is None:
        try:
            contact = mc.get_contact_by_key_prefix(who)
        except Exception:
            contact = None
    if contact is None:
        return {"ok": False, "error": "contact '%s' not found" % who}

    info = _route_info(contact.get("out_path_len"),
                       contact.get("out_path"),
                       contact.get("out_path_hash_mode"),
                       mc.contacts)
    info.update({"ok": True, "target": who})
    return info


def add_contact(public_key, name, kind=1):
    """Add a contact from a public key, display name and MeshCore contact type."""
    mc, err = _get_mc()
    if mc is None:
        return {"ok": False, "error": err or "not connected"}
    from meshcore import EventType
    public_key = (public_key or "").strip()
    name = (name or "").strip()
    try:
        bytes.fromhex(public_key)
    except ValueError:
        return {"ok": False, "error": "public key must be hex"}
    if len(public_key) != 64:
        return {"ok": False, "error": "public key must be 64 hex characters"}
    if not name:
        return {"ok": False, "error": "name is required"}
    try:
        kind = int(kind)
    except (TypeError, ValueError):
        kind = 1
    if kind not in (1, 2, 3):
        kind = 1
    contact = {
        "public_key": public_key,
        "type": kind,
        "flags": 0,
        "out_path_len": -1,
        "out_path": "",
        "out_path_hash_mode": 0,
        "adv_name": name[:32],
        "adv_lat": 0,
        "adv_lon": 0,
        "last_advert": 0,
    }
    try:
        ev = _submit(mc.commands.add_contact(contact), timeout=TIMEOUT)
        if ev.type == EventType.ERROR:
            return {"ok": False, "error": str(ev.payload)[:200]}
        mc.contacts[public_key] = contact
        try:
            _submit(mc.commands.get_contacts(), timeout=10)
        except Exception as exc:  # noqa: BLE001 - contact is already added
            log.warning("contact refresh after add failed: %s", exc)
        return {"ok": True, "contact": {"id": "dm:%s" % contact["adv_name"],
                                        "name": contact["adv_name"]}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "add contact error: %s" % exc}


def import_contact(uri):
    """Import a meshcore:// contact URI."""
    mc, err = _get_mc()
    if mc is None:
        return {"ok": False, "error": err or "not connected"}
    from meshcore import EventType
    uri = (uri or "").strip()
    if not uri.startswith("meshcore://"):
        return {"ok": False, "error": "contact URI must start with meshcore://"}
    payload = uri[11:].strip()
    try:
        card_data = bytes.fromhex(payload)
    except ValueError:
        return {"ok": False, "error": "contact URI payload is not valid hex"}
    try:
        ev = _submit(mc.commands.import_contact(card_data), timeout=TIMEOUT)
        if ev.type == EventType.ERROR:
            return {"ok": False, "error": str(ev.payload)[:200]}
        try:
            _submit(mc.commands.get_contacts(), timeout=10)
        except Exception as exc:  # noqa: BLE001 - contact is already imported
            log.warning("contact refresh after import failed: %s", exc)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "import contact error: %s" % exc}


def export_contact(name=None):
    """Export this node's URI, or a known contact's URI when name is provided."""
    mc, err = _get_mc()
    if mc is None:
        return {"ok": False, "error": err or "not connected"}
    from meshcore import EventType
    target = None
    name = (name or "").strip()
    if name:
        target = mc.get_contact_by_name(name)
        if target is None:
            try:
                target = mc.get_contact_by_key_prefix(name)
            except Exception:
                target = None
        if target is None:
            return {"ok": False, "error": "contact '%s' not found" % name}
    try:
        ev = _submit(mc.commands.export_contact(target), timeout=TIMEOUT)
        if ev.type == EventType.ERROR:
            return {"ok": False, "error": str(ev.payload)[:200]}
        return {"ok": True, "uri": ev.payload.get("uri", "")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "export contact error: %s" % exc}


def send(targets, text):
    """Send to each target. targets are ids from destinations()."""
    mc, err = _get_mc()
    if mc is None:
        return [{"target": t, "ok": False, "out": err} for t in targets]

    from meshcore import EventType
    results = []
    for t in targets:
        if t.startswith("chan:"):
            idx = int(t.split(":", 1)[1])
            try:
                ev = _submit(mc.commands.send_chan_msg(idx, text), timeout=TIMEOUT)
                ok = ev.type != EventType.ERROR
                out = "" if ok else str(ev.payload)[:200]
            except Exception as e:
                ok, out = False, "send_chan_msg error: %s" % e
            results.append({"target": _channel_name(idx), "ok": ok, "out": out})
        else:
            who = t.split(":", 1)[1] if ":" in t else t
            contact = mc.get_contact_by_name(who)
            if contact is None:
                # Might be a pubkey prefix stored as scope by old CLI transport
                try:
                    contact = mc.get_contact_by_key_prefix(who)
                except Exception:
                    contact = None
            if contact is None:
                results.append({"target": who, "ok": False, "acked": False,
                                 "out": "contact '%s' not found" % who})
                continue
            route = _route_info(contact.get("out_path_len"),
                                contact.get("out_path"),
                                contact.get("out_path_hash_mode"),
                                mc.contacts)
            try:
                ack_ev = _submit(
                    mc.commands.send_msg_with_retry(
                        contact, text,
                        timeout=min(TIMEOUT * 0.4, 15.0),
                        min_timeout=2.0,
                        max_attempts=2,
                        max_flood_attempts=1,
                    ),
                    timeout=TIMEOUT + 5,
                )
                # None = sent, no ACK received; Event = ACK received
                acked = ack_ev is not None and ack_ev.type != EventType.ERROR
                ok = True
                out = "ACK received" if acked else "sent (no ACK)"
            except Exception as e:
                ok, acked, out = False, False, "send error: %s" % e
            results.append({"target": who, "ok": ok, "acked": acked, "out": out,
                            **route})
    return results


def send_one_ack(contact_name, text, timeout=None):
    """Send a DM with retries and wait for ACK.

    Returns (acked, rtt_ms, detail_str).
    acked=True means the remote node confirmed receipt — not just 'queued'.
    Used by the range-test loop.
    """
    t = float(timeout or TIMEOUT)
    mc, err = _get_mc()
    if mc is None:
        return False, 0, "no connection: %s" % (err or "")

    contact = mc.get_contact_by_name(contact_name)
    if contact is None:
        return False, 0, "contact '%s' not found" % contact_name

    import time as _time
    t0 = _time.monotonic()
    try:
        ev = _submit(
            mc.commands.send_msg_with_retry(
                contact, text,
                timeout=min(t * 0.4, 20.0),   # per-attempt timeout
                min_timeout=2.0,
                max_attempts=2,
                max_flood_attempts=1,
            ),
            timeout=t + 5,
        )
        rtt = round((_time.monotonic() - t0) * 1000)
        if ev is None:
            return False, rtt, "no ACK within %.0fs" % t
        return True, rtt, "ACK received"
    except Exception as e:
        rtt = round((_time.monotonic() - t0) * 1000)
        return False, rtt, "error: %s" % e


async def _drain_queue_async(mc) -> None:
    """Drain all pending messages from the device queue into _inbox."""
    import asyncio
    from meshcore import EventType
    for _ in range(100):  # safety cap
        ev = await mc.commands.get_msg()
        if ev.type in (EventType.NO_MORE_MSGS, EventType.ERROR):
            break
        p = ev.payload or {}
        if ev.type == EventType.CONTACT_MSG_RECV:
            pubkey = p.get("pubkey_prefix", "")
            text = (p.get("text") or "").strip()
            try:
                contact = mc.get_contact_by_key_prefix(pubkey) if pubkey else None
                if contact is None and pubkey:
                    await mc.ensure_contacts()
                    contact = mc.get_contact_by_key_prefix(pubkey)
                name = (contact.get("adv_name") if contact else None) or pubkey[:8] or "unknown"
            except Exception:
                name = pubkey[:8] or "unknown"
            _add_inbox(scope=name, sender=name, text=text, direction="in",
                       pubkey_prefix=pubkey,
                       **_route_info(p.get("path_len"), p.get("path"),
                                     p.get("path_hash_mode"), mc.contacts))
        elif ev.type == EventType.CHANNEL_MSG_RECV:
            idx = p.get("channel_idx", 0)
            text = (p.get("text") or "").strip()
            scope = _channel_name(idx)
            sender = None
            if ": " in text:
                sender, text = text.split(": ", 1)
            _add_inbox(scope=scope, sender=sender, text=text, direction="in",
                       **_route_info(p.get("path_len"), p.get("path"),
                                     p.get("path_hash_mode"), mc.contacts))
        else:
            log.debug("drain: unexpected event type %s", ev.type)
        await asyncio.sleep(0.05)


def messages(limit: int = 60):
    """Return (messages, error). Drains pending queue from device first.

    Messages: [{scope, sender, text, at, direction, raw}]
    direction: "in" | "out"
    """
    mc, err = _get_mc()
    if mc is None:
        return [], err

    try:
        _submit(_drain_queue_async(mc), timeout=90)
    except Exception as e:
        log.warning("drain queue: %s", e)

    with _inbox_lock:
        return list(_inbox[-limit:]), None


# ── background drain thread ──────────────────────────────────────────────────
# Periodically drains the device message queue so incoming replies appear
# in the UI automatically without requiring a manual "Fetch new".

def _bg_drain_loop() -> None:
    while True:
        time.sleep(_DRAIN_INTERVAL)
        try:
            mc, _ = _get_mc()
            if mc is None:
                continue
            _submit(_drain_queue_async(mc), timeout=_DRAIN_INTERVAL + 10)
        except Exception as e:
            log.debug("bg drain: %s", e)


threading.Thread(target=_bg_drain_loop, daemon=True, name="mc-drain").start()
