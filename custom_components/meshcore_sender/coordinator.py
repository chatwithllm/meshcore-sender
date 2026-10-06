"""Poll the running server; scheduling stays on the server, not the dashboard."""

from datetime import timedelta
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeshCoreAuthError, MeshCoreError
from .const import DOMAIN


class MeshCoreCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, logging.getLogger(__name__),
                         name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=10))
        self.entry = entry
        self.client = client

    async def _async_update_data(self):
        try:
            nodes = await self.client.request("GET", "/api/nodes")
            range_test = await self.client.request("GET", "/api/range/status")
            health = await self.client.request("GET", "/api/health")
            return {"nodes": nodes.get("nodes", []), "range": range_test, "health": health}
        except MeshCoreAuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from error
        except MeshCoreError as error:
            raise UpdateFailed(str(error)) from error

    def setting(self, key, default=None):
        return self.entry.options.get(key, default)

    def save_setting(self, key, value):
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, key: value}
        )
        self.async_update_listeners()

    async def action(self, path, payload=None):
        result = await self.client.request("POST", path, payload or {})
        await self.async_request_refresh()
        return result

    async def start(self, targets=None, interval=None, prefix="ping", started_by="Home Assistant"):
        targets = targets or [self.setting("target")]
        if not targets or not all(targets):
            raise MeshCoreError("Choose a range test target first")
        return await self.action("/api/range/start", {
            "targets": targets, "interval": interval or self.setting("interval", 30),
            "prefix": prefix, "started_by": started_by, "started_via": "HA",
        })
