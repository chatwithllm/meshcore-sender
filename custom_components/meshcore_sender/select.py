"""Contact/channel picker using actual names and stable destination IDs."""

from collections import Counter

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import MeshCoreEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([MeshCoreTarget(hass.data[DOMAIN][entry.entry_id])])


class MeshCoreTarget(MeshCoreEntity, SelectEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator, "target", "Range test target")

    def _choices(self):
        nodes = self.coordinator.data["nodes"]
        counts = Counter(node.get("name") or node["id"] for node in nodes)
        return {
            ((node.get("name") or node["id"]) +
             (f" ({node['id']})" if counts[node.get("name") or node["id"]] > 1 else "")): node["id"]
            for node in nodes
        }

    @property
    def options(self):
        return sorted(self._choices(), key=str.casefold)

    @property
    def current_option(self):
        selected = self.coordinator.setting("target")
        return next((label for label, target in self._choices().items() if target == selected), None)

    async def async_select_option(self, option):
        if option not in self._choices():
            raise HomeAssistantError("Target is no longer available")
        self.coordinator.save_setting("target", self._choices()[option])
