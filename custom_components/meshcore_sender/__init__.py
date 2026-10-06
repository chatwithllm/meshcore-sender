"""Home Assistant controls for an independently hosted MeshCore server."""

import voluptuous as vol

from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MeshCoreClient, MeshCoreError
from .const import CONF_ADDRESS, CONF_CONNECTION, CONF_PASSPHRASE, CONF_URL, DOMAIN, PLATFORMS
from .coordinator import MeshCoreCoordinator


async def async_setup_entry(hass, entry):
    if entry.data.get(CONF_CONNECTION) == "bluetooth":
        from .bluetooth_client import NativeMeshCoreClient
        client = NativeMeshCoreClient(hass, entry.data[CONF_ADDRESS])
    else:
        client = MeshCoreClient(async_get_clientsession(hass), entry.data[CONF_URL],
                               entry.data[CONF_PASSPHRASE])
    coordinator = MeshCoreCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        if hasattr(client, "close"):
            await client.close()
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if hasattr(client, "close"):
        async def stop_native(event):
            await client.close()
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_native))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_action(call):
        entries = hass.data[DOMAIN]
        entry_id = call.data.get("entry_id")
        if entry_id:
            chosen = entries.get(entry_id)
        else:
            chosen = next(iter(entries.values())) if len(entries) == 1 else None
        if chosen is None:
            raise HomeAssistantError("Choose a valid MeshCore config entry")
        try:
            if call.service == "start_range_test":
                await chosen.start(call.data["targets"], call.data["interval"],
                                   call.data["prefix"])
            elif call.service == "stop_range_test":
                await chosen.action("/api/range/stop")
            else:
                result = await chosen.action("/api/send", {
                    "targets": call.data["targets"], "text": call.data["message"],
                })
                if any(not item.get("ok") for item in result.get("results", [])):
                    raise MeshCoreError("One or more messages could not be sent")
        except MeshCoreError as error:
            raise HomeAssistantError(str(error)) from error

    common = {vol.Optional("entry_id"): str}
    targets = vol.All(cv.ensure_list, [cv.string], vol.Length(min=1))
    for name, fields in {
        "start_range_test": {
            vol.Required("targets"): targets,
            vol.Optional("interval", default=30): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            vol.Optional("prefix", default="ping"): cv.string,
        },
        "stop_range_test": {},
        "send_message": {vol.Required("targets"): targets, vol.Required("message"): cv.string},
    }.items():
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handle_action,
                                         schema=vol.Schema({**common, **fields}))
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    if hasattr(coordinator.client, "close"):
        await coordinator.client.close()
    if not hass.data[DOMAIN]:
        for service in ("start_range_test", "stop_range_test", "send_message"):
            hass.services.async_remove(DOMAIN, service)
    return True
