"""Runtime PIN updates using the bridge's existing encrypted ESPHome connection."""

import re


def find_pin_bridge(hass, coordinator):
    host = getattr(coordinator.client, "host", None)
    if not host:
        return None
    for entry in hass.config_entries.async_entries("esphome"):
        runtime = getattr(entry, "runtime_data", None)
        if not runtime or not entry.data.get("noise_psk"):
            continue
        addresses = {entry.data.get("host"), getattr(runtime.client, "connected_address", None)}
        if host not in addresses:
            continue
        service = next((s for s in runtime.services.values() if s.name == "update_meshcore_pin"), None)
        if service and runtime.available:
            return runtime, service
    return None


async def update_radio_pin(hass, coordinator, password):
    if not isinstance(password, str) or not re.fullmatch(r"[0-9]{6}", password):
        raise ValueError("Enter exactly six digits")
    if coordinator.client.range.snapshot()["running"]:
        raise ValueError("Stop the range test before updating the PIN")
    bridge = find_pin_bridge(hass, coordinator)
    if not bridge:
        raise ValueError("The matching encrypted ESPHome bridge is unavailable or needs the runtime PIN firmware")
    runtime, service = bridge
    # Bypass HA's service bus: no PIN entity, recorder state or automation trace.
    response = await runtime.client.execute_service(service, {"password": password}, return_response=False)
    if response is None or not response.success:
        raise ValueError("The bridge could not confirm saving the PIN")
    return {"ok": True, "message": "PIN saved on the bridge. Reconnecting to the radio."}
