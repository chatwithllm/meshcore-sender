#!/usr/bin/env python3
"""MeshCore transport for the sender UI.

MeshCore, not Meshtastic: same Heltec board, different firmware and wire
protocol. Destinations are the device's own contacts (direct messages) and
channels (the public channel is one of them).

Transport is `meshcore-cli`, the only MeshCore client installed on this Mac.

REACHABILITY, the thing that bit us repeatedly:
  * BLE allows ONE central per peripheral. If the MeshCore One app (or anything
    else on this Mac) holds the connection, the CLI cannot connect and scanning
    finds nothing -- because a connected peripheral stops advertising.
  * That failure is silent at the scan level and looks identical to "device is
    off". So this module never reports a bare failure: it carries the CLI's own
    words back to the UI, and `probe()` separates "CLI missing", "no device
    visible" and "device visible but connection refused".

Output formats are parsed defensively: `meshcore-cli` is a text CLI, so the
parsers below take the first token as the id and the rest as a label, and skip
its INFO/ERROR log lines. `probe()` prints raw output so a format change can be
diagnosed from the UI rather than guessed at here.
"""

import os
import shutil
import subprocess

CLI = os.environ.get("MESHCORE_CLI", "meshcore-cli")
ADDR = os.environ.get("MESHCORE_ADDR",
                       "DDE75E06-4BF2-DB42-7B69-B29FE29CB836")  # MeshCore-MacMini UUID
TIMEOUT = int(os.environ.get("MESHCORE_TIMEOUT", "30"))

# The public channel is channel index 0 on MeshCore.
PUBLIC = "chan:0"


def _run(args, timeout=None):
    """Run meshcore-cli. Returns (ok, combined_output)."""
    if not shutil.which(CLI):
        return False, "meshcore-cli not found on PATH (looked for %r)" % CLI
    cmd = [CLI]
    if ADDR:
        cmd += ["-a", ADDR]
    cmd += list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout or TIMEOUT)
        out = (p.stdout or "") + (p.stderr or "")
        # meshcore-cli exits 0 even when it never found the device, so the exit
        # code alone is not a success signal. Without this, a failed scan reads
        # as "ran fine, nothing to parse" and the UI blames the wrong thing.
        for marker in ("Couldn't find device", "Can't connect", "No response from"):
            if marker in out:
                return False, out
        return (p.returncode == 0), out
    except subprocess.TimeoutExpired:
        return False, ("timed out after %ss - the device is probably connected to "
                       "the MeshCore One app or another BLE central" % (timeout or TIMEOUT))
    except Exception as exc:                                        # noqa: BLE001
        return False, "could not run %s: %s" % (CLI, exc)


def _clean(out):
    """Drop meshcore-cli's log noise, keep payload lines."""
    keep = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("INFO", "WARNING", "DEBUG")):
            continue
        keep.append(s)
    return keep


def probe():
    """Is the device visible at all? Separates the three failure modes."""
    found = _run(["-T", "6", "-l"], timeout=25)
    body = found[1] if found[0] else found[1]
    ble = []
    seen_serial = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("BLE devices:"):
            seen_serial = False
            continue
        if s.startswith("Serial ports:"):
            seen_serial = True
            continue
        if s and not seen_serial and not s.startswith(("INFO", "ERROR")):
            ble.append(s)
    # a direct connect tells us whether it is reachable, not just advertising
    ok, out = _run(["clock"], timeout=25)
    return {
        "cli_present": bool(shutil.which(CLI)),
        "addr": ADDR,
        "ble_devices_seen": ble,
        "connect_ok": ok,
        "connect_detail": "" if ok else (out.strip()[-400:] or "no detail"),
        "hint": None if ok else (
            "Close MeshCore One (or any app holding the radio) and retry - BLE "
            "allows one connection at a time, and a connected device stops "
            "advertising, so an empty scan can just mean 'busy'."),
    }


def _destinations_once():
    """The picker list: channels first, then contacts. Returns (items, error)."""
    items, errors = [], []

    ok, out = _run(["get_channels"], timeout=30)
    if ok:
        for line in _clean(out):
            bits = line.split()
            if not bits:
                continue
            # device prints "0: Public [8b33...]" - strip the colon and the key
            idx = bits[0].strip().rstrip(":")
            if not idx.isdigit():
                continue
            name = " ".join(bits[1:]).split("[")[0].strip() or ("channel %s" % idx)
            if idx == "0":
                name = "Public channel (%s)" % name if name else "Public channel"
            items.append({"id": "chan:" + idx, "name": name})
    else:
        errors.append(out.strip()[-300:])

    # The device often reports 0 contacts until it has synced, and the CLI
    # prints that as a sentence ("0 from 0 contacts in device"). Ask it to
    # reload first, then refuse to treat prose as a contact name.
    _run(["reload_contacts"], timeout=45)
    ok2, out2 = _run(["contacts"], timeout=30)
    if ok2:
        for line in _clean(out2):
            s = line.strip()
            low = s.lower()
            # Deliberately NOT a length test: real contact lines are column-
            # padded to ~70 chars ("OptimusPrime   CLI  beb9019e697d  11h ab,ac"),
            # so a length cap silently discards every contact. Prose is
            # identified by its wording, never by how long it happens to be.
            is_prose = (s.startswith((">", "-", "*")) or "contacts in device" in low
                        or (" from " in low and "device" in low))
            if is_prose:
                errors.append(s[:120])
                continue
            name = s.split("  ")[0].strip() or s
            items.append({"id": "dm:" + name, "name": name})
        if not any(i["id"].startswith("dm:") for i in items):
            errors.append("device reports no contacts yet (it may still be syncing "
                          "- press Refresh in a few seconds)")
    else:
        errors.append(out2.strip()[-300:])

    if not items:
        return [], " | ".join(e for e in errors if e) or "no destinations returned"
    # DEDUPE-MARK: the device can report the same channel more than
    # once per connection, and the UI must never show duplicates.
    seen = set()
    uniq = []
    for _it in items:
        if _it["id"] in seen:
            continue
        seen.add(_it["id"])
        if _it["id"].startswith("chan:"):
            _it["kind"] = "public" if _it["id"] == "chan:0" else "private"
        else:
            _it["kind"] = "contact"
        uniq.append(_it)
    items = uniq

    return items, None


def send(targets, text):
    """Send to each target. `targets` are ids from destinations()."""
    results = []
    for t in targets:
        if t.startswith("chan:"):
            idx = t.split(":", 1)[1]
            ok, out = _run(["chan", idx, text], timeout=TIMEOUT)
            label = "channel %s" % idx
        else:
            who = t.split(":", 1)[1] if ":" in t else t
            ok, out = _run(["msg", who, text, "wait_ack"], timeout=TIMEOUT)
            label = who
        detail = " ".join(_clean(out))[-300:]
        results.append({"target": label, "ok": ok, "out": detail})
    return results


def send_one_ack(contact_name, text, timeout=None):
    """Send a single DM with wait_ack. Returns (acked, rtt_ms, detail_str).

    Used by the range-test loop where the ACK — not the send exit code — is
    the delivery datum. A non-zero rtt means the message reached the target
    and a reply was heard on the mesh.
    """
    import time as _time
    t0 = _time.monotonic()
    ok, out = _run(["msg", contact_name, text, "wait_ack"],
                   timeout=timeout or TIMEOUT)
    rtt = round((_time.monotonic() - t0) * 1000)
    detail = " ".join(_clean(out))[-300:]
    return ok, rtt, detail


# --- auto-recovery ---------------------------------------------------------
# A MeshCore node's contact table is a CACHE of adverts it has heard, held in
# working memory. Every BLE session can come back with it empty (54 -> 0 -> 53
# -> 0 -> 54 observed on this device). Refresh asks the same empty table again,
# so flood ONE advert and read once more. Bounded on purpose: one attempt per
# call plus a cooldown - an advert is a mesh-wide broadcast and a page refresh
# must not spam it.
ADVERT_COOLDOWN = 90.0
_LAST_ADVERT = 0.0


def destinations():
    """Destinations, with one automatic flood-advert recovery if contacts are empty."""
    global _LAST_ADVERT
    import time

    items, err = _destinations_once()
    if any(i.get("kind") == "contact" for i in items):
        return _stamp_roles(items), err         # healthy: nothing to do

    age = time.time() - _LAST_ADVERT
    if _LAST_ADVERT and age < ADVERT_COOLDOWN:
        return items, ("no contacts - an advert was sent %ds ago, waiting %ds"
                       % (int(age), int(ADVERT_COOLDOWN - age)))

    _LAST_ADVERT = time.time()
    _run(["floodadv"], timeout=90)
    time.sleep(5)
    _run(["reload_contacts"], timeout=40)

    items2, err2 = _destinations_once()
    if any(i.get("kind") == "contact" for i in items2):
        return _stamp_roles(items2), err2
    return items2, ("no contacts after a flood advert - the radio may have "
                    "no neighbours in range")


# --- contact roles ---------------------------------------------------------
# The contacts table has a TYPE column: CLI = a node (companion/handheld),
# REP = a repeater, ROOM = a room server. Real line, escapes included:
#   'OptimusPrime\x1b[34G CLI  beb9019e697d  11h ab,ac'
# The escape is a cursor move to a fixed column, so everything after it begins
# at TYPE. Falls back to "<TYPE><spaces><hex key>", which a contact NAME cannot
# fake (names like "Death Star Repeater" must not be mistaken for repeaters).
_ROLE_TYPES = {"REP": "repeater", "REPEATER": "repeater", "ROUTER": "repeater",
               "ROOM": "room"}
def strip_ansi(text):
    """Strip terminal escape sequences. The CLI emits cursor escapes to align
    its columns, and they can land inside a short contact name."""
    import re
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text or "")


def _contact_roles():
    """name -> 'node' | 'repeater' | 'room', from the TYPE column."""
    import re
    esc = re.compile(r"\x1b\[[0-9]*G")
    head = re.compile(r"^\s*(CLI|REP|REPEATER|ROUTER|ROOM|SEN|CHAT)\b", re.I)
    fallback = re.compile(r"\s(CLI|REP|REPEATER|ROUTER|ROOM)\s{1,}[0-9a-fA-F]{8,}")
    roles = {}
    ok, out = _run(["contacts"], timeout=40)
    if not ok:
        return roles
    for raw in (out or "").splitlines():
        if not raw.strip() or raw.startswith(("INFO", "WARNING", "ERROR")):
            continue
        low = raw.lower()
        if "contacts in device" in low:
            continue
        m = esc.search(raw)
        name = strip_ansi(raw[:m.start()] if m else raw.split("  ")[0]).strip()
        if not name:
            continue
        hit = head.match(strip_ansi(raw[m.end():])) if m else None
        if not hit:
            fb = fallback.search(strip_ansi(raw))
            hit = fb
        code = (hit.group(1).upper() if hit else "")
        roles[name] = _ROLE_TYPES.get(code, "node")
    return roles


def _stamp_roles(items):
    """Turn kind='contact' into node/repeater/room using the TYPE column."""
    roles = _contact_roles()
    if not roles:
        return items
    for it in items:
        if it.get("kind") == "contact":
            it["kind"] = roles.get(it.get("name", ""), "node")
    return items


# --- inbox -----------------------------------------------------------------
# sync_msgs returns the device's message queue. Real format (VERIFIED):
#   'public (7): KQ4EZN T-Deck: *emoji*'      <- channel: sender is inside the text
#   'OptimusPrime (0): Hello'                 <- direct message
# The flag in parentheses is a device value. json_msgs is NOT supported by this
# firmware, so this is deliberately a text parse - built from real output.
_MSG_RE = None


def messages(limit=60):
    """Return (messages, error). Each: {scope, flag, sender, text, raw}."""
    global _MSG_RE
    import re
    if _MSG_RE is None:
        _MSG_RE = re.compile(r"^(?P<scope>[^:()]{1,40}?)\s*\((?P<flag>[^)]*)\)\s*:\s*(?P<text>.*)$")
    ok, out = _run(["sync_msgs"], timeout=90)
    if not ok:
        return [], strip_ansi((out or "").strip())[-200:]
    msgs = []
    for raw in (out or "").splitlines():
        line = strip_ansi(raw).rstrip()
        if not line.strip() or line.lstrip().startswith(("INFO", "WARNING", "ERROR")):
            continue
        m = _MSG_RE.match(line.strip())
        if not m:
            continue
        scope = m.group("scope").strip()
        text = m.group("text").strip()
        sender = None
        if scope.lower().startswith(("public", "chan", "priv")):
            if ": " in text:
                sender, text = text.split(": ", 1)
        msgs.append({"scope": scope, "flag": m.group("flag").strip(),
                     "sender": sender, "text": text.strip(), "raw": line.strip()[:300]})
    return msgs[-limit:], None
