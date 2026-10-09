"""Start and stop range tests from dashboards."""

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .api import MeshCoreError
from .const import DOMAIN
from .entity import MeshCoreEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MeshCoreButton(coordinator, "start", "Start range test"),
        MeshCoreButton(coordinator, "stop", "Stop range test"),
    ])
    from .repeater_entity import async_add_repeater_entities
    async_add_repeater_entities(coordinator, entry, async_add_entities, "button")


class MeshCoreButton(MeshCoreEntity, ButtonEntity):
    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, key, name)
        self.key = key
        self._attr_icon = "mdi:play" if key == "start" else "mdi:stop"

    async def async_press(self):
        try:
            user_id = self._context.user_id if self._context else None
            user = await self.hass.auth.async_get_user(user_id) if user_id else None
            actor = user.name if user and user.name else "Home Assistant"
            if self.key == "start":
                await self.coordinator.start(started_by=actor)
            else:
                await self.coordinator.action("/api/range/stop", {"stopped_by": actor, "stopped_via": "HA"})
        except MeshCoreError as error:
            raise HomeAssistantError(str(error)) from error
