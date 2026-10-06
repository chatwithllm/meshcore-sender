"""Range statistics; broadcasts are not delivery acknowledgements."""

from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import MeshCoreEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MeshCoreSensor(coordinator, key, name) for key, name in (
        ("sent", "Messages sent"), ("acked", "Messages acknowledged"),
        ("broadcasts", "Channel broadcasts"), ("interval", "Active test interval"),
        ("started_by", "Test started by"),
    )])


class MeshCoreSensor(MeshCoreEntity, SensorEntity):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        if key == "interval":
            self._attr_native_unit_of_measurement = "s"

    @property
    def native_value(self):
        test = self.coordinator.data["range"]
        stats = test.get("per_target", {})
        if self.key == "acked":
            return sum(item.get("acked", 0) for target, item in stats.items()
                       if not target.startswith("chan:"))
        if self.key == "broadcasts":
            return sum(item.get("broadcasts_sent", item.get("acked", 0)) for target, item in stats.items()
                       if target.startswith("chan:"))
        return test.get(self.key)

    @property
    def extra_state_attributes(self):
        if self.key != "sent":
            return None
        test = self.coordinator.data["range"]
        stats = {}
        for target, item in test.get("per_target", {}).items():
            stats[target] = {"sent": item.get("sent", 0),
                             "acknowledged": None if target.startswith("chan:")
                             else item.get("acked", 0)}
            if target.startswith("chan:"):
                stats[target]["broadcasts_sent"] = item.get("broadcasts_sent", item.get("acked", 0))
        return {"targets": test.get("targets", []), "per_target": stats,
                "next_due_at": test.get("next_due_at"), "started_by": test.get("started_by"),
                "started_via": test.get("started_via"), "stopped_by": test.get("stopped_by"),
                "stopped_via": test.get("stopped_via"), "summary_messages": test.get("summary_messages", [])}
