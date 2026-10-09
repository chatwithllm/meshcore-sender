"""Response-capable HA actions with strict schemas and an administrator boundary."""

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from .const import DOMAIN
from .repeater_admin import RepeaterAdmin, SERVICES


def schemas():
    common = {vol.Required("target"): vol.All(cv.string, vol.Length(min=1, max=128)),
              vol.Optional("entry_id"): cv.string,
              vol.Optional("timeout", default=20): vol.All(vol.Coerce(int), vol.Range(min=5, max=60))}
    password = {vol.Optional("password"): vol.All(cv.string, vol.Length(max=64))}
    fields = {
        "remote_status": password, "remote_telemetry": password,
        "remote_neighbors": {**password,
            vol.Optional("count", default=8): vol.All(vol.Coerce(int), vol.Range(min=1, max=16)),
            vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535))},
        "remote_command": {**password, vol.Required("command"): cv.string,
            vol.Optional("mode", default="read_only"): vol.In(("read_only", "admin")),
            vol.Optional("allow_mutation", default=False): cv.boolean},
        "remote_login": {**password, vol.Optional("save_password", default=False): cv.boolean},
        "remote_logout": {vol.Optional("forget_password", default=False): cv.boolean},
        "trace": {},
    }
    return {name: vol.Schema({**common, **fields[name]}) for name in SERVICES}


async def async_attach_admin(hass, entry, coordinator):
    manager = RepeaterAdmin(coordinator, Store(hass, 1, f"{DOMAIN}.repeaters.{entry.entry_id}"))
    await manager.load()
    coordinator.repeater_admin = manager


async def async_register_admin_services(hass):
    async def handle(call):
        user_id = call.context.user_id if call.context else None
        if user_id:
            user = await hass.auth.async_get_user(user_id)
            if user is None or not user.is_admin:
                return {"request_success": False, "error": "forbidden", "message": "HA administrator access is required"}
        # Context-free HA automations are trusted local configuration, not LoRa controllers or an LLM tool.
        entries = hass.data.get(DOMAIN, {})
        entry_id = call.data.get("entry_id")
        chosen = entries.get(entry_id) if entry_id else (next(iter(entries.values())) if len(entries) == 1 else None)
        if chosen is None:
            return {"request_success": False, "error": "not_connected", "message": "Choose a loaded MeshCore config entry"}
        if getattr(chosen.client, "url", None):
            return {"request_success": False, "error": "unsupported", "message": "Use a native HA BLE or bridge connection for remote administration"}
        return await chosen.repeater_admin.request(call.service, dict(call.data))

    for name, schema in schemas().items():
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handle, schema=schema,
                                         supports_response=SupportsResponse.OPTIONAL)
