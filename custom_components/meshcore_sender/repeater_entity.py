"""Dynamically tracked repeater devices; observations expire without polling LoRa."""

import time
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from .const import DOMAIN
from .repeater_admin import MAX_AGE

SENSORS = (
    ("battery_voltage", "Battery voltage", "V", SensorDeviceClass.VOLTAGE),
    ("battery_percent", "Battery percent", "%", SensorDeviceClass.BATTERY),
    ("uptime", "Uptime", "s", SensorDeviceClass.DURATION),
    ("firmware", "Firmware", None, None), ("board", "Board", None, None),
    ("role", "Role", None, None), ("tx_power", "TX power", "dBm", None),
    ("radio", "Radio", None, None), ("out_path_len", "Out path len", None, None),
    ("last_rssi", "Last RSSI", "dBm", SensorDeviceClass.SIGNAL_STRENGTH),
    ("last_snr", "Last SNR", "dB", None), ("neighbor_count", "Neighbor count", None, None),
    ("request_successes", "Request successes", None, None),
    ("request_failures", "Request failures", None, None),
    ("queue_length", "Queue length", None, None),
)


def async_add_repeater_entities(coordinator, entry, add, platform):
    manager = coordinator.repeater_admin
    def discovered(key):
        if platform == "sensor":
            entities = [RepeaterSensor(coordinator, key, *description) for description in SENSORS]
        elif platform == "binary_sensor":
            entities = [RepeaterOnline(coordinator, key, "online", "Online")]
        else:
            entities = [RepeaterButton(coordinator, key, "refresh_status", "Refresh status"),
                        RepeaterButton(coordinator, key, "refresh_neighbors", "Refresh neighbors")]
        add(entities)
    for key in manager.records:
        discovered(key)
    entry.async_on_unload(manager.listen(discovered))


class RepeaterEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, public_key, key, name):
        super().__init__(coordinator)
        self.public_key, self.key = public_key, key
        target_name = self.record["target_name"]
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{public_key}_{key}"
        self._attr_suggested_object_id = f"meshcore_{slugify(target_name)}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{public_key}")},
            name=f"MeshCore {target_name}", manufacturer="MeshCore",
            via_device=(DOMAIN, coordinator.entry.entry_id))

    @property
    def record(self):
        return self.coordinator.repeater_admin.records[self.public_key]

    @property
    def available(self):
        return True

    @property
    def extra_state_attributes(self):
        return {"public_key_prefix": self.public_key[:12], "target_name": self.record["target_name"],
                "last_seen_at": self.record["last_seen_at"], "last_error": self.record["error"],
                "round_trip_ms": self.record.get("round_trip_ms"),
                "sampled_at": self.record["field_updated_at"].get(self.key)}


class RepeaterSensor(RepeaterEntity, SensorEntity):
    def __init__(self, coordinator, public_key, key, name, unit, device_class):
        super().__init__(coordinator, public_key, key, name)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if key in ("battery_voltage", "battery_percent", "tx_power", "last_rssi", "last_snr", "neighbor_count", "queue_length"):
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        timestamp = self.record["field_updated_at"].get(self.key)
        if self.key not in ("request_successes", "request_failures") and (not timestamp or time.time() - timestamp > MAX_AGE):
            return None
        return self.record.get(self.key)

    @property
    def extra_state_attributes(self):
        fields = super().extra_state_attributes
        if self.key == "neighbor_count":
            fields["neighbors"] = self.record.get("neighbors") or []
        if self.key == "out_path_len":
            fields["path_bytes"] = self.record.get("out_path")
            fields["source"] = "Companion contact cache, not a live trace"
        return fields


class RepeaterOnline(RepeaterEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self):
        timestamp = self.record["last_attempt_at"]
        if not timestamp or time.time() - timestamp > MAX_AGE:
            return None
        return self.record["online"]


class RepeaterButton(RepeaterEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    async def async_press(self):
        service = "remote_status" if self.key == "refresh_status" else "remote_neighbors"
        result = await self.hass.services.async_call(DOMAIN, service,
            {"entry_id": self.coordinator.entry.entry_id, "target": self.public_key},
            blocking=True, return_response=True, context=self._context)
        if not result.get("request_success"):
            raise HomeAssistantError(result.get("message") or result.get("error") or "No response")
