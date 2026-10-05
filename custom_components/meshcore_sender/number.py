"""Persistent interval setting for the next range test."""

from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN
from .entity import MeshCoreEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([MeshCoreInterval(hass.data[DOMAIN][entry.entry_id])])


class MeshCoreInterval(MeshCoreEntity, NumberEntity):
    _attr_native_min_value = 5
    _attr_native_max_value = 300
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator):
        super().__init__(coordinator, "interval_setting", "Range test interval")

    @property
    def native_value(self):
        return self.coordinator.setting("interval", 30)

    async def async_set_native_value(self, value):
        self.coordinator.save_setting("interval", int(value))
