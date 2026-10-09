"""Connection and live range test indicators."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .const import DOMAIN
from .entity import MeshCoreEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MeshCoreBinarySensor(coordinator, "radio", "Radio connected"),
        MeshCoreBinarySensor(coordinator, "range", "Range test running"),
    ])
    from .repeater_entity import async_add_repeater_entities
    async_add_repeater_entities(coordinator, entry, async_add_entities, "binary_sensor")


class MeshCoreBinarySensor(MeshCoreEntity, BinarySensorEntity):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        if key == "radio":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self):
        data = self.coordinator.data
        return bool(data["health"].get("radio_ok") if self.key == "radio"
                    else data["range"].get("running"))
