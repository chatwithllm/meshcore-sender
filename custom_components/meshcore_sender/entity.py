"""Shared device identity for dashboard entities."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class MeshCoreEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = name
        info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="MeshCore Sender", manufacturer="MeshCore",
        )
        if coordinator.client.url:
            info["configuration_url"] = coordinator.client.url
        self._attr_device_info = info
