"""Authenticated HA sidebar and persistent native-radio inbox."""

import asyncio
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .history import MessageHistory
from .bridge import find_pin_bridge, update_radio_pin
from .remote_commands import RemoteCommands
from .ai_agent import interpret, list_agents, agent_safe

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


async def async_attach_remote(hass, entry, coordinator):
    client = coordinator.client
    if not hasattr(client, "history"):
        return
    store = Store(hass, 1, f"{DOMAIN}.remote.{entry.entry_id}")

    async def send(key, text):
        matches = [c for c in client.mc.contacts.values() if c.get("public_key") == key] if client.mc else []
        if len(matches) != 1:
            raise ValueError("Controller is no longer available")
        name = matches[0].get("adv_name")
        if not name or sum(c.get("adv_name") == name for c in client.mc.contacts.values()) != 1:
            raise ValueError("Controller name is ambiguous")
        return await client.send_one("dm:" + name, text)

    async def execute(proposal, name):
        if proposal["action"] == "status":
            status = client.range.snapshot()
            if not status["running"]:
                return "Range test idle."
            return (f"Range test running: {len(status['targets'])} targets, every {status['interval']}s. "
                    f"{status['sent']} sent, {status['acked']} ACKs.")
        if proposal["action"] == "start" and client.range.snapshot()["running"]:
            return "A test is already running. Stop it before starting another."
        path = "/api/range/start" if proposal["action"] == "start" else "/api/range/stop"
        result = await coordinator.action(path, {**proposal, "started_by": "Remote: " + name,
            "started_via": "LoRa", "stopped_by": name, "stopped_via": "LoRa",
            "summary_exclude": "dm:" + name})
        return ("Range test started." if proposal["action"] == "start" else
                result.get("summary_messages") or "Range test already stopped.")

    client.remote = RemoteCommands(client._nodes, send, execute,
        lambda agent, text, nodes: interpret(hass, agent, text, nodes), await store.async_load(),
        menu_nodes=lambda: [n for n in client._nodes() if n["id"] in client.history.data["favorites"]])
    client.remote.changed = lambda: store.async_delay_save(client.remote.snapshot, 2)
    client.remote_store = store


@websocket_api.websocket_command({
    vol.Required("type"): "meshcore_sender/workspace",
    vol.Optional("entry_id"): str,
    vol.Optional("action", default="snapshot"): vol.In(
        ["snapshot", "send", "start", "stop", "favorite", "remote_settings", "preview_command"]),
    vol.Optional("targets"): [str],
    vol.Optional("text"): str,
    vol.Optional("prefix", default="ping"): str,
    vol.Optional("interval", default=30): vol.All(int, vol.Range(min=5, max=300)),
    vol.Optional("enabled", default=True): bool,
    vol.Optional("controllers"): [str],
    vol.Optional("agent_id", default=""): str,
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
        preview = None
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
            await chosen.action("/api/range/stop", {"stopped_by": connection.user.name or "Home Assistant",
                                                    "stopped_via": "HA"})
        elif action == "favorite":
            targets = msg.get("targets", [])
            valid = {n["id"] for n in (chosen.data or {}).get("nodes", [])}
            if not hasattr(client, "history") or not targets or any(t not in valid for t in targets):
                raise ValueError("Choose an available native-radio contact")
            for target in targets:
                client.history.favorite(target, msg["enabled"])
        elif action == "remote_settings":
            if not hasattr(client, "remote"):
                raise ValueError("Remote commands require a native radio")
            selected = msg.get("controllers", [])
            if len(selected) != len(set(selected)) or len(selected) > 32:
                raise ValueError("Choose up to 32 distinct controllers")
            nodes = client._nodes() if client.mc else []
            controllers = []
            for key in selected:
                matches = [n for n in nodes if n.get("public_key") == key and n["id"] in client.history.data["favorites"]]
                saved = [c for c in client.remote.data["controllers"] if c["key"] == key]
                if len(matches) == 1:
                    controllers.append({"key": key, "name": matches[0]["name"]})
                elif len(saved) == 1:
                    controllers.extend(saved)
                else:
                    raise ValueError("Choose a favorited direct contact")
            agent_id = msg["agent_id"]
            if agent_id and not agent_safe(hass, agent_id):
                raise ValueError("Choose a supported AI agent with Home Assistant control disabled")
            if msg["enabled"] and not controllers:
                raise ValueError("Select at least one controller")
            client.remote.configure(msg["enabled"], controllers, agent_id)
            await client.remote_store.async_save(client.remote.snapshot())
        elif action == "preview_command":
            if not hasattr(client, "remote"):
                raise ValueError("Native radio required")
            text = msg.get("text", "").strip()
            if not text or len(text.encode()) > 150:
                raise ValueError("Enter a command of 1 to 150 bytes")
            try:
                proposal = await asyncio.wait_for(interpret(hass, msg["agent_id"], text, client._nodes()), 25)
                preview = client.remote.validate(proposal)
            except Exception:
                raise ValueError("AI preview failed. No radio action was taken. Check agent availability and sign-in.") from None
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
            "battery_entity_id": er.async_get(hass).async_get_entity_id(
                "sensor", DOMAIN, f"{chosen.entry.entry_id}_battery_voltage"),
            "pin_update_supported": bool(find_pin_bridge(hass, chosen)),
            "settings": {"target": chosen.setting("target"), "interval": chosen.setting("interval", 30),
                         "targets": chosen.setting("workspace_targets"),
                         "prefix": chosen.setting("workspace_prefix", "ping")},
            "range": await client.request("GET", "/api/range/status"),
            "history_supported": hasattr(client, "history"), **history,
            "remote": client.remote.snapshot() if hasattr(client, "remote") else None,
            "agents": list_agents(hass),
            "preview": preview,
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
            module_url="/meshcore_sender_static/workspace.js?v=0.6.3",
            require_admin=True,
        )
        state["panel"] = True


def async_remove_workspace(hass):
    frontend.async_remove_panel(hass, "meshcore")
    hass.data[STATE_KEY]["panel"] = False
