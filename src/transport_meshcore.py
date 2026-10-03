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


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _add_inbox(scope: str, sender, text: str, direction: str = "in") -> None:
    ts = _now()
    raw = "%s|%s|%s|%s|%s" % (direction, scope, sender or "", text, ts)
    with _inbox_lock:
        if not any(m.get("raw") == raw for m in _inbox):
            _inbox.append({
                "scope": scope,
                "sender": sender,
                "text": text,
                "at": ts,
                "direction": direction,
                "raw": raw,
            })
        if len(_inbox) > 400:
            del _inbox[:-400]


# ── connection ──────────────────────────────────────────────────────────────

async def _connect_async():
    """Create a BLE connection, subscribe to messages, load contacts/channels."""
    global _mc, _channels
    from meshcore import MeshCore, EventType

    mc = await MeshCore.create_ble(ADDR, timeout=15)

    # Subscribe to live incoming DMs
    def _on_dm(event):
        p = event.payload
        pubkey = p.get("pubkey_prefix", "")
        text = (p.get("text") or "").strip()
        contact = mc.get_contact_by_key_prefix(pubkey) if pubkey else None
        name = (contact.get("adv_name") if contact else None) or pubkey[:8] or "unknown"
        _add_inbox(scope=name, sender=name, text=text, direction="in")

    # Subscribe to live incoming channel messages
    def _on_chan(event):
        p = event.payload
        idx = p.get("channel_idx", 0)
        text = (p.get("text") or "").strip()
        scope = "public" if idx == 0 else "chan%d" % idx
        sender = None
        if ": " in text:
            sender, text = text.split(": ", 1)
        _add_inbox(scope=scope, sender=sender, text=text, direction="in")

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
        if idx == 0:
            name = ("Public channel (%s)" % raw_name) if raw_name else "Public channel"
        else:
            name = raw_name or ("Channel %d" % idx)
        channels.append({
            "id": "chan:%d" % idx,
            "name": name,
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
        if _mc is not None and _mc.is_connected():
            return _mc, None
        if _mc is not None:
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

    for contact in mc.contacts.values():
        name = (contact.get("adv_name") or "").strip()
        if not name:
            continue
        kind = _kind_map.get(contact.get("type", 0), "node")
        items.append({"id": "dm:%s" % name, "name": name, "kind": kind})

    if not items:
        return [], "no destinations — device may have no contacts yet"

    seen = set()
    uniq = []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            uniq.append(it)
    return uniq, None


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
            results.append({"target": "channel %d" % idx, "ok": ok, "out": out})
        else:
            who = t.split(":", 1)[1] if ":" in t else t
            contact = mc.get_contact_by_name(who)
            if contact is None:
                results.append({"target": who, "ok": False,
                                 "out": "contact '%s' not found" % who})
                continue
            try:
                ev = _submit(mc.commands.send_msg(contact, text), timeout=TIMEOUT)
                ok = ev.type != EventType.ERROR
                out = "" if ok else str(ev.payload)[:200]
            except Exception as e:
                ok, out = False, "send_msg error: %s" % e
            results.append({"target": who, "ok": ok, "out": out})
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
