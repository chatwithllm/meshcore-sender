#!/usr/bin/env python3
"""MeshCore sender - a local web UI to send a message to one contact, several
contacts, or a channel over BLE.

Stdlib only, on purpose: no pip install step, so it runs on this Mac as-is.
Transport is handled by the MeshCore Python SDK through transport_meshcore.py.

Run:  python3 src/server.py            # http://127.0.0.1:8788
Env:  PORT, DATA_DIR, MESHCORE_ADDR, MESHCORE_TIMEOUT
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
PUBLIC = os.path.join(ROOT, "public")
CONFIG = os.path.join(DATA, "config.json")   # readable, never secrets
AUTH = os.path.join(DATA, "auth.json")       # passphrase hash, mode 0600
AI_CONFIG = os.path.join(DATA, "ai.json")    # optional LLM provider key, mode 0600
COMMAND_HISTORY = os.path.join(DATA, "command_history.json")
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
    "targets": [],
    "prefix": "ping",
    "interval": 30,
    "sent": 0,
    "acked": 0,
    "per_target": {},
    "log": [],          # list of {"seq":N,"ts":"HH:MM:SS","acked":bool,"rtt_ms":N,"detail":str}
    "thread": None,
    "next_due_at": None,
    "started_by": None,
}
_range_lock = threading.Lock()
_RANGE_LOG_MAX = 200

_cmd_lock = threading.Lock()
_commands = {
    "pending": None,
    "history": [],
}
_CMD_HISTORY_MAX = 80


def _validate_range_targets(target_inputs):
    import re as _re
    targets = []
    for target in target_inputs:
        target = str(target or "").strip()
        if _re.fullmatch(r"chan:\d+", target):
            pass
        elif _re.fullmatch(r"dm:[A-Za-z0-9 _./#@-]{1,60}", target) and not target[3:].startswith("-"):
            pass
        elif _re.fullmatch(r"[A-Za-z0-9 _./#@-]{1,60}", target) and not target.startswith("-"):
            target = "dm:%s" % target
        else:
            raise ValueError("invalid target")
        if target not in targets:
            targets.append(target)
    if not targets:
        raise ValueError("invalid target")
    return targets


def _validate_range_prefix(prefix):
    import re as _re
    prefix = (prefix or "ping").strip()
    if not _re.fullmatch(r"[A-Za-z0-9_./#@-]{1,40}", prefix) or prefix.startswith("-"):
        raise ValueError("invalid prefix")
    return prefix


def _range_start(targets, prefix="ping", interval=30, started_by="you"):
    targets = _validate_range_targets(targets)
    prefix = _validate_range_prefix(prefix)
    try:
        interval = max(5, min(300, int(interval or 30)))
    except (ValueError, TypeError):
        interval = 30
    with _range_lock:
        if _range["running"]:
            return None, "range test already running"
        _range.update({"running": True, "target": targets[0], "targets": targets,
                        "prefix": prefix, "interval": interval, "sent": 0,
                        "acked": 0, "per_target": {}, "log": [],
                        "next_due_at": time.time(),
                        "started_by": (started_by or "you"),
                        "_init_note": "reloading contacts before first ping"})
        t = threading.Thread(target=_range_loop, args=(targets, prefix, interval),
                             daemon=True)
        _range["thread"] = t
    t.start()
    return {"ok": True, "target": targets[0], "targets": targets,
            "prefix": prefix, "interval": interval,
            "started_by": (started_by or "you")}, None


def _range_stop():
    with _range_lock:
        was_running = bool(_range["running"])
        _range["running"] = False
        _range["next_due_at"] = None
    return {"ok": True, "was_running": was_running}


def _range_snapshot():
    with _range_lock:
        snap = {k: _range[k] for k in
                ("running", "target", "prefix", "interval", "sent", "acked",
                 "log", "next_due_at", "targets", "per_target", "started_by")}
        snap["server_now"] = time.time()
    return snap


def _range_loop(_targets, prefix, interval):
    """Background thread: send one range-test message per tick."""
    import transport_meshcore as mc
    seq = 0
    next_at = time.monotonic()
    with _range_lock:
        _range["next_due_at"] = time.time()
    while True:
        while True:
            delay = next_at - time.monotonic()
            if delay <= 0:
                break
            time.sleep(min(1, delay))
            with _range_lock:
                if not _range["running"]:
                    return
        with _range_lock:
            if not _range["running"]:
                break
            targets = list(_range.get("targets") or [])
        if not targets:
            with _range_lock:
                _range["running"] = False
                _range["next_due_at"] = None
            return
        seq += 1
        for target in targets:
            with _range_lock:
                if not _range["running"]:
                    return
            ts = time.strftime("%H:%M:%S")
            text = "%s %d [%s]" % (prefix, seq, ts)
            try:
                if target.startswith("chan:"):
                    results = mc.send([target], text)
                    ok = all(r.get("ok") for r in results)
                    acked = ok
                    rtt = 0
                    detail = "channel broadcast sent" if ok else (
                        (results[0].get("out") if results else None) or "send failed")
                else:
                    contact_name = target.split(":", 1)[1] if target.startswith("dm:") else target
                    ack_timeout = max(3, min(TIMEOUT, 20, interval - 2))
                    acked, rtt, detail = mc.send_one_ack(contact_name, text, timeout=ack_timeout)
                    ok = bool(acked)
            except Exception as exc:  # noqa: BLE001 - keep scheduled test alive
                ok = False
                acked = False
                rtt = 0
                detail = str(exc) or "send failed"
            entry = {"seq": seq, "target": target, "ts": ts, "acked": acked,
                     "rtt_ms": rtt, "detail": detail}
            with _range_lock:
                _range["sent"] += 1
                stat = _range["per_target"].setdefault(target, {"sent": 0, "acked": 0})
                stat["sent"] += 1
                if ok:
                    _range["acked"] += 1
                    stat["acked"] += 1
                _range["log"].append(entry)
                if len(_range["log"]) > _RANGE_LOG_MAX:
                    _range["log"] = _range["log"][-_RANGE_LOG_MAX:]
                if not _range["running"]:
                    break
        next_at += interval
        with _range_lock:
            if _range["running"]:
                _range["next_due_at"] = time.time() + max(0, next_at - time.monotonic())


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


def _command_config():
    cfg = _load_config()
    rc = cfg.setdefault("remote_commands", {})
    rc.setdefault("enabled", False)
    rc.setdefault("controllers", [])
    rc.setdefault("favorites", [])
    return rc


def _clean_name_list(items, limit=20):
    clean = []
    if not isinstance(items, list):
        items = []
    for item in items or []:
        val = str(item or "").strip()
        if val and val not in clean:
            clean.append(val)
    return clean[:limit]


def _save_command_config(enabled, controllers, favorites=None):
    cfg = _load_config()
    old = cfg.get("remote_commands") or {}
    favs = old.get("favorites", [])
    if favorites is not None:
        favs = favorites
    cfg["remote_commands"] = {
        "enabled": bool(enabled),
        "controllers": _clean_name_list(controllers, 20),
        "favorites": _clean_name_list(favs, 30),
    }
    _save_config(cfg)
    return cfg["remote_commands"]


def _load_ai_config():
    if not os.path.exists(AI_CONFIG):
        return {"enabled": False, "provider": "openai", "model": "", "api_key": ""}
    try:
        with open(AI_CONFIG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except Exception:  # noqa: BLE001 - corrupt AI config should not break the app
        data = {}
    return {
        "enabled": bool(data.get("enabled")),
        "provider": str(data.get("provider") or "openai").strip() or "openai",
        "model": str(data.get("model") or "").strip(),
        "api_key": str(data.get("api_key") or ""),
    }


def _public_ai_config():
    cfg = _load_ai_config()
    return {
        "enabled": bool(cfg.get("enabled")),
        "provider": cfg.get("provider") or "openai",
        "model": cfg.get("model") or "",
        "key_saved": bool(cfg.get("api_key")),
        "mode": "parse_only",
        "note": "AI parser can propose intents; deterministic confirmation still controls execution.",
    }


def _save_ai_config(enabled=None, provider=None, model=None, api_key=None, clear_key=False):
    import re as _re
    cfg = _load_ai_config()
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if provider is not None:
        provider = str(provider or "").strip().lower()
        if provider not in ("openai", "claude", "google", "grok", "deepseek", "other"):
            raise ValueError("unsupported provider")
        cfg["provider"] = provider
    if model is not None:
        model = str(model or "").strip()
        if model and not _re.fullmatch(r"[A-Za-z0-9_.:/@#+-]{1,80}", model):
            raise ValueError("invalid model")
        cfg["model"] = model
    if clear_key:
        cfg["api_key"] = ""
    elif api_key is not None:
        api_key = str(api_key or "").strip()
        if api_key:
            cfg["api_key"] = api_key
    if cfg.get("enabled") and not cfg.get("api_key"):
        raise ValueError("save an API key before enabling AI")
    os.makedirs(DATA, exist_ok=True)
    tmp = AI_CONFIG + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, sort_keys=True)
    os.replace(tmp, AI_CONFIG)
    try:
        os.chmod(AI_CONFIG, 0o600)
    except OSError:
        pass
    return _public_ai_config()


def _load_command_history():
    if not os.path.exists(COMMAND_HISTORY):
        return []
    try:
        with open(COMMAND_HISTORY, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)][-_CMD_HISTORY_MAX:]
    except Exception:  # noqa: BLE001 - command history is diagnostics only
        pass
    return []


def _save_command_history(history):
    try:
        os.makedirs(DATA, exist_ok=True)
        tmp = COMMAND_HISTORY + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(list(history or [])[-_CMD_HISTORY_MAX:], fh, indent=2, sort_keys=True)
        os.replace(tmp, COMMAND_HISTORY)
    except Exception:  # noqa: BLE001 - logging must not break radio commands
        pass


def _ensure_command_history_loaded():
    with _cmd_lock:
        if not _commands.get("history"):
            _commands["history"] = _load_command_history()


def _cmd_log(kind, text, source=None, detail=None):
    _ensure_command_history_loaded()
    item = {"at": _now(), "kind": kind, "text": text}
    if source:
        item["source"] = source
    if detail:
        item["detail"] = detail
    with _cmd_lock:
        _commands["history"].append(item)
        if len(_commands["history"]) > _CMD_HISTORY_MAX:
            _commands["history"] = _commands["history"][-_CMD_HISTORY_MAX:]
        history = list(_commands["history"])
    _save_command_history(history)
    return item


def _cmd_status():
    _ensure_command_history_loaded()
    rc = _command_config()
    with _cmd_lock:
        pending = dict(_commands["pending"]) if _commands["pending"] else None
        history = list(_commands["history"])
    return {"enabled": rc.get("enabled", False),
            "controllers": rc.get("controllers", []),
            "pending": pending,
            "history": history}


def _target_label(target):
    info = radio_nodes()
    for item in info.get("nodes", []):
        if item.get("id") == target:
            return item.get("name") or target
    return target.replace("dm:", "")


def _find_command_targets(query):
    q = (query or "").strip().lower()
    if not q:
        return []
    info = radio_nodes()
    matches = []
    for item in info.get("nodes", []):
        name = str(item.get("name") or "")
        ident = str(item.get("id") or "")
        hay = " ".join([name, ident, item.get("kind") or ""]).lower()
        if q == name.lower() or q == ident.lower() or q in hay:
            matches.append({"id": ident, "name": name or ident,
                            "kind": item.get("kind") or "node"})
    return matches[:8]


def _ai_available_targets():
    info = radio_nodes()
    targets = []
    for item in info.get("nodes", [])[:120]:
        name = str(item.get("name") or "").strip()
        ident = str(item.get("id") or "").strip()
        if not name or not ident:
            continue
        targets.append({"name": name, "id": ident, "kind": item.get("kind") or "node"})
    return targets


def _ai_default_model(provider):
    return {
        "openai": "gpt-4o-mini",
        "claude": "claude-3-5-haiku-latest",
        "google": "gemini-1.5-flash",
        "grok": "grok-2-latest",
        "deepseek": "deepseek-chat",
        "other": "gpt-4o-mini",
    }.get(provider, "gpt-4o-mini")


def _ai_prompt(text):
    targets = _ai_available_targets()
    target_lines = [
        "- %s | %s | %s" % (t["name"], t["id"], t["kind"])
        for t in targets[:80]
    ]
    system = (
        "You parse MeshCore radio controller messages into JSON only. "
        "Never execute actions. Never invent targets. "
        "Allowed actions: status, range_start, range_stop, cancel, unknown. "
        "Treat phrases like 'ping TARGET every 30 sec', 'ping TARGET in 30 sec', "
        "'check TARGET every half minute', or 'keep checking TARGET' as range_start. "
        "For range_start, return target_queries as an array of names or ids from the provided targets, "
        "interval_sec as an integer 5-300, and prefix if clearly requested, else ping. "
        "For status/range_stop/cancel, return only the action. "
        "If the request is not about range testing, command status, stopping, or cancelling, return unknown. "
        "Output compact JSON with keys: action, target_queries, interval_sec, prefix, reason."
    )
    user = (
        "Available targets:\n%s\n\nController message:\n%s" %
        ("\n".join(target_lines) if target_lines else "(none)", text)
    )
    return system, user


def _extract_json_object(text):
    import re as _re
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.I).strip()
        raw = _re.sub(r"\s*```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def _http_json(url, headers, payload, timeout=25, attempts=2):
    import socket as _socket
    import urllib.error as _urlerr
    import urllib.request as _urlreq
    data = json.dumps(payload).encode("utf-8")
    last_error = None
    for attempt in range(max(1, int(attempts or 1))):
        req = _urlreq.Request(url, data=data, headers=headers, method="POST")
        try:
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except _urlerr.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            last_error = RuntimeError("AI provider HTTP %s: %s" % (exc.code, body))
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt + 1 >= attempts:
                raise last_error from exc
        except (_urlerr.URLError, TimeoutError, _socket.timeout) as exc:
            last_error = RuntimeError("AI provider network error: %s" % exc)
            if attempt + 1 >= attempts:
                raise last_error from exc
        time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError("AI provider request failed")


def _ai_provider_call(cfg, system, user):
    provider = (cfg.get("provider") or "openai").lower()
    key = cfg.get("api_key") or ""
    model = cfg.get("model") or _ai_default_model(provider)
    if not key:
        raise RuntimeError("AI API key is not saved")
    if provider in ("openai", "grok", "deepseek", "other"):
        base = {
            "openai": "https://api.openai.com/v1",
            "grok": "https://api.x.ai/v1",
            "deepseek": "https://api.deepseek.com",
            "other": os.environ.get("MESHCORE_AI_BASE_URL", "https://api.openai.com/v1"),
        }.get(provider)
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if provider in ("openai", "deepseek"):
            body["response_format"] = {"type": "json_object"}
        data = _http_json(base.rstrip("/") + "/chat/completions", {
            "Authorization": "Bearer %s" % key,
            "Content-Type": "application/json",
        }, body)
        return (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    if provider == "claude":
        data = _http_json("https://api.anthropic.com/v1/messages", {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }, {
            "model": model,
            "max_tokens": 500,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        })
        parts = data.get("content") or []
        return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    if provider == "google":
        from urllib.parse import quote as _quote
        data = _http_json(
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" %
            (_quote(model, safe=""), _quote(key, safe="")),
            {"Content-Type": "application/json"},
            {
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
                "contents": [{"role": "user", "parts": [{"text": system + "\n\n" + user}]}],
            })
        cand = (data.get("candidates") or [{}])[0]
        parts = ((cand.get("content") or {}).get("parts") or [])
        return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    raise RuntimeError("unsupported provider")


def _ai_interpret_command(text):
    cfg = _load_ai_config()
    if not cfg.get("enabled"):
        return None, "disabled"
    system, user = _ai_prompt(text)
    raw = _ai_provider_call(cfg, system, user)
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        raise RuntimeError("AI response was not an object")
    action = str(data.get("action") or "unknown").strip().lower()
    if action not in ("status", "range_start", "range_stop", "cancel", "unknown"):
        action = "unknown"
    try:
        interval = int(data.get("interval_sec") or 30)
    except (TypeError, ValueError):
        interval = 30
    prefix = _validate_range_prefix(data.get("prefix") or "ping")
    queries = data.get("target_queries") or []
    if isinstance(queries, str):
        queries = [queries]
    queries = [str(q or "").strip() for q in queries if str(q or "").strip()][:5]
    return {
        "action": action,
        "target_queries": queries,
        "interval": max(5, min(300, interval)),
        "prefix": prefix,
        "reason": str(data.get("reason") or "").strip()[:160],
    }, None


def _options_from_ai_intent(intent):
    action = (intent or {}).get("action")
    if action == "status":
        return "status", []
    if action == "cancel":
        return "cancel", []
    if action == "range_stop":
        return "pending", [{"action": "range_stop"}]
    if action == "range_start":
        options = []
        seen = set()
        for query in intent.get("target_queries") or []:
            for match in _find_command_targets(query):
                target = match.get("id")
                if target and target not in seen:
                    seen.add(target)
                    options.append({"action": "range_start",
                                    "targets": [target],
                                    "interval": intent.get("interval") or 30,
                                    "prefix": intent.get("prefix") or "ping"})
                if len(options) >= 5:
                    break
            if len(options) >= 5:
                break
        return "pending", options
    return "unknown", []


def _command_source(message):
    return {
        "scope": str(message.get("scope") or ""),
        "sender": str(message.get("sender") or ""),
        "raw": str(message.get("raw") or ""),
    }


def _source_key(source):
    sender = (source.get("sender") or "").strip()
    scope = (source.get("scope") or "").strip()
    return sender or scope


def _controller_allowed(message):
    rc = _command_config()
    if not rc.get("enabled"):
        return False
    allowed = [str(x).strip().lower() for x in rc.get("controllers", []) if str(x).strip()]
    if not allowed:
        return False
    vals = [str(message.get("sender") or "").strip().lower(),
            str(message.get("scope") or "").strip().lower()]
    return any(v and v in allowed for v in vals)


def _reply_target_for_message(message):
    scope = str(message.get("scope") or "").strip()
    sender = str(message.get("sender") or "").strip()
    info = radio_nodes()
    lower_scope = scope.lower()
    if lower_scope in ("public", "public channel"):
        return "chan:0"
    for item in info.get("nodes", []):
        item_id = item.get("id") or ""
        name = str(item.get("name") or "")
        if item_id.startswith("chan:") and name.lower() == lower_scope:
            return item_id
    if sender:
        for item in info.get("nodes", []):
            if item.get("id", "").startswith("dm:") and str(item.get("name") or "").lower() == sender.lower():
                return item.get("id")
    if scope and scope.lower() not in ("public", "public channel") and not scope.lower().startswith("chan"):
        return "dm:%s" % scope
    return None


def _append_command_reply_to_inbox(message, text, ok, results=None):
    scope = str(message.get("scope") or message.get("sender") or "remote command").strip()
    if not scope:
        scope = "remote command"
    item = {
        "scope": scope,
        "sender": None,
        "text": text,
        "at": _now(),
        "direction": "out",
        "raw": "cmdout|%s|%s|%d" % (scope, text, int(time.time() * 1000)),
        "acked": bool(ok),
        "command_reply": True,
    }
    first = (results or [{}])[0] if isinstance(results, list) and results else {}
    for key in ("route_hops", "route_mode", "route_path"):
        if key in first:
            item[key] = first.get(key)
    path = os.path.join(DATA, "inbox.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            store = json.load(fh)
        if not isinstance(store, list):
            store = []
    except Exception:  # noqa: BLE001 - command history should never break replies
        store = []
    store.append(item)
    store = store[-300:]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(store, fh)
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        _cmd_log("reply_store_failed", text, _source_key(_command_source(message)), str(exc))


def _send_command_reply(message, text):
    target = _reply_target_for_message(message)
    if not target:
        _cmd_log("reply_failed", text, _source_key(_command_source(message)), "no reply target")
        return False
    try:
        results = send([target], text)
        ok = all(r.get("ok") for r in results)
        _append_command_reply_to_inbox(message, text, ok, results)
        _cmd_log("reply", text, _source_key(_command_source(message)), "sent" if ok else "send failed")
        return ok
    except Exception as exc:  # noqa: BLE001
        _append_command_reply_to_inbox(message, text, False)
        _cmd_log("reply_failed", text, _source_key(_command_source(message)), str(exc))
        return False


def _message_key(message):
    raw = str(message.get("raw") or "").strip()
    if raw:
        return ("raw", raw)
    return ("msg",
            str(message.get("direction") or ""),
            str(message.get("scope") or ""),
            str(message.get("sender") or ""),
            str(message.get("text") or "").strip(),
            str(message.get("at") or ""))


def _public_message(message):
    return {k: v for k, v in message.items() if not str(k).startswith("_")}


def _range_status_text():
    snap = _range_snapshot()
    if not snap.get("running"):
        return "Range test is idle."
    sent = int(snap.get("sent") or 0)
    acked = int(snap.get("acked") or 0)
    pct = round((acked / sent) * 100) if sent else 0
    targets = ", ".join(_target_label(t) for t in (snap.get("targets") or []))
    return "Range test running: %s. %d sent, %d acked, %d%%. Interval %ss." % (
        targets or "no targets", sent, acked, pct, snap.get("interval") or "?")


def _parse_range_command(text):
    import re as _re
    s = " ".join(str(text or "").split())
    lower = s.lower()
    interval = 30
    m = _re.search(r"\b(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b", lower)
    if m:
        interval = int(m.group(1))
        s = _re.sub(r"\b\d{1,3}\s*(?:s|sec|secs|second|seconds)\b", " ", s, flags=_re.I)
    m = _re.search(r"\b(\d{1,2})\s*(?:m|min|mins|minute|minutes)\b", lower)
    if m:
        interval = int(m.group(1)) * 60
        s = _re.sub(r"\b\d{1,2}\s*(?:m|min|mins|minute|minutes)\b", " ", s, flags=_re.I)
    cleaned = _re.sub(r"\b(start|run|begin|please|range|test|ping|for|to|every|each|the)\b", " ", s, flags=_re.I)
    target_query = " ".join(cleaned.split()).strip()
    return target_query, max(5, min(300, interval))


def _parse_ping_range_command(text):
    import re as _re
    s = " ".join(str(text or "").split()).strip()
    if not _re.search(r"\b(ping|check|checking)\b", s, flags=_re.I):
        return None, None
    interval = 30
    m = _re.search(r"\b(?:in|every|each)\s+(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b", s, flags=_re.I)
    if m:
        interval = int(m.group(1))
        s = _re.sub(r"\b(?:in|every|each)\s+\d{1,3}\s*(?:s|sec|secs|second|seconds)\b", " ", s, flags=_re.I)
    else:
        m = _re.search(r"\b(?:in|every|each)\s+half\s+(?:a\s+)?minute\b", s, flags=_re.I)
        if m:
            interval = 30
            s = _re.sub(r"\b(?:in|every|each)\s+half\s+(?:a\s+)?minute\b", " ", s, flags=_re.I)
        else:
            return None, None
    cleaned = _re.sub(r"\b(can|could|you|please|start|run|begin|keep|checking|check|ping|target|node|contact|for|to|the)\b",
                      " ", s, flags=_re.I)
    target_query = " ".join(cleaned.split()).strip(" ?.,")
    if not target_query:
        return None, None
    return target_query, max(5, min(300, interval))


def _set_pending_command(source, options):
    pending = {"source": source, "options": options, "created_at": time.time(),
               "expires_at": time.time() + 300}
    with _cmd_lock:
        _commands["pending"] = pending
    return pending


def _clear_pending_command():
    with _cmd_lock:
        _commands["pending"] = None


def _format_pending_options(options, intro):
    lines = [intro]
    for idx, opt in enumerate(options, start=1):
        if opt["action"] == "range_start":
            lines.append("%d. Start range test: %s every %ss" % (
                idx, ", ".join(_target_label(t) for t in opt["targets"]), opt["interval"]))
        elif opt["action"] == "range_stop":
            lines.append("%d. Stop current range test" % idx)
    lines.append("Reply with a number, or cancel.")
    return "\n".join(lines)


def _execute_command_option(option, source_label=None):
    if option["action"] == "range_start":
        result, err = _range_start(option["targets"], option.get("prefix") or "ping",
                                   option.get("interval") or 30,
                                   started_by=source_label or "remote command")
        if err:
            return False, err
        return True, "Started range test: %s every %ss." % (
            ", ".join(_target_label(t) for t in result["targets"]), result["interval"])
    if option["action"] == "range_stop":
        _range_stop()
        return True, "Stopped range test."
    return False, "unknown command"


def _process_remote_command(message):
    text = str(message.get("text") or "").strip()
    if not text or str(message.get("direction") or "in") != "in":
        return
    if not _controller_allowed(message):
        return
    source = _command_source(message)
    source_key = _source_key(source)
    lower = text.lower().strip()

    with _cmd_lock:
        pending = _commands.get("pending")
    if pending and time.time() > pending.get("expires_at", 0):
        _clear_pending_command()
        pending = None

    if lower in ("cancel", "never mind", "nevermind"):
        _clear_pending_command()
        _cmd_log("cancel", text, source_key)
        _send_command_reply(message, "Pending command cancelled.")
        return

    if pending and source_key == _source_key(pending.get("source", {})) and lower.isdigit():
        idx = int(lower) - 1
        options = pending.get("options") or []
        if 0 <= idx < len(options):
            ok, reply = _execute_command_option(options[idx], source_key)
            _clear_pending_command()
            _cmd_log("execute" if ok else "execute_failed", text, source_key, reply)
            _send_command_reply(message, reply)
            return
        _send_command_reply(message, "That option is not available. Reply with a listed number, or cancel.")
        return

    if lower in ("status", "range status", "test status"):
        _cmd_log("status", text, source_key)
        _send_command_reply(message, _range_status_text())
        return

    if "stop" in lower and "range" in lower:
        options = [{"action": "range_stop"}]
        _set_pending_command(source, options)
        _cmd_log("pending", text, source_key, "stop range")
        _send_command_reply(message, _format_pending_options(options, "Stop range test?"))
        return

    if "range" in lower or "range test" in lower:
        query, interval = _parse_range_command(text)
        if not query:
            _cmd_log("need_target", text, source_key)
            _send_command_reply(message, "Range test needs a target. Example: range test OptimusPrime every 30s")
            return
        matches = _find_command_targets(query)
        if not matches:
            _cmd_log("no_match", text, source_key, query)
            _send_command_reply(message, "I could not find a target matching '%s'. Send cancel or try a clearer name." % query)
            return
        options = [{"action": "range_start", "targets": [m["id"]],
                    "interval": interval, "prefix": "ping"} for m in matches[:5]]
        _set_pending_command(source, options)
        _cmd_log("pending", text, source_key, "%d option(s)" % len(options))
        _send_command_reply(message, _format_pending_options(options, "Range test request:"))
        return

    ping_query, ping_interval = _parse_ping_range_command(text)
    if ping_query:
        matches = _find_command_targets(ping_query)
        if not matches:
            _cmd_log("ping_no_match", text, source_key, ping_query)
            _send_command_reply(message, "I understood that as a range ping, but could not find '%s'. Try a clearer contact name." % ping_query)
            return
        options = [{"action": "range_start", "targets": [m["id"]],
                    "interval": ping_interval, "prefix": "ping"} for m in matches[:5]]
        _set_pending_command(source, options)
        _cmd_log("ping_pending", text, source_key, "%d option(s)" % len(options))
        _send_command_reply(message, _format_pending_options(options, "Ping/range request:"))
        return

    try:
        intent, skipped = _ai_interpret_command(text)
    except Exception as exc:  # noqa: BLE001 - AI must not break deterministic commands
        _cmd_log("ai_failed", text, source_key, str(exc))
        _send_command_reply(message, "AI parser could not understand that safely. Try: range test OptimusPrime every 30s")
        return
    if not intent:
        if skipped != "disabled":
            _cmd_log("ai_skipped", text, source_key, skipped or "not available")
        return
    kind, options = _options_from_ai_intent(intent)
    if kind == "status":
        _cmd_log("ai_status", text, source_key, intent.get("reason") or "AI parsed status")
        _send_command_reply(message, _range_status_text())
        return
    if kind == "cancel":
        _clear_pending_command()
        _cmd_log("ai_cancel", text, source_key, intent.get("reason") or "AI parsed cancel")
        _send_command_reply(message, "Pending command cancelled.")
        return
    if kind == "pending" and options:
        _set_pending_command(source, options)
        _cmd_log("ai_pending", text, source_key, intent.get("reason") or "%d option(s)" % len(options))
        intro = "AI parsed request:"
        _send_command_reply(message, _format_pending_options(options, intro))
        return
    if kind == "pending" and not options:
        _cmd_log("ai_no_match", text, source_key, ", ".join(intent.get("target_queries") or []))
        _send_command_reply(message, "AI parsed a command, but I could not match the target. Try a clearer contact or channel name.")
        return
    if kind == "unknown":
        _cmd_log("ai_unknown", text, source_key, intent.get("reason") or "unknown")
        _send_command_reply(message, "I could not turn that into a safe command. Try: status, stop range, or range test <contact> every 30s.")


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
    server_version = "meshcore-sender"

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
            _p = _os.path.join(DATA, "inbox.json")
            try:
                _store = _json.load(open(_p))
            except Exception:
                _store = []
            # Merge live in-memory inbox (subscription events not yet persisted)
            try:
                from transport_meshcore import _inbox as _live, _inbox_lock as _ilock
                with _ilock:
                    _live_copy = list(_live)
                _seen = set(_message_key(x) for x in _store)
                _added = [_m for _m in _live_copy
                          if _message_key(_m) not in _seen]
                if _added:
                    for _m in _added:
                        _process_remote_command(_m)
                    _store.extend(_public_message(_m) for _m in _added)
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
            self._json(200, _range_snapshot())
        elif path == "/api/commands":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            self._json(200, _cmd_status())
        elif path == "/api/ai/config":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            self._json(200, _public_ai_config())
        elif path == "/api/nodes":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            info = radio_nodes(force=self._qs_force())
            self._json(200, {"nodes": info["nodes"], "error": info["error"]})
        elif path == "/api/route":
            if not _auth_set():
                self._json(428, {"error": "not_configured", "setup": "/setup"})
                return
            if not self._session():
                self._json(401, {"error": "unauthorized"})
                return
            qs = parse_qs(urlparse(self.path).query or "")
            target = (qs.get("target") or [""])[0]
            import re as _re
            if not (_re.fullmatch(r"chan:\d+", target) or
                    (_re.fullmatch(r"dm:[A-Za-z0-9 _./#@-]{1,60}", target)
                     and not target[3:].startswith("-"))):
                self._json(400, {"ok": False, "error": "bad destination"})
                return
            import transport_meshcore as mc
            self._json(200, mc.route(target))
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
            _p = _os.path.join(DATA, "inbox.json")
            try:
                _store = _json.load(open(_p))
            except Exception:
                _store = []
            from transport_meshcore import messages as _msgs
            _new, _e = _msgs()
            _seen = set(_message_key(_m) for _m in _store)
            for _m in _new:
                if _message_key(_m) not in _seen:
                    _m.setdefault("at", _now())
                    _store.append(_public_message(_m))
                    _process_remote_command(_m)
                    _seen.add(_message_key(_m))
            _store = _store[-300:]
            try:
                _os.makedirs(os.path.dirname(_p), exist_ok=True)
                _json.dump(_store, open(_p, "w"))
            except Exception:
                pass
            self._json(200, {"messages": _store, "fetched": len(_new), "error": _e})
        elif path == "/api/commands/config":
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
            rc = _save_command_config(bool(body.get("enabled")),
                                      body.get("controllers") or [],
                                      body.get("favorites"))
            _cmd_log("config", "remote command settings updated",
                     detail=("enabled" if rc.get("enabled") else "disabled"))
            self._json(200, _cmd_status())
        elif path == "/api/ai/config":
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
            try:
                cfg = _save_ai_config(enabled=body.get("enabled"),
                                      provider=body.get("provider"),
                                      model=body.get("model"),
                                      api_key=body.get("api_key"),
                                      clear_key=bool(body.get("clear_key")))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            _cmd_log("ai_config", "AI interpreter settings updated",
                     detail=("enabled" if cfg.get("enabled") else "disabled"))
            self._json(200, cfg)
        elif path in ("/api/contacts/import", "/api/contacts/add", "/api/contacts/export"):
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
            import re as _re
            import transport_meshcore as mc
            if path == "/api/contacts/import":
                uri = (body.get("uri") or "").strip()
                if not uri.startswith("meshcore://") or not _re.fullmatch(r"meshcore://[0-9a-fA-F]+", uri):
                    self._json(400, {"ok": False, "error": "paste a valid meshcore:// contact URI"})
                    return
                result = mc.import_contact(uri)
            elif path == "/api/contacts/add":
                key = (body.get("public_key") or "").strip()
                name = (body.get("name") or "").strip()
                kind = body.get("kind") or 1
                if not _re.fullmatch(r"[0-9a-fA-F]{64}", key):
                    self._json(400, {"ok": False, "error": "public key must be 64 hex characters"})
                    return
                if not _re.fullmatch(r"[A-Za-z0-9 _./#@-]{1,32}", name) or name.startswith("-"):
                    self._json(400, {"ok": False, "error": "name must be 1-32 safe characters"})
                    return
                result = mc.add_contact(key, name, kind)
            else:
                name = (body.get("name") or "").strip()
                if name and (not _re.fullmatch(r"[A-Za-z0-9 _./#@-]{1,64}", name) or name.startswith("-")):
                    self._json(400, {"ok": False, "error": "bad contact name"})
                    return
                result = mc.export_contact(name or None)
            if result.get("ok"):
                _nodes_cache.update({"nodes": [], "at": 0, "error": None})
            self._json(200 if result.get("ok") else 502, result)
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
            raw_targets = body.get("targets")
            target_inputs = [str(t).strip() for t in raw_targets] if isinstance(raw_targets, list) else [str(body.get("target") or "").strip()]
            prefix = (body.get("prefix") or "ping").strip()
            started_by = (body.get("started_by") or "you").strip()
            if not started_by or len(started_by) > 40:
                started_by = "you"
            try:
                interval = max(5, min(300, int(body.get("interval") or 30)))
            except (ValueError, TypeError):
                interval = 30
            try:
                result, err = _range_start(target_inputs, prefix, interval, started_by=started_by)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            if err:
                self._json(409, {"error": err})
                return
            self._json(200, result)
        elif path == "/api/range/targets":
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
            raw_targets = body.get("targets")
            target_inputs = [str(t).strip() for t in raw_targets] if isinstance(raw_targets, list) else []
            try:
                targets = _validate_range_targets(target_inputs)
            except ValueError:
                self._json(400, {"error": "pick at least one target"})
                return
            with _range_lock:
                if not _range["running"]:
                    self._json(409, {"error": "range test is not running"})
                    return
                _range["target"] = targets[0]
                _range["targets"] = targets
                for target in targets:
                    _range["per_target"].setdefault(target, {"sent": 0, "acked": 0})
                snap = {k: _range[k] for k in
                        ("running", "target", "prefix", "interval", "sent", "acked",
                         "log", "next_due_at", "targets", "per_target", "started_by")}
                snap["server_now"] = time.time()
            self._json(200, snap)
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
            self._json(200, _range_stop())
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
                _p = _os.path.join(DATA, "inbox.json")
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
                    _result = _result_map.get(scope, {})
                    _acked = _result.get("acked", False)
                    if not any(m.get("raw") == raw for m in _store):
                        _msg = {"scope": scope, "sender": None, "text": text,
                                "at": ts, "direction": "out", "raw": raw,
                                "acked": _acked}
                        if "route_hops" in _result:
                            _msg["route_hops"] = _result.get("route_hops")
                        if "route_mode" in _result:
                            _msg["route_mode"] = _result.get("route_mode")
                        if "route_path" in _result:
                            _msg["route_path"] = _result.get("route_path")
                        _store.append(_msg)
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
        elif path == "/api/reconnect":
            rec = self._session()
            if not rec:
                self._json(401, {"error": "unauthorized"})
                return
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token") or "", rec["csrf"]):
                self._json(403, {"error": "bad csrf token"})
                return
            try:
                import transport_meshcore as _t
                ok, detail = _t.reconnect()
            except Exception as e:
                self._json(500, {"ok": False, "detail": str(e)})
                return
            self._json(200, {"ok": ok, "detail": detail})
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
