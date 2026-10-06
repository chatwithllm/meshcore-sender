"""Authenticated HA sidebar and persistent native-radio inbox."""

from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .history import MessageHistory
from .bridge import find_pin_bridge, update_radio_pin

STATE_KEY = DOMAIN + "_workspace"


async def async_attach_history(hass, entry, client):
    if not hasattr(client, "_receive"):
        return
    store = Store(hass, 1, f"{DOMAIN}.inbox.{entry.entry_id}")
    data = await store.async_load()
    history = MessageHistory(data)
    history.changed = lambda: store.async_delay_save(history.snapshot, 2)
    client.history = history
    client.history_store = store


@websocket_api.websocket_command({
    vol.Required("type"): "meshcore_sender/workspace",
    vol.Optional("entry_id"): str,
    vol.Optional("action", default="snapshot"): vol.In(
        ["snapshot", "send", "start", "stop", "favorite"]),
    vol.Optional("targets"): [str],
    vol.Optional("text"): str,
    vol.Optional("prefix", default="ping"): str,
    vol.Optional("interval", default=30): vol.All(int, vol.Range(min=5, max=300)),
    vol.Optional("enabled", default=True): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_workspace(hass, connection, msg):
    entries = hass.data.get(DOMAIN, {})
    chosen = entries.get(msg.get("entry_id")) if msg.get("entry_id") else (
        next(iter(entries.values())) if entries and (len(entries) == 1 or msg["action"] == "snapshot") else None)
    if chosen is None:
        connection.send_error(msg["id"], "invalid_entry", "Choose a MeshCore radio")
        return
    try:
        client = chosen.client
        action = msg["action"]
        if action == "send":
            await chosen.action("/api/send", {"targets": msg.get("targets", []),
                                              "text": msg.get("text", "")})
        elif action == "start":
            await chosen.action("/api/range/start", {
                "targets": msg.get("targets", []), "interval": msg["interval"],
                "prefix": msg["prefix"], "started_by": connection.user.name or "Home Assistant",
            })
            chosen.save_setting("interval", msg["interval"])
            chosen.save_setting("target", msg["targets"][0])
            chosen.save_setting("workspace_targets", msg["targets"])
            chosen.save_setting("workspace_prefix", msg["prefix"])
        elif action == "stop":
            await chosen.action("/api/range/stop")
        elif action == "favorite":
            targets = msg.get("targets", [])
            valid = {n["id"] for n in (chosen.data or {}).get("nodes", [])}
            if not hasattr(client, "history") or not targets or any(t not in valid for t in targets):
                raise ValueError("Choose an available native-radio contact")
            for target in targets:
                client.history.favorite(target, msg["enabled"])
        data = chosen.data or {}
        history = client.history.snapshot() if hasattr(client, "history") else {"messages": [], "favorites": []}
        if hasattr(client, "mc") and client.mc:
            for message in history["messages"]:
                prefix = message.get("pubkey_prefix")
                contact = client.mc.get_contact_by_key_prefix(prefix) if prefix else None
                if contact and contact.get("adv_name"):
                    message["target"] = "dm:" + contact["adv_name"]
                    message["name"] = contact["adv_name"]
                    if message["direction"] == "in":
                        message["sender"] = contact["adv_name"]
        connection.send_result(msg["id"], {
            "entry_id": chosen.entry.entry_id,
            "entries": [{"id": k, "name": v.entry.title} for k, v in entries.items()],
            "nodes": data.get("nodes", []), "health": data.get("health", {}),
            "available": chosen.last_update_success,
            "pin_update_supported": bool(find_pin_bridge(hass, chosen)),
            "settings": {"target": chosen.setting("target"), "interval": chosen.setting("interval", 30),
                         "targets": chosen.setting("workspace_targets"),
                         "prefix": chosen.setting("workspace_prefix", "ping")},
            "range": await client.request("GET", "/api/range/status"),
            "history_supported": hasattr(client, "history"), **history,
        })
    except Exception as error:
        connection.send_error(msg["id"], "meshcore_error", str(error) or "Radio action failed")


@websocket_api.websocket_command({
    vol.Required("type"): "meshcore_sender/update_radio_pin",
    vol.Required("entry_id"): str,
    # HA's websocket exception logger redacts the standard password field.
    vol.Required("password"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_update_radio_pin(hass, connection, msg):
    chosen = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if chosen is None:
        connection.send_error(msg["id"], "invalid_entry", "Choose a valid MeshCore radio")
        return
    try:
        result = await update_radio_pin(hass, chosen, msg["password"])
        connection.send_result(msg["id"], result)
    except ValueError as error:
        connection.send_error(msg["id"], "invalid_pin_update", str(error))
    except Exception:
        # Transport exceptions can contain serialized arguments; never echo them.
        connection.send_error(msg["id"], "pin_update_failed", "Could not update the bridge PIN. Check its connection.")


async def async_setup_workspace(hass):
    state = hass.data.setdefault(STATE_KEY, {})
    if not state.get("registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig("/meshcore_sender_static", str(Path(__file__).parent / "www"), False)
        ])
        websocket_api.async_register_command(hass, websocket_workspace)
        websocket_api.async_register_command(hass, websocket_update_radio_pin)
        state["registered"] = True
    if not state.get("panel"):
        await panel_custom.async_register_panel(
            hass, frontend_url_path="meshcore", webcomponent_name="meshcore-workspace",
            sidebar_title="MeshCore", sidebar_icon="mdi:radio-handheld",
            module_url="/meshcore_sender_static/workspace.js?v=0.5.0",
            require_admin=True,
        )
        state["panel"] = True


def async_remove_workspace(hass):
    frontend.async_remove_panel(hass, "meshcore")
    hass.data[STATE_KEY]["panel"] = False
