#!/usr/bin/env python3
"""MeshCore sender - a local web UI to send a message to one contact, several
contacts, or the public channel over BLE.

Stdlib only, on purpose: no pip install step, so it runs on this Mac as-is.
Transport is the `meshtastic` CLI (the Python lib is not installed for python3).

Run:  python3 src/server.py            # http://127.0.0.1:8788
Env:  PORT, DATA_DIR, APP_BASE_URL
"""
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
PUBLIC = os.path.join(ROOT, "public")
CONFIG = os.path.join(DATA, "config.json")   # readable, never secrets
AUTH = os.path.join(DATA, "auth.json")       # passphrase hash, mode 0600
CLI = os.environ.get("MESHTASTIC_CLI", "meshtastic")
PORT = int(os.environ.get("PORT", "8788"))
TIMEOUT = int(os.environ.get("SEND_TIMEOUT", "45"))

_sessions = {}          # token -> {"exp": ts, "csrf": str}
_lock = threading.Lock()
_nodes_cache = {"nodes": [], "at": 0, "error": None}
_load_ok = False        # see _load_config: refuse to save before load

# ---- range-test state -------------------------------------------------------
_range = {
    "running": False,
    "target": None,
    "prefix": "ping",
    "interval": 30,
    "sent": 0,
    "acked": 0,
    "log": [],          # list of {"seq":N,"ts":"HH:MM:SS","acked":bool,"rtt_ms":N,"detail":str}
    "thread": None,
}
_range_lock = threading.Lock()
_RANGE_LOG_MAX = 200


def _range_loop(target, prefix, interval):
    """Background thread: send one DM per tick, record ACK."""
    import transport_meshcore as mc
    seq = 0
    while True:
        with _range_lock:
            if not _range["running"]:
                break
        seq += 1
        ts = time.strftime("%H:%M:%S")
        text = "%s %d [%s]" % (prefix, seq, ts)
        ok, rtt, detail = mc.send_one_ack(target, text, timeout=45)
        entry = {"seq": seq, "ts": ts, "acked": ok, "rtt_ms": rtt, "detail": detail}
        with _range_lock:
            _range["sent"] += 1
            if ok:
                _range["acked"] += 1
            _range["log"].append(entry)
            if len(_range["log"]) > _RANGE_LOG_MAX:
                _range["log"] = _range["log"][-_RANGE_LOG_MAX:]
            if not _range["running"]:
                break
        # sleep interval in 1s increments so stop is responsive
        for _ in range(interval):
            time.sleep(1)
            with _range_lock:
                if not _range["running"]:
                    return


# ---------------------------------------------------------------- config store
def _load_config():
    """Load the store. Sets _load_ok so save() can refuse to clobber it."""
    global _load_ok, _config
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(CONFIG):
        with open(CONFIG) as fh:
            _config = json.load(fh)
    else:
        _config = {"default_target": "public", "known_contacts": []}
    _load_ok = True
    return _config


def _save_config(cfg):
    """A store must refuse to write before it has loaded, or a stray save
    writes defaults over the user's configuration."""
    if not _load_ok:
        raise RuntimeError("config store not loaded; refusing to save")
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cfg, fh, indent=2, sort_keys=True)
    os.replace(tmp, CONFIG)
    return True


def _now():
    import time
    return time.strftime("%H:%M:%S")


def _auth_set():
    return os.path.exists(AUTH)


def _auth_create(passphrase):
    os.makedirs(DATA, exist_ok=True)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt.encode(), 200_000).hex()
    fd = os.open(AUTH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # mode at create
    with os.fdopen(fd, "w") as fh:
        json.dump({"salt": salt, "digest": digest}, fh)
    return True


def _auth_check(passphrase):
    if not _auth_set():
        return False
    with open(AUTH) as fh:
        rec = json.load(fh)
    digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), rec["salt"].encode(), 200_000).hex()
    return hmac.compare_digest(digest, rec["digest"])


# -------------------------------------------------------------------- radio io
def cli(args, timeout=TIMEOUT):
    """Kept for reference; the CLI subprocess approach is superseded by the SDK transport."""
    raise NotImplementedError("CLI transport removed; use transport_meshcore SDK functions directly")


def radio_nodes(force=False):
    """Destinations for the picker: MeshCore channels, then contacts."""
    import transport_meshcore as mc
    now = time.time()
    if not force and _nodes_cache["nodes"] and now - _nodes_cache["at"] < 60:
        return _nodes_cache
    items, err = mc.destinations()
    _nodes_cache.update({"nodes": items, "at": now, "error": err})
    return _nodes_cache


def radio_probe():
    """Three-way diagnosis: CLI missing / nothing advertising / connect refused."""
    import transport_meshcore as mc
    return mc.probe()


def send(targets, text):
    """Send to each destination. Returns one result per target."""
    import transport_meshcore as mc
    return mc.send(targets, text)


# ---------------------------------------------------------------------- routes
class Handler(BaseHTTPRequestHandler):
    server_version = "meshtastic-sender"

    def log_message(self, fmt, *args):        # quieter, and no secrets in logs
        print("%s - %s" % (self.address_string(), fmt % args))

    # -- helpers
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code, path):
        if not os.path.exists(path):
            self._json(404, {"error": "missing asset %s" % os.path.basename(path)})
            return
        with open(path, "rb") as fh:
            body = fh.read()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")       # shell is never cached hard
        self.end_headers()
        self.wfile.write(body)

    def _session(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            tok = SimpleCookie(raw).get("ms_session")
        except Exception:                                    # noqa: BLE001
            return None
        if not tok:
            return None
        with _lock:
            rec = _sessions.get(tok.value)
            if rec and rec["exp"] > time.time():
                return rec
            _sessions.pop(tok.value, None)
        return None

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:                                    # noqa: BLE001
            return {}

    # -- GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._html(200, os.path.join(PUBLIC, "index.html"))
        elif path == "/api/session":
            rec = self._session()
            self._json(200, {"first_run": not _auth_set(),
                             "authed": bool(rec),
                             "csrf": rec["csrf"] if rec else None})
        elif path == "/api/health":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            info = radio_nodes()
            _e = (info.get("error") or "").lower()
            # Empty contacts is NOT "radio down": the link answered, it just has
            # nothing cached. Only a real connection failure is unreachable.
            _reachable = (not info.get("error")) or ("no contacts" in _e)
            self._json(200, {"radio_ok": _reachable,
                             "radio_partial": bool(info.get("error")) and _reachable,
                             "radio_error": info["error"],
                             "nodes": len(info["nodes"])})
        elif path == "/api/messages":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            import json as _json, os as _os
            _p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                               "data", "inbox.json")
            try:
                _store = _json.load(open(_p))
            except Exception:
                _store = []
            # Merge live in-memory inbox (subscription events not yet persisted)
            try:
                from transport_meshcore import _inbox as _live, _inbox_lock as _ilock
                with _ilock:
                    _live_copy = list(_live)
                # Dedup by (scope, text) — handles old CLI format vs new SDK format
                _seen = set(
                    ((x.get("scope") or ""), (x.get("text") or "").strip())
                    for x in _store
                )
                _added = [_m for _m in _live_copy
                          if ((_m.get("scope") or ""), (_m.get("text") or "").strip())
                          not in _seen]
                if _added:
                    _store.extend(_added)
                    _store = _store[-300:]
                    try:
                        _os.makedirs(_os.path.dirname(_p), exist_ok=True)
                        _json.dump(_store, open(_p, "w"))
                    except Exception:
                        pass
            except ImportError:
                pass
            self._json(200, {"messages": _store, "error": None})
        elif path == "/api/advert":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            import os as _os, subprocess as _sp
            mode = (payload or {}).get("mode") or "flood"
            cmd = "zerohop" if mode == "zero" else "floodadv"
            addr = _os.environ.get("MESHCORE_ADDR",
                                   "DDE75E06-4BF2-DB42-7B69-B29FE29CB836")
            _p = _sp.run(["meshcore-cli", "-a", addr, cmd],
                         capture_output=True, text=True, timeout=120)
            _out = (_p.stdout + _p.stderr).strip()
            self._json(200, {"ok": "Advert sent" in _out, "mode": mode,
                             "detail": _out[-200:]})
        elif path == "/api/range/status":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            with _range_lock:
                snap = {k: _range[k] for k in
                        ("running", "target", "prefix", "interval", "sent", "acked", "log")}
            self._json(200, snap)
        elif path == "/api/nodes":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            info = radio_nodes(force=self._qs_force())
            self._json(200, {"nodes": info["nodes"], "error": info["error"]})
        else:
            self._json(404, {"error": "no such route"})      # never the SPA html

    def _qs_force(self):
        return "force=1" in (urlparse(self.path).query or "")

    # -- POST
    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        if path == "/api/setup":
            if _auth_set():
                self._json(409, {"error": "already configured"})
                return
            pw = (body.get("passphrase") or "").strip()
            if len(pw) < 8:
                self._json(400, {"error": "passphrase must be at least 8 characters"})
                return
            _auth_create(pw)
            _load_config()
            self._json(200, {"ok": True})
        elif path == "/api/login":
            if not _auth_set():
                self._json(428, {"error": "not_configured"})
                return
            if not _auth_check((body.get("passphrase") or "")):
                time.sleep(1.0)                              # crude rate limit
                self._json(401, {"error": "wrong passphrase"})
                return
            tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            with _lock:
                _sessions[tok] = {"exp": time.time() + 12 * 3600, "csrf": csrf}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie",
                             "ms_session=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200" % tok)
            payload = json.dumps({"ok": True, "csrf": csrf}).encode()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif path == "/api/messages/fetch":
            if not _auth_set():
                self._json(428, {"error": "not_configured"})
                return
            rec = self._session()
            if not rec:
                self._json(401, {"error": "unauthorized"})
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", rec["csrf"]):
                self._json(403, {"error": "bad csrf token"})
                return
            import json as _json, os as _os
            _p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                               "data", "inbox.json")
            try:
                _store = _json.load(open(_p))
            except Exception:
                _store = []
            from transport_meshcore import messages as _msgs
            _new, _e = _msgs()
            _seen = set(
                ((_m.get("scope") or ""), (_m.get("text") or "").strip())
                for _m in _store
            )
            for _m in _new:
                if ((_m.get("scope") or ""), (_m.get("text") or "").strip()) not in _seen:
                    _m.setdefault("at", _now())
                    _store.append(_m)
            _store = _store[-300:]
            try:
                _os.makedirs(os.path.dirname(_p), exist_ok=True)
                _json.dump(_store, open(_p, "w"))
            except Exception:
                pass
            self._json(200, {"messages": _store, "fetched": len(_new), "error": _e})
        elif path == "/api/range/start":
            if not _auth_set():
                self._json(428, {"error": "not_configured"})
                return
            rec = self._session()
            if not rec:
                self._json(401, {"error": "unauthorized"})
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", rec["csrf"]):
                self._json(403, {"error": "bad csrf token"})
                return
            target = (body.get("target") or "").strip()
            prefix = (body.get("prefix") or "ping").strip()
            try:
                interval = max(5, min(300, int(body.get("interval") or 30)))
            except (ValueError, TypeError):
                interval = 30
            import re as _re
            if not _re.fullmatch(r"[A-Za-z0-9 _./#@-]{1,60}", target) or target.startswith("-"):
                self._json(400, {"error": "invalid target name"})
                return
            if not _re.fullmatch(r"[A-Za-z0-9_./#@-]{1,40}", prefix) or prefix.startswith("-"):
                self._json(400, {"error": "invalid prefix"})
                return
            with _range_lock:
                if _range["running"]:
                    self._json(409, {"error": "range test already running"})
                    return
                _range.update({"running": True, "target": target, "prefix": prefix,
                                "interval": interval, "sent": 0, "acked": 0, "log": [],
                                "_init_note": "reloading contacts before first ping"})
                t = threading.Thread(target=_range_loop, args=(target, prefix, interval),
                                     daemon=True)
                _range["thread"] = t
            t.start()
            self._json(200, {"ok": True, "target": target, "interval": interval})
        elif path == "/api/range/stop":
            if not _auth_set():
                self._json(428, {"error": "not_configured"})
                return
            rec = self._session()
            if not rec:
                self._json(401, {"error": "unauthorized"})
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", rec["csrf"]):
                self._json(403, {"error": "bad csrf token"})
                return
            with _range_lock:
                _range["running"] = False
            self._json(200, {"ok": True})
        elif path == "/api/send":
            if not _auth_set():
                self._json(428, {"error": "not_configured"})
                return
            rec = self._session()
            if not rec:
                self._json(401, {"error": "unauthorized"})
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", rec["csrf"]):
                self._json(403, {"error": "bad csrf token"})
                return
            text = (body.get("text") or "").strip()
            targets = body.get("targets") or []
            if not isinstance(targets, list):
                targets = [targets]
            targets = [t for t in targets if t]
            if not text:
                self._json(400, {"error": "message is empty"})
                return
            if not targets:
                self._json(400, {"error": "pick a destination"})
                return
            import re as _re
            for t in targets:                                # validate at the boundary
                # MeshCore ids: "chan:<digit>" or "dm:<safe name>"
                # Reject anything starting with '-' to prevent flag injection.
                if _re.fullmatch(r"chan:\d+", t):
                    pass
                elif _re.fullmatch(r"dm:[A-Za-z0-9 _./#@-]{1,60}", t) and not t[3:].startswith("-"):
                    pass
                else:
                    self._json(400, {"error": "bad destination: %s" % t})
                    return
            results = send(targets, text)
            ok = all(r["ok"] for r in results)
            # persist sent messages so they survive a page reload
            if ok:
                import json as _json, os as _os
                _p = _os.path.join(ROOT, "data", "inbox.json")
                try:
                    _store = _json.load(open(_p))
                except Exception:
                    _store = []
                ts = _now()
                _result_map = {r["target"]: r for r in results}
                for t in targets:
                    scope = ("public" if t == "chan:0"
                             else "chan%s" % t.split(":",1)[1] if t.startswith("chan:")
                             else t.split(":",1)[1] if ":" in t else t)
                    raw = "out|%s|%s" % (scope, text)
                    _acked = _result_map.get(scope, {}).get("acked", False)
                    if not any(m.get("raw") == raw for m in _store):
                        _store.append({"scope": scope, "sender": None, "text": text,
                                       "at": ts, "direction": "out", "raw": raw,
                                       "acked": _acked})
                _store = _store[-300:]
                try:
                    _os.makedirs(os.path.dirname(_p), exist_ok=True)
                    _json.dump(_store, open(_p, "w"))
                except Exception:
                    pass
            self._json(200 if ok else 502,
                       {"ok": ok, "results": results,
                        "hint": None if ok else "check the radio is powered and not "
                                               "connected to the phone app"})
        else:
            self._json(404, {"error": "no such route"})


def main():
    _load_config()
    if not _auth_set():
        print("first run: open http://127.0.0.1:%d/ and set a passphrase" % PORT)
    print("meshcore-sender on http://127.0.0.1:%d  (data: %s)" % (PORT, DATA))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
